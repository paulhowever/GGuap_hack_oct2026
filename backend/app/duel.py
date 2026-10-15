import secrets

ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
ID_LEN = 6
CHALLENGE_ID = rf"^[a-z0-9]{{{ID_LEN}}}$"


def new_challenge_id() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(ID_LEN))


def verdict(delta: int) -> str:
    if delta > 0:
        return "win"
    return "lose" if delta < 0 else "draw"


def compare(challenge_id: str, owner: dict, mine: dict) -> dict:
    theirs = {line["i"]: line["score"] for line in owner["lines"]}
    won = sum(1 for line in mine["lines"] if line["score"] > theirs.get(line["i"], 0))
    lost = sum(1 for line in mine["lines"] if line["score"] < theirs.get(line["i"], 0))
    delta = mine["score"]["total"] - owner["score"]["total"]
    return {
        "id": challenge_id,
        "opponent": owner["player"],
        "opponent_total": owner["score"]["total"],
        "delta": delta,
        "verdict": verdict(delta),
        "lines_won": won,
        "lines_lost": lost,
    }
