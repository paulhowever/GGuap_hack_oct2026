from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True)
class F0Track:
    t: np.ndarray
    hz: np.ndarray
    conf: np.ndarray
    rms: np.ndarray


class F0Engine(Protocol):
    name: str
    version: str

    def track(self, audio: np.ndarray, sr: int) -> F0Track: ...


def frame_rms(audio: np.ndarray, sr: int, times: np.ndarray, win_s: float = 0.032) -> np.ndarray:
    half = max(int(win_s * sr / 2), 1)
    x = np.asarray(audio, dtype=np.float64)
    out = np.zeros(times.size)
    for i, c in enumerate(np.round(times * sr).astype(int)):
        seg = x[max(c - half, 0) : c + half]
        if seg.size:
            out[i] = float(np.sqrt(np.mean(seg**2)))
    return out
