import json
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.board import avatar_of, bio_of, display_name, iso
from app.ids import CLIENT_ID_PATTERN, Difficulty
from app.store.db import get_take, players_by_id
from app.store.models import PublishedTake, Take
from app.store.published import add_published, get_published, published_for_song, remove_published

router = APIRouter(prefix="/api/v1")
DEFAULT_WAV_T0 = -0.15


class PublishIn(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    take_id: str = Field(min_length=1, max_length=32)
    client_id: str = Field(pattern=CLIENT_ID_PATTERN)
    wav_t0: float | None = Field(default=None, ge=-5, le=5)


class RemoveIn(BaseModel):
    client_id: str = Field(pattern=CLIENT_ID_PATTERN)


def applied_ms(take: Take) -> float:
    try:
        result = json.loads(take.result_json)
    except ValueError:
        return 0.0
    latency = result.get("latency") if isinstance(result, dict) else None
    value = latency.get("applied_ms") if isinstance(latency, dict) else None
    return float(value) if isinstance(value, int | float) else 0.0


def minus_of(request: Request, song_id: str) -> str | None:
    ref = request.app.state.songs.get(song_id)
    return ref.get("audio", {}).get("minus") if ref else None


def wav_path(request: Request, take: Take) -> Path | None:
    takes_dir = (request.app.state.settings.data_dir / "takes").resolve()
    path = (takes_dir / f"{take.id}.wav").resolve()
    return path if path.parent == takes_dir and path.is_file() else None


async def items_of(request: Request, rows: list[tuple[PublishedTake, Take]]) -> list[dict]:
    profiles = await players_by_id(request.app.state.sessions, [t.client_id for _, t in rows if t.client_id])
    minus: dict[str, str | None] = {}
    items = []
    for pub, take in rows:
        if take.song_id not in minus:
            minus[take.song_id] = minus_of(request, take.song_id)
        profile = profiles.get(take.client_id or "")
        t0 = pub.wav_t0 if pub.wav_t0 is not None else DEFAULT_WAV_T0
        items.append(
            {
                "take_id": take.id,
                "song_id": take.song_id,
                "difficulty": take.difficulty,
                "player": display_name(profile, take.player),
                "avatar": avatar_of(profile),
                "bio": bio_of(profile),
                "total": take.total,
                "grade": take.grade,
                "at": iso(take.created_at),
                "published_at": iso(pub.published_at),
                "offset_s": round(t0 - applied_ms(take) / 1000, 3),
                "offset_source": "measured" if pub.wav_t0 is not None else "default",
                "audio": f"/api/v1/published/{take.id}/audio",
                "minus": minus[take.song_id],
            }
        )
    return items


async def published_take(request: Request, take_id: str) -> tuple[PublishedTake, Take]:
    sessions = request.app.state.sessions
    pub = await get_published(sessions, take_id)
    take = await get_take(sessions, take_id) if pub else None
    if pub is None or take is None or take.integrity_status != "ok":
        raise HTTPException(status_code=404, detail="not_published")
    return pub, take


@router.post("/published")
async def publish(payload: Annotated[dict[str, Any], Body()], request: Request) -> dict:
    try:
        body = PublishIn.model_validate(payload)
    except ValidationError:
        raise HTTPException(status_code=422, detail="bad_body") from None
    sessions = request.app.state.sessions
    take = await get_take(sessions, body.take_id)
    if take is None:
        raise HTTPException(status_code=404, detail="take_not_found")
    if take.client_id is None or take.client_id != body.client_id:
        raise HTTPException(status_code=403, detail="not_owner")
    if take.integrity_status != "ok":
        raise HTTPException(status_code=422, detail="take_not_ok")
    if wav_path(request, take) is None:
        raise HTTPException(status_code=404, detail="audio_not_found")
    pub = await add_published(sessions, take.id, body.wav_t0)
    return (await items_of(request, [(pub, take)]))[0]


@router.post("/published/{take_id}/remove")
async def unpublish(take_id: str, body: RemoveIn, request: Request) -> dict:
    sessions = request.app.state.sessions
    pub = await get_published(sessions, take_id)
    take = await get_take(sessions, take_id) if pub else None
    if pub is None or take is None:
        raise HTTPException(status_code=404, detail="not_published")
    if take.client_id is None or take.client_id != body.client_id:
        raise HTTPException(status_code=403, detail="not_owner")
    await remove_published(sessions, take_id)
    return {"take_id": take_id, "published": False}


@router.get("/published")
async def list_published(
    request: Request,
    song_id: str,
    difficulty: Difficulty = "normal",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict:
    if request.app.state.songs.get(song_id) is None:
        raise HTTPException(status_code=404, detail="song_not_found")
    rows = await published_for_song(request.app.state.sessions, song_id, difficulty, limit)
    return {"items": await items_of(request, rows)}


@router.get("/published/{take_id}")
async def read_published(take_id: str, request: Request) -> dict:
    pub, take = await published_take(request, take_id)
    return (await items_of(request, [(pub, take)]))[0]


@router.get("/published/{take_id}/audio")
async def published_audio(take_id: str, request: Request) -> FileResponse:
    _, take = await published_take(request, take_id)
    path = wav_path(request, take)
    if path is None:
        raise HTTPException(status_code=404, detail="not_published")
    return FileResponse(path, media_type="audio/wav")
