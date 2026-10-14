from dataclasses import dataclass

import numpy as np

from app.f0.base import F0Track
from app.scoring.config import ScoringConfig
from app.scoring.pitch import hz_to_midi
from app.scoring.synth import iter_notes

GRID_S = 0.01
PITCHED = frozenset({"normal", "golden"})


@dataclass(frozen=True)
class Grid:
    t: np.ndarray
    voiced: np.ndarray
    midi: np.ndarray


def song_duration(ref: dict) -> float:
    last_end = max(n["t"] + n["d"] for _, n in iter_notes(ref))
    return max(float(ref["audio"]["duration"]), last_end + 1.0)


def shifted(a: np.ndarray, steps: int, fill) -> np.ndarray:
    out = np.full_like(a, fill)
    n = a.size
    if steps >= n or -steps >= n:
        return out
    if steps >= 0:
        out[: n - steps] = a[steps:]
    else:
        out[-steps:] = a[: n + steps]
    return out


def to_grid(track: F0Track, wav_t0: float, duration: float, cfg: ScoringConfig) -> Grid:
    t = np.round(np.arange(0.0, duration, GRID_S), 3)
    if track.t.size < 2:
        return Grid(t, np.zeros(t.size, dtype=bool), np.full(t.size, np.nan))
    ts = wav_t0 + track.t
    rms_db = 20.0 * np.log10(np.maximum(track.rms, 1e-9))
    ok = (track.conf >= cfg.conf_min) & (track.hz > 0) & (rms_db > cfg.rms_gate_db)
    idx = np.clip(np.searchsorted(ts, t), 1, ts.size - 1)
    left = idx - 1
    nearest = np.where(np.abs(ts[left] - t) <= np.abs(ts[idx] - t), left, idx)
    voiced = (np.abs(ts[nearest] - t) <= 0.02) & ok[nearest]
    midi = np.where(voiced, hz_to_midi(track.hz)[nearest], np.nan)
    return Grid(t, voiced, midi)


def ref_arrays(ref: dict, t: np.ndarray, cfg: ScoringConfig) -> tuple[np.ndarray, np.ndarray]:
    mask = np.zeros(t.size, dtype=bool)
    midi = np.full(t.size, np.nan)
    for _, note in iter_notes(ref):
        inside = (t >= note["t"]) & (t < note["t"] + note["d"])
        if cfg.mult.get(note["type"], 0.0) > 0:
            mask |= inside
        if note["type"] in PITCHED:
            midi[inside] = note["midi"]
    return mask, midi
