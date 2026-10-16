import argparse
import math
from collections import Counter
from pathlib import Path

import mido

from refpipe import usdx
from refpipe.errors import MidiError
from refpipe.usdx import Line, Note, UsdxSong

MIN_TXT_BPM = 200.0


def first_tempo(mid: mido.MidiFile) -> int:
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                return msg.tempo
    return 500000


def txt_bpm(tempo: int) -> float:
    real = mido.tempo2bpm(tempo)
    return round(real * max(1, math.ceil(MIN_TXT_BPM / real)), 3)


def is_note_on(msg: mido.Message) -> bool:
    return msg.type == "note_on" and msg.velocity > 0


def read_midi(path: Path) -> mido.MidiFile:
    try:
        return mido.MidiFile(str(path))
    except (OSError, EOFError, ValueError) as exc:
        raise MidiError(f"{path}: cannot read MIDI file: {str(exc) or type(exc).__name__}") from exc


def midi_events(mid: mido.MidiFile) -> tuple[list[tuple[float, mido.Message]], float]:
    events = []
    now = 0.0
    for msg in mid:
        now += msg.time
        if msg.type in ("note_on", "note_off"):
            events.append((now, msg))
    events.sort(key=lambda event: (event[0], is_note_on(event[1])))
    return events, now


def pick_channel(events: list[tuple[float, mido.Message]], channel: int | None) -> int:
    starts = Counter(msg.channel for _, msg in events if is_note_on(msg))
    if not starts:
        raise MidiError("no notes in MIDI file")
    if channel is None:
        return starts.most_common(1)[0][0]
    return channel


def channel_notes(
    events: list[tuple[float, mido.Message]], end: float, channel: int
) -> list[tuple[float, float, int]]:
    notes = []
    current = None
    for now, msg in events:
        if msg.channel != channel:
            continue
        if is_note_on(msg):
            if current is not None and now > current[0]:
                notes.append((current[0], now, current[1]))
            current = (now, msg.note)
        elif current is not None and msg.note == current[1]:
            if now > current[0]:
                notes.append((current[0], now, current[1]))
            current = None
    if current is not None and end > current[0]:
        notes.append((current[0], end, current[1]))
    return notes


def melody_notes(mid: mido.MidiFile, channel: int | None = None) -> list[tuple[float, float, int]]:
    events, end = midi_events(mid)
    channel = pick_channel(events, channel)
    notes = channel_notes(events, end, channel)
    if not notes:
        raise MidiError(f"no notes on channel {channel}")
    return notes


def channel_hint(mid: mido.MidiFile, channel: int | None) -> str:
    events, end = midi_events(mid)
    chosen = pick_channel(events, channel)
    used = sorted({msg.channel for _, msg in events if is_note_on(msg)})
    counts = ", ".join(f"{ch}: {len(channel_notes(events, end, ch))}" for ch in used)
    return f"; used channel {chosen}, notes per channel {counts}; pick the melody with --channel"


def syllables(text: str) -> list[list[str]]:
    lines = []
    for raw in text.splitlines():
        words = raw.split()
        syls: list[str] = []
        for index, word in enumerate(words):
            parts = [part for part in word.split("-") if part]
            if not parts:
                continue
            if index < len(words) - 1:
                parts[-1] += " "
            syls.extend(parts)
        if syls:
            lines.append(syls)
    return lines


def build_song(
    notes: list[tuple[float, float, int]],
    lyrics: list[list[str]],
    bpm: float,
    title: str,
    artist: str,
    offset_ms: float = 0.0,
    hint: str = "",
) -> UsdxSong:
    counts = [len(syls) for syls in lyrics]
    if sum(counts) != len(notes):
        lyric = f"lyrics have {sum(counts)} syllables in {len(counts)} lines {counts}"
        raise MidiError(f"{lyric}, melody has {len(notes)} notes{hint}")
    beat_s = 15.0 / bpm
    origin = notes[0][0]
    beats = [round((start - origin) / beat_s) for start, _, _ in notes]
    for k in range(1, len(notes)):
        if beats[k] <= beats[k - 1]:
            raise MidiError(
                f"melody note {k + 1} at {notes[k][0]:.3f} s rounds onto the same beat as note {k} "
                f"at BPM {usdx.fmt_num(bpm)}; quantize the MIDI or pass a higher --bpm"
            )
    ends = [round((end - origin) / beat_s) for _, end, _ in notes]
    for k in range(len(notes) - 1):
        ends[k] = min(ends[k], beats[k + 1])
    lines = []
    k = 0
    for syls in lyrics:
        line_notes = []
        for syl in syls:
            line_notes.append(Note(":", beats[k], max(1, ends[k] - beats[k]), notes[k][2] - 60, syl))
            k += 1
        lines.append(Line(tuple(line_notes), line_notes[-1].end))
    lines[-1] = Line(lines[-1].notes, None)
    return UsdxSong(
        title=title,
        artist=artist,
        bpm=bpm,
        gap_ms=float(round(origin * 1000 + offset_ms)),
        audio="minus.mp3",
        lines=lines,
        extra={"VOCALS": "guide.mp3", "CREATOR": "refpipe from-midi"},
    )


def from_midi(
    midi_path: Path,
    lyrics_path: Path,
    title: str,
    artist: str,
    channel: int | None = None,
    offset_ms: float = 0.0,
    bpm: float | None = None,
) -> UsdxSong:
    if bpm is not None and not 0 < bpm < math.inf:
        raise MidiError("--bpm must be positive")
    mid = read_midi(midi_path)
    notes = melody_notes(mid, channel)
    try:
        lyrics = syllables(usdx.decode_text(Path(lyrics_path).read_bytes()))
    except (OSError, UnicodeDecodeError) as exc:
        raise MidiError(f"{lyrics_path}: cannot read lyrics: {exc}") from exc
    bpm = bpm if bpm is not None else txt_bpm(first_tempo(mid))
    return build_song(notes, lyrics, bpm, title, artist, offset_ms, channel_hint(mid, channel))


def cmd(args: argparse.Namespace) -> int:
    song = from_midi(args.midi, args.lyrics, args.title, args.artist, args.channel, args.offset_ms, args.bpm)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    usdx.write(song, args.out)
    print(
        f"{args.out}: {len(song.notes)} notes, {len(song.lines)} lines, "
        f"BPM {usdx.fmt_num(song.bpm)}, GAP {usdx.fmt_num(song.gap_ms)}"
    )
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("from-midi", help="melody.mid + lyrics.txt -> song.txt")
    p.add_argument("midi", type=Path)
    p.add_argument("lyrics", type=Path)
    p.add_argument("-o", "--out", type=Path, required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--artist", required=True)
    p.add_argument("--channel", type=int, default=None)
    p.add_argument("--offset-ms", type=float, default=0.0)
    p.add_argument("--bpm", type=float, default=None)
    p.set_defaults(func=cmd)
