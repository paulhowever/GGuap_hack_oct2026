import json
import sqlite3
import uuid

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.anticheat.session import make_token
from app.main import create_app


def issue(client, **kw):
    return client.post(
        "/api/v1/sessions", json={"song_id": "demo", "client_id": None, "difficulty": "normal", **kw}
    )


def test_issue_session(client, clock):
    r = issue(client)
    assert r.status_code == 200
    body = r.json()
    assert body["issued_at"] == pytest.approx(clock.t)
    assert body["expires_in"] == 900
    assert body["token"].count(".") == 2


def test_issue_errors(client):
    r = issue(client, song_id="nope")
    assert r.status_code == 404
    assert r.json()["detail"] == "song_not_found"
    assert issue(client, difficulty="insane").status_code == 422
    assert issue(client, client_id="nope").status_code == 422


def test_honest_take_is_ok(submit, settings):
    body = submit().json()
    assert body["integrity"] == {"status": "ok", "flags": []}
    assert body["completion"] == {"ratio": 1.0}
    assert body["leaderboard"] == {"rank": 1, "of": 1, "personal_best": True}
    with sqlite3.connect(settings.data_dir / "app.db") as db:
        status, sha = db.execute("select integrity_status, audio_sha256 from takes").fetchone()
    assert status == "ok"
    assert len(sha) == 64


def test_no_session_is_unverified(client, submit):
    body = submit(session=False).json()
    assert body["integrity"] == {"status": "unverified", "flags": ["no_session"]}
    assert body["leaderboard"] is None
    assert client.get("/api/v1/leaderboard/demo").json()["items"] == []


def test_token_is_single_use(client, submit, clock):
    token = issue(client).json()["token"]
    clock.advance(12)
    assert submit(session=False, session_token=token).json()["integrity"]["status"] == "ok"
    again = submit(session=False, session_token=token, synth={"cents": 20}).json()
    assert again["integrity"] == {"status": "suspect", "flags": ["bad_session"]}


def test_expired_token(client, submit, clock):
    token = issue(client).json()["token"]
    clock.advance(901)
    assert submit(session=False, session_token=token).json()["integrity"]["flags"] == ["bad_session"]


@pytest.mark.parametrize(("wait", "flags"), [(9.9, ["too_fast"]), (10.0, [])])
def test_too_fast(client, submit, clock, wait, flags):
    token = issue(client).json()["token"]
    clock.advance(wait)
    assert submit(session=False, session_token=token).json()["integrity"]["flags"] == flags


def test_full_take_sent_too_early_is_suspect(client, submit, clock):
    token = issue(client).json()["token"]
    clock.advance(9.9)
    body = submit(session=False, session_token=token).json()
    assert body["integrity"] == {"status": "suspect", "flags": ["too_fast"]}
    assert body["completion"] == {"ratio": 1.0}
    assert body["leaderboard"] is None


def test_recorded_length_is_capped_by_song_duration(client, submit, clock):
    token = issue(client).json()["token"]
    clock.advance(10.0)
    body = submit(session=False, session_token=token, wav_t0=5.0).json()
    assert "too_fast" not in body["integrity"]["flags"]
    assert body["completion"] == {"ratio": 1.0}


def test_early_exit_is_incomplete(client, submit, clock, partial, settings):
    token = issue(client).json()["token"]
    clock.advance(7.2)
    body = submit(session=False, session_token=token, audio=partial()).json()
    assert body["integrity"] == {"status": "incomplete", "flags": ["incomplete"]}
    assert body["completion"] == {"ratio": 0.73}
    assert body["leaderboard"] is None
    assert body["score"]["total"] > 0
    keys = list(body)
    assert keys.index("completion") == keys.index("integrity") + 1
    assert client.get(f"/api/v1/takes/{body['take_id']}").json() == body
    assert client.get("/api/v1/leaderboard/demo").json()["items"] == []
    assert client.get("/api/v1/songs").json()[0]["top"] is None
    with sqlite3.connect(settings.data_dir / "app.db") as db:
        assert db.execute("select integrity_status from takes").fetchone() == ("incomplete",)


def test_early_exit_with_session_helper_is_incomplete(submit, partial):
    body = submit(audio=partial(0.4)).json()
    assert body["integrity"] == {"status": "incomplete", "flags": ["incomplete"]}
    assert 0.0 < body["completion"]["ratio"] < 0.5
    assert body["leaderboard"] is None


@pytest.mark.parametrize(("wait", "flags"), [(5.1, ["too_fast", "incomplete"]), (5.3, ["incomplete"])])
def test_too_fast_counts_only_the_recorded_length(client, submit, clock, partial, wait, flags):
    token = issue(client).json()["token"]
    clock.advance(wait)
    body = submit(session=False, session_token=token, audio=partial()).json()
    assert body["integrity"]["flags"] == flags
    assert body["integrity"]["status"] == ("suspect" if "too_fast" in flags else "incomplete")


def test_no_session_early_exit_is_incomplete(submit, partial):
    body = submit(session=False, audio=partial()).json()
    assert body["integrity"] == {"status": "incomplete", "flags": ["no_session", "incomplete"]}


def test_recorded_length_includes_wav_t0(client, submit, clock, partial):
    token = issue(client).json()["token"]
    clock.advance(9.0)
    body = submit(session=False, session_token=token, audio=partial(), wav_t0=1.5).json()
    assert "incomplete" not in body["integrity"]["flags"]
    assert body["completion"] == {"ratio": 0.97}


@pytest.mark.parametrize(
    "issued", [{"difficulty": "easy"}, {"client_id": str(uuid.uuid4())}, {"song_id": "demo2"}]
)
def test_token_is_bound_to_song_client_and_difficulty(client, submit, clock, settings, demo_ref, issued):
    (settings.songs_dir / "demo2").mkdir()
    (settings.songs_dir / "demo2" / "reference.json").write_text(json.dumps({**demo_ref, "id": "demo2"}))
    token = issue(client, **issued).json()["token"]
    clock.advance(12)
    assert submit(session=False, session_token=token).json()["integrity"]["flags"] == ["bad_session"]


def test_tampered_or_unknown_token(client, submit, clock):
    token = issue(client).json()["token"]
    clock.advance(12)
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert submit(session=False, session_token=forged).json()["integrity"]["flags"] == ["bad_session"]
    unknown = make_token(
        client.app.state.secret, "demo", None, "normal", round(clock.t * 1000) - 12000, "feedfeedfeedfeed"
    )
    body = submit(session=False, session_token=unknown, synth={"cents": 20}).json()
    assert body["integrity"]["flags"] == ["bad_session"]


def test_duplicate_audio(submit):
    assert submit().json()["integrity"]["status"] == "ok"
    second = submit().json()
    assert second["integrity"] == {"status": "suspect", "flags": ["duplicate"]}
    assert second["leaderboard"] is None


def test_secret_from_settings(settings):
    settings.secret = "s3cret"
    with TestClient(create_app(settings)) as c:
        assert c.app.state.secret == "s3cret"


def test_secret_generated_when_missing(settings, caplog):
    with TestClient(create_app(settings)) as c:
        assert len(c.app.state.secret) == 64
    assert any(r.getMessage() == "secret_generated" for r in caplog.records)


def test_malformed_token_is_bad_session(submit):
    r = submit(session=False, session_token="1.a.é")
    assert r.status_code == 200
    assert "bad_session" in r.json()["integrity"]["flags"]


@pytest.mark.parametrize("raw", [b"not a wav at all", None])
def test_undecodable_audio_does_not_burn_token(client, submit, clock, raw):
    token = issue(client).json()["token"]
    clock.advance(12)
    if raw is None:
        r = submit(session=False, session_token=token, audio=np.zeros(100, dtype=np.float32))
    else:
        meta = {"song_id": "demo", "player": "Паша", "wav_t0": 0.0, "wav_sr": 16000, "session_token": token}
        r = client.post(
            "/api/v1/takes",
            files={"audio": ("take.wav", raw, "audio/wav")},
            data={"meta": json.dumps(meta, ensure_ascii=False)},
        )
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_audio"
    good = submit(session=False, session_token=token)
    assert good.status_code == 200
    assert good.json()["integrity"] == {"status": "ok", "flags": []}
