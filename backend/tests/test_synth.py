import numpy as np
import pytest

from app.scoring.synth import iter_notes, synth_take


def dominant_hz(x, sr):
    spec = np.abs(np.fft.rfft(x * np.hanning(x.size)))
    return np.fft.rfftfreq(x.size, 1 / sr)[int(np.argmax(spec))]


def segment(x, sr, t0, t1):
    return x[int(t0 * sr) : int(t1 * sr)]


def test_length_and_dtype(demo_ref):
    x = synth_take(demo_ref, sr=16000)
    assert x.dtype == np.float32
    assert x.size == int(round(demo_ref["audio"]["duration"] * 16000))


def test_first_note_frequency(demo_ref):
    x = synth_take(demo_ref, sr=16000)
    _, note = next(iter_notes(demo_ref))
    hz = dominant_hz(segment(x, 16000, note["t"] + 0.1, note["t"] + note["d"] - 0.1), 16000)
    assert hz == pytest.approx(261.63, abs=3)


def test_cents_and_octave(demo_ref):
    _, note = next(iter_notes(demo_ref))
    up = synth_take(demo_ref, cents=100)
    low = synth_take(demo_ref, octave=-1)
    seg = (note["t"] + 0.1, note["t"] + note["d"] - 0.1)
    assert dominant_hz(segment(up, 16000, *seg), 16000) == pytest.approx(277.18, abs=3)
    assert dominant_hz(segment(low, 16000, *seg), 16000) == pytest.approx(130.81, abs=3)


def test_delay_and_mute(demo_ref):
    _, note = next(iter_notes(demo_ref))
    delayed = synth_take(demo_ref, delay_s=0.25)
    assert np.abs(segment(delayed, 16000, note["t"], note["t"] + 0.2)).max() == 0.0
    muted = synth_take(demo_ref, mute_lines=frozenset({0}))
    assert np.abs(segment(muted, 16000, note["t"], note["t"] + note["d"])).max() == 0.0


def test_noise_is_deterministic(demo_ref):
    a = synth_take(demo_ref, noise_db=-40)
    b = synth_take(demo_ref, noise_db=-40)
    assert np.array_equal(a, b)
    assert np.abs(a[:1000]).max() > 0


def test_jitter_is_off_by_default(demo_ref):
    assert np.array_equal(synth_take(demo_ref), synth_take(demo_ref, jitter_cents=0.0))


def test_jitter_wobbles_around_the_note(demo_ref):
    a = synth_take(demo_ref, jitter_cents=20)
    assert np.array_equal(a, synth_take(demo_ref, jitter_cents=20))
    assert not np.array_equal(a, synth_take(demo_ref))
    _, note = next(iter_notes(demo_ref))
    hz = dominant_hz(segment(a, 16000, note["t"] + 0.1, note["t"] + note["d"] - 0.1), 16000)
    assert hz == pytest.approx(261.63, abs=6)
