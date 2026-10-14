import io
import json
import os

import numpy as np
import soundfile as sf

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
