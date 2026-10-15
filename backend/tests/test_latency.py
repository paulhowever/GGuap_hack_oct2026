import numpy as np
import pytest

from app.f0 import get_engine
from app.f0.base import F0Track
from app.scoring.grid import Grid, ref_arrays, shifted, song_duration, to_grid
from app.scoring.latency import estimate_latency
from app.scoring.synth import synth_take


def grid_for(ref, cfg, x, wav_t0=0.0):
    tr = get_engine("swiftf0").track(x, 16000)
    return to_grid(tr, wav_t0, song_duration(ref), cfg)


def test_shifted():
    a = np.array([1, 2, 3, 4])
    assert shifted(a, 1, 0).tolist() == [2, 3, 4, 0]
    assert shifted(a, -1, 0).tolist() == [0, 1, 2, 3]
    assert shifted(a, 0, 0).tolist() == [1, 2, 3, 4]
    assert shifted(a, 9, 0).tolist() == [0, 0, 0, 0]


def test_ref_arrays(demo_ref, cfg):
    t = np.arange(0, song_duration(demo_ref), 0.01)
    mask, midi = ref_arrays(demo_ref, t, cfg)
    assert mask[int(2.6 / 0.01)]
    assert not mask[int(1.0 / 0.01)]
    assert midi[int(2.6 / 0.01)] == 60


@pytest.mark.parametrize("delay", [0.0, 0.12, 0.25])
def test_estimates_delay_without_hint(demo_ref, cfg, delay):
    g = grid_for(demo_ref, cfg, synth_take(demo_ref, delay_s=delay))
    mask, midi = ref_arrays(demo_ref, g.t, cfg)
    lat = estimate_latency(g, mask, midi, cfg, cfg.tol("normal"), None)
    assert lat.estimated_ms == pytest.approx(delay * 1000, abs=20)
    assert lat.applied_ms == lat.estimated_ms
    assert lat.confidence >= cfg.rho_min


def test_hint_clips_estimate(demo_ref, cfg):
    g = grid_for(demo_ref, cfg, synth_take(demo_ref, delay_s=0.25))
    mask, midi = ref_arrays(demo_ref, g.t, cfg)
    lat = estimate_latency(g, mask, midi, cfg, cfg.tol("normal"), 0.0, "calibrated")
    assert lat.applied_ms == pytest.approx(cfg.lag_clip_ms)
    assert lat.residual_ms == pytest.approx(lat.estimated_ms - cfg.lag_clip_ms)


@pytest.mark.parametrize("source", ["estimated", "config", None])
def test_uncalibrated_hint_does_not_clip(demo_ref, cfg, source):
    g = grid_for(demo_ref, cfg, synth_take(demo_ref, delay_s=0.3))
    mask, midi = ref_arrays(demo_ref, g.t, cfg)
    lat = estimate_latency(g, mask, midi, cfg, cfg.tol("normal"), 40.0, source)
    assert lat.applied_ms == pytest.approx(300, abs=20)
    assert lat.applied_ms == lat.estimated_ms
    assert lat.residual_ms == 0.0


def test_calibrated_hint_clips_far_estimate(demo_ref, cfg):
    g = grid_for(demo_ref, cfg, synth_take(demo_ref, delay_s=0.3))
    mask, midi = ref_arrays(demo_ref, g.t, cfg)
    lat = estimate_latency(g, mask, midi, cfg, cfg.tol("normal"), 40.0, "calibrated")
    assert lat.applied_ms == pytest.approx(40.0 + cfg.lag_clip_ms)


@pytest.mark.parametrize("source", ["calibrated", "estimated"])
def test_silence_keeps_hint_for_any_source(demo_ref, cfg, source):
    g = grid_for(demo_ref, cfg, np.zeros(16000 * 12, dtype=np.float32))
    mask, midi = ref_arrays(demo_ref, g.t, cfg)
    lat = estimate_latency(g, mask, midi, cfg, cfg.tol("normal"), 48.0, source)
    assert lat.applied_ms == 48.0
    assert lat.residual_ms == 0.0


def test_silence_falls_back_to_hint(demo_ref, cfg):
    g = grid_for(demo_ref, cfg, np.zeros(16000 * 12, dtype=np.float32))
    mask, midi = ref_arrays(demo_ref, g.t, cfg)
    lat = estimate_latency(g, mask, midi, cfg, cfg.tol("normal"), 48.0)
    assert lat.confidence == 0.0
    assert lat.applied_ms == 48.0
    assert lat.residual_ms == 0.0
    assert not g.voiced.any()


def test_to_grid_handles_empty_track(cfg):
    e = np.zeros(0)
    g = to_grid(F0Track(e, e, e, e), 0.0, 5.0, cfg)
    assert isinstance(g, Grid)
    assert not g.voiced.any()
