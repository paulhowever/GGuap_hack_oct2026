import json
import shutil

import pytest


def test_list(client):
    body = client.get("/api/v1/songs").json()
    assert [s["id"] for s in body] == ["demo"]
    assert body[0]["license"]["attribution"] == "huap team"


def test_get(client):
    body = client.get("/api/v1/songs/demo").json()
    assert body["status"] == "ready"
    assert body["lines"][0]["notes"][0]["midi"] == 60


def test_not_found_and_traversal(client):
    assert client.get("/api/v1/songs/nope").status_code == 404
    assert client.get("/api/v1/songs/..%2Fdata").status_code == 404


def test_failed_check_hides_song(client, settings):
    (settings.songs_dir / "demo" / "check.json").write_text(json.dumps({"pass": False}))
    assert client.get("/api/v1/songs").json() == []
    assert client.get("/api/v1/songs/demo").status_code == 404


def test_media_static(client, settings):
    (settings.songs_dir / "demo" / "minus.wav").write_bytes(b"RIFF0000")
    assert client.get("/media/demo/minus.wav").content == b"RIFF0000"


def broken_song(songs_dir, demo_ref, case):
    if case == "truncated":
        d = songs_dir / "truncated"
        d.mkdir()
        (d / "reference.json").write_text(json.dumps({**demo_ref, "id": "truncated"})[:200])
    elif case == "nostats":
        d = songs_dir / "nostats"
        d.mkdir()
        ref = {k: v for k, v in demo_ref.items() if k != "stats"}
        (d / "reference.json").write_text(json.dumps({**ref, "id": "nostats"}))
    elif case == "listcheck":
        d = songs_dir / "listcheck"
        d.mkdir()
        (d / "reference.json").write_text(json.dumps({**demo_ref, "id": "listcheck"}))
        (d / "check.json").write_text("[]")
    elif case == "Kalinka":
        d = songs_dir / "Kalinka"
        shutil.copytree(songs_dir / "demo", d)
    else:
        d = songs_dir / "renamed"
        shutil.copytree(songs_dir / "demo", d)
    return d.name


@pytest.mark.parametrize("case", ["truncated", "nostats", "listcheck", "Kalinka", "renamed"])
def test_broken_song_is_skipped(client, settings, demo_ref, caplog, case):
    name = broken_song(settings.songs_dir, demo_ref, case)
    r = client.get("/api/v1/songs")
    assert r.status_code == 200
    assert [s["id"] for s in r.json()] == ["demo"]
    assert client.get(f"/api/v1/songs/{name}").status_code == 404
    assert client.get("/api/v1/songs/demo").status_code == 200
    skipped = [rec.fields for rec in caplog.records if rec.getMessage() == "song_skipped"]
    assert skipped
    assert {f["dir"] for f in skipped} == {name}
    assert all(f["error"] for f in skipped)
    health = client.get("/api/v1/health").json()
    assert health["status"] == "degraded"
    songs = next(c for c in health["components"] if c["name"] == "songs")
    assert songs["status"] == "fail"
    assert name in songs["error"]
    assert "1 songs, 1 broken" in songs["error"]


def test_hidden_song_is_logged_not_broken(client, settings, caplog):
    (settings.songs_dir / "demo" / "check.json").write_text(json.dumps({"pass": False}))
    assert client.get("/api/v1/songs").json() == []
    hidden = [rec.fields for rec in caplog.records if rec.getMessage() == "song_hidden"]
    assert hidden[0] == {"dir": "demo", "reason": "check_failed"}
    assert client.get("/api/v1/health").json()["status"] == "ok"
