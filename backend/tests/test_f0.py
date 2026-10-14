import numpy as np
import pytest

from app.f0 import get_engine
from app.f0.base import F0Track, frame_rms
from app.f0.frames import FramesEngine


def tone(hz, seconds=1.0, sr=16000, amp=0.3):
    t = np.arange(int(seconds * sr)) / sr
    x = sum(np.sin(2 * np.pi * k * hz * t) / k for k in range(1, 6))
    return (amp / np.sqrt(2) * x / np.sqrt(np.mean(x**2))).astype(np.float32)


def test_swiftf0_tracks_a_tone():
    engine = get_engine("swiftf0")
    tr = engine.track(tone(220.0), 16000)
    voiced = tr.conf >= 0.5
    assert voiced.sum() > 0.8 * tr.t.size
    assert np.median(tr.hz[voiced]) == pytest.approx(220.0, rel=0.01)
    assert tr.rms[voiced].mean() == pytest.approx(0.3 / np.sqrt(2), rel=0.1)


def test_swiftf0_silence_is_unvoiced():
    tr = get_engine("swiftf0").track(np.zeros(16000, dtype=np.float32), 16000)
    assert (tr.conf >= 0.5).sum() == 0


def test_swiftf0_resamples_48k():
    tr = get_engine("swiftf0").track(tone(330.0, sr=48000), 48000)
    voiced = tr.conf >= 0.5
    assert np.median(tr.hz[voiced]) == pytest.approx(330.0, rel=0.01)


def test_get_engine_is_cached_and_validates():
    assert get_engine("swiftf0") is get_engine("swiftf0")
    with pytest.raises(ValueError, match="unknown f0 engine"):
        get_engine("nope")


def test_frame_rms():
    x = np.ones(16000, dtype=np.float32) * 0.5
    assert frame_rms(x, 16000, np.array([0.5]))[0] == pytest.approx(0.5)


def test_frames_engine_maps_to_audio_time():
    frames = [
        {"t": 1.0, "hz": 220.0, "conf": 1.0, "rms": 0.1},
        {"t": 1.01, "hz": 0.0, "conf": 0.0, "rms": 0.0},
    ]
    tr = FramesEngine(frames, wav_t0=-0.2, lag_s=0.05).track(np.zeros(1), 16000)
    assert isinstance(tr, F0Track)
    assert tr.t[0] == pytest.approx(1.25)
    assert tr.hz.tolist() == [220.0, 0.0]


def test_frames_engine_empty():
    tr = FramesEngine([], wav_t0=0.0, lag_s=0.0).track(np.zeros(1), 16000)
    assert tr.t.size == 0
