import asyncio
import platform
import time
import urllib.request
from importlib.metadata import version

import numpy as np

from app.store.db import ping

TIMEOUT_S = 2.0
LIBS = ("fastapi", "numpy", "scipy", "swift-f0", "sqlalchemy", "aiosqlite", "uvicorn")


def tone(seconds: float = 0.25, sr: int = 16000) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return (0.3 * np.sin(2 * np.pi * 220.0 * t)).astype(np.float32)


async def timed(name: str, critical: bool, coro) -> dict:
    start = time.perf_counter()
    try:
        ver = await asyncio.wait_for(coro, TIMEOUT_S)
        status, error = "ok", None
    except Exception as exc:
        ver, status, error = None, "fail", f"{type(exc).__name__}: {exc}"
    ms = round((time.perf_counter() - start) * 1000, 1)
    return {"name": name, "status": status, "version": ver, "ms": ms, "critical": critical, "error": error}


async def check_f0(engine) -> str:
    await asyncio.to_thread(engine.track, tone(), 16000)
    return f"{engine.name}-{engine.version}"


async def check_songs(repo) -> str:
    n = await asyncio.to_thread(repo.count)
    if repo.skipped:
        raise RuntimeError(f"{n} songs, {len(repo.skipped)} broken: {', '.join(repo.skipped)}")
    return f"{n} songs"


async def check_pipeline(url: str) -> str:
    def call() -> str:
        with urllib.request.urlopen(url, timeout=TIMEOUT_S) as r:
            return f"http {r.status}"

    return await asyncio.to_thread(call)


async def run_checks(state) -> tuple[str, list[dict]]:
    jobs = [
        timed("db", True, ping(state.db)),
        timed("f0", True, check_f0(state.f0)),
        timed("songs", False, check_songs(state.songs)),
    ]
    if state.settings.pipeline_url:
        jobs.append(timed("pipeline", False, check_pipeline(state.settings.pipeline_url)))
    components = list(await asyncio.gather(*jobs))
    if any(c["critical"] and c["status"] != "ok" for c in components):
        return "down", components
    if any(c["status"] != "ok" for c in components):
        return "degraded", components
    return "ok", components


def libs() -> dict:
    out = {"python": platform.python_version()}
    for name in LIBS:
        out[name] = version(name)
    return out
