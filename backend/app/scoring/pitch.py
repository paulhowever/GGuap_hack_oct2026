import numpy as np


def hz_to_midi(hz) -> np.ndarray:
    arr = np.asarray(hz, dtype=float)
    out = np.full(arr.shape, np.nan)
    voiced = arr > 0
    out[voiced] = 69.0 + 12.0 * np.log2(arr[voiced] / 440.0)
    return out


def fold_cents(cents) -> np.ndarray:
    return np.mod(np.asarray(cents, dtype=float) + 600.0, 1200.0) - 600.0
