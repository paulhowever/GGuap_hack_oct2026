import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import ROOT, Settings
from app.main import create_app
from app.scoring.config import load_scoring_config


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
