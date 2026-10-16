import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from refpipe import audio, usdx
from refpipe.compile import mark_check_stale
from refpipe.errors import CutError
from refpipe.limits import FRAGMENT_S, LEAD_S, NOTE_COUNT, TAIL_S
from refpipe.meta import load_meta, set_t0_ms
from refpipe.usdx import Line, Note, UsdxSong

EPS = 1e-6
KEEP_HEADERS = ("VERSION", "LANGUAGE", "GENRE", "YEAR", "CREATOR", "COMMENT")


@dataclass(frozen=True)
class Cut:
    t0: float
    t1: float
    song: UsdxSong
    warnings: tuple[str, ...]


def line_span(song: UsdxSong, line: Line) -> tuple[float, float]:
    return song.note_t(line.notes[0]), song.note_end_t(line.notes[-1])


def fragment_warnings(duration: float, notes: int) -> tuple[str, ...]:
    out = []
    lo_s, hi_s = FRAGMENT_S
    lo_n, hi_n = NOTE_COUNT
    if not lo_s <= duration <= hi_s:
        out.append(f"fragment is {duration:.1f} s, expected {lo_s}-{hi_s} s")
    if not lo_n <= notes <= hi_n:
        out.append(f"fragment has {notes} notes, expected {lo_n}-{hi_n}")
    return tuple(out)


def cut_song(song: UsdxSong, t0: float, t1: float, lead_s: float = LEAD_S, tail_s: float = TAIL_S) -> Cut:
    if t0 < 0:
        raise CutError(
            f"t0 must be >= 0; to keep a phrase that starts in the first {lead_s:g} s, add an intro "
            "(e.g. 2 empty bars) in MuseScore and re-export melody.mid and minus.wav"
        )
    if t1 <= t0:
        raise CutError("t1 must be greater than t0")
    lo, hi = t0 + lead_s, t1 - tail_s
    keep = []
    dropped = []
    for number, line in enumerate(song.lines, 1):
        a, b = line_span(song, line)
        if a >= lo - EPS and b <= hi + EPS:
            keep.append(line)
        elif a < t1 and b > t0:
            dropped.append(
                f"phrase {number} ({a:.1f}–{b:.1f} s) dropped: needs {lead_s:g} s lead-in "
                f"and {tail_s:g} s tail inside [{t0:g}, {t1:g}]"
            )
    if not keep:
        raise CutError(f"no whole phrase fits into [{lo:.3f}, {hi:.3f}] s")
    b0 = keep[0].notes[0].beat
    lines = []
    for index, line in enumerate(keep):
        notes = tuple(Note(n.kind, n.beat - b0, n.length, n.pitch, n.syl) for n in line.notes)
        last = index == len(keep) - 1
        lines.append(Line(notes, None if last or line.break_beat is None else line.break_beat - b0))
    extra = {key: value for key, value in song.extra.items() if key in KEEP_HEADERS}
    extra["VOCALS"] = "guide.mp3"
    cut = UsdxSong(
        title=song.title,
        artist=song.artist,
        bpm=song.bpm,
        gap_ms=round(song.gap_ms + b0 * song.beat_s * 1000 - t0 * 1000, 3),
        audio="minus.mp3",
        lines=lines,
        extra=extra,
    )
    return Cut(t0, t1, cut, (*dropped, *fragment_warnings(t1 - t0, len(cut.notes))))


def cmd(args: argparse.Namespace) -> int:
    result = cut_song(usdx.read(args.txt), args.t0, args.t1)
    off = args.guide_offset_ms / 1000
    if result.t0 + off < 0:
        raise CutError(
            f"guide cut would start at {result.t0 + off:g} s: t0 + guide offset must be >= 0, "
            "trim the guide head or lower --guide-offset-ms"
        )
    jobs = [
        (src, name, shift)
        for src, name, shift in ((args.minus, "minus.mp3", 0.0), (args.guide, "guide.mp3", off))
        if src is not None
    ]
    for src, _, _ in jobs:
        if not src.is_file():
            raise CutError(f"source not found: {src}")
    meta = args.out / "meta.yaml"
    if meta.exists():
        load_meta(meta)
    args.out.mkdir(parents=True, exist_ok=True)
    for src, name, shift in jobs:
        audio.run_tool(audio.ffmpeg_cut_argv(src, args.out / name, result.t0 + shift, result.t1 + shift))
    usdx.write(result.song, args.out / "song.txt")
    if meta.exists():
        set_t0_ms(meta, round(result.t0 * 1000))
    mark_check_stale(args.out)
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(
        f"{args.out / 'song.txt'}: {len(result.song.notes)} notes, {len(result.song.lines)} lines, "
        f"GAP {usdx.fmt_num(result.song.gap_ms)}"
    )
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("cut", help="keep whole phrases between t0 and t1, recalc GAP, cut minus and guide")
    p.add_argument("txt", type=Path)
    p.add_argument("--t0", type=float, required=True)
    p.add_argument("--t1", type=float, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--minus", type=Path, default=None)
    p.add_argument("--guide", type=Path, default=None)
    p.add_argument("--guide-offset-ms", type=float, default=0.0)
    p.set_defaults(func=cmd)
