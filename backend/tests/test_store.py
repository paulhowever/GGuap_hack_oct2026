import asyncio
import sqlite3

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.main import create_app
from app.store.db import add_row, init_db, make_engine, ping
from app.store.models import Take


def test_roundtrip(tmp_path):
    async def go():
        engine = make_engine(tmp_path / "data")
        await init_db(engine)
        assert (await ping(engine)).count(".") == 2
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        await add_row(
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


OLD_TAKES = (
    "create table takes (id varchar(32) primary key, song_id varchar(64), client_id varchar(36), "
    "player varchar(24), difficulty varchar(8), total integer, grade varchar(2), result_json text, "
    "created_at datetime)"
)


def test_old_takes_schema_is_reset(settings, caplog):
    settings.data_dir.mkdir(parents=True)
    with sqlite3.connect(settings.data_dir / "app.db") as db:
        db.execute(OLD_TAKES)
        db.execute("create index ix_takes_board on takes (song_id, difficulty, total)")
        db.execute(
            "insert into takes values ('tk_old', 'demo', null, 'A', 'normal', 9000, 'S', '{}', '2026-10-14')"
        )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/songs").status_code == 200
        board = client.get("/api/v1/leaderboard/demo")
        assert board.status_code == 200
        assert board.json()["items"] == []
    resets = [r for r in caplog.records if r.getMessage() == "schema_reset"]
    assert [r.levelname for r in resets] == ["WARNING"]
    assert resets[0].fields == {"missing": ["audio_sha256", "integrity_status"]}


def test_current_schema_is_kept(settings, seed, client, caplog):
    seed("tk_1", 9000)
    with TestClient(create_app(settings)) as again:
        assert [i["take_id"] for i in again.get("/api/v1/leaderboard/demo").json()["items"]] == ["tk_1"]
    assert not [r for r in caplog.records if r.getMessage() == "schema_reset"]
