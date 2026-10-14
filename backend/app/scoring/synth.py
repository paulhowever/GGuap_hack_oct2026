from collections.abc import Iterator

import numpy as np


def iter_notes(ref: dict) -> Iterator[tuple[int, dict]]:
    for line in ref["lines"]:
        for note in line["notes"]:
            yield line["i"], note


def synth_take(
    ref: dict,
    sr: int = 16000,
    cents: float = 0.0,
    delay_s: float = 0.0,
    octave: int = 0,
    mute_lines: frozenset[int] = frozenset(),
    noise_db: float | None = None,
) -> np.ndarray:
    duration = float(ref["audio"]["duration"]) + max(delay_s, 0.0)
    out = np.zeros(int(round(duration * sr)), dtype=np.float32)
    fade = int(0.01 * sr)
    for line_i, note in iter_notes(ref):
        if line_i in mute_lines:
            continue
        start = int(round((note["t"] + delay_s) * sr))
        length = int(round(note["d"] * sr))
        if start < 0 or start + length > out.size or length <= 2 * fade:
            continue
        f0 = 440.0 * 2.0 ** ((note["midi"] + 12 * octave - 69) / 12.0) * 2.0 ** (cents / 1200.0)
        n = np.arange(length) / sr
        wave = np.zeros(length)
        for k in range(1, 6):
            wave += np.sin(2 * np.pi * k * f0 * n) / k
        env = np.ones(length)
        env[:fade] = np.linspace(0.0, 1.0, fade)
        env[-fade:] = np.linspace(1.0, 0.0, fade)
        out[start : start + length] += (0.2 * wave * env).astype(np.float32)
    if noise_db is not None:
        rng = np.random.default_rng(0)
        out += (10 ** (noise_db / 20) * rng.standard_normal(out.size)).astype(np.float32)
    return out
