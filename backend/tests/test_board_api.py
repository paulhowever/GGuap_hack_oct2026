import uuid


def cid():
    return str(uuid.uuid4())


def test_leaderboard_best_per_player(client, seed):
    c1, c2 = cid(), cid()
    client.post("/api/v1/players", json={"client_id": c1, "nickname": "Макс", "avatar": {"hat": 2}})
    seed("tk_a1", 8000, "Max", c1)
    seed("tk_a2", 9000, "Max", c1)
    seed("tk_b1", 9500, "Саня", c2)
    seed("tk_g1", 7000, "Гость")
    seed("tk_g2", 7100, "Гость")
    seed("tk_s1", 9999, "Читер", cid(), status="suspect")
    seed("tk_e1", 9900, "Изи", cid(), difficulty="easy")
    items = client.get("/api/v1/leaderboard/demo").json()["items"]
    assert [i["take_id"] for i in items] == ["tk_b1", "tk_a2", "tk_g2"]
    second = {k: v for k, v in items[1].items() if k != "at"}
    assert second == {
        "rank": 2,
        "client_id": c1,
        "player": "Макс",
        "avatar": {"hat": 2},
        "total": 9000,
        "grade": "S",
        "take_id": "tk_a2",
        "attempts": 2,
    }
    assert all(i["at"].endswith("+00:00") for i in items)
    assert items[2]["player"] == "Гость"
    assert items[2]["avatar"] is None
    assert items[2]["attempts"] == 2
    easy = client.get("/api/v1/leaderboard/demo", params={"difficulty": "easy"}).json()["items"]
    assert [i["take_id"] for i in easy] == ["tk_e1"]


def test_leaderboard_limit_and_errors(client, seed):
    for n in range(3):
        seed(f"tk_{n}", 9000 + n, f"P{n}", cid())
    assert len(client.get("/api/v1/leaderboard/demo", params={"limit": 2}).json()["items"]) == 2
    assert client.get("/api/v1/leaderboard/demo", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/leaderboard/demo", params={"difficulty": "insane"}).status_code == 422
    r = client.get("/api/v1/leaderboard/nope")
    assert r.status_code == 404
    assert r.json()["detail"] == "song_not_found"


def test_get_take_returns_stored_result(client, submit):
    body = submit().json()
    assert client.get(f"/api/v1/takes/{body['take_id']}").json() == body
    r = client.get("/api/v1/takes/tk_missing")
    assert r.status_code == 404
    assert r.json()["detail"] == "take_not_found"


def test_post_take_reports_placement(submit, seed):
    c = cid()
    first = submit(client_id=c).json()
    assert first["leaderboard"] == {"rank": 1, "of": 1, "personal_best": True}
    seed("tk_rival", 5000, "Саня", cid())
    second = submit(client_id=c, synth={"cents": 150}).json()
    assert second["leaderboard"] == {"rank": 1, "of": 2, "personal_best": False}


def test_songs_list_shows_top(client, seed):
    assert client.get("/api/v1/songs").json()[0]["top"] is None
    seed("tk_n", 9100, "Паша", cid())
    seed("tk_e", 9900, "Изи", cid(), difficulty="easy")
    seed("tk_s", 9999, "Читер", cid(), status="suspect")
    assert client.get("/api/v1/songs").json()[0]["top"] == {"player": "Паша", "total": 9100}
