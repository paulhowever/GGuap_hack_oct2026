from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/api/v1")


@router.get("/songs")
async def list_songs(request: Request) -> list[dict]:
    return request.app.state.songs.list()


@router.get("/songs/{song_id}")
async def get_song(song_id: str, request: Request) -> dict:
    ref = request.app.state.songs.get(song_id)
    if ref is None:
        raise HTTPException(status_code=404, detail="song_not_found")
    return {**ref, "status": "ready"}
