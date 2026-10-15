import io
import json
import os
import sqlite3
import uuid

import numpy as np
import pytest
import soundfile as sf

from app.core.config import ROOT
from app.scoring.synth import synth_take


def wav_bytes(x, sr=16000):
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def meta(**kw):
    base = {
        "song_id": "demo",
        "player": "Паша",
        "difficulty": "normal",
        "challenge_id": None,
        "wav_t0": 0.0,
        "wav_sr": 16000,
        "lag_ms": None,
        "frames": [],
        "client": {},
    }
    base.update(kw)
    return json.dumps(base, ensure_ascii=False)


def post(client, audio, m):
    return client.post("/api/v1/takes", files={"audio": ("take.wav", audio, "audio/wav")}, data={"meta": m})


def test_perfect_take_scores_high(client, settings, demo_ref):
    r = post(client, wav_bytes(synth_take(demo_ref)), meta())
    assert r.status_code == 200
    body = r.json()
    assert body["score"]["total"] >= 9000
    assert body["take_id"].startswith("tk_")
    assert body["player"] == "Паша"
    assert body["engine"]["final"].startswith("swiftf0-")
    assert body["score"]["source"] == "final"
    assert body["score"]["live_total"] is None
    assert (settings.data_dir / "takes" / f"{body['take_id']}.wav").exists()


def test_live_frames_are_scored_too(client, demo_ref):
    frames = [{"t": round(t, 3), "hz": 261.63, "conf": 1.0, "rms": 0.1} for t in np.arange(2.5, 3.3, 0.0107)]
    r = post(client, wav_bytes(synth_take(demo_ref)), meta(frames=frames, lag_ms=0))
    assert isinstance(r.json()["score"]["live_total"], int)


def test_48k_upload(client, demo_ref):
    r = post(client, wav_bytes(synth_take(demo_ref, sr=48000), sr=48000), meta(wav_sr=48000))
    assert r.status_code == 200
    assert r.json()["score"]["total"] >= 9000


def test_unknown_song(client, demo_ref):
    assert post(client, wav_bytes(synth_take(demo_ref)), meta(song_id="nope")).status_code == 404


def test_bad_meta(client, demo_ref):
    r = post(client, wav_bytes(synth_take(demo_ref)), "{not json")
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_meta"
    assert post(client, wav_bytes(synth_take(demo_ref)), meta(difficulty="insane")).status_code == 422


def test_bad_audio(client):
    r = post(client, b"definitely not a wav", meta())
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_audio"


def test_empty_audio(client):
    r = post(client, wav_bytes(np.zeros(0, dtype=np.float32)), meta())
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_audio"


def test_short_audio(client):
    r = post(client, wav_bytes(np.zeros(10, dtype=np.float32)), meta())
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_audio"


def test_oversized_upload_rejected_before_decode(client):
    client.app.state.settings.max_take_s = 1.0
    r = post(client, os.urandom(300_000), meta())
    assert r.status_code == 413
    assert r.json()["detail"] == "take_too_long"


def test_too_long(client, demo_ref):
    client.app.state.settings.max_take_s = 1.0
    assert post(client, wav_bytes(synth_take(demo_ref)), meta()).status_code == 413


def test_take_stores_client_id(client, settings, demo_ref):
    c = str(uuid.uuid4())
    r = post(client, wav_bytes(synth_take(demo_ref)), meta(client_id=c))
    assert r.status_code == 200
    with sqlite3.connect(settings.data_dir / "app.db") as db:
        row = db.execute("select client_id from takes where id = ?", (r.json()["take_id"],)).fetchone()
    assert row == (c,)


def test_take_rejects_bad_client_id(client, demo_ref):
    assert post(client, wav_bytes(synth_take(demo_ref)), meta(client_id="nope")).status_code == 422


def test_tiny_samplerate_rejected(client):
    r = post(client, wav_bytes(np.zeros(20, dtype=np.float32), sr=5), meta())
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_audio"


def test_nan_meta_rejected(client, demo_ref):
    m = meta(lag_ms=0).replace('"lag_ms": 0', '"lag_ms": NaN')
    r = post(client, wav_bytes(synth_take(demo_ref)), m)
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_meta"


def test_engine_value_error_is_bad_audio(client, demo_ref):
    class Boom:
        name = "boom"
        version = "0"

        def track(self, audio, sr):
            raise ValueError("nope")

    client.app.state.f0 = Boom()
    r = post(client, wav_bytes(synth_take(demo_ref)), meta())
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_audio"


def float_wav(x, sr=16000):
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV", subtype="FLOAT")
    return buf.getvalue()


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_non_finite_audio_is_bad_audio_and_keeps_the_token(client, demo_ref, clock, bad):
    body = {"song_id": "demo", "client_id": None, "difficulty": "normal"}
    token = client.post("/api/v1/sessions", json=body).json()["token"]
    clock.advance(demo_ref["audio"]["duration"])
    x = synth_take(demo_ref, jitter_cents=20.0).astype(np.float32)
    broken = x.copy()
    broken[8000] = bad
    r = post(client, float_wav(broken), meta(session_token=token))
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_audio"
    assert post(client, float_wav(x), meta(session_token=token)).json()["integrity"] == {
        "status": "ok",
        "flags": [],
    }


@pytest.mark.parametrize(
    "path",
    [
        "contracts/fixtures/result.perfect.json",
        *(f"web/mock/result.{mode}.json" for mode in ("perfect", "offkey", "octave", "late200", "silent")),
    ],
)
def test_mock_results_have_the_real_keys(submit, path):
    body = submit().json()
    mock = json.loads((ROOT / path).read_text(encoding="utf-8"))
    assert list(mock) == list(body)
    assert list(mock["score"]) == list(body["score"])


def logged_scored(caplog):
    return [r.fields for r in caplog.records if r.getMessage() == "take_scored"]


@pytest.mark.parametrize(
    ("source", "applied"), [("estimated", 300), ("config", 300), (None, 300), ("calibrated", 160)]
)
def test_lag_source_decides_the_clip(submit, caplog, source, applied):
    extra = {} if source is None else {"lag_source": source}
    r = submit(synth={"delay_s": 0.3}, lag_ms=40, **extra)
    assert r.status_code == 200
    body = r.json()
    assert body["latency"]["applied_ms"] == pytest.approx(applied, abs=20)
    if source != "calibrated":
        assert body["score"]["total"] >= 9000
    assert logged_scored(caplog)[0]["lag_source"] == source


def test_unknown_lag_source_is_bad_meta(client, demo_ref):
    r = post(client, wav_bytes(synth_take(demo_ref)), meta(lag_source="guess"))
    assert r.status_code == 422
