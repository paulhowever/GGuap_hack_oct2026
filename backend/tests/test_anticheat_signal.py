import copy

import numpy as np
import pytest
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

from app.anticheat.replay import REPLAY_MAX_CENTS, media_path, replay_cents
from app.anticheat.signal import check_signal
from app.anticheat.voice import FLAT_MAX_CENTS, HARM_MIN, voice_stats
from app.core.config import ROOT
from app.demo import build_demo
from app.f0 import get_engine
from app.scoring.synth import synth_take

SR = 16000
LEAD_S = 0.15
DELAY_S = 0.25
WEB_T0 = -LEAD_S
WEB_LAG_MS = 1000 * DELAY_S


@pytest.fixture(scope="module")
def media(tmp_path_factory):
    songs = tmp_path_factory.mktemp("songs")
    ref = build_demo(songs / "demo", ROOT / "contracts" / "fixtures" / "demo.reference.json")
    return songs, ref


def voice_of(x, ref, cfg, wav_t0=0.0, lag_s=0.0):
    return voice_stats(x, SR, get_engine("swiftf0").track(x, SR), ref, wav_t0, lag_s, cfg.conf_min)


def check(x, ref, songs, cfg, sr=SR, wav_t0=0.0, lag_ms=0.0):
    engine = get_engine("swiftf0")
    return check_signal(x, sr, engine.track(x, sr), ref, wav_t0, lag_ms, songs, engine, cfg.conf_min)


def web_timing(x, sr=SR, delay_s=0.0):
    return np.concatenate([np.zeros(round((LEAD_S + delay_s) * sr), dtype=np.float32), x])


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


def test_media_url_with_nul_is_skipped(media, cfg):
    songs, ref = media
    engine = get_engine("swiftf0")
    bad = {**ref, "audio": {**ref["audio"], "guide": "/media/demo/guide\x00.wav"}}
    take = engine.track(synth_take(ref, jitter_cents=20), SR)
    out = replay_cents(take, 0.0, bad, songs, engine, cfg.conf_min)
    assert out["guide"] is None
    assert out["minus"] > REPLAY_MAX_CENTS


@pytest.mark.parametrize(("jitter", "not_voice"), [(0.0, True), (20.0, False)])
def test_voice_stats_with_web_timing(demo_ref, cfg, jitter, not_voice):
    x = web_timing(synth_take(demo_ref, delay_s=DELAY_S, jitter_cents=jitter))
    stats = voice_of(x, demo_ref, cfg, WEB_T0, DELAY_S)
    assert stats.notes == 6
    assert stats.not_voice is not_voice


@pytest.mark.parametrize(("jitter", "flags"), [(0.0, {"replay", "not_voice"}), (20.0, set())])
def test_check_signal_with_web_timing(media, cfg, jitter, flags):
    songs, ref = media
    x = web_timing(synth_take(ref, delay_s=DELAY_S, jitter_cents=jitter))
    result = check(x, ref, songs, cfg, wav_t0=WEB_T0, lag_ms=WEB_LAG_MS)
    assert set(result.flags) == flags
    assert result.metrics["long_notes"] == 6


def test_guide_playback_with_web_timing_is_replay(media, cfg):
    songs, ref = media
    x, sr = sf.read(songs / "demo" / "guide.wav", dtype="float32")
    result = check(web_timing(x, sr, DELAY_S), ref, songs, cfg, sr, WEB_T0, WEB_LAG_MS)
    assert "replay" in result.flags
    assert result.metrics["long_notes"] == 6


def test_live_guide_playback_with_web_timing_is_replay(demo_ref, cfg, tmp_path):
    (tmp_path / "demo").mkdir()
    guide = synth_take(demo_ref, jitter_cents=20)
    sf.write(tmp_path / "demo" / "guide.wav", guide, SR, subtype="PCM_16")
    ref = {**demo_ref, "audio": {**demo_ref["audio"], "guide": "/media/demo/guide.wav", "minus": None}}
    delay_s = 0.35
    result = check(web_timing(guide, SR, delay_s), ref, tmp_path, cfg, SR, WEB_T0, 1000 * delay_s)
    assert result.metrics["replay_guide_c"] < REPLAY_MAX_CENTS
    assert result.flags == ["replay"]


def four_line_ref(demo_ref, shift=8.5):
    ref = copy.deepcopy(demo_ref)
    lines, notes = len(demo_ref["lines"]), demo_ref["stats"]["notes"]
    for line in demo_ref["lines"]:
        moved = [{**n, "i": n["i"] + notes, "t": n["t"] + shift} for n in line["notes"]]
        span = {"t0": line["t0"] + shift, "t1": line["t1"] + shift}
        ref["lines"].append({**line, **span, "i": line["i"] + lines, "notes": moved})
    media = {"guide": "/media/demo/guide.wav", "minus": "/media/demo/minus.wav"}
    ref["audio"] = {**ref["audio"], **media, "duration": 20.0}
    return ref


def organ_minus(duration, roots=(57, 55, 53, 52), bar_s=2.0):
    t = np.arange(round(duration * SR)) / SR
    out = np.zeros(t.size)
    for b in range(int(np.ceil(duration / bar_s))):
        seg = slice(round(b * bar_s * SR), min(t.size, round((b + 1) * bar_s * SR)))
        tb = t[seg]
        f0 = 440.0 * 2 ** ((roots[b % len(roots)] - 69) / 12)
        wave = sum(np.sin(2 * np.pi * k * f0 * tb) / k for k in range(1, 9))
        out[seg] = wave * np.minimum(1.0, np.minimum(tb - tb[0], tb[-1] - tb) / 0.01)
    return 0.5 * out / np.abs(out).max()


def speaker_bleed(x, gain, delay_s=0.12):
    y = sosfiltfilt(butter(4, [150, 6000], btype="band", fs=SR, output="sos"), x)
    pad = round(delay_s * SR)
    return gain * np.concatenate([np.zeros(pad), y[: y.size - pad]])


def test_minus_bleed_in_skipped_lines_is_not_replay(demo_ref, cfg, tmp_path):
    ref = four_line_ref(demo_ref)
    duration = ref["audio"]["duration"]
    minus = organ_minus(duration)
    (tmp_path / "demo").mkdir()
    sf.write(tmp_path / "demo" / "minus.wav", minus.astype(np.float32), SR, subtype="PCM_16")
    sf.write(tmp_path / "demo" / "guide.wav", synth_take(ref), SR, subtype="PCM_16")
    voice = synth_take(ref, jitter_cents=20, mute_lines=frozenset({1, 2}))
    bleed = speaker_bleed(minus, 0.1)
    noise = 10 ** (-55 / 20) * np.random.default_rng(3).standard_normal(voice.size)
    sung = voice[np.abs(voice) > 1e-4]
    assert 15 < 20 * np.log10(np.sqrt(np.mean(sung**2)) / np.sqrt(np.mean(bleed**2))) < 20
    result = check((voice + bleed + noise).astype(np.float32), ref, tmp_path, cfg)
    assert result.flags == []
    assert result.metrics["replay_minus_c"] > 2 * REPLAY_MAX_CENTS
    assert result.metrics["replay_guide_c"] > 2 * REPLAY_MAX_CENTS
    assert result.metrics["jitter_c"] > 2 * FLAT_MAX_CENTS
