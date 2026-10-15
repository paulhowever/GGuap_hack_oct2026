from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request

from app.api.players import CLIENT_ID
from app.board import leaderboard

router = APIRouter(prefix="/api/v1")


@router.get("/leaderboard/{song_id}")
async def get_leaderboard(
    song_id: str,
    request: Request,
    difficulty: Literal["easy", "normal", "hard"] = "normal",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    client_id: Annotated[str | None, Query(pattern=CLIENT_ID)] = None,
) -> dict:
    if request.app.state.songs.get(song_id) is None:
        raise HTTPException(status_code=404, detail="song_not_found")
    return {"items": await leaderboard(request.app.state.sessions, song_id, difficulty, limit, client_id)}
