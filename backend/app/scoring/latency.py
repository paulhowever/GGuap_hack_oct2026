from dataclasses import asdict, dataclass

import numpy as np

from app.scoring.config import ScoringConfig
from app.scoring.grid import GRID_S, Grid, shifted
from app.scoring.pitch import fold_cents


@dataclass(frozen=True)
class Latency:
    hint_ms: float | None
    estimated_ms: float
    applied_ms: float
    residual_ms: float
    confidence: float

    def as_dict(self) -> dict:
        return asdict(self)


def steps_for(lag_ms: float) -> int:
    return int(round(lag_ms / 1000.0 / GRID_S))


def pitch_hit_rate(grid: Grid, ref_midi: np.ndarray, lag_ms: float, tol: float) -> float:
    inside = ~np.isnan(ref_midi)
    if not inside.any():
        return 0.0
    m = shifted(grid.midi, steps_for(lag_ms), np.nan)
    sung = inside & ~np.isnan(m)
    dc = np.where(sung, fold_cents(100.0 * (np.nan_to_num(m) - np.nan_to_num(ref_midi))), np.inf)
    return float((np.abs(dc) <= tol).sum() / inside.sum())


def estimate_latency(
    grid: Grid,
    ref_mask: np.ndarray,
    ref_midi: np.ndarray,
    cfg: ScoringConfig,
    tol: float,
    hint_ms: float | None,
) -> Latency:
    lo, hi = cfg.lag_range_ms
    lags = np.arange(lo, hi + 1, 10.0)
    v = grid.voiced.astype(float) - grid.voiced.mean()
    r = ref_mask.astype(float) - ref_mask.mean()
    denom = float(np.linalg.norm(v) * np.linalg.norm(r))
    corr = np.array([float(np.dot(shifted(v, steps_for(lag), 0.0), r)) for lag in lags])
    coarse = float(lags[int(np.argmax(corr))])
    rho = float(corr.max() / denom) if denom > 0 else 0.0
    fine = np.arange(max(lo, coarse - 50), min(hi, coarse + 50) + 1, 10.0)
    hits = np.array([pitch_hit_rate(grid, ref_midi, lag, tol) for lag in fine])
    if hits.size and hits.max() > 0:
        best = fine[hits == hits.max()]
        estimated = float(best[int(np.argmin(np.abs(best - coarse)))])
    else:
        estimated = coarse
    if rho < cfg.rho_min:
        applied = hint_ms if hint_ms is not None else 0.0
    elif hint_ms is None:
        applied = estimated
    else:
        applied = float(np.clip(estimated, hint_ms - cfg.lag_clip_ms, hint_ms + cfg.lag_clip_ms))
    return Latency(
        hint_ms=hint_ms,
        estimated_ms=estimated,
        applied_ms=float(applied),
        residual_ms=float(estimated - applied),
        confidence=round(max(rho, 0.0), 3),
    )
