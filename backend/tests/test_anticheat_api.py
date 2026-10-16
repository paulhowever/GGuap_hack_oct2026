import json

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import resample_poly

from app.anticheat.signal import METRIC_KEYS
from app.core.config import ROOT
from app.demo import build_demo
from app.scoring.synth import synth_take


def test_flat_synth_keeps_score_but_is_suspect(submit):
    body = submit(synth={"jitter_cents": 0.0}).json()
    assert body["score"]["total"] >= 9000
    assert body["integrity"]["status"] == "suspect"
    assert "not_voice" in body["integrity"]["flags"]
    assert body["leaderboard"] is None


def test_jittered_take_is_ok(submit):
    body = submit().json()
    assert body["score"]["total"] >= 9000
    assert body["integrity"] == {"status": "ok", "flags": []}
    assert body["leaderboard"]["rank"] == 1


@pytest.mark.parametrize("name", ["guide.wav", "minus.wav"])
def test_playback_is_flagged_as_replay(submit, settings, name):
    build_demo(settings.songs_dir / "demo", ROOT / "contracts" / "fixtures" / "demo.reference.json")
    x, sr = sf.read(settings.songs_dir / "demo" / name, dtype="float32")
    body = submit(audio=resample_poly(x, 16000, sr).astype(np.float32)).json()
    assert body["score"]["total"] >= 9000
    assert body["integrity"]["status"] == "suspect"
    assert "replay" in body["integrity"]["flags"]


def test_jittered_take_with_media_is_ok(submit, settings):
    build_demo(settings.songs_dir / "demo", ROOT / "contracts" / "fixtures" / "demo.reference.json")
    assert submit().json()["integrity"] == {"status": "ok", "flags": []}


def test_jittered_take_with_web_timing_is_ok(submit, settings, demo_ref):
    build_demo(settings.songs_dir / "demo", ROOT / "contracts" / "fixtures" / "demo.reference.json")
    lead = np.zeros(round(0.15 * 16000), dtype=np.float32)
    x = np.concatenate([lead, synth_take(demo_ref, delay_s=0.25, jitter_cents=20.0)])
    body = submit(audio=x, wav_t0=-0.15, lag_ms=250, lag_source="calibrated").json()
    assert body["score"]["total"] >= 9000
    assert not {"replay", "not_voice"} & set(body["integrity"]["flags"])


def logged(caplog, msg):
    return [r.fields for r in caplog.records if r.getMessage() == msg]


def test_empty_guide_is_skipped(submit, settings, demo_ref, caplog):
    song = settings.songs_dir / "demo"
    sf.write(song / "guide.wav", np.zeros(0, dtype=np.float32), 22050, subtype="PCM_16")
    ref = {**demo_ref, "audio": {**demo_ref["audio"], "guide": "/media/demo/guide.wav", "minus": None}}
    (song / "reference.json").write_text(json.dumps(ref, ensure_ascii=False), encoding="utf-8")
    response = submit()
    assert response.status_code == 200
    assert response.json()["integrity"] == {"status": "ok", "flags": []}
    assert logged(caplog, "take_scored")[0]["replay_guide_c"] is None


def test_signal_check_failure_fails_open(submit, monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise ValueError("boom")

    monkeypatch.setattr("app.api.takes.check_signal", boom)
    response = submit(synth={"jitter_cents": 0.0})
    assert response.status_code == 200
    assert response.json()["integrity"] == {"status": "ok", "flags": []}
    assert logged(caplog, "anticheat_failed")[0]["error"] == "ValueError('boom')"
    failed = next(r for r in caplog.records if r.getMessage() == "anticheat_failed")
    assert failed.levelname == "WARNING"
    assert failed.exc_info[0] is ValueError
    scored = logged(caplog, "take_scored")[0]
    assert all(scored[k] is None for k in METRIC_KEYS)
