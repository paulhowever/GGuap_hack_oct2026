import re

from fastapi.testclient import TestClient

from app.main import create_app


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
