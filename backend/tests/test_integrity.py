import pytest

from app.anticheat.integrity import integrity_of
from app.anticheat.session import make_token, token_hash, verify

CLIENT = "7b1e2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"


@pytest.mark.parametrize(
    ("flags", "status"),
    [
        ([], "ok"),
        (["no_session"], "unverified"),
        (["no_session", "duplicate"], "suspect"),
        (["too_fast"], "suspect"),
        (["not_voice", "bad_session"], "suspect"),
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


def test_token_roundtrip():
    token = make_token("k", "demo", CLIENT, "normal", 1_900_000_000_123, "ab12")
    assert verify("k", token, "demo", CLIENT, "normal") == pytest.approx(1_900_000_000.123)
    assert verify("other", token, "demo", CLIENT, "normal") is None
    assert verify("k", token, "demo", CLIENT, "hard") is None
    assert verify("k", token, "demo2", CLIENT, "normal") is None
    assert verify("k", token, "demo", None, "normal") is None
    assert verify("k", "garbage", "demo", CLIENT, "normal") is None
    assert verify("k", "x.y.z", "demo", CLIENT, "normal") is None
    assert len(token_hash(token)) == 64
