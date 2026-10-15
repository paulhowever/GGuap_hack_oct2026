FLAGS = ("no_session", "bad_session", "too_fast", "duplicate", "replay", "not_voice")
SUSPECT = frozenset(FLAGS[1:])


def integrity_of(flags: list[str]) -> dict:
    found = [flag for flag in FLAGS if flag in flags]
    if SUSPECT.intersection(found):
        status = "suspect"
    elif found:
        status = "unverified"
    else:
        status = "ok"
    return {"status": status, "flags": found}
