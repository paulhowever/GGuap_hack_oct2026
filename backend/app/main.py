import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import async_sessionmaker
from starlette.responses import Response
from starlette.types import Scope

from app.api import board, challenges, health, players, published, sessions, songs, takes
from app.core.config import Settings, get_settings
from app.core.logging import RequestIdMiddleware, configure_logging, log_event
from app.core.version import app_version
from app.f0 import get_engine
from app.health import tone
from app.scoring.config import load_scoring_config
from app.songs import SongRepo
from app.store.db import init_db, make_engine

log = logging.getLogger("karaoke")


class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def load_secret(data_dir: Path) -> str:
    path = data_dir / "secret.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        stored = path.read_text(encoding="utf-8").strip()
        if stored:
            log_event(log, "secret_loaded", path=str(path))
            return stored
        path.unlink()
    secret = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(secret)
    log.warning("secret_generated", extra={"fields": {"hint": "set KARAOKE_SECRET", "path": str(path)}})
    return secret


@asynccontextmanager
async def lifespan(app: FastAPI):
    s: Settings = app.state.settings
    configure_logging(s.log_level)
    app.state.scoring = load_scoring_config(s.scoring_path)
    app.state.f0 = await asyncio.to_thread(get_engine, s.f0_engine)
    await asyncio.to_thread(app.state.f0.track, tone(1.0), 16000)
    app.state.db = make_engine(s.data_dir)
    await init_db(app.state.db)
    app.state.sessions = async_sessionmaker(app.state.db, expire_on_commit=False)
    app.state.songs = SongRepo(s.songs_dir)
    app.state.score_sem = asyncio.Semaphore(s.score_concurrency)
    app.state.secret = s.secret or load_secret(s.data_dir)
    log_event(
        log,
        "startup",
        version=app_version(),
        git_sha=s.git_sha,
        f0=app.state.f0.name,
        scoring=app.state.scoring.version,
        songs_dir=str(s.songs_dir),
    )
    yield
    await app.state.db.dispose()
    log_event(log, "shutdown")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="karaoke-backend", version=app_version(), lifespan=lifespan)
    app.state.settings = settings
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(health.api)
    app.include_router(songs.router)
    app.include_router(takes.router)
    app.include_router(players.router)
    app.include_router(board.router)
    app.include_router(challenges.router)
    app.include_router(challenges.short)
    app.include_router(sessions.router)
    app.include_router(published.router)
    if settings.songs_dir.is_dir():
        app.mount("/media", NoCacheStaticFiles(directory=settings.songs_dir), name="media")
    if settings.web_dir is not None and settings.web_dir.is_dir():
        app.mount("/", NoCacheStaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


app = create_app()
