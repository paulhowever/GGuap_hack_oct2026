import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import inspect, select, text, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.store.models import Base, Challenge, GameSession, Player, Rival, Take

log = logging.getLogger("karaoke.store")
TAKE_COLUMNS = frozenset({"integrity_status", "audio_sha256"})


def make_engine(data_dir: Path) -> AsyncEngine:
    data_dir.mkdir(parents=True, exist_ok=True)
    return create_async_engine(f"sqlite+aiosqlite:///{data_dir / 'app.db'}")


def missing_take_columns(conn) -> list[str]:
    inspector = inspect(conn)
    if not inspector.has_table("takes"):
        return []
    return sorted(TAKE_COLUMNS - {column["name"] for column in inspector.get_columns("takes")})


async def init_db(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        missing = await conn.run_sync(missing_take_columns)
        if missing:
            log.warning("schema_reset", extra={"fields": {"missing": missing}})
            await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


async def ping(engine: AsyncEngine) -> str:
    async with engine.connect() as conn:
        return str((await conn.execute(text("select sqlite_version()"))).scalar_one())


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


async def get_row[Row: Base](sessions: async_sessionmaker, model: type[Row], pk: str) -> Row | None:
    async with sessions() as session:
        return await session.get(model, pk)


async def get_player(sessions: async_sessionmaker, client_id: str) -> Player | None:
    return await get_row(sessions, Player, client_id)


async def get_take(sessions: async_sessionmaker, take_id: str) -> Take | None:
    return await get_row(sessions, Take, take_id)


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
    return await get_row(sessions, Challenge, challenge_id)


async def challenge_for_take(sessions: async_sessionmaker, take_id: str) -> Challenge | None:
    async with sessions() as session:
        rows = await session.execute(select(Challenge).where(Challenge.take_id == take_id))
        return rows.scalar_one_or_none()


async def rival_takes(sessions: async_sessionmaker, challenge_id: str) -> list[Take]:
    query = (
        select(Take)
        .join(Rival, Rival.take_id == Take.id)
        .where(Rival.challenge_id == challenge_id, Take.integrity_status == "ok")
        .order_by(Take.total.desc(), Take.created_at)
    )
    async with sessions() as session:
        return list((await session.execute(query)).scalars())


async def consume_session(sessions: async_sessionmaker, token_hash: str, used_at: float) -> bool:
    query = (
        update(GameSession)
        .where(GameSession.token_hash == token_hash, GameSession.used_at.is_(None))
        .values(used_at=used_at)
    )
    async with sessions() as session, session.begin():
        return (await session.execute(query)).rowcount == 1


async def sha_seen(sessions: async_sessionmaker, sha: str) -> bool:
    async with sessions() as session:
        rows = await session.execute(select(Take.id).where(Take.audio_sha256 == sha).limit(1))
        return rows.first() is not None
