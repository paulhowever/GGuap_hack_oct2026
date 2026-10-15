import json


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
