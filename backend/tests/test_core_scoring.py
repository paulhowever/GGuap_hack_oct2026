import copy
from itertools import pairwise

import numpy as np
import pytest

from app.f0 import get_engine
from app.scoring.core import score_take
from app.scoring.synth import synth_take


def run(ref, cfg, x, difficulty="normal", hint=None):
    tr = get_engine("swiftf0").track(x, 16000)
    return score_take(ref, tr, 0.0, cfg, difficulty, hint)


@pytest.fixture(scope="module")
def perfect(demo_ref, cfg):
    return run(demo_ref, cfg, synth_take(demo_ref))


def test_perfect_take(perfect):
    assert perfect["score"]["total"] >= 9300
    assert perfect["score"]["grade"] == "S"
    assert all(line["grade"] == "Perfect" for line in perfect["lines"])
    assert abs(perfect["latency"]["estimated_ms"]) <= 20
    assert len(perfect["notes"]) == 6


def test_result_shape(perfect):
    assert perfect["version"] == "score-v1"
    assert set(perfect["score"]) == {"total", "max", "grade", "pitch_pct", "rhythm_pct", "extras_pct"}
    assert perfect["chart"]["hop_ms"] == 20
    assert any(v is not None for v in perfect["chart"]["sung"])
    assert sum(n["pts"] for n in perfect["notes"]) == pytest.approx(perfect["score"]["total"], abs=6)


def test_sharp_150_depends_on_difficulty(demo_ref, cfg):
    x = synth_take(demo_ref, cents=150)
    assert run(demo_ref, cfg, x, "normal")["score"]["total"] < 4000
    assert run(demo_ref, cfg, x, "easy")["score"]["total"] >= 9000


def test_sharp_50_passes_hard(demo_ref, cfg):
    assert run(demo_ref, cfg, synth_take(demo_ref, cents=50), "hard")["score"]["total"] >= 8500


def test_delay_250_without_hint(demo_ref, cfg):
    res = run(demo_ref, cfg, synth_take(demo_ref, delay_s=0.25))
    assert res["latency"]["estimated_ms"] == pytest.approx(250, abs=20)
    assert res["score"]["total"] >= 9000


@pytest.mark.parametrize("octave", [-1, 1])
def test_octave_is_not_penalised(demo_ref, cfg, perfect, octave):
    res = run(demo_ref, cfg, synth_take(demo_ref, octave=octave))
    assert res["score"]["total"] == pytest.approx(perfect["score"]["total"], rel=0.02)
    assert res["octave_shift"] == octave


def test_silence(demo_ref, cfg):
    res = run(demo_ref, cfg, np.zeros(16000 * 12, dtype=np.float32))
    assert res["score"]["total"] <= 200
    assert all(n["cents"] is None for n in res["notes"])


def test_constant_wrong_tone(demo_ref, cfg):
    t = np.arange(16000 * 12) / 16000
    x = (0.3 * np.sin(2 * np.pi * 300.0 * t)).astype(np.float32)
    assert run(demo_ref, cfg, x)["score"]["total"] < 3000


def test_missing_golden_note(demo_ref, cfg, perfect):
    x = synth_take(demo_ref)
    golden = demo_ref["lines"][0]["notes"][2]
    x[int(golden["t"] * 16000) : int((golden["t"] + golden["d"]) * 16000) + 800] = 0.0
    res = run(demo_ref, cfg, x)
    assert res["notes"][2]["hit"] < 0.1
    assert res["score"]["pitch_pct"] < perfect["score"]["pitch_pct"] - 25


def test_muted_line_drops_only_that_line(demo_ref, cfg):
    res = run(demo_ref, cfg, synth_take(demo_ref, mute_lines=frozenset({1})))
    assert res["lines"][0]["grade"] == "Perfect"
    assert res["lines"][1]["score"] <= 10


@pytest.mark.parametrize("difficulty", ["easy", "normal"])
def test_contiguous_notes_keep_their_own_onset(demo_ref, cfg, difficulty):
    ref = copy.deepcopy(demo_ref)
    notes = ref["lines"][1]["notes"]
    notes[1]["midi"] = 65
    notes[2]["midi"] = 66
    for prev, cur in pairwise(notes):
        cur["t"] = round(prev["t"] + prev["d"], 3)
    res = run(ref, cfg, synth_take(ref), difficulty)
    assert res["score"]["total"] >= 9500
    for k in (4, 5):
        assert res["notes"][k]["onset_ms"] is not None
        assert abs(res["notes"][k]["onset_ms"]) <= cfg.onset_ok_ms
        assert res["notes"][k]["perfect"] is True
