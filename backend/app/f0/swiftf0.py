from importlib.metadata import version

import numpy as np
from swift_f0 import SwiftF0

from app.f0.base import F0Track, frame_rms


class SwiftF0Engine:
    name = "swiftf0"

    def __init__(self, fmin: float = 65.0, fmax: float = 1400.0) -> None:
        self.version = version("swift-f0")
        self._fmin = fmin
        self._fmax = fmax
        self._model = SwiftF0(spin=False)

    def track(self, audio: np.ndarray, sr: int) -> F0Track:
        x = np.asarray(audio, dtype=np.float32)
        res = self._model.detect(x, sr, fmin=self._fmin, fmax=self._fmax)
        t = np.asarray(res.timestamps, dtype=float)
        hz = np.maximum(np.asarray(res.pitch_hz, dtype=float), 0.0)
        conf = np.asarray(res.confidence, dtype=float)
        return F0Track(t=t, hz=hz, conf=conf, rms=frame_rms(x, sr, t))
