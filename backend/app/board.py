import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.store.db import players_by_id
from app.store.models import Take


@dataclass(frozen=True)
class Entry:
    take_id: str
    client_id: str | None
    player: str
    total: int
    grade: str
    at: datetime


def player_key(client_id: str | None, player: str) -> str:
    return client_id or f"name:{player}"


def iso(at: datetime) -> str:
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).isoformat(timespec="seconds")


def rank_entries(entries: list[Entry]) -> list[dict]:
    best: dict[str, Entry] = {}
    attempts: Counter[str] = Counter()
    for e in sorted(entries, key=lambda e: (-e.total, e.at)):
        key = player_key(e.client_id, e.player)
        attempts[key] += 1
        best.setdefault(key, e)
    return [
        {
            "rank": rank,
            "client_id": e.client_id,
            "player": e.player,
            "total": e.total,
            "grade": e.grade,
            "take_id": e.take_id,
            "at": iso(e.at),
            "attempts": attempts[key],
        }
        for rank, (key, e) in enumerate(best.items(), start=1)
    ]


async def board_entries(sessions: async_sessionmaker, song_id: str, difficulty: str) -> list[Entry]:
    query = select(Take.id, Take.client_id, Take.player, Take.total, Take.grade, Take.created_at).where(
        Take.song_id == song_id, Take.difficulty == difficulty, Take.integrity_status == "ok"
    )
    async with sessions() as session:
        rows = (await session.execute(query)).all()
    return [Entry(*row) for row in rows]


async def leaderboard(sessions: async_sessionmaker, song_id: str, difficulty: str, limit: int) -> list[dict]:
    rows = rank_entries(await board_entries(sessions, song_id, difficulty))[:limit]
    profiles = await players_by_id(sessions, [r["client_id"] for r in rows if r["client_id"]])
    items = []
    for row in rows:
        profile = profiles.get(row["client_id"] or "")
        items.append(
            {
                **row,
                "player": profile.nickname if profile else row["player"],
                "avatar": json.loads(profile.avatar) if profile else None,
            }
        )
    return items


async def placement(sessions: async_sessionmaker, take: Take) -> dict | None:
    rows = rank_entries(await board_entries(sessions, take.song_id, take.difficulty))
    key = player_key(take.client_id, take.player)
    for row in rows:
        if player_key(row["client_id"], row["player"]) == key:
            return {"rank": row["rank"], "of": len(rows), "personal_best": row["take_id"] == take.id}
    return None
