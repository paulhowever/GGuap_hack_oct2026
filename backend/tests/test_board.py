from datetime import datetime

from app.board import Entry, player_key, rank_entries


def entry(take_id, total, client_id=None, player="A", minute=0, published=True):
    return Entry(take_id, client_id, player, total, "S", datetime(2026, 10, 17, 12, minute), published)


def test_player_key():
    assert player_key("c1", "Паша") == "c1"
    assert player_key(None, "Паша") == "name:Паша"


def test_best_take_per_player_and_attempts():
    rows = rank_entries(
        [
            entry("t1", 8000, "c1"),
            entry("t2", 9000, "c1", minute=1),
            entry("t3", 9500, "c2", player="B"),
            entry("t4", 7000, None, "Гость"),
            entry("t5", 7100, None, "Гость", minute=2),
        ]
    )
    assert [r["take_id"] for r in rows] == ["t3", "t2", "t5"]
    assert [r["rank"] for r in rows] == [1, 2, 3]
    assert [r["attempts"] for r in rows] == [1, 2, 2]
    assert rows[0]["at"] == "2026-10-17T12:00:00+00:00"


def test_tie_goes_to_earlier_take():
    rows = rank_entries([entry("late", 9000, "c1", minute=5), entry("early", 9000, "c2", minute=1)])
    assert [r["take_id"] for r in rows] == ["early", "late"]


def test_same_player_tie_keeps_first_take():
    rows = rank_entries([entry("second", 9000, "c1", minute=5), entry("first", 9000, "c1", minute=1)])
    assert [r["take_id"] for r in rows] == ["first"]
    assert rows[0]["attempts"] == 2


def test_empty_board():
    assert rank_entries([]) == []
