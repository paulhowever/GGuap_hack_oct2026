import math

import numpy as np
import pytest

from app.scoring.pitch import fold_cents, hz_to_midi


@pytest.mark.parametrize(
    ("cents", "folded"), [(1150, -50), (-1150, 50), (1200, 0), (0, 0), (2450, 50), (-30, -30)]
)
def test_fold_cents(cents, folded):
    assert float(fold_cents(cents)) == pytest.approx(folded)


def test_hz_to_midi():
    out = hz_to_midi(np.array([440.0, 261.6256, 0.0, -5.0]))
    assert out[0] == pytest.approx(69.0)
    assert out[1] == pytest.approx(60.0, abs=1e-3)
    assert math.isnan(out[2])
    assert math.isnan(out[3])


def test_scoring_config(cfg):
    assert cfg.version == "score-v1"
    assert cfg.tol("normal") == 120
    assert cfg.grade(9500) == "S"
    assert cfg.grade(7600) == "A"
    assert cfg.grade(100) == "D"
    assert cfg.line_grade(91) == "Perfect"
    assert cfg.line_grade(10) == "Miss"
    assert cfg.weights.pitch + cfg.weights.rhythm + cfg.weights.extras == pytest.approx(1.0)
