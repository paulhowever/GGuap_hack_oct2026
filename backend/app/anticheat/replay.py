from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from app.f0.base import F0Engine, F0Track
from app.scoring.pitch import fold_cents, hz_to_midi

REPLAY_MAX_CENTS = 2.0
LAG_MIN_S = -0.2
LAG_MAX_S = 0.6
STEP_S = 0.005
MIN_JOINT = 100
SMOOTH_FRAMES = 41
TOP_LAGS = 3
SOURCES = ("guide", "minus")


def media_path(url: str | None, songs_dir: Path) -> Path | None:
    if not url or not url.startswith("/media/"):
        return None
    root = songs_dir.resolve()
    path = (root / url.removeprefix("/media/")).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


@lru_cache(maxsize=32)
def source_track(path: str, mtime_ns: int, engine: F0Engine) -> F0Track | None:
    try:
        data, sr = sf.read(path, dtype="float32", always_2d=True)
        if data.shape[0] == 0:
            return None
        return engine.track(data.mean(axis=1), int(sr))
    except (sf.SoundFileError, RuntimeError, ValueError, OSError):
        return None


def source_of(url: str | None, songs_dir: Path, engine: F0Engine) -> F0Track | None:
    try:
        path = media_path(url, songs_dir)
        if path is None:
            return None
        mtime_ns = path.stat().st_mtime_ns
    except (ValueError, OSError):
        return None
    return source_track(str(path), mtime_ns, engine)


def voiced_midi(track: F0Track, conf_min: float) -> np.ndarray:
    return hz_to_midi(np.where(track.conf >= conf_min, track.hz, 0.0))


def running_median(x: np.ndarray, size: int) -> np.ndarray:
    half = size // 2
    windows = np.lib.stride_tricks.sliding_window_view(np.pad(x, half, mode="edge"), size)
    return np.median(windows, axis=1)


def contour_gap(diff: np.ndarray) -> float:
    return float(np.median(np.abs(diff - running_median(diff, SMOOTH_FRAMES))))


def pitch_match(take: F0Track, wav_t0: float, source: F0Track, conf_min: float) -> float | None:
    if take.t.size < 2 or source.t.size < 2:
        return None
    t_take = wav_t0 + take.t
    grid = np.arange(t_take[0], t_take[-1], STEP_S)
    sung = np.interp(grid, t_take, voiced_midi(take, conf_min))
    played = voiced_midi(source, conf_min)

    def diff_at(lag: float) -> np.ndarray | None:
        other = np.interp(grid - lag, source.t, played, left=np.nan, right=np.nan)
        both = ~np.isnan(sung) & ~np.isnan(other)
        if both.sum() < MIN_JOINT:
            return None
        return fold_cents(100.0 * (sung[both] - other[both]))

    scored = []
    for lag in np.arange(LAG_MIN_S, LAG_MAX_S + STEP_S / 2, STEP_S):
        diff = diff_at(lag)
        if diff is not None:
            scored.append((float(np.median(np.abs(diff))), float(lag)))
    if not scored:
        return None
    return round(min(contour_gap(diff_at(lag)) for _, lag in sorted(scored)[:TOP_LAGS]), 2)


def replay_cents(
    take: F0Track, wav_t0: float, ref: dict, songs_dir: Path, engine: F0Engine, conf_min: float
) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for name in SOURCES:
        source = source_of(ref.get("audio", {}).get(name), songs_dir, engine)
        out[name] = pitch_match(take, wav_t0, source, conf_min) if source else None
    return out
