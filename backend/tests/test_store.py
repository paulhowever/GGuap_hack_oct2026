import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.store.db import init_db, make_engine, ping, save_take
from app.store.models import Take


def test_roundtrip(tmp_path):
    async def go():
        engine = make_engine(tmp_path / "data")
        await init_db(engine)
        assert (await ping(engine)).count(".") == 2
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        await save_take(
            sessions,
            Take(
                id="tk_1",
                song_id="demo",
                player="Паша",
                difficulty="normal",
                total=9100,
                grade="S",
                result_json="{}",
            ),
        )
        async with sessions() as s:
            row = (await s.execute(select(Take))).scalar_one()
        await engine.dispose()
        return row

    row = asyncio.run(go())
    assert row.player == "Паша"
    assert row.created_at is not None
    assert (tmp_path / "data" / "app.db").exists()


def test_concurrent_upsert_single_row(tmp_path):
    from app.store.db import upsert_player
    from app.store.models import Player

    async def go():
        engine = make_engine(tmp_path / "data")
        await init_db(engine)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        cid = "11111111-1111-4111-8111-111111111111"
        await asyncio.gather(upsert_player(sessions, cid, "A", "{}"), upsert_player(sessions, cid, "B", "{}"))
        async with sessions() as s:
            rows = (await s.execute(select(Player))).scalars().all()
        await engine.dispose()
        return rows

    rows = asyncio.run(go())
    assert len(rows) == 1
    assert rows[0].nickname in {"A", "B"}
