from collections.abc import Iterator

import numpy as np

JITTER_SEED = 7


def iter_notes(ref: dict) -> Iterator[tuple[int, dict]]:
    for line in ref["lines"]:
        for note in line["notes"]:
            yield line["i"], note


def wobble(length: int, sr: int, cents: float, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(length) / sr
    vibrato = np.sqrt(2) * np.sin(2 * np.pi * rng.uniform(4.5, 6.5) * t + rng.uniform(0, 2 * np.pi))
    walk = np.cumsum(rng.standard_normal(length))
    walk -= np.linspace(walk[0], walk[-1], length)
    walk = (walk - walk.mean()) / (walk.std() + 1e-9)
    return cents * (0.8 * vibrato + 0.6 * walk)


def synth_take(
    ref: dict,
    sr: int = 16000,
    cents: float = 0.0,
    delay_s: float = 0.0,
    octave: int = 0,
    mute_lines: frozenset[int] = frozenset(),
    noise_db: float | None = None,
    jitter_cents: float = 0.0,
) -> np.ndarray:
    duration = float(ref["audio"]["duration"]) + max(delay_s, 0.0)
    out = np.zeros(int(round(duration * sr)), dtype=np.float32)
    fade = int(0.01 * sr)
    rng = np.random.default_rng(JITTER_SEED)
    for line_i, note in iter_notes(ref):
        if line_i in mute_lines:
            continue
        start = int(round((note["t"] + delay_s) * sr))
        length = int(round(note["d"] * sr))
        if start < 0 or start + length > out.size or length <= 2 * fade:
            continue
        f0 = 440.0 * 2.0 ** ((note["midi"] + 12 * octave - 69) / 12.0) * 2.0 ** (cents / 1200.0)
        n = np.arange(length) / sr
        phase = None
        if jitter_cents:
            phase = 2 * np.pi * np.cumsum(f0 * 2.0 ** (wobble(length, sr, jitter_cents, rng) / 1200.0)) / sr
        wave = np.zeros(length)
        for k in range(1, 6):
            wave += (np.sin(2 * np.pi * k * f0 * n) if phase is None else np.sin(k * phase)) / k
        env = np.ones(length)
        env[:fade] = np.linspace(0.0, 1.0, fade)
        env[-fade:] = np.linspace(1.0, 0.0, fade)
        out[start : start + length] += (0.2 * wave * env).astype(np.float32)
    if noise_db is not None:
        rng = np.random.default_rng(0)
        out += (10 ** (noise_db / 20) * rng.standard_normal(out.size)).astype(np.float32)
    return out
