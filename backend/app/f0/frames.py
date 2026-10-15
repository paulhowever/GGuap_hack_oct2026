import numpy as np

from app.f0.base import F0Track


class FramesEngine:
    name = "frames"
    version = "client"

    def __init__(self, frames: list[dict], wav_t0: float, lag_s: float) -> None:
        self._frames = frames
        self._wav_t0 = wav_t0
        self._lag_s = lag_s

    def track(self, audio: np.ndarray, sr: int) -> F0Track:
        if not self._frames:
            empty = np.zeros(0)
            return F0Track(empty, empty, empty, empty)
        t = np.array([f["t"] for f in self._frames], dtype=float) + self._lag_s - self._wav_t0
        hz = np.array([f["hz"] for f in self._frames], dtype=float)
        conf = np.array([f["conf"] for f in self._frames], dtype=float)
        rms = np.array([f["rms"] for f in self._frames], dtype=float)
        return F0Track(t=t, hz=hz, conf=conf, rms=rms)
