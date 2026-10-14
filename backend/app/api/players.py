import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.store.db import get_player, upsert_player

router = APIRouter(prefix="/api/v1")
CLIENT_ID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
AVATAR_MAX_BYTES = 4096


class PlayerIn(BaseModel):
    client_id: str = Field(pattern=CLIENT_ID)
    nickname: str = Field(min_length=1, max_length=24)
    avatar: dict[str, Any] = Field(default_factory=dict)

    @field_validator("nickname")
    @classmethod
    def strip_nickname(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty nickname")
        return value


def player_out(player) -> dict:
    return {"client_id": player.client_id, "nickname": player.nickname, "avatar": json.loads(player.avatar)}


@router.post("/players")
async def post_player(body: PlayerIn, request: Request) -> dict:
    avatar = json.dumps(body.avatar, ensure_ascii=False, separators=(",", ":"))
    if len(avatar.encode("utf-8")) > AVATAR_MAX_BYTES:
        raise HTTPException(status_code=422, detail="avatar_too_large")
    player = await upsert_player(request.app.state.sessions, body.client_id, body.nickname, avatar)
    return player_out(player)


@router.get("/players/{client_id}")
async def read_player(client_id: str, request: Request) -> dict:
    player = await get_player(request.app.state.sessions, client_id)
    if player is None:
        raise HTTPException(status_code=404, detail="player_not_found")
    return player_out(player)
