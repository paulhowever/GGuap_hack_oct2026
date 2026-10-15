import hashlib
import hmac
import re
import secrets
import time

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.store.db import add_row, consume_session
from app.store.models import GameSession

SESSION_TTL_S = 900
TOO_FAST_SLACK_S = 2.0
TOKEN_PATTERN = re.compile(r"([1-9][0-9]{0,15})\.([0-9a-f]{16})\.([0-9a-f]{64})")


def now() -> float:
    return time.time()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def sign(
    secret: str, song_id: str, client_id: str | None, difficulty: str, issued_ms: int, nonce: str
) -> str:
    message = "|".join((song_id, client_id or "-", difficulty, str(issued_ms), nonce))
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def make_token(
    secret: str, song_id: str, client_id: str | None, difficulty: str, issued_ms: int, nonce: str
) -> str:
    return f"{issued_ms}.{nonce}.{sign(secret, song_id, client_id, difficulty, issued_ms, nonce)}"


def verify(secret: str, token: str, song_id: str, client_id: str | None, difficulty: str) -> float | None:
    match = TOKEN_PATTERN.fullmatch(token)
    if match is None:
        return None
    issued_ms = int(match[1])
    expected = sign(secret, song_id, client_id, difficulty, issued_ms, match[2])
    if not hmac.compare_digest(match[3], expected):
        return None
    return issued_ms / 1000.0


async def issue(
    sessions: async_sessionmaker, secret: str, song_id: str, client_id: str | None, difficulty: str
) -> dict:
    issued_ms = round(now() * 1000)
    token = make_token(secret, song_id, client_id, difficulty, issued_ms, secrets.token_hex(8))
    row = GameSession(
        token_hash=token_hash(token),
        song_id=song_id,
        client_id=client_id,
        difficulty=difficulty,
        issued_at=issued_ms / 1000.0,
    )
    await add_row(sessions, row)
    return {"token": token, "issued_at": issued_ms / 1000.0, "expires_in": SESSION_TTL_S}


async def session_flags(
    sessions: async_sessionmaker,
    secret: str,
    token: str | None,
    song_id: str,
    client_id: str | None,
    difficulty: str,
    duration: float,
) -> list[str]:
    if not token:
        return ["no_session"]
    issued_at = verify(secret, token, song_id, client_id, difficulty)
    t = now()
    if issued_at is None or t > issued_at + SESSION_TTL_S:
        return ["bad_session"]
    if not await consume_session(sessions, token_hash(token), t):
        return ["bad_session"]
    if t < issued_at + duration - TOO_FAST_SLACK_S:
        return ["too_fast"]
    return []
