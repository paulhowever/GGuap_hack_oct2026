import io
import json

import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.core.config import ROOT, Settings
from app.main import create_app
from app.scoring.config import load_scoring_config
from app.scoring.synth import synth_take
from app.store.db import save_take
from app.store.models import Take


@pytest.fixture(scope="session")
def demo_ref() -> dict:
    return json.loads((ROOT / "contracts" / "fixtures" / "demo.reference.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def cfg():
    return load_scoring_config(ROOT / "contracts" / "scoring.json")


@pytest.fixture
def settings(tmp_path, demo_ref) -> Settings:
    song = tmp_path / "songs" / "demo"
    song.mkdir(parents=True)
    (song / "reference.json").write_text(json.dumps(demo_ref, ensure_ascii=False), encoding="utf-8")
    return Settings(
        _env_file=None,
        pipeline_url=None,
        f0_engine="swiftf0",
        songs_dir=tmp_path / "songs",
        web_dir=None,
        data_dir=tmp_path / "data",
        scoring_path=ROOT / "contracts" / "scoring.json",
        git_sha="abc1234def",
    )


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as c:
        yield c


def wav_bytes(x, sr=16000) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, x, sr, format="WAV", subtype="PCM_16")
    return buf.getvalue()


@pytest.fixture
def submit(client, demo_ref):
    def go(synth=None, audio=None, **meta):
        m = {
            "song_id": "demo",
            "player": "Паша",
            "difficulty": "normal",
            "challenge_id": None,
            "wav_t0": 0.0,
            "wav_sr": 16000,
            "lag_ms": None,
            "frames": [],
            "client": {},
            **meta,
        }
        x = synth_take(demo_ref, **(synth or {})) if audio is None else audio
        files = {"audio": ("take.wav", wav_bytes(x), "audio/wav")}
        return client.post("/api/v1/takes", files=files, data={"meta": json.dumps(m, ensure_ascii=False)})

    return go


@pytest.fixture
def seed(client):
    def go(take_id, total, player="A", client_id=None, difficulty="normal", status="ok"):
        take = Take(
            id=take_id,
            song_id="demo",
            player=player,
            client_id=client_id,
            difficulty=difficulty,
            total=total,
            grade="S",
            integrity_status=status,
            result_json=json.dumps({"take_id": take_id}),
        )
        client.portal.call(save_take, client.app.state.sessions, take)
        return take

    return go
