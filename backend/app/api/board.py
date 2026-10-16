from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request

from app.board import leaderboard
from app.ids import CLIENT_ID_PATTERN, Difficulty

router = APIRouter(prefix="/api/v1")


@router.get("/leaderboard/{song_id}")
async def get_leaderboard(
    song_id: str,
    request: Request,
    difficulty: Difficulty = "normal",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    client_id: Annotated[str | None, Query(pattern=CLIENT_ID_PATTERN)] = None,
) -> dict:
    if request.app.state.songs.get(song_id) is None:
        raise HTTPException(status_code=404, detail="song_not_found")
    return {"items": await leaderboard(request.app.state.sessions, song_id, difficulty, limit, client_id)}
