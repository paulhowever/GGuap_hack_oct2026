from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.anticheat.session import issue
from app.ids import CLIENT_ID_PATTERN, SONG_ID_PATTERN, Difficulty

router = APIRouter(prefix="/api/v1")


class SessionIn(BaseModel):
    song_id: str = Field(pattern=SONG_ID_PATTERN)
    client_id: str | None = Field(default=None, pattern=CLIENT_ID_PATTERN)
    difficulty: Difficulty = "normal"


@router.post("/sessions")
async def post_session(body: SessionIn, request: Request) -> dict:
    state = request.app.state
    if state.songs.get(body.song_id) is None:
        raise HTTPException(status_code=404, detail="song_not_found")
    return await issue(state.sessions, state.secret, body.song_id, body.client_id, body.difficulty)
