import asyncio
import re

import httpx2
from fastapi.testclient import TestClient

from app.api import challenges
from app.main import create_app
from app.store.db import save_take
from app.store.models import Take


def make_challenge(client, submit):
    owner = submit(player="Макс", synth={"mute_lines": frozenset({1})}).json()
    return owner, client.post("/api/v1/challenges", json={"take_id": owner["take_id"]})


def test_create_challenge_is_idempotent(client, submit):
    owner, r = make_challenge(client, submit)
    assert r.status_code == 200
    body = r.json()
    assert re.fullmatch(r"[a-z0-9]{6}", body["id"])
    assert body["url"] == f"http://testserver/c/{body['id']}"
    assert client.post("/api/v1/challenges", json={"take_id": owner["take_id"]}).json() == body


def test_concurrent_create_returns_same_challenge(settings):
    async def go():
        app = create_app(settings)
        async with app.router.lifespan_context(app):
            take = Take(
                id="tk_race",
                song_id="demo",
                player="Макс",
                difficulty="normal",
                total=7000,
                grade="A",
                result_json="{}",
            )
            await save_take(app.state.sessions, take)
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url="http://testserver"
            ) as ac:
                return await asyncio.gather(
                    *(ac.post("/api/v1/challenges", json={"take_id": "tk_race"}) for _ in range(6))
                )

    responses = asyncio.run(go())
    assert [r.status_code for r in responses] == [200] * 6
    assert len({r.json()["id"] for r in responses}) == 1


def test_id_collision_is_retried(client, submit, monkeypatch):
    _, first = make_challenge(client, submit)
    taken = first.json()["id"]
    other = submit(player="Саня").json()
    ids = iter([taken, taken, "fresh1"])

    async def fake_unused_id(sessions):
        return next(ids)

    monkeypatch.setattr(challenges, "unused_id", fake_unused_id)
    r = client.post("/api/v1/challenges", json={"take_id": other["take_id"]})
    assert r.status_code == 200
    assert r.json()["id"] == "fresh1"


def test_id_collision_gives_up_after_three_attempts(client, submit, monkeypatch):
    _, first = make_challenge(client, submit)
    taken = first.json()["id"]
    other = submit(player="Саня").json()
    calls = []

    async def fake_unused_id(sessions):
        calls.append(taken)
        return taken

    monkeypatch.setattr(challenges, "unused_id", fake_unused_id)
    r = client.post("/api/v1/challenges", json={"take_id": other["take_id"]})
    assert r.status_code == 500
    assert len(calls) == 3


def test_unknown_take(client):
    r = client.post("/api/v1/challenges", json={"take_id": "tk_missing"})
    assert r.status_code == 404
    assert r.json()["detail"] == "take_not_found"


def test_short_link_redirects(client):
    r = client.get("/c/ab12cd", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/?challenge=ab12cd"
    assert client.get("/c/toolong1", follow_redirects=False).status_code == 422


def test_short_link_wins_over_static_web(settings, tmp_path):
    settings.web_dir = tmp_path / "web"
    settings.web_dir.mkdir()
    (settings.web_dir / "index.html").write_text("<html></html>")
    with TestClient(create_app(settings)) as c:
        assert c.get("/c/ab12cd", follow_redirects=False).status_code == 302
        assert c.get("/").status_code == 200


def test_rival_take_is_compared_with_owner(client, submit):
    owner, r = make_challenge(client, submit)
    cid = r.json()["id"]
    rival = submit(player="Саня", challenge_id=cid).json()
    duel = rival["challenge"]
    assert duel["id"] == cid
    assert duel["opponent"] == "Макс"
    assert duel["opponent_total"] == owner["score"]["total"]
    assert duel["delta"] == rival["score"]["total"] - owner["score"]["total"] > 0
    assert duel["verdict"] == "win"
    assert duel["lines_won"] == 1
    assert duel["lines_lost"] == 0
    assert client.get(f"/api/v1/takes/{rival['take_id']}").json()["challenge"] == duel
    view = client.get(f"/api/v1/challenges/{cid}").json()
    assert (view["id"], view["song_id"], view["difficulty"]) == (cid, "demo", "normal")
    assert view["owner"] == {"player": "Макс", "total": owner["score"]["total"], "take_id": owner["take_id"]}
    assert view["rivals"] == [
        {"player": "Саня", "total": rival["score"]["total"], "take_id": rival["take_id"], "verdict": "win"}
    ]


def test_challenge_errors(client, submit):
    _, r = make_challenge(client, submit)
    cid = r.json()["id"]
    missing = submit(challenge_id="zzzzzz")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "challenge_not_found"
    wrong = submit(challenge_id=cid, difficulty="easy")
    assert wrong.status_code == 422
    assert wrong.json()["detail"] == "challenge_difficulty"
    r = client.get("/api/v1/challenges/zzzzzz")
    assert r.status_code == 404
    assert r.json()["detail"] == "challenge_not_found"


def test_only_ok_rivals_are_listed(client, submit, partial):
    owner, r = make_challenge(client, submit)
    cid = r.json()["id"]
    ok = submit(player="Саня", challenge_id=cid).json()
    flat = submit(player="Вася", challenge_id=cid, synth={"jitter_cents": 0.0}).json()
    early = submit(player="Петя", challenge_id=cid, audio=partial()).json()
    unsigned = submit(player="Коля", challenge_id=cid, session=False, synth={"cents": 20}).json()
    assert flat["integrity"]["status"] == "suspect"
    assert early["integrity"]["status"] == "incomplete"
    assert unsigned["integrity"]["status"] == "unverified"
    for body in (flat, early, unsigned):
        assert body["challenge"]["id"] == cid
        assert body["challenge"]["opponent"] == "Макс"
    view = client.get(f"/api/v1/challenges/{cid}").json()
    assert [t["take_id"] for t in view["rivals"]] == [ok["take_id"]]
    assert view["owner"]["take_id"] == owner["take_id"]
