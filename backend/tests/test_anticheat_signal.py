import numpy as np
import pytest
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from app.anticheat.replay import REPLAY_MAX_CENTS, media_path
from app.anticheat.signal import check_signal
from app.anticheat.voice import FLAT_MAX_CENTS, HARM_MIN, voice_stats
from app.core.config import ROOT
from app.demo import build_demo
from app.f0 import get_engine
from app.scoring.synth import synth_take

SR = 16000


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    songs = tmp_path_factory.mktemp("songs")
    ref = build_demo(songs / "demo", ROOT / "contracts" / "fixtures" / "demo.reference.json")
    return songs, ref


def voice_of(x, ref, cfg):
    return voice_stats(x, SR, get_engine("swiftf0").track(x, SR), ref, 0.0, 0.0, cfg.conf_min)


def check(x, ref, songs, cfg, sr=SR):
    engine = get_engine("swiftf0")
    return check_signal(x, sr, engine.track(x, sr), ref, 0.0, 0.0, songs, engine, cfg.conf_min)


def test_flat_synth_is_not_voice(demo_ref, cfg):
    stats = voice_of(synth_take(demo_ref), demo_ref, cfg)
    assert stats.notes == 6
    assert stats.jitter_c < FLAT_MAX_CENTS
    assert stats.not_voice


def test_jittered_synth_is_voice(demo_ref, cfg):
    stats = voice_of(synth_take(demo_ref, jitter_cents=20), demo_ref, cfg)
    assert stats.jitter_c > 2 * FLAT_MAX_CENTS
    assert stats.harm > HARM_MIN
    assert not stats.not_voice


def test_whistle_has_no_harmonics(demo_ref, cfg):
    lowpass = butter(8, 450, fs=SR, output="sos")
    x = sosfiltfilt(lowpass, synth_take(demo_ref, jitter_cents=20)).astype(np.float32)
    stats = voice_of(x, demo_ref, cfg)
    assert stats.jitter_c > FLAT_MAX_CENTS
    assert stats.harm < HARM_MIN
    assert stats.not_voice


@pytest.mark.parametrize("kind", ["silence", "noise"])
def test_silence_and_noise_are_not_judged(demo_ref, cfg, tmp_path, kind):
    n = 12 * SR
    rng = np.random.default_rng(1)
    x = (
        np.zeros(n, dtype=np.float32)
        if kind == "silence"
        else (0.1 * rng.standard_normal(n)).astype(np.float32)
    )
    result = check(x, demo_ref, tmp_path, cfg)
    assert result.flags == []
    assert result.metrics["long_notes"] == 0


@pytest.mark.parametrize("name", ["guide.wav", "minus.wav"])
def test_playback_is_replay(media, cfg, name):
    songs, ref = media
    x, sr = sf.read(songs / "demo" / name, dtype="float32")
    result = check(x, ref, songs, cfg, sr)
    assert "replay" in result.flags
    assert min(result.metrics["replay_guide_c"], result.metrics["replay_minus_c"]) < REPLAY_MAX_CENTS


def test_mp3_guide_playback_is_replay(media, cfg, tmp_path):
    songs, ref = media
    if "MP3" not in sf.available_formats():
        pytest.skip("libsndfile without mp3")
    x, sr = sf.read(songs / "demo" / "guide.wav", dtype="float32")
    (tmp_path / "demo").mkdir()
    sf.write(tmp_path / "demo" / "guide.mp3", x, sr, format="MP3")
    mp3_ref = {**ref, "audio": {**ref["audio"], "guide": "/media/demo/guide.mp3", "minus": None}}
    result = check(synth_take(ref), mp3_ref, tmp_path, cfg)
    assert result.metrics["replay_guide_c"] < REPLAY_MAX_CENTS
    assert "replay" in result.flags


def test_jittered_take_is_not_replay(media, cfg):
    songs, ref = media
    result = check(synth_take(ref, jitter_cents=20), ref, songs, cfg)
    assert result.flags == []
    assert result.metrics["replay_guide_c"] > 2 * REPLAY_MAX_CENTS


def test_missing_or_broken_media_is_skipped(media, cfg, tmp_path):
    _, ref = media
    (tmp_path / "demo").mkdir()
    (tmp_path / "demo" / "guide.wav").write_bytes(b"not audio")
    result = check(synth_take(ref, jitter_cents=20), ref, tmp_path, cfg)
    assert result.metrics["replay_guide_c"] is None
    assert result.metrics["replay_minus_c"] is None
    assert result.flags == []


def test_media_path_stays_inside_songs_dir(media):
    songs, _ = media
    assert media_path("/media/demo/guide.wav", songs) == (songs / "demo" / "guide.wav").resolve()
    assert media_path("/media/../../etc/passwd", songs) is None
    assert media_path("https://cdn.example/guide.mp3", songs) is None
    assert media_path(None, songs) is None
