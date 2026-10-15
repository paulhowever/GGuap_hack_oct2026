import json

import soundfile as sf

from app.core.config import ROOT
from app.demo import build_demo
from app.f0 import get_engine
from app.scoring.core import score_take


def test_build_demo(tmp_path, cfg):
    ref = build_demo(tmp_path, ROOT / "contracts" / "fixtures" / "demo.reference.json")
    saved = json.loads((tmp_path / "reference.json").read_text(encoding="utf-8"))
    assert saved == ref
    assert ref["audio"]["minus"] == "/media/demo/minus.wav"
    for name in ("minus.wav", "guide.wav"):
        info = sf.info(tmp_path / name)
        assert info.samplerate == 22050
        assert abs(info.duration - ref["audio"]["duration"]) < 0.05
    guide, sr = sf.read(tmp_path / "guide.wav", dtype="float32")
    res = score_take(ref, get_engine("swiftf0").track(guide, sr), 0.0, cfg, "normal", None)
    assert res["score"]["total"] >= 9000
