from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.store.models import Base, Player, Take


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
