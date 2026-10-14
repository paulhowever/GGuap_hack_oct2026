import uuid

import pytest


def cid():
    return str(uuid.uuid4())


def test_create_and_get(client):
    c = cid()
    r = client.post(
        "/api/v1/players",
        json={"client_id": c, "nickname": "  Паша  ", "avatar": {"body": 2, "color": "#ff0"}},
    )
    assert r.status_code == 200
    assert r.json() == {"client_id": c, "nickname": "Паша", "avatar": {"body": 2, "color": "#ff0"}}
    assert client.get(f"/api/v1/players/{c}").json()["nickname"] == "Паша"


def test_upsert_updates(client):
    c = cid()
    client.post("/api/v1/players", json={"client_id": c, "nickname": "A"})
    r = client.post("/api/v1/players", json={"client_id": c, "nickname": "B", "avatar": {"hat": 1}})
    assert r.json()["nickname"] == "B"
    assert client.get(f"/api/v1/players/{c}").json()["avatar"] == {"hat": 1}


@pytest.mark.parametrize(
    ("client_id", "nickname"), [("not-a-uuid", "A"), (None, "   "), (None, "x" * 25), (None, "")]
)
def test_validation(client, client_id, nickname):
    body = {"client_id": client_id or cid(), "nickname": nickname}
    assert client.post("/api/v1/players", json=body).status_code == 422


def test_avatar_too_large(client):
    r = client.post(
        "/api/v1/players", json={"client_id": cid(), "nickname": "A", "avatar": {"blob": "x" * 5000}}
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "avatar_too_large"


def test_unknown_player(client):
    r = client.get(f"/api/v1/players/{cid()}")
    assert r.status_code == 404
    assert r.json()["detail"] == "player_not_found"
