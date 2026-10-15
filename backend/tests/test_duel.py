import re

from app.duel import compare, new_challenge_id, verdict


def result(player, total, *line_scores):
    return {
        "player": player,
        "score": {"total": total},
        "lines": [{"i": i, "score": s} for i, s in enumerate(line_scores)],
    }


def test_new_challenge_id():
    ids = {new_challenge_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(re.fullmatch(r"[a-z0-9]{6}", i) for i in ids)


def test_verdict():
    assert verdict(1) == "win"
    assert verdict(-1) == "lose"
    assert verdict(0) == "draw"


def test_compare_counts_lines():
    out = compare("ab12cd", result("Макс", 7000, 90, 50, 70), result("Саня", 7500, 95, 40, 70))
    assert out == {
        "id": "ab12cd",
        "opponent": "Макс",
        "opponent_total": 7000,
        "delta": 500,
        "verdict": "win",
        "lines_won": 1,
        "lines_lost": 1,
    }
