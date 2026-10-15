import pytest

from app.anticheat.integrity import completion_of, integrity_of
from app.anticheat.session import make_token, token_hash, verify

CLIENT = "7b1e2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
NONCE = "ab12cd34ef567890"


@pytest.mark.parametrize(
    ("flags", "status"),
    [
        ([], "ok"),
        (["no_session"], "unverified"),
        (["no_session", "duplicate"], "suspect"),
        (["too_fast"], "suspect"),
        (["not_voice", "bad_session"], "suspect"),
        (["incomplete"], "incomplete"),
        (["no_session", "incomplete"], "incomplete"),
        (["incomplete", "replay"], "suspect"),
        (["incomplete", "too_fast"], "suspect"),
    ],
)
def test_integrity_status(flags, status):
    assert integrity_of(flags)["status"] == status


def test_integrity_flags_are_ordered():
    assert integrity_of(["not_voice", "duplicate", "no_session"])["flags"] == [
        "no_session",
        "duplicate",
        "not_voice",
    ]


def test_integrity_flags_put_incomplete_last():
    assert integrity_of(["incomplete", "not_voice", "no_session"])["flags"] == [
        "no_session",
        "not_voice",
        "incomplete",
    ]


@pytest.mark.parametrize(
    ("covered_end", "ratio", "flags"),
    [
        (12.0, 1.0, []),
        (8.9, 1.0, []),
        (8.4, 1.0, []),
        (8.39, 0.92, ["incomplete"]),
        (7.4, 0.76, ["incomplete"]),
        (7.2, 0.73, ["incomplete"]),
        (2.5, 0.0, ["incomplete"]),
        (-1.0, 0.0, ["incomplete"]),
        (100.0, 1.0, []),
    ],
)
def test_completion(demo_ref, covered_end, ratio, flags):
    assert completion_of(demo_ref, covered_end) == ({"ratio": ratio}, flags)


def test_completion_falls_back_to_notes_without_stats(demo_ref):
    ref = {**demo_ref, "stats": {}}
    assert completion_of(ref, 7.2) == ({"ratio": 0.73}, ["incomplete"])
    assert completion_of(ref, 8.4) == ({"ratio": 1.0}, [])
    assert completion_of({k: v for k, v in demo_ref.items() if k != "stats"}, 7.2) == (
        {"ratio": 0.73},
        ["incomplete"],
    )


def test_completion_prefers_stats_over_notes(demo_ref):
    ref = {**demo_ref, "stats": {**demo_ref["stats"], "first_note": 0.0, "last_end": 10.0}}
    assert completion_of(ref, 5.0) == ({"ratio": 0.5}, ["incomplete"])


def test_completion_of_incomplete_take_never_reaches_one(demo_ref):
    ref = {**demo_ref, "stats": {**demo_ref["stats"], "first_note": 0.0, "last_end": 1000.0}}
    assert completion_of(ref, 999.0) == ({"ratio": 0.99}, ["incomplete"])
    assert completion_of(ref, 999.5) == ({"ratio": 1.0}, [])


def test_completion_of_degenerate_span(demo_ref):
    ref = {**demo_ref, "stats": {**demo_ref["stats"], "first_note": 5.0, "last_end": 5.0}}
    assert completion_of(ref, 1.0) == ({"ratio": 0.99}, ["incomplete"])
    assert completion_of(ref, 4.5) == ({"ratio": 1.0}, [])


def test_token_roundtrip():
    token = make_token("k", "demo", CLIENT, "normal", 1_900_000_000_123, NONCE)
    assert verify("k", token, "demo", CLIENT, "normal") == pytest.approx(1_900_000_000.123)
    assert verify("other", token, "demo", CLIENT, "normal") is None
    assert verify("k", token, "demo", CLIENT, "hard") is None
    assert verify("k", token, "demo2", CLIENT, "normal") is None
    assert verify("k", token, "demo", None, "normal") is None
    assert verify("k", "garbage", "demo", CLIENT, "normal") is None
    assert verify("k", "x.y.z", "demo", CLIENT, "normal") is None
    assert verify("k", "1.a.é", "demo", CLIENT, "normal") is None
    assert verify("k", "0" + token, "demo", CLIENT, "normal") is None
    assert len(token_hash(token)) == 64


def test_malformed_tokens_are_rejected():
    token = make_token("k", "demo", CLIENT, "normal", 1_900_000_000_123, NONCE)
    issued, nonce, signature = token.split(".")
    malformed = [
        f"+{issued}.{nonce}.{signature}",
        f" {issued}.{nonce}.{signature}",
        f"{issued[:3]}_{issued[3:]}.{nonce}.{signature}",
        f"٣{issued[1:]}.{nonce}.{signature}",
        f"{issued}.{nonce.upper()}.{signature}",
        f"{issued}.{nonce[:-1]}.{signature}",
        f"{issued}.{nonce}.{signature.upper()}",
        f"{issued}.{nonce}.{signature[:-1]}",
        f"{issued}.{nonce}.{signature}\n",
        f"{issued}.{nonce}.{signature}.x",
        f"{issued}.{nonce}.{signature[:-1]}é",
        "",
    ]
    for bad in malformed:
        assert verify("k", bad, "demo", CLIENT, "normal") is None
