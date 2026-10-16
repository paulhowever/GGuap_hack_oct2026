import json

import pytest
from pydantic import ValidationError

from app.core.config import ROOT
from app.scoring.config import ScoringConfig, load_scoring_config

SCORING = ROOT / "contracts" / "scoring.json"


def raw() -> dict:
    return json.loads(SCORING.read_text(encoding="utf-8"))


def write(tmp_path, data):
    path = tmp_path / "scoring.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_contract_scoring_loads():
    cfg = load_scoring_config(SCORING)
    assert isinstance(cfg, ScoringConfig)
    assert set(cfg.tol_cents) >= {"easy", "normal", "hard"}
    assert set(cfg.mult) >= {"normal", "golden", "free", "rap", "rap_golden"}


def missing_hard(d):
    del d["tol_cents"]["hard"]


def golden_typo(d):
    d["mult"]["goldne"] = d["mult"].pop("golden")


def lag_reversed(d):
    d["lag_range_ms"] = [500, -100]


def weights_over(d):
    d["weights"] = {"pitch": 0.7, "rhythm": 0.3, "extras": 0.1}


def onset_reversed(d):
    d["onset_ok_ms"], d["onset_zero_ms"] = 300, 80


def grade_over_max(d):
    d["grades"]["S"] = d["max"] + 1


def line_grade_over_100(d):
    d["line_grades"]["Perfect"] = 101


def line_grade_negative(d):
    d["line_grades"]["OK"] = -1


@pytest.mark.parametrize(
    "mutate",
    [
        missing_hard,
        golden_typo,
        lag_reversed,
        weights_over,
        onset_reversed,
        grade_over_max,
        line_grade_over_100,
        line_grade_negative,
    ],
)
def test_bad_scoring_is_rejected(tmp_path, mutate):
    data = raw()
    mutate(data)
    with pytest.raises(ValidationError):
        load_scoring_config(write(tmp_path, data))


def test_weights_within_tolerance_load(tmp_path):
    data = raw()
    data["weights"] = {"pitch": 0.655, "rhythm": 0.25, "extras": 0.1}
    assert load_scoring_config(write(tmp_path, data)).weights.pitch == 0.655
