import argparse
import dataclasses
import statistics
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import numpy as np

from refpipe import audio, paths, usdx
from refpipe.compile import GOLDEN, PITCHED, all_notes, compile_dir, read_reference, write_json
from refpipe.errors import RefpipeError
from refpipe.limits import FRAGMENT_S, GOLDEN_SHARE, LEAD_S, MAX_SPAN, MIN_NOTE_S, NOTE_COUNT, TAIL_S

SR = 16000
MAX_MEDIA_KB = 1024
DIFFICULTY = "normal"
ScoreFn = Callable[..., dict]


@dataclass(frozen=True)
class Check:
    code: str
    ok: bool
    value: float | int | None
    limit: str
    level: str = "error"


def structural_checks(ref: dict) -> list[Check]:
    notes = all_notes(ref)
    overlaps = sum(1 for a, b in pairwise(notes) if a["beat"] + a["len"] > b["beat"])
    short = sum(1 for n in notes if n["d"] < MIN_NOTE_S - 1e-9)
    pitched = [n["midi"] for n in notes if n["type"] in PITCHED]
    span = max(pitched) - min(pitched) if pitched else 0
    golden = sum(n["type"] in GOLDEN for n in notes) / len(notes)
    duration = ref["audio"]["duration"]
    first = notes[0]["t"]
    tail = round(duration - max(n["t"] + n["d"] for n in notes), 3)
    glued = sum(1 for line in ref["lines"] if len(line["notes"]) >= 6 and " " not in line["text"].strip())
    g_lo, g_hi = GOLDEN_SHARE
    f_lo, f_hi = FRAGMENT_S
    n_lo, n_hi = NOTE_COUNT
    return [
        Check("no_overlap", overlaps == 0, overlaps, "== 0"),
        Check("min_note_len", short == 0, short, f"notes shorter than {MIN_NOTE_S:g} s == 0"),
        Check("range", span <= MAX_SPAN, span, f"<= {MAX_SPAN} semitones"),
        Check("golden_share", g_lo <= golden <= g_hi, round(golden, 3), f"{g_lo:g}..{g_hi:g}"),
        Check("lead_in", first >= LEAD_S - 1e-9, first, f">= {LEAD_S:g} s"),
        Check("tail", tail >= TAIL_S - 1e-9, tail, f">= {TAIL_S:g} s"),
        Check("fragment_len", f_lo <= duration <= f_hi, duration, f"{f_lo}..{f_hi} s", "warn"),
        Check("note_count", n_lo <= len(notes) <= n_hi, len(notes), f"{n_lo}..{n_hi}", "warn"),
        Check("word_breaks", glued == 0, glued, "lines with >= 6 syllables and no spaces == 0", "warn"),
    ]


def variants(track) -> dict[str, tuple[object, float]]:
    def shifted(semitones: float):
        return dataclasses.replace(track, hz=np.where(track.hz > 0, track.hz * 2 ** (semitones / 12), 0.0))

    silent = dataclasses.replace(
        track, hz=np.zeros_like(track.hz), conf=np.zeros_like(track.conf), rms=np.zeros_like(track.rms)
    )
    return {
        "guide": (track, 0.0),
        "octave_up": (shifted(12), 0.0),
        "octave_down": (shifted(-12), 0.0),
        "plus2": (shifted(2), 0.0),
        "silence": (silent, 0.0),
        "delay150": (track, 0.15),
    }


def run_cases(ref: dict, track, cfg, score_fn: ScoreFn) -> dict[str, dict]:
    return {
        name: score_fn(ref, case, wav_t0=wav_t0, cfg=cfg, difficulty=DIFFICULTY, lag_hint_ms=0.0)
        for name, (case, wav_t0) in variants(track).items()
    }


def self_score_checks(ref: dict, results: dict[str, dict]) -> list[Check]:
    top = results["guide"]["score"]["max"]
    totals = {name: res["score"]["total"] for name, res in results.items()}
    types = {n["i"]: n["type"] for n in all_notes(ref)}
    scored = [n for n in results["guide"]["notes"] if types.get(n["i"]) in PITCHED]
    in_pc = sum(1 for n in scored if n.get("cents") is not None and abs(n["cents"]) <= 100)
    pc_share = round(in_pc / len(scored), 3) if scored else 0.0
    onsets = [abs(n["onset_ms"]) for n in scored if n.get("onset_ms") is not None]
    onset = statistics.median(onsets) if onsets else None
    found = round(len(onsets) / len(scored), 3) if scored else 0.0
    octave = max(abs(totals["octave_up"] - totals["guide"]), abs(totals["octave_down"] - totals["guide"]))
    lag = results["guide"].get("latency", {}).get("estimated_ms")
    checks = [
        Check("guide_pitch_class", pc_share >= 0.9, pc_share, ">= 0.9 of notes within 100 cents"),
        Check("guide_onset", onset is not None and onset <= 80, onset, "median |onset| <= 80 ms"),
        Check("guide_onset_found", found >= 0.8, found, ">= 0.8 of pitched notes have an onset", "warn"),
        Check("score_guide", totals["guide"] >= 0.9 * top, totals["guide"], f">= {0.9 * top:g}"),
        Check("score_octave", octave <= 0.01 * top, octave, f"|delta| <= {0.01 * top:g}"),
        Check("score_plus2", totals["plus2"] <= 0.4 * top, totals["plus2"], f"<= {0.4 * top:g}"),
        Check("score_silence", totals["silence"] == 0, totals["silence"], "== 0"),
        Check("score_delay150", totals["delay150"] >= 0.85 * top, totals["delay150"], f">= {0.85 * top:g}"),
    ]
    if lag is not None:
        checks.append(
            Check("guide_lag", abs(lag) <= 50, round(lag), "|estimated guide lag| <= 50 ms", "warn")
        )
    return checks


def build_report(
    ref: dict, checks: list[Check], engine: str | None = None, scores: dict | None = None
) -> dict:
    return {
        "schema": 1,
        "song_id": ref["id"],
        "pass": all(c.ok for c in checks if c.level == "error"),
        "engine": engine,
        "difficulty": DIFFICULTY,
        "scores": scores,
        "checks": [dataclasses.asdict(c) for c in checks],
    }


def run_check(
    ref: dict,
    guide: np.ndarray | None,
    sr: int,
    cfg,
    engine,
    score_fn: ScoreFn | None,
    extra: Iterable[Check] = (),
) -> dict:
    checks = structural_checks(ref) + list(extra)
    if guide is None:
        checks.append(Check("guide_present", False, None, "guide.mp3 exists"))
        return build_report(ref, checks)
    results = run_cases(ref, engine.track(guide, sr), cfg, score_fn)
    checks += self_score_checks(ref, results)
    scores = {name: res["score"]["total"] for name, res in results.items()}
    return build_report(ref, checks, f"{engine.name}-{engine.version}", scores)


def media_checks(song_dir: Path, ref: dict) -> list[Check]:
    minus = song_dir / Path(ref["audio"]["minus"]).name
    guide = song_dir / Path(ref["audio"]["guide"]).name
    sizes = [path.stat().st_size for path in (minus, guide) if path.is_file()]
    largest_kb = round(max(sizes, default=0) / 1024)
    return [
        Check("minus_present", minus.is_file(), None, "minus.mp3 exists"),
        Check("media_size", largest_kb <= MAX_MEDIA_KB, largest_kb, "each mp3 <= 1 MB", "warn"),
    ]


def source_checks(song_dir: Path, ref: dict) -> list[Check]:
    try:
        fresh = compile_dir(song_dir, duration=ref["audio"]["duration"])
    except RefpipeError:
        fresh = None
    checks = [
        Check("reference_fresh", fresh == ref, None, "reference.json == compile(song.txt, meta.yaml)", "warn")
    ]
    txt = song_dir / "song.txt"
    if txt.is_file():
        try:
            song = usdx.read(txt)
        except RefpipeError:
            song = None
        if song is not None:
            same = song.title == ref["title"] and song.artist == ref["artist"]
            checks.append(
                Check("meta_matches_txt", same, None, "#TITLE/#ARTIST == meta.yaml title/artist", "warn")
            )
    return checks


def check_dir(song_dir: Path, scoring: Path = paths.SCORING_JSON) -> dict:
    song_dir = Path(song_dir)
    ref = read_reference(song_dir / "reference.json")
    extra = media_checks(song_dir, ref) + source_checks(song_dir, ref)
    guide_path = song_dir / "guide.mp3"
    if guide_path.exists():
        from app.f0 import get_engine
        from app.scoring.config import load_scoring_config
        from app.scoring.core import score_take

        guide = audio.load_audio(guide_path, SR)
        report = run_check(
            ref, guide, SR, load_scoring_config(scoring), get_engine("swiftf0"), score_take, extra
        )
    else:
        report = run_check(ref, None, SR, None, None, None, extra)
    write_json(report, song_dir / "check.json")
    return report


def cmd(args: argparse.Namespace) -> int:
    report = check_dir(args.song_dir, args.scoring)
    for c in report["checks"]:
        mark = "ok" if c["ok"] else ("WARN" if c["level"] == "warn" else "FAIL")
        print(f"{mark:4} {c['code']:18} {c['value']} ({c['limit']})")
    print(f"{report['song_id']}: {'PASS' if report['pass'] else 'FAIL'}")
    return 0 if report["pass"] else 1


def add_parser(sub) -> None:
    p = sub.add_parser("check", help="structural checks and guide self-scoring -> check.json")
    p.add_argument("song_dir", type=Path)
    p.add_argument("--scoring", type=Path, default=paths.SCORING_JSON)
    p.set_defaults(func=cmd)
