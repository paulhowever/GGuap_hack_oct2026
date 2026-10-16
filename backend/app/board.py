import json
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.store.db import players_by_id
from app.store.models import Player, PublishedTake, Take


@dataclass(frozen=True)
class Entry:
    take_id: str
    client_id: str | None
    player: str
    total: int
    grade: str
    at: datetime
    # В таблицу идут только опубликованные дубли (ADR-024); по умолчанию True — для ручных списков.
    published: bool = True


def display_name(profile: Player | None, player: str) -> str:
    return profile.nickname if profile else player


def avatar_of(profile: Player | None) -> dict | None:
    return json.loads(profile.avatar) if profile else None


def bio_of(profile: Player | None) -> str:
    return (profile.bio or "") if profile else ""


def player_key(client_id: str | None, player: str) -> str:
    return client_id or f"name:{player}"


def iso(at: datetime) -> str:
    return (at if at.tzinfo else at.replace(tzinfo=UTC)).isoformat(timespec="seconds")


def order(e: Entry) -> tuple[int, datetime]:
    return -e.total, e.at


def best_published(entries: list[Entry]) -> dict[str, Entry]:
    """Строка игрока — его опубликованный дубль (если их несколько — лучший), в порядке таблицы."""
    best: dict[str, Entry] = {}
    for e in sorted((e for e in entries if e.published), key=order):
        best.setdefault(player_key(e.client_id, e.player), e)
    return best


def rank_entries(entries: list[Entry]) -> list[dict]:
    attempts = Counter(player_key(e.client_id, e.player) for e in entries)
    best = best_published(entries)
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
    """Все ok-дубли песни на сложности с пометкой публикации (для attempts нужны и неопубликованные)."""
    query = (
        select(
            Take.id,
            Take.client_id,
            Take.player,
            Take.total,
            Take.grade,
            Take.created_at,
            PublishedTake.take_id.is_not(None),
        )
        .outerjoin(PublishedTake, PublishedTake.take_id == Take.id)
        .where(Take.song_id == song_id, Take.difficulty == difficulty, Take.integrity_status == "ok")
    )
    async with sessions() as session:
        rows = (await session.execute(query)).all()
    return [Entry(*row[:6], published=bool(row[6])) for row in rows]


async def leaderboard(
    sessions: async_sessionmaker, song_id: str, difficulty: str, limit: int, client_id: str | None = None
) -> list[dict]:
    rows = rank_entries(await board_entries(sessions, song_id, difficulty))[:limit]
    profiles = await players_by_id(sessions, [r["client_id"] for r in rows if r["client_id"]])
    items = []
    for row in rows:
        profile = profiles.get(row["client_id"] or "")
        public = {key: value for key, value in row.items() if key != "client_id"}
        items.append(
            {
                **public,
                "player": display_name(profile, row["player"]),
                "avatar": avatar_of(profile),
                "bio": bio_of(profile),
                "me": client_id is not None and row["client_id"] == client_id,
            }
        )
    return items


async def display_names(sessions: async_sessionmaker, takes: list[Take]) -> dict[str, str]:
    profiles = await players_by_id(sessions, [t.client_id for t in takes if t.client_id])
    return {t.id: display_name(profiles.get(t.client_id), t.player) for t in takes}


async def placement(sessions: async_sessionmaker, take: Take) -> dict | None:
    """Место, которое дубль займёт, если его опубликовать (ADR-024): среди опубликованных строк
    других игроков. personal_best — лучший ли это ok-дубль игрока, опубликован он или нет."""
    entries = await board_entries(sessions, take.song_id, take.difficulty)
    key = player_key(take.client_id, take.player)
    mine = [e for e in entries if player_key(e.client_id, e.player) == key]
    this = next((e for e in mine if e.take_id == take.id), None)
    if this is None:
        return None
    others = best_published([e for e in entries if player_key(e.client_id, e.player) != key])
    ahead = sum(1 for e in others.values() if order(e) < order(this))
    return {
        "rank": ahead + 1,
        "of": len(others) + 1,
        "personal_best": min(mine, key=order).take_id == take.id,
    }
