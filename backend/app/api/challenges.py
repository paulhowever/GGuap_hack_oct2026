from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.board import display_names
from app.duel import new_challenge_id, verdict
from app.ids import CHALLENGE_ID
from app.store.db import add_row, challenge_for_take, get_challenge, get_take, rival_takes
from app.store.models import Challenge, Take

router = APIRouter(prefix="/api/v1")
short = APIRouter()

MAX_ATTEMPTS = 3


class ChallengeIn(BaseModel):
    take_id: str = Field(min_length=1, max_length=32)


async def unused_id(sessions: async_sessionmaker) -> str:
    while True:
        challenge_id = new_challenge_id()
        if await get_challenge(sessions, challenge_id) is None:
            return challenge_id


async def create_challenge(sessions: async_sessionmaker, take: Take) -> Challenge:
    failure = None
    for _ in range(MAX_ATTEMPTS):
        challenge = Challenge(
            id=await unused_id(sessions), take_id=take.id, song_id=take.song_id, difficulty=take.difficulty
        )
        try:
            await add_row(sessions, challenge)
        except IntegrityError as error:
            existing = await challenge_for_take(sessions, take.id)
            if existing is not None:
                return existing
            failure = error
        else:
            return challenge
    raise failure


@router.post("/challenges")
async def post_challenge(body: ChallengeIn, request: Request) -> dict:
    sessions = request.app.state.sessions
    take = await get_take(sessions, body.take_id)
    if take is None:
        raise HTTPException(status_code=404, detail="take_not_found")
    challenge = await challenge_for_take(sessions, take.id)
    if challenge is None:
        if take.integrity_status != "ok":
            raise HTTPException(status_code=422, detail="challenge_take_not_ok")
        challenge = await create_challenge(sessions, take)
    s = request.app.state.settings
    base = s.public_url.rstrip("/") + "/" if s.public_url else str(request.base_url)
    return {"id": challenge.id, "url": f"{base}c/{challenge.id}"}


@router.get("/challenges/{challenge_id}")
async def read_challenge(challenge_id: str, request: Request) -> dict:
    sessions = request.app.state.sessions
    challenge = await get_challenge(sessions, challenge_id)
    if challenge is None:
        raise HTTPException(status_code=404, detail="challenge_not_found")
    owner = await get_take(sessions, challenge.take_id)
    rivals = await rival_takes(sessions, challenge.id)
    names = await display_names(sessions, [owner, *rivals])
    return {
        "id": challenge.id,
        "song_id": challenge.song_id,
        "difficulty": challenge.difficulty,
        "owner": {"player": names[owner.id], "total": owner.total, "take_id": owner.id},
        "rivals": [
            {
                "player": names[t.id],
                "total": t.total,
                "take_id": t.id,
                "verdict": verdict(t.total - owner.total),
            }
            for t in rivals
        ],
    }


@short.get("/c/{challenge_id}")
async def short_link(challenge_id: Annotated[str, Path(pattern=CHALLENGE_ID)]) -> RedirectResponse:
    return RedirectResponse(f"/?challenge={challenge_id}", status_code=302)
