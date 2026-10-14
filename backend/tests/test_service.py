import json
import logging

from fastapi.testclient import TestClient

from app.core.logging import JsonFormatter
from app.core.version import app_version
from app.main import create_app


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    assert r.headers["x-request-id"]


def test_request_id_is_propagated(client):
    assert client.get("/healthz", headers={"x-request-id": "rq42"}).headers["x-request-id"] == "rq42"


def test_version(client):
    body = client.get("/api/v1/version").json()
    assert body["app"] == app_version()
    assert body["git_sha"] == "abc1234"
    assert body["scoring"] == "score-v1"
    assert body["f0_engine"].startswith("swiftf0-")


def test_health_ok(client):
    r = client.get("/api/v1/health")
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "ok"
    names = {c["name"]: c for c in body["components"]}
    assert set(names) == {"db", "f0", "songs"}
    assert all(c["ms"] >= 0 for c in body["components"])
    assert names["songs"]["version"] == "1 songs"
    assert "fastapi" in body["libs"]


def test_health_degraded_without_songs(settings):
    settings.songs_dir = settings.songs_dir / "missing"
    with TestClient(create_app(settings)) as c:
        r = c.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "degraded"


def test_health_down_when_f0_breaks(client):
    class Broken:
        name = "broken"
        version = "0"

        def track(self, audio, sr):
            raise RuntimeError("model crashed")

    client.app.state.f0 = Broken()
    r = client.get("/api/v1/health")
    assert r.status_code == 503
    f0 = next(c for c in r.json()["components"] if c["name"] == "f0")
    assert f0["status"] == "fail"
    assert "model crashed" in f0["error"]


def test_json_formatter():
    rec = logging.LogRecord("x", logging.INFO, __file__, 1, "take_scored", None, None)
    rec.fields = {"total": 9100}
    out = json.loads(JsonFormatter().format(rec))
    assert out["msg"] == "take_scored"
    assert out["total"] == 9100
    assert out["level"] == "INFO"
