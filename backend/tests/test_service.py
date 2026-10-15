import json
import logging

import pytest
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


def _boom_client(client):
    async def boom():
        raise RuntimeError("route exploded")

    client.app.add_api_route("/boom", boom)
    return TestClient(client.app, raise_server_exceptions=False)


def test_unhandled_error_keeps_request_id(client):
    r = _boom_client(client).get("/boom", headers={"x-request-id": "rq500"})
    assert r.status_code == 500
    assert r.text == "Internal Server Error"
    assert r.headers["x-request-id"] == "rq500"


def test_unhandled_error_is_logged_with_request_id(client, caplog):
    caplog.handler.setFormatter(JsonFormatter())
    _boom_client(client).get("/boom", headers={"x-request-id": "rq501"})
    lines = [json.loads(line) for line in caplog.text.splitlines() if line.startswith("{")]
    requests = [x for x in lines if x["msg"] == "request" and x["path"] == "/boom"]
    assert len(requests) == 1
    assert requests[0]["request_id"] == "rq501"
    assert requests[0]["status"] == 500
    assert requests[0]["level"] == "ERROR"
    assert "route exploded" in requests[0]["exc"]


@pytest.fixture
def web_client(settings, tmp_path):
    web = settings.web_dir = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>")
    (web / "app.js").write_text("export const A = 1;")
    with TestClient(create_app(settings)) as c:
        yield c


@pytest.mark.parametrize("path", ["/", "/index.html", "/app.js"])
def test_web_files_are_served_with_no_cache(web_client, path):
    r = web_client.get(path)
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-cache"


def test_web_conditional_request_stays_no_cache(web_client):
    etag = web_client.get("/app.js").headers["etag"]
    r = web_client.get("/app.js", headers={"if-none-match": etag})
    assert r.status_code == 304
    assert r.headers["cache-control"] == "no-cache"


def test_web_missing_file_is_404(web_client):
    assert web_client.get("/missing.js").status_code == 404


def test_api_and_media_are_not_forced_to_no_cache(web_client):
    assert "cache-control" not in web_client.get("/api/v1/version").headers
    assert "cache-control" not in web_client.get("/media/demo/reference.json").headers
