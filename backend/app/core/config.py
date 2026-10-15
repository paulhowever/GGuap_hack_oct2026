from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KARAOKE_", env_file=".env", extra="ignore")

    songs_dir: Path = ROOT / "songs"
    web_dir: Path | None = ROOT / "web"
    data_dir: Path = ROOT / "data"
    scoring_path: Path = ROOT / "contracts" / "scoring.json"
    f0_engine: str = "swiftf0"
    pipeline_url: str | None = None
    max_take_s: float = 60.0
    score_concurrency: int = 2
    log_level: str = "INFO"
    git_sha: str = "dev"


@lru_cache
def get_settings() -> Settings:
    return Settings()
