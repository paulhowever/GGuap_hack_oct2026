from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.store.models import PublishedTake, Take


async def add_published(sessions: async_sessionmaker, take_id: str, wav_t0: float | None) -> PublishedTake:
    stmt = insert(PublishedTake).values(take_id=take_id, wav_t0=wav_t0, published_at=datetime.now(UTC))
    async with sessions() as session, session.begin():
        await session.execute(stmt.on_conflict_do_nothing(index_elements=[PublishedTake.take_id]))
    async with sessions() as session:
        return await session.get(PublishedTake, take_id)


async def get_published(sessions: async_sessionmaker, take_id: str) -> PublishedTake | None:
    async with sessions() as session:
        return await session.get(PublishedTake, take_id)


async def remove_published(sessions: async_sessionmaker, take_id: str) -> bool:
    async with sessions() as session, session.begin():
        result = await session.execute(delete(PublishedTake).where(PublishedTake.take_id == take_id))
        return result.rowcount == 1


async def published_for_song(
    sessions: async_sessionmaker, song_id: str, difficulty: str, limit: int
) -> list[tuple[PublishedTake, Take]]:
    query = (
        select(PublishedTake, Take)
        .join(Take, Take.id == PublishedTake.take_id)
        .where(Take.song_id == song_id, Take.difficulty == difficulty, Take.integrity_status == "ok")
        .order_by(Take.total.desc(), PublishedTake.published_at)
        .limit(limit)
    )
    async with sessions() as session:
        return [(pub, take) for pub, take in (await session.execute(query)).all()]
