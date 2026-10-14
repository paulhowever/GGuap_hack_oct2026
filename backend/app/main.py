import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api import health
from app.core.config import Settings, get_settings
from app.core.logging import RequestIdMiddleware, configure_logging, log_event
from app.core.version import app_version
from app.f0 import get_engine
from app.health import tone
from app.scoring.config import load_scoring_config
from app.songs import SongRepo
from app.store.db import init_db, make_engine

log = logging.getLogger("karaoke")


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
    if settings.songs_dir.is_dir():
        app.mount("/media", StaticFiles(directory=settings.songs_dir), name="media")
    if settings.web_dir is not None and settings.web_dir.is_dir():
        app.mount("/", StaticFiles(directory=settings.web_dir, html=True), name="web")
    return app


app = create_app()
