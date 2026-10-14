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
