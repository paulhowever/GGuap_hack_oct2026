import argparse
import json
import statistics
import sys
from pathlib import Path

from app.songs import SONG_ID

from refpipe import audio, usdx
from refpipe.errors import RefpipeError
from refpipe.limits import TAIL_S
from refpipe.meta import VOICE_RANGES, Meta, load_meta
from refpipe.usdx import Line, UsdxSong

PITCHED = {"normal", "golden"}
GOLDEN = {"golden", "rap_golden"}


def all_notes(ref: dict) -> list[dict]:
    return [note for line in ref["lines"] for note in line["notes"]]


def octave_shift(midis: list[int], voice: str) -> int:
    lo, hi = VOICE_RANGES[voice]
    center = (lo + hi) / 2
    median = statistics.median(midis)
    best = max(
        range(-3, 4),
        key=lambda k: (sum(lo <= m + 12 * k <= hi for m in midis), -abs(median + 12 * k - center)),
    )
    return 12 * best


def difficulty(span: int, notes: int, sung_s: float) -> int:
    nps = notes / sung_s if sung_s > 0 else 0.0
    return 1 + int(span >= 12) + int(nps >= 2.5)


def line_text(line: Line) -> str:
    return " ".join("".join(n.syl for n in line.notes).replace("~", "").split())


def compile_reference(song: UsdxSong, meta: Meta, song_id: str, duration: float) -> dict:
    gap_ms = round(song.gap_ms)
    beat_s = song.beat_s

    def sec(beat: int) -> float:
        return round(gap_ms / 1000 + beat * beat_s, 3)

    raw = [n.pitch + 60 for n in song.notes if n.type in PITCHED] or [n.pitch + 60 for n in song.notes]
    shift = octave_shift(raw, meta.voice)
    lines = []
    index = 0
    for line_index, line in enumerate(song.lines):
        notes = []
        for n in line.notes:
            midi = n.pitch + 60 + shift
            notes.append(
                {
                    "i": index,
                    "t": sec(n.beat),
                    "d": round(n.length * beat_s, 3),
                    "beat": n.beat,
                    "len": n.length,
                    "midi": midi,
                    "pc": midi % 12,
                    "type": n.type,
                    "syl": n.syl,
                }
            )
            index += 1
        lines.append(
            {
                "i": line_index,
                "t0": notes[0]["t"],
                "t1": sec(line.notes[-1].end),
                "text": line_text(line),
                "notes": notes,
            }
        )
    flat = all_notes({"lines": lines})
    midis = [n["midi"] for n in flat if n["type"] in PITCHED] or [n["midi"] for n in flat]
    first = flat[0]["t"]
    last = max(line["t1"] for line in lines)
    duration = round(duration, 3)
    if duration <= 0:
        raise RefpipeError(f"audio duration must be positive, got {duration} s")
    if duration < last:
        raise RefpipeError(f"audio duration {duration} s is shorter than the last note end {last} s")
    golden = sum(n["type"] in GOLDEN for n in flat)
    recording = meta.license.recording
    return {
        "schema": 1,
        "id": song_id,
        "title": meta.title,
        "artist": meta.artist,
        "language": meta.language,
        "audio": {
            "minus": f"/media/{song_id}/minus.mp3",
            "guide": f"/media/{song_id}/guide.mp3",
            "duration": duration,
            "offset_ms": 0,
        },
        "timing": {"bpm_txt": float(song.bpm), "gap_ms": gap_ms, "beat_s": round(beat_s, 6)},
        "stats": {
            "notes": len(flat),
            "lines": len(lines),
            "range_midi": [min(midis), max(midis)],
            "difficulty": difficulty(max(midis) - min(midis), len(flat), last - first),
            "first_note": first,
            "last_end": last,
            "golden_share": round(golden / len(flat), 2),
        },
        "lines": lines,
        "source": {
            "origin": meta.source.origin,
            "generator": meta.source.generator,
            "t0_ms": meta.source.t0_ms,
        },
        "license": {
            "music": meta.license.music.license,
            "recording": recording.license,
            "attribution": meta.license.attribution,
            "url": recording.source or recording.license_url,
        },
    }


def compile_dir(song_dir: Path, duration: float | None = None) -> dict:
    song_dir = Path(song_dir).resolve()
    if not SONG_ID.fullmatch(song_dir.name):
        raise RefpipeError(
            f"song id {song_dir.name!r} must match {SONG_ID.pattern}: lowercase latin, digits, _ and -"
        )
    song = usdx.read(song_dir / "song.txt")
    meta = load_meta(song_dir / "meta.yaml")
    if duration is None:
        minus = song_dir / "minus.mp3"
        if minus.exists():
            duration = audio.probe_duration(minus)
        else:
            duration = max(song.note_end_t(n) for n in song.notes) + TAIL_S
    return compile_reference(song, meta, song_dir.name, duration)


def write_json(obj: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def mark_check_stale(song_dir: Path) -> None:
    song_dir = Path(song_dir)
    if (song_dir / "reference.json").exists():
        write_json(
            {
                "schema": 1,
                "song_id": song_dir.resolve().name,
                "pass": False,
                "stale": "rerun refpipe compile and check",
            },
            song_dir / "check.json",
        )


def read_reference(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise RefpipeError(f"{path} not found, run refpipe compile first")
    try:
        ref = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RefpipeError(f"{path}: {exc}") from exc
    try:
        notes = all_notes(ref)
    except (KeyError, TypeError) as exc:
        raise RefpipeError(f"{path}: malformed reference, bad {exc}") from exc
    if not notes:
        raise RefpipeError(f"{path}: reference has no notes")
    return ref


def cmd(args: argparse.Namespace) -> int:
    guessed = args.duration is None and not (Path(args.song_dir) / "minus.mp3").exists()
    ref = compile_dir(args.song_dir, args.duration)
    if guessed:
        print("warning: minus.mp3 not found, duration guessed from the last note", file=sys.stderr)
    write_json(ref, args.song_dir / "reference.json")
    stats = ref["stats"]
    lo, hi = stats["range_midi"]
    print(
        f"{ref['id']}: {stats['notes']} notes, {stats['lines']} lines, range {lo}-{hi}, "
        f"duration {ref['audio']['duration']} s"
    )
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("compile", help="song.txt + meta.yaml -> reference.json")
    p.add_argument("song_dir", type=Path)
    p.add_argument("--duration", type=float, default=None)
    p.set_defaults(func=cmd)
