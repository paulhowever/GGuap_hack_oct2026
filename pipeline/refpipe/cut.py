import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from refpipe import audio, usdx
from refpipe.errors import CutError
from refpipe.meta import load_meta, set_t0_ms
from refpipe.usdx import Line, Note, UsdxSong

LEAD_S = 2.5
TAIL_S = 1.5
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
    if not 20 <= duration <= 40:
        out.append(f"fragment is {duration:.1f} s, expected 20-40 s")
    if not 40 <= notes <= 120:
        out.append(f"fragment has {notes} notes, expected 40-120")
    return tuple(out)


def cut_song(song: UsdxSong, t0: float, t1: float, lead_s: float = LEAD_S, tail_s: float = TAIL_S) -> Cut:
    if t1 <= t0:
        raise CutError("t1 must be greater than t0")
    lo, hi = t0 + lead_s, t1 - tail_s
    keep = [
        line
        for line in song.lines
        if line_span(song, line)[0] >= lo - EPS and line_span(song, line)[1] <= hi + EPS
    ]
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
    return Cut(t0, t1, cut, fragment_warnings(t1 - t0, len(cut.notes)))


def cmd(args: argparse.Namespace) -> int:
    result = cut_song(usdx.read(args.txt), args.t0, args.t1)
    jobs = [
        (src, name) for src, name in ((args.minus, "minus.mp3"), (args.guide, "guide.mp3")) if src is not None
    ]
    for src, _ in jobs:
        if not src.is_file():
            raise CutError(f"source not found: {src}")
    meta = args.out / "meta.yaml"
    if meta.exists():
        load_meta(meta)
    args.out.mkdir(parents=True, exist_ok=True)
    for src, name in jobs:
        audio.run_tool(audio.ffmpeg_cut_argv(src, args.out / name, args.t0, args.t1))
    usdx.write(result.song, args.out / "song.txt")
    if meta.exists():
        set_t0_ms(meta, round(args.t0 * 1000))
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
    p.set_defaults(func=cmd)
