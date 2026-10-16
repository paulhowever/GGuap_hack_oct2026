from fastapi import APIRouter, HTTPException, Request

from app.board import leaderboard

router = APIRouter(prefix="/api/v1")
TOP_DIFFICULTY = "normal"


@router.get("/songs")
async def list_songs(request: Request) -> list[dict]:
    state = request.app.state
    items = state.songs.list()
    for item in items:
        best = await leaderboard(state.sessions, item["id"], TOP_DIFFICULTY, 1)
        item["top"] = {"player": best[0]["player"], "total": best[0]["total"]} if best else None
    return items


@router.get("/songs/{song_id}")
async def get_song(song_id: str, request: Request) -> dict:
    ref = request.app.state.songs.get(song_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="song_not_found")
    return {**ref, "status": "ready"}
