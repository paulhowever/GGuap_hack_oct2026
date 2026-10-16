import json
from pathlib import Path

from pydantic import BaseModel, model_validator

TOL_KEYS = frozenset({"easy", "normal", "hard"})
MULT_KEYS = frozenset({"normal", "golden", "free", "rap", "rap_golden"})


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

    @model_validator(mode="after")
    def check(self) -> "ScoringConfig":
        problems = []
        if missing := TOL_KEYS - set(self.tol_cents):
            problems.append(f"tol_cents is missing {sorted(missing)}")
        if missing := MULT_KEYS - set(self.mult):
            problems.append(f"mult is missing {sorted(missing)}")
        if not self.lag_range_ms[0] < self.lag_range_ms[1]:
            problems.append(f"lag_range_ms {list(self.lag_range_ms)} must be increasing")
        if not self.onset_ok_ms < self.onset_zero_ms:
            problems.append(
                f"onset_ok_ms {self.onset_ok_ms:g} must be below onset_zero_ms {self.onset_zero_ms:g}"
            )
        w = self.weights
        if abs(w.pitch + w.rhythm + w.extras - 1.0) > 0.01:
            problems.append(f"weights sum to {w.pitch + w.rhythm + w.extras:g}, expected 1")
        bad = {k: v for k, v in self.grades.items() if not 0 <= v <= self.max}
        if bad:
            problems.append(f"grades {bad} must be within [0, {self.max}]")
        bad = {k: v for k, v in self.line_grades.items() if not 0 <= v <= 100}
        if bad:
            problems.append(f"line_grades {bad} must be within [0, 100]")
        if problems:
            raise ValueError("invalid scoring.json: " + "; ".join(problems))
        return self

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
