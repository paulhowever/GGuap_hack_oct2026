from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.anticheat.replay import REPLAY_MAX_CENTS, replay_cents
from app.anticheat.voice import voice_stats
from app.f0.base import F0Engine, F0Track

METRIC_KEYS = ("replay_guide_c", "replay_minus_c", "jitter_c", "harm", "long_notes")


@dataclass(frozen=True)
class SignalCheck:
    flags: list[str]
    metrics: dict


def skipped_check() -> SignalCheck:
    return SignalCheck(flags=[], metrics=dict.fromkeys(METRIC_KEYS))


def check_signal(
    audio: np.ndarray,
    sr: int,
    track: F0Track,
    ref: dict,
    wav_t0: float,
    lag_ms: float,
    songs_dir: Path,
    engine: F0Engine,
    conf_min: float,
) -> SignalCheck:
    voice = voice_stats(audio, sr, track, ref, wav_t0, lag_ms / 1000.0, conf_min)
    replay = replay_cents(track, wav_t0, ref, songs_dir, engine, conf_min)
    flags = []
    if any(c is not None and c < REPLAY_MAX_CENTS for c in replay.values()):
        flags.append("replay")
    if voice.not_voice:
        flags.append("not_voice")
    metrics = {
        "replay_guide_c": replay["guide"],
        "replay_minus_c": replay["minus"],
        "jitter_c": voice.jitter_c,
        "harm": voice.harm,
        "long_notes": voice.notes,
    }
    return SignalCheck(flags, metrics)
