import asyncio
import io
import json
import logging
import secrets
import time
from typing import Annotated, Any, Literal

import numpy as np
import soundfile as sf
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.players import CLIENT_ID
from app.core.logging import log_event
from app.f0.frames import FramesEngine
from app.scoring.core import score_take
from app.store.db import save_take
from app.store.models import Take

router = APIRouter(prefix="/api/v1")
log = logging.getLogger("karaoke.takes")


class Frame(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    t: float
    hz: float
    conf: float
    rms: float


class TakeMeta(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    song_id: str = Field(pattern=r"^[a-z0-9_-]{1,64}$")
    client_id: str | None = Field(default=None, pattern=CLIENT_ID)
    player: str = Field(min_length=1, max_length=24)
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    challenge_id: str | None = None
    wav_t0: float
    wav_sr: int
    lag_ms: float | None = None
    frames: list[Frame] = Field(default_factory=list)
    client: dict[str, Any] = Field(default_factory=dict)


def decode_wav(raw: bytes) -> tuple[np.ndarray, int]:
    data, sr = sf.read(io.BytesIO(raw), dtype="float32", always_2d=True)
    return data.mean(axis=1), int(sr)


def evaluate(state, ref: dict, audio: np.ndarray, sr: int, m: TakeMeta) -> tuple[dict, dict]:
    t0 = time.perf_counter()
    track = state.f0.track(audio, sr)
    t1 = time.perf_counter()
    result = score_take(ref, track, m.wav_t0, state.scoring, m.difficulty, m.lag_ms)
    t2 = time.perf_counter()
    live_total = None
    if m.frames:
        frames = [f.model_dump() for f in m.frames]
        live = FramesEngine(frames, m.wav_t0, (m.lag_ms or 0.0) / 1000.0).track(audio, sr)
        live_total = score_take(ref, live, m.wav_t0, state.scoring, m.difficulty, m.lag_ms)["score"]["total"]
    timings = {"f0_ms": round((t1 - t0) * 1000, 1), "score_ms": round((t2 - t1) * 1000, 1)}
    result["score"]["live_total"] = live_total
    result["score"]["source"] = "final"
    return result, timings


@router.post("/takes")
async def post_take(
    request: Request, audio: Annotated[UploadFile, File()], meta: Annotated[str, Form()]
) -> dict:
    state = request.app.state
    try:
        m = TakeMeta.model_validate(json.loads(meta))
    except (ValueError, ValidationError):
        raise HTTPException(status_code=422, detail="bad_meta") from None
    ref = state.songs.get(m.song_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="song_not_found")
    if audio.size is not None and audio.size > int(state.settings.max_take_s * 48000 * 4) + 65536:
        raise HTTPException(status_code=413, detail="take_too_long")
    raw = await audio.read()
    try:
        samples, sr = await asyncio.to_thread(decode_wav, raw)
    except (sf.LibsndfileError, RuntimeError, ValueError):
        raise HTTPException(status_code=422, detail="bad_audio") from None
    if sr < 8000 or samples.size < max(sr // 10, 1):
        raise HTTPException(status_code=422, detail="bad_audio")
    if samples.size / sr > state.settings.max_take_s:
        raise HTTPException(status_code=413, detail="take_too_long")
    async with state.score_sem:
        try:
            result, timings = await asyncio.to_thread(evaluate, state, ref, samples, sr, m)
        except ValueError:
            raise HTTPException(status_code=422, detail="bad_audio") from None
    take_id = f"tk_{secrets.token_hex(4)}"
    takes_dir = state.settings.data_dir / "takes"
    takes_dir.mkdir(parents=True, exist_ok=True)
    await asyncio.to_thread((takes_dir / f"{take_id}.wav").write_bytes, raw)
    body = {
        "take_id": take_id,
        "song_id": m.song_id,
        "client_id": m.client_id,
        "player": m.player,
        "difficulty": m.difficulty,
        "engine": {"final": f"{state.f0.name}-{state.f0.version}", "live": "pitchy-mpm"},
        **result,
        "challenge": None,
        "leaderboard": None,
    }
    await save_take(
        state.sessions,
        Take(
            id=take_id,
            song_id=m.song_id,
            client_id=m.client_id,
            player=m.player,
            difficulty=m.difficulty,
            total=result["score"]["total"],
            grade=result["score"]["grade"],
            result_json=json.dumps(body, ensure_ascii=False),
        ),
    )
    log_event(
        log,
        "take_scored",
        take_id=take_id,
        song_id=m.song_id,
        client_id=m.client_id,
        difficulty=m.difficulty,
        dur_s=round(samples.size / sr, 2),
        lag_hint_ms=m.lag_ms,
        lag_est_ms=result["latency"]["estimated_ms"],
        lag_applied_ms=result["latency"]["applied_ms"],
        rho=result["latency"]["confidence"],
        total=result["score"]["total"],
        pitch_pct=result["score"]["pitch_pct"],
        rhythm_pct=result["score"]["rhythm_pct"],
        live_total=result["score"]["live_total"],
        f0_engine=state.f0.name,
        **timings,
    )
    return body
