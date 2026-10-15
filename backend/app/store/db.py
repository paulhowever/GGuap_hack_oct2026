from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, text, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.store.models import Base, Challenge, Player, Rival, Take


def make_engine(data_dir: Path) -> AsyncEngine:
    data_dir.mkdir(parents=True, exist_ok=True)
    return create_async_engine(f"sqlite+aiosqlite:///{data_dir / 'app.db'}")


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def ping(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        return str((await conn.execute(text("select sqlite_version()"))).scalar_one())


async def save_take(sessions: async_sessionmaker, take: Take) -> None:
    async with sessions() as session, session.begin():
        session.add(take)


async def upsert_player(sessions: async_sessionmaker, client_id: str, nickname: str, avatar: str) -> Player:
    stmt = insert(Player).values(client_id=client_id, nickname=nickname, avatar=avatar)
    stmt = stmt.on_conflict_do_update(
        index_elements=[Player.client_id],
        set_={"nickname": nickname, "avatar": avatar, "updated_at": datetime.now(UTC)},
    )
    async with sessions() as session, session.begin():
        await session.execute(stmt)
    async with sessions() as session:
        return await session.get(Player, client_id)


async def get_player(sessions: async_sessionmaker, client_id: str) -> Player | None:
    async with sessions() as session:
        return await session.get(Player, client_id)


async def get_take(sessions: async_sessionmaker, take_id: str) -> Take | None:
    async with sessions() as session:
        return await session.get(Take, take_id)


async def set_result_json(sessions: async_sessionmaker, take_id: str, result_json: str) -> None:
    async with sessions() as session, session.begin():
        await session.execute(update(Take).where(Take.id == take_id).values(result_json=result_json))


async def players_by_id(sessions: async_sessionmaker, client_ids: list[str]) -> dict[str, Player]:
    if not client_ids:
        return {}
    async with sessions() as session:
        rows = await session.execute(select(Player).where(Player.client_id.in_(client_ids)))
        return {p.client_id: p for p in rows.scalars()}


async def add_row(sessions: async_sessionmaker, row: Base) -> None:
    async with sessions() as session, session.begin():
        session.add(row)


async def get_challenge(sessions: async_sessionmaker, challenge_id: str) -> Challenge | None:
    async with sessions() as session:
        return await session.get(Challenge, challenge_id)


async def challenge_for_take(sessions: async_sessionmaker, take_id: str) -> Challenge | None:
    async with sessions() as session:
        rows = await session.execute(select(Challenge).where(Challenge.take_id == take_id))
        return rows.scalar_one_or_none()


async def rival_takes(sessions: async_sessionmaker, challenge_id: str) -> list[Take]:
    query = (
        select(Take)
        .join(Rival, Rival.take_id == Take.id)
        .where(Rival.challenge_id == challenge_id)
        .order_by(Take.total.desc(), Take.created_at)
    )
    async with sessions() as session:
        return list((await session.execute(query)).scalars())
