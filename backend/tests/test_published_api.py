import uuid

import pytest

from app.store.published import add_published

KEYS = [
    "take_id",
    "song_id",
    "difficulty",
    "player",
    "avatar",
    "bio",
    "total",
    "grade",
    "at",
    "published_at",
    "offset_s",
    "offset_source",
    "audio",
    "minus",
]


def cid():
    return str(uuid.uuid4())


@pytest.fixture
def owner(client):
    c = cid()
    client.post(
        "/api/v1/players", json={"client_id": c, "nickname": "Макс", "avatar": {"hat": 2}, "bio": "Пою басом"}
    )
    return c


@pytest.fixture
def take(submit, owner):
    body = submit(client_id=owner).json()
    assert body["integrity"]["status"] == "ok"
    return body


@pytest.fixture
def publish(client):
    def go(take_id, client_id, wav_t0=None):
        return client.post(
            "/api/v1/published", json={"take_id": take_id, "client_id": client_id, "wav_t0": wav_t0}
        )

    return go


@pytest.fixture
def wav_file(settings):
    def go(take_id, data=b"RIFF-fake-wav"):
        takes_dir = settings.data_dir / "takes"
        takes_dir.mkdir(parents=True, exist_ok=True)
        (takes_dir / f"{take_id}.wav").write_bytes(data)

    return go


def test_publish_own_ok_take(client, publish, take, owner):
    r = publish(take["take_id"], owner, 0.25)
    assert r.status_code == 200
    item = r.json()
    assert list(item) == KEYS
    assert "client_id" not in item
    assert owner not in r.text
    applied = take["latency"]["applied_ms"]
    assert item["take_id"] == take["take_id"]
    assert item["song_id"] == "demo"
    assert item["difficulty"] == "normal"
    assert item["player"] == "Макс"
    assert item["avatar"] == {"hat": 2}
    assert item["bio"] == "Пою басом"
    assert item["total"] == take["score"]["total"]
    assert item["grade"] == take["score"]["grade"]
    assert item["at"].endswith("+00:00")
    assert item["published_at"].endswith("+00:00")
    assert item["offset_s"] == round(0.25 - applied / 1000, 3)
    assert item["offset_source"] == "measured"
    assert item["audio"] == f"/api/v1/published/{take['take_id']}/audio"
    assert item["minus"] == "/media/demo/minus.mp3"


def test_publish_is_idempotent(client, publish, take, owner):
    first = publish(take["take_id"], owner, 0.25).json()
    again = publish(take["take_id"], owner, 1.0)
    assert again.status_code == 200
    assert again.json() == first


def test_publish_default_offset(publish, take, owner):
    item = publish(take["take_id"], owner).json()
    assert item["offset_s"] == round(-0.15 - take["latency"]["applied_ms"] / 1000, 3)
    assert item["offset_source"] == "default"


def test_publish_rejects_foreign_and_guest(submit, publish, take):
    r = publish(take["take_id"], cid())
    assert r.status_code == 403
    assert r.json()["detail"] == "not_owner"
    guest = submit().json()
    r = publish(guest["take_id"], cid())
    assert r.status_code == 403
    assert r.json()["detail"] == "not_owner"


def test_publish_rejects_not_ok(submit, publish, partial, owner):
    unverified = submit(client_id=owner, session=False).json()
    assert unverified["integrity"]["status"] == "unverified"
    incomplete = submit(client_id=owner, audio=partial()).json()
    assert incomplete["integrity"]["status"] == "incomplete"
    for body in (unverified, incomplete):
        r = publish(body["take_id"], owner)
        assert r.status_code == 422
        assert r.json()["detail"] == "take_not_ok"


def test_publish_unknown_and_traversal(client, publish, owner):
    for take_id in ("tk_missing", "../x", "%2e%2e"):
        r = publish(take_id, owner)
        assert r.status_code == 404
        assert r.json()["detail"] == "take_not_found"
    for path in ("/api/v1/published/%2e%2e/audio", "/api/v1/published/..%2Fsecret.key/audio"):
        r = client.get(path)
        assert r.status_code == 404


def test_publish_validates_body(client, publish, take, owner):
    for r in (
        publish(take["take_id"], "nope"),
        publish(take["take_id"], owner, 9.0),
        publish("", owner),
        publish("x" * 33, owner),
    ):
        assert r.status_code == 422
        assert r.json()["detail"] == "bad_body"
    assert client.post("/api/v1/published", json=[1]).status_code == 422
    r = client.post(
        "/api/v1/published",
        content=f'{{"take_id": "{take["take_id"]}", "client_id": "{owner}", "wav_t0": NaN}}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "bad_body"
    assert client.get(f"/api/v1/published/{take['take_id']}").status_code == 404


def test_seed_take_without_wav(publish, seed, owner):
    seed("tk_seed", 9000, client_id=owner)
    r = publish("tk_seed", owner)
    assert r.status_code == 404
    assert r.json()["detail"] == "audio_not_found"


def test_seed_take_without_latency_uses_zero(publish, seed, wav_file, owner):
    seed("tk_seed", 9000, client_id=owner)
    wav_file("tk_seed")
    r = publish("tk_seed", owner, 0.1)
    assert r.status_code == 200
    assert r.json()["offset_s"] == 0.1
    assert r.json()["player"] == "Макс"


def test_audio_only_after_publish(client, settings, publish, take, owner):
    url = f"/api/v1/published/{take['take_id']}/audio"
    r = client.get(url)
    assert r.status_code == 404
    assert r.json()["detail"] == "not_published"
    publish(take["take_id"], owner)
    r = client.get(url)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    raw = (settings.data_dir / "takes" / f"{take['take_id']}.wav").read_bytes()
    assert r.content == raw
    part = client.get(url, headers={"Range": "bytes=0-99"})
    assert part.status_code == 206
    assert part.content == raw[:100]
    assert part.headers["content-range"] == f"bytes 0-99/{len(raw)}"


def test_audio_missing_file_after_publish(client, settings, publish, take, owner):
    publish(take["take_id"], owner)
    (settings.data_dir / "takes" / f"{take['take_id']}.wav").unlink()
    r = client.get(f"/api/v1/published/{take['take_id']}/audio")
    assert r.status_code == 404
    assert r.json()["detail"] == "not_published"


def test_get_published_item(client, publish, take, owner):
    r = client.get(f"/api/v1/published/{take['take_id']}")
    assert r.status_code == 404
    assert r.json()["detail"] == "not_published"
    item = publish(take["take_id"], owner, 0.2).json()
    r = client.get(f"/api/v1/published/{take['take_id']}")
    assert r.status_code == 200
    assert r.json() == item
    assert owner not in r.text
    assert client.get("/api/v1/published/tk_missing").status_code == 404


def test_item_without_song_has_no_minus(client, settings, publish, take, owner):
    publish(take["take_id"], owner)
    (settings.songs_dir / "demo" / "reference.json").unlink()
    r = client.get(f"/api/v1/published/{take['take_id']}")
    assert r.status_code == 200
    assert r.json()["minus"] is None


def test_list_filters_and_sorts(client, seed, wav_file, publish):
    c1, c2, c3 = cid(), cid(), cid()
    client.post("/api/v1/players", json={"client_id": c1, "nickname": "Макс", "avatar": {}})
    seed("tk_low", 7000, "Max", c1)
    seed("tk_high", 9500, "Саня", c2)
    seed("tk_mid", 8000, "Гость", c3)
    seed("tk_easy", 9900, "Изи", c1, difficulty="easy")
    seed("tk_sus", 9999, "Читер", cid(), status="suspect")
    seed("tk_hidden", 9800, "Тихий", c3)
    for take_id, owner in (("tk_low", c1), ("tk_high", c2), ("tk_mid", c3), ("tk_easy", c1)):
        wav_file(take_id)
        assert publish(take_id, owner).status_code == 200
    wav_file("tk_hidden")
    client.portal.call(add_published, client.app.state.sessions, "tk_sus", None)
    r = client.get("/api/v1/published", params={"song_id": "demo"})
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["take_id"] for i in items] == ["tk_high", "tk_mid", "tk_low"]
    assert items[2]["player"] == "Макс"
    assert items[1]["player"] == "Гость"
    assert all(list(i) == KEYS for i in items)
    for c in (c1, c2, c3):
        assert c not in r.text
    easy = client.get("/api/v1/published", params={"song_id": "demo", "difficulty": "easy"}).json()
    assert [i["take_id"] for i in easy["items"]] == ["tk_easy"]
    limited = client.get("/api/v1/published", params={"song_id": "demo", "limit": 1}).json()
    assert [i["take_id"] for i in limited["items"]] == ["tk_high"]
    assert client.get("/api/v1/published/tk_sus").status_code == 404
    assert client.get("/api/v1/published/tk_sus/audio").status_code == 404


def test_list_errors(client):
    r = client.get("/api/v1/published", params={"song_id": "nope"})
    assert r.status_code == 404
    assert r.json()["detail"] == "song_not_found"
    assert client.get("/api/v1/published").status_code == 422
    assert client.get("/api/v1/published", params={"song_id": "demo", "limit": 0}).status_code == 422
    assert client.get("/api/v1/published", params={"song_id": "demo", "limit": 101}).status_code == 422
    assert client.get("/api/v1/published", params={"song_id": "demo", "difficulty": "x"}).status_code == 422
    assert client.get("/api/v1/published", params={"song_id": "demo"}).json() == {"items": []}


def test_remove(client, settings, publish, take, owner):
    take_id = take["take_id"]
    publish(take_id, owner)
    r = client.post(f"/api/v1/published/{take_id}/remove", json={"client_id": cid()})
    assert r.status_code == 403
    assert r.json()["detail"] == "not_owner"
    r = client.post(f"/api/v1/published/{take_id}/remove", json={"client_id": owner})
    assert r.status_code == 200
    assert r.json() == {"take_id": take_id, "published": False}
    assert client.get(f"/api/v1/published/{take_id}").status_code == 404
    assert client.get(f"/api/v1/published/{take_id}/audio").status_code == 404
    assert client.get("/api/v1/published", params={"song_id": "demo"}).json() == {"items": []}
    assert client.get(f"/api/v1/takes/{take_id}").status_code == 200
    assert (settings.data_dir / "takes" / f"{take_id}.wav").exists()
    r = client.post(f"/api/v1/published/{take_id}/remove", json={"client_id": owner})
    assert r.status_code == 404
    assert r.json()["detail"] == "not_published"
    assert client.post(f"/api/v1/published/{take_id}/remove", json={"client_id": "nope"}).status_code == 422
    assert publish(take_id, owner).status_code == 200


def test_publish_leaves_duel_unchanged_and_fills_board(client, submit, publish, owner):
    own = submit(client_id=owner, player="Макс", synth={"mute_lines": frozenset({1})}).json()
    challenge = client.post("/api/v1/challenges", json={"take_id": own["take_id"]}).json()
    rival_owner = cid()
    rival = submit(client_id=rival_owner, player="Саня", challenge_id=challenge["id"]).json()
    urls = [
        f"/api/v1/takes/{own['take_id']}",
        f"/api/v1/takes/{rival['take_id']}",
        f"/api/v1/challenges/{challenge['id']}",
    ]
    before = [client.get(u).content for u in urls]
    board = "/api/v1/leaderboard/demo"
    assert client.get(board).json()["items"] == []
    assert publish(own["take_id"], owner, 0.1).status_code == 200
    assert publish(rival["take_id"], rival_owner).status_code == 200
    assert [client.get(u).content for u in urls] == before
    rows = client.get(board).json()["items"]
    assert [r["take_id"] for r in rows] == [rival["take_id"], own["take_id"]]
    assert list(rows[0]) == [
        "rank",
        "player",
        "total",
        "grade",
        "take_id",
        "at",
        "attempts",
        "avatar",
        "bio",
        "me",
    ]
    client.post(f"/api/v1/published/{own['take_id']}/remove", json={"client_id": owner})
    assert [client.get(u).content for u in urls] == before
    assert [r["take_id"] for r in client.get(board).json()["items"]] == [rival["take_id"]]


def test_publishing_another_take_replaces_the_previous_one(client, submit, publish, owner):
    first = submit(client_id=owner).json()
    second = submit(client_id=owner, synth={"cents": 150}).json()
    assert second["score"]["total"] < first["score"]["total"]
    assert publish(first["take_id"], owner).status_code == 200
    assert publish(second["take_id"], owner).status_code == 200
    assert client.get(f"/api/v1/published/{first['take_id']}").status_code == 404
    rows = client.get("/api/v1/leaderboard/demo").json()["items"]
    assert [(r["take_id"], r["attempts"]) for r in rows] == [(second["take_id"], 2)]
    listed = client.get("/api/v1/published", params={"song_id": "demo"}).json()["items"]
    assert [i["take_id"] for i in listed] == [second["take_id"]]
