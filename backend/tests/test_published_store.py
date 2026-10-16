import asyncio

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.store.db import add_row, init_db, make_engine
from app.store.models import Base, Challenge, Take
from app.store.published import add_published, get_published, published_for_song, remove_published


def tables_of(conn) -> set[str]:
    return set(inspect(conn).get_table_names())


def test_init_db_adds_published_table_and_keeps_rows(tmp_path):
    async def go():
        engine = make_engine(tmp_path / "data")
        old = [t for name, t in Base.metadata.tables.items() if name != "published_takes"]
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=old))
            before = await conn.run_sync(tables_of)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        await add_row(
            sessions,
            Take(
                id="tk_1",
                song_id="demo",
                player="A",
                difficulty="normal",
                total=9000,
                grade="S",
                result_json="{}",
            ),
        )
        await add_row(sessions, Challenge(id="abc123", take_id="tk_1", song_id="demo", difficulty="normal"))
        await init_db(engine)
        async with engine.connect() as conn:
            after = await conn.run_sync(tables_of)
        async with sessions() as s:
            takes = (await s.execute(select(Take.id))).scalars().all()
            challenges = (await s.execute(select(Challenge.id))).scalars().all()
        await engine.dispose()
        return before, after, takes, challenges

    before, after, takes, challenges = asyncio.run(go())
    assert "published_takes" not in before
    assert after == before | {"published_takes"}
    assert takes == ["tk_1"]
    assert challenges == ["abc123"]


def test_published_store_roundtrip(tmp_path):
    async def go():
        engine = make_engine(tmp_path / "data")
        await init_db(engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        for take_id, total, status in (("tk_a", 7000, "ok"), ("tk_b", 9000, "ok"), ("tk_c", 9999, "suspect")):
            take = Take(
                id=take_id,
                song_id="demo",
                player="A",
                difficulty="normal",
                total=total,
                grade="S",
                integrity_status=status,
                result_json="{}",
            )
            await add_row(sessions, take)
        first = await add_published(sessions, "tk_a", 0.2)
        again = await add_published(sessions, "tk_a", 1.5)
        await add_published(sessions, "tk_b", None)
        await add_published(sessions, "tk_c", None)
        rows = await published_for_song(sessions, "demo", "normal", 10)
        removed = await remove_published(sessions, "tk_a")
        missing = await remove_published(sessions, "tk_a")
        gone = await get_published(sessions, "tk_a")
        await engine.dispose()
        return first, again, rows, removed, missing, gone

    first, again, rows, removed, missing, gone = asyncio.run(go())
    assert first.wav_t0 == 0.2
    assert again.wav_t0 == 0.2
    assert again.published_at == first.published_at
    assert [(take.id, pub.take_id) for pub, take in rows] == [("tk_b", "tk_b"), ("tk_a", "tk_a")]
    assert removed is True
    assert missing is False
    assert gone is None
