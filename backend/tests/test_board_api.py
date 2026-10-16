import uuid

import pytest


def cid():
    return str(uuid.uuid4())


@pytest.fixture
def pub(seed):
    """Опубликованный дубль: в лидерборд идут только такие (ADR-024)."""

    def go(*args, **kwargs):
        return seed(*args, published=True, **kwargs)

    return go


def test_leaderboard_best_per_player(client, pub):
    c1, c2 = cid(), cid()
    client.post(
        "/api/v1/players", json={"client_id": c1, "nickname": "Макс", "avatar": {"hat": 2}, "bio": "Бас"}
    )
    pub("tk_a1", 8000, "Max", c1)
    pub("tk_a2", 9000, "Max", c1)
    pub("tk_b1", 9500, "Саня", c2)
    pub("tk_g1", 7000, "Гость")
    pub("tk_g2", 7100, "Гость")
    pub("tk_s1", 9999, "Читер", cid(), status="suspect")
    pub("tk_e1", 9900, "Изи", cid(), difficulty="easy")
    items = client.get("/api/v1/leaderboard/demo").json()["items"]
    assert [i["take_id"] for i in items] == ["tk_b1", "tk_a2", "tk_g2"]
    second = {k: v for k, v in items[1].items() if k != "at"}
    assert second == {
        "rank": 2,
        "me": False,
        "player": "Макс",
        "avatar": {"hat": 2},
        "bio": "Бас",
        "total": 9000,
        "grade": "S",
        "take_id": "tk_a2",
        "attempts": 2,
    }
    assert all("client_id" not in i and i["me"] is False for i in items)
    assert all(i["at"].endswith("+00:00") for i in items)
    assert items[2]["player"] == "Гость"
    assert items[2]["avatar"] is None
    assert items[2]["bio"] == ""
    assert items[2]["attempts"] == 2
    easy = client.get("/api/v1/leaderboard/demo", params={"difficulty": "easy"}).json()["items"]
    assert [i["take_id"] for i in easy] == ["tk_e1"]


def test_leaderboard_marks_my_row(client, pub):
    c1, c2 = cid(), cid()
    pub("tk_a", 9000, "Max", c1)
    pub("tk_b", 9500, "Саня", c2)
    pub("tk_g", 7000, "Гость")
    mine = client.get("/api/v1/leaderboard/demo", params={"client_id": c1}).json()["items"]
    assert [(i["take_id"], i["me"]) for i in mine] == [("tk_b", False), ("tk_a", True), ("tk_g", False)]
    assert all("client_id" not in i for i in mine)
    stranger = client.get("/api/v1/leaderboard/demo", params={"client_id": cid()}).json()["items"]
    assert [i["me"] for i in stranger] == [False, False, False]
    anonymous = client.get("/api/v1/leaderboard/demo").json()["items"]
    assert [i["me"] for i in anonymous] == [False, False, False]
    assert [i["rank"] for i in mine] == [i["rank"] for i in anonymous] == [1, 2, 3]


def test_leaderboard_rejects_bad_client_id(client):
    r = client.get("/api/v1/leaderboard/demo", params={"client_id": "nope"})
    assert r.status_code == 422


def test_leaderboard_limit_and_errors(client, pub):
    for n in range(3):
        pub(f"tk_{n}", 9000 + n, f"P{n}", cid())
    assert len(client.get("/api/v1/leaderboard/demo", params={"limit": 2}).json()["items"]) == 2
    assert client.get("/api/v1/leaderboard/demo", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/leaderboard/demo", params={"difficulty": "insane"}).status_code == 422
    r = client.get("/api/v1/leaderboard/nope")
    assert r.status_code == 404
    assert r.json()["detail"] == "song_not_found"


def test_get_take_returns_stored_result_without_client_id(client, submit):
    c = cid()
    body = submit(client_id=c).json()
    assert body["client_id"] == c
    stored = client.get(f"/api/v1/takes/{body['take_id']}").json()
    assert stored["client_id"] is None
    assert list(stored) == list(body)
    assert stored == {**body, "client_id": None}
    assert c not in client.get(f"/api/v1/takes/{body['take_id']}").text
    r = client.get("/api/v1/takes/tk_missing")
    assert r.status_code == 404
    assert r.json()["detail"] == "take_not_found"


def test_post_take_reports_placement(submit, seed, pub):
    c = cid()
    first = submit(client_id=c).json()
    assert first["leaderboard"] == {"rank": 1, "of": 1, "personal_best": True}
    pub("tk_rival", 100, "Саня", cid())
    second = submit(client_id=c, synth={"cents": 150}).json()
    assert second["leaderboard"] == {"rank": 1, "of": 2, "personal_best": False}
    # место считается для этого дубля среди опубликованных строк других игроков (ADR-024)
    pub("tk_top", 9999, "Топ", cid())
    seed("tk_hidden", 9998, "Тихий", cid())
    third = submit(client_id=c, synth={"cents": 120}).json()
    assert third["leaderboard"] == {"rank": 2, "of": 3, "personal_best": False}


def test_songs_list_shows_top(client, pub):
    assert client.get("/api/v1/songs").json()[0]["top"] is None
    pub("tk_n", 9100, "Паша", cid())
    pub("tk_e", 9900, "Изи", cid(), difficulty="easy")
    pub("tk_s", 9999, "Читер", cid(), status="suspect")
    assert client.get("/api/v1/songs").json()[0]["top"] == {"player": "Паша", "total": 9100}
