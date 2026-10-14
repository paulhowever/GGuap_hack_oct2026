from dataclasses import dataclass


@dataclass(frozen=True)
class NoteMetrics:
    i: int
    line: int
    type: str
    syl: str
    d: float
    hit: float
    coverage: float
    cents: float | None
    onset_ms: float | None
    stab_c: float | None
    perfect: bool
    pts: int = 0


@dataclass(frozen=True)
class LineMetrics:
    i: int
    text: str
    score: int
    grade: str
    pitch: float
    rhythm: float
    coverage: float
