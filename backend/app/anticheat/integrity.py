FLAGS = ("no_session", "bad_session", "too_fast", "duplicate", "replay", "not_voice", "incomplete")
SUSPECT = frozenset({"bad_session", "too_fast", "duplicate", "replay", "not_voice"})
INCOMPLETE_SLACK_S = 0.5


def integrity_of(flags: list[str]) -> dict:
    found = [flag for flag in FLAGS if flag in flags]
    if SUSPECT.intersection(found):
        status = "suspect"
    elif "incomplete" in found:
        status = "incomplete"
    elif "no_session" in found:
        status = "unverified"
    else:
        status = "ok"
    return {"status": status, "flags": found}


def song_span(ref: dict) -> tuple[float, float]:
    stats = ref.get("stats") or {}
    notes = [note for line in ref["lines"] for note in line["notes"]]
    first = stats["first_note"] if "first_note" in stats else min(n["t"] for n in notes)
    last = stats["last_end"] if "last_end" in stats else max(n["t"] + n["d"] for n in notes)
    return float(first), float(last)


def completion_of(ref: dict, covered_end: float) -> tuple[dict, list[str]]:
    first, last = song_span(ref)
    ratio = 1.0 if last <= first else round(min(1.0, max(0.0, (covered_end - first) / (last - first))), 2)
    flags = ["incomplete"] if covered_end < last - INCOMPLETE_SLACK_S else []
    return {"ratio": ratio}, flags
