import dataclasses
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.anticheat.replay import REPLAY_MAX_CENTS, replay_cents
from app.anticheat.voice import voice_stats
from app.f0.base import F0Engine, F0Track

METRIC_KEYS = ("replay_guide_c", "replay_minus_c", "jitter_c", "harm", "long_notes")
AUDIBLE_DB = 15.0


@dataclass(frozen=True)
class SignalCheck:
    flags: list[str]
    metrics: dict


def skipped_check() -> SignalCheck:
    return SignalCheck(flags=[], metrics=dict.fromkeys(METRIC_KEYS))


def audible(track: F0Track, conf_min: float) -> F0Track:
    voiced = (track.conf >= conf_min) & (track.hz > 0)
    if not voiced.any():
        return track
    loud = np.percentile(track.rms[voiced], 90)
    return dataclasses.replace(
        track, conf=np.where(track.rms >= loud * 10 ** (-AUDIBLE_DB / 20), track.conf, 0.0)
    )


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
    heard = audible(track, conf_min)
    voice = voice_stats(audio, sr, heard, ref, wav_t0, lag_ms / 1000.0, conf_min)
    replay = replay_cents(heard, wav_t0, ref, songs_dir, engine, conf_min)
    flags = []
    if any(c is not None and c < REPLAY_MAX_CENTS for c in replay.values()):
        flags.append("replay")
    if voice.not_voice:
        flags.append("not_voice")
    values = (replay["guide"], replay["minus"], voice.jitter_c, voice.harm, voice.notes)
    return SignalCheck(flags, dict(zip(METRIC_KEYS, values, strict=True)))
