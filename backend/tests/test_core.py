import tomllib
from pathlib import Path

from app.core.config import ROOT, Settings
from app.core.version import app_version


def test_version_matches_pyproject():
    data = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    assert app_version() == data["project"]["version"]


def test_settings_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("KARAOKE_SONGS_DIR", str(tmp_path))
    monkeypatch.setenv("KARAOKE_SCORE_CONCURRENCY", "3")
    s = Settings()
    assert s.songs_dir == tmp_path
    assert s.score_concurrency == 3


def test_settings_defaults_point_into_repo():
    s = Settings()
    assert s.scoring_path == ROOT / "contracts" / "scoring.json"
    assert isinstance(s.songs_dir, Path)
