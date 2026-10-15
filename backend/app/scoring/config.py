import json
from pathlib import Path

from pydantic import BaseModel


class Weights(BaseModel):
    pitch: float
    rhythm: float
    extras: float


class ScoringConfig(BaseModel):
    version: str
    tol_cents: dict[str, float]
    conf_min: float
    rms_gate_db: float
    onset_ok_ms: float
    onset_zero_ms: float
    weights: Weights
    mult: dict[str, float]
    lag_range_ms: tuple[float, float]
    lag_clip_ms: float
    rho_min: float
    max: int
    grades: dict[str, int]
    line_grades: dict[str, int]

    def tol(self, difficulty: str) -> float:
        return self.tol_cents[difficulty]

    def grade(self, total: int) -> str:
        for name, threshold in sorted(self.grades.items(), key=lambda kv: -kv[1]):
            if total >= threshold:
                return name
        return "D"

    def line_grade(self, score: float) -> str:
        for name, threshold in sorted(self.line_grades.items(), key=lambda kv: -kv[1]):
            if score >= threshold:
                return name
        return "Miss"


def load_scoring_config(path: Path) -> ScoringConfig:
    return ScoringConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))
