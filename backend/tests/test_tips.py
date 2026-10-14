from app.f0 import get_engine
from app.scoring.core import score_take
from app.scoring.latency import Latency
from app.scoring.metrics import LineMetrics, NoteMetrics
from app.scoring.synth import synth_take
from app.scoring.tips import build_tips

LAT = Latency(hint_ms=None, estimated_ms=0, applied_ms=0, residual_ms=0, confidence=0.9)


def note(i, line, **kw):
    base = {
        "type": "normal",
        "syl": "ля",
        "d": 0.8,
        "hit": 0.95,
        "coverage": 0.95,
        "cents": 0.0,
        "onset_ms": 10.0,
        "stab_c": 10.0,
        "perfect": True,
    }
    base.update(kw)
    return NoteMetrics(i=i, line=line, **base)


def line(i, score=95, coverage=0.95, text="до ре ми фа соль ля си"):
    return LineMetrics(i=i, text=text, score=score, grade="Perfect", pitch=0.9, rhythm=0.9, coverage=coverage)


def codes(tips):
    return [t["code"] for t in tips]


def test_silence_has_priority():
    tips, per_line = build_tips(
        [note(0, 0, coverage=0.0, hit=0.0, cents=None)], [line(0, 0, 0.0)], LAT, 0, 120
    )
    assert codes(tips)[0] == "silence"
    assert "почти не слышно" in per_line[0]


def test_flat_and_sharp():
    tips, _ = build_tips([note(i, 0, cents=-90.0, hit=0.4) for i in range(3)], [line(0, 50)], LAT, 0, 120)
    assert "flat" in codes(tips)
    tips, _ = build_tips([note(i, 0, cents=95.0, hit=0.4) for i in range(3)], [line(0, 50)], LAT, 0, 120)
    assert "sharp" in codes(tips)


def test_golden_miss():
    tips, _ = build_tips([note(0, 0, type="golden", hit=0.1)], [line(0, 60)], LAT, 0, 120)
    assert "golden_miss" in codes(tips)


def test_late_and_early_by_line():
    tips, per_line = build_tips([note(0, 0, onset_ms=180.0)], [line(0, 70)], LAT, 0, 120)
    assert "late" in codes(tips)
    assert "опаздываешь" in per_line[0]
    tips, _ = build_tips([note(0, 0, onset_ms=-170.0)], [line(0, 70)], LAT, 0, 120)
    assert "early" in codes(tips)


def test_global_residual_latency():
    lat = Latency(hint_ms=0, estimated_ms=250, applied_ms=120, residual_ms=130, confidence=0.9)
    tips, _ = build_tips([note(0, 0)], [line(0)], lat, 0, 120)
    assert any(t["code"] == "late" and t["line"] is None for t in tips)


def test_unstable_then_octave():
    tips, _ = build_tips([note(0, 0, stab_c=80.0, d=1.0)], [line(0, 80)], LAT, -1, 120)
    assert codes(tips)[:2] == ["unstable", "octave_info"]


def test_praise_only_when_nothing_else():
    tips, per_line = build_tips([note(0, 0)], [line(0, 95)], LAT, 0, 120)
    assert codes(tips) == ["praise"]
    assert per_line[0].endswith("отлично!")


def test_at_most_three_tips():
    many = [note(i, i, coverage=0.0, hit=0.0, cents=None) for i in range(5)]
    tips, per_line = build_tips(many, [line(i, 0, 0.0) for i in range(5)], LAT, 0, 120)
    assert len(tips) == 3
    assert len(per_line) == 5


def test_score_take_fills_tips(demo_ref, cfg):
    tr = get_engine("swiftf0").track(synth_take(demo_ref, cents=150), 16000)
    res = score_take(demo_ref, tr, 0.0, cfg, "normal", None)
    assert "sharp" in codes(res["tips"])
    assert any(line["tip"] for line in res["lines"])
