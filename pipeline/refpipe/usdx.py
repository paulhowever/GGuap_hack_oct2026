import re
from dataclasses import dataclass, field
from pathlib import Path

from refpipe.errors import UsdxError

NOTE_RE = re.compile(r"^([:*FRG]) (-?\d+) (\d+) (-?\d+) (.*)$")
BREAK_RE = re.compile(r"^-\s*(-?\d+)(?:\s+-?\d+)?\s*$")
DUET_RE = re.compile(r"^P\s*\d+$")
NOTE_TYPES = {":": "normal", "*": "golden", "F": "free", "R": "rap", "G": "rap_golden"}
DUET_HEADERS = {"P1", "P2", "DUETSINGERP1", "DUETSINGERP2"}
OWN_HEADERS = {"TITLE", "ARTIST", "BPM", "GAP", "AUDIO", "MP3", "ENCODING", "RELATIVE"}


@dataclass(frozen=True)
class Note:
    kind: str
    beat: int
    length: int
    pitch: int
    syl: str

    @property
    def type(self) -> str:
        return NOTE_TYPES[self.kind]

    @property
    def end(self) -> int:
        return self.beat + self.length


@dataclass(frozen=True)
class Line:
    notes: tuple[Note, ...]
    break_beat: int | None = None


@dataclass
class UsdxSong:
    title: str
    artist: str
    bpm: float
    gap_ms: float
    audio: str
    lines: list[Line]
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def beat_s(self) -> float:
        return 15.0 / self.bpm

    @property
    def notes(self) -> list[Note]:
        return [note for line in self.lines for note in line.notes]

    def note_t(self, note: Note) -> float:
        return self.gap_ms / 1000.0 + note.beat * self.beat_s

    def note_end_t(self, note: Note) -> float:
        return self.gap_ms / 1000.0 + note.end * self.beat_s


def decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1251")


def parse_number(value: str, key: str) -> float:
    try:
        return float(value.strip().replace(",", "."))
    except ValueError as exc:
        raise UsdxError(f"#{key} is not a number: {value!r}") from exc


def parse(text: str) -> UsdxSong:
    headers: dict[str, str] = {}
    lines: list[Line] = []
    current: list[Note] = []
    in_body = False
    for lineno, row in enumerate(text.splitlines(), start=1):
        if row.startswith("#"):
            if not in_body:
                key, sep, value = row[1:].partition(":")
                if sep:
                    headers[key.strip().upper()] = value.strip()
            continue
        stripped = row.strip()
        if not stripped:
            continue
        in_body = True
        if stripped == "E":
            break
        if DUET_RE.match(stripped):
            raise UsdxError(f"line {lineno}: duet tracks (P1/P2) are not supported")
        note = NOTE_RE.match(row)
        if note:
            kind, beat, length, pitch, syl = note.groups()
            current.append(Note(kind, int(beat), int(length), int(pitch), syl))
            continue
        brk = BREAK_RE.match(stripped)
        if brk:
            if current:
                lines.append(Line(tuple(current), int(brk.group(1))))
                current = []
            continue
        raise UsdxError(f"line {lineno}: cannot parse {row!r}")
    if current:
        lines.append(Line(tuple(current), None))
    elif lines:
        lines[-1] = Line(lines[-1].notes, None)
    return build_song(headers, lines)


def build_song(headers: dict[str, str], lines: list[Line]) -> UsdxSong:
    if headers.get("RELATIVE", "").strip().lower() in {"yes", "true", "1"}:
        raise UsdxError("RELATIVE files are not supported")
    if DUET_HEADERS & headers.keys():
        raise UsdxError("duet files (P1/P2) are not supported")
    for key in ("TITLE", "ARTIST", "BPM", "GAP"):
        if key not in headers:
            raise UsdxError(f"missing #{key}")
    audio = headers.get("AUDIO") or headers.get("MP3")
    if not audio:
        raise UsdxError("missing #AUDIO or #MP3")
    bpm = parse_number(headers["BPM"], "BPM")
    if bpm <= 0:
        raise UsdxError("#BPM must be positive")
    if not lines:
        raise UsdxError("no notes")
    extra = {k: v for k, v in headers.items() if k not in OWN_HEADERS}
    return UsdxSong(
        title=headers["TITLE"],
        artist=headers["ARTIST"],
        bpm=bpm,
        gap_ms=parse_number(headers["GAP"], "GAP"),
        audio=audio,
        lines=lines,
        extra=extra,
    )


def fmt_num(x: float) -> str:
    if float(x).is_integer():
        return str(int(x))
    return f"{x:.3f}".rstrip("0").rstrip(".")


def serialize(song: UsdxSong) -> str:
    out = [f"#TITLE:{song.title}", f"#ARTIST:{song.artist}"]
    out += [f"#{key}:{value}" for key, value in song.extra.items()]
    out += [
        f"#MP3:{song.audio}",
        f"#AUDIO:{song.audio}",
        f"#BPM:{fmt_num(song.bpm)}",
        f"#GAP:{fmt_num(song.gap_ms)}",
    ]
    for index, line in enumerate(song.lines):
        out += [f"{n.kind} {n.beat} {n.length} {n.pitch} {n.syl}" for n in line.notes]
        if index < len(song.lines) - 1:
            brk = line.break_beat if line.break_beat is not None else line.notes[-1].end
            out.append(f"- {brk}")
    out.append("E")
    return "\n".join(out) + "\n"


def read(path: Path) -> UsdxSong:
    try:
        text = decode_text(Path(path).read_bytes())
    except (OSError, UnicodeDecodeError) as exc:
        raise UsdxError(f"{path}: {exc}") from exc
    return parse(text)


def write(song: UsdxSong, path: Path) -> None:
    Path(path).write_text(serialize(song), encoding="utf-8")
