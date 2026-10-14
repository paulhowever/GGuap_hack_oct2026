from dataclasses import replace

import numpy as np

from app.f0.base import F0Track
from app.scoring.config import ScoringConfig
from app.scoring.grid import PITCHED, Grid, ref_arrays, shifted, song_duration, to_grid
from app.scoring.latency import estimate_latency, steps_for
from app.scoring.metrics import LineMetrics, NoteMetrics
from app.scoring.pitch import fold_cents

EDGE_TRIM_S = 0.03
ONSET_PRE_S = 0.15
STAB_SKIP_S = 0.08
STAB_WIN = 15
CHART_STEP = 2


def note_dc(midi: np.ndarray, voiced: np.ndarray, target: float) -> np.ndarray:
    return np.where(voiced, fold_cents(100.0 * (np.nan_to_num(midi) - target)), np.inf)


def find_onset(t, ok, t0: float, d: float, prev_end: float | None) -> float | None:
    start = t0 - ONSET_PRE_S if prev_end is None else max(t0 - ONSET_PRE_S, prev_end)
    window = np.flatnonzero((t >= start) & (t <= t0 + min(0.4, 0.6 * d)))
    for k in window:
        if k + 2 < ok.size and ok[k] and ok[k + 1] and ok[k + 2]:
            return round(float((t[k] - t0) * 1000.0), 1)
    return None


def stability(t, voiced, dc, t0: float, t1: float) -> float | None:
    x = dc[voiced & (t >= t0 + STAB_SKIP_S) & (t < t1)]
    if x.size < STAB_WIN + 2:
        return None
    ma = np.convolve(x, np.ones(STAB_WIN) / STAB_WIN, mode="valid")
    half = STAB_WIN // 2
    return round(float(np.std(x[half : half + ma.size] - ma)), 1)


def measure_note(
    i: int, line: int, note: dict, grid: Grid, tol: float, cfg: ScoringConfig, prev_end: float | None
) -> NoteMetrics:
    t0, t1 = note["t"], note["t"] + note["d"]
    body = (grid.t >= t0 + EDGE_TRIM_S) & (grid.t < t1 - EDGE_TRIM_S)
    if not body.any():
        body = (grid.t >= t0) & (grid.t < t1)
    n = int(body.sum())
    pitched = note["type"] in PITCHED
    dc = note_dc(grid.midi, grid.voiced, note["midi"])
    sung = grid.voiced & body
    coverage = float(sung.sum() / n) if n else 0.0
    hit = float((sung & (np.abs(dc) <= tol)).sum() / n) if pitched and n else coverage
    cents = round(float(np.median(dc[sung])), 1) if pitched and sung.any() else None
    onset_ok = grid.voiced & (np.abs(dc) <= tol + 50) if pitched else grid.voiced
    onset = find_onset(grid.t, onset_ok, t0, note["d"], prev_end)
    stab = stability(grid.t, grid.voiced, dc, t0, t1) if pitched else None
    perfect = hit >= 0.9 and onset is not None and abs(onset) <= cfg.onset_ok_ms
    return NoteMetrics(
        i=i,
        line=line,
        type=note["type"],
        syl=note.get("syl", ""),
        d=note["d"],
        hit=round(hit, 3),
        coverage=round(coverage, 3),
        cents=cents,
        onset_ms=onset,
        stab_c=stab,
        perfect=perfect,
    )


def rhythm_factor(onset: float | None, cfg: ScoringConfig) -> float:
    if onset is None:
        return 0.0
    a = abs(onset)
    if a <= cfg.onset_ok_ms:
        return 1.0
    if a >= cfg.onset_zero_ms:
        return 0.0
    return 1.0 - (a - cfg.onset_ok_ms) / (cfg.onset_zero_ms - cfg.onset_ok_ms)


def weight(note: dict, cfg: ScoringConfig) -> float:
    return note["len"] * cfg.mult.get(note["type"], 0.0)


def aggregate(pairs: list[tuple[dict, NoteMetrics]], cfg: ScoringConfig) -> tuple[float, float, float]:
    pitch_pairs = [(weight(n, cfg), m.hit) for n, m in pairs if n["type"] in PITCHED and weight(n, cfg) > 0]
    rhythm_pairs = [
        (weight(n, cfg), m.coverage * rhythm_factor(m.onset_ms, cfg)) for n, m in pairs if weight(n, cfg) > 0
    ]
    extra_pairs = [(n["len"], float(m.perfect)) for n, m in pairs if weight(n, cfg) > 0]

    def mean(items: list[tuple[float, float]]) -> float:
        total = sum(a for a, _ in items)
        return sum(a * b for a, b in items) / total if total > 0 else 0.0

    rhythm = mean(rhythm_pairs)
    pitch = mean(pitch_pairs) if pitch_pairs else rhythm
    return pitch, rhythm, mean(extra_pairs)


def note_points(pairs: list[tuple[dict, NoteMetrics]], cfg: ScoringConfig) -> list[NoteMetrics]:
    wt = cfg.weights
    wp = sum(weight(n, cfg) for n, _ in pairs if n["type"] in PITCHED)
    wr = sum(weight(n, cfg) for n, _ in pairs)
    lx = sum(n["len"] for n, _ in pairs if weight(n, cfg) > 0)
    out = []
    for n, m in pairs:
        w = weight(n, cfg)
        p = wt.pitch * (w * m.hit / wp if wp and n["type"] in PITCHED else 0.0)
        r = wt.rhythm * (w * m.coverage * rhythm_factor(m.onset_ms, cfg) / wr if wr else 0.0)
        e = wt.extras * (n["len"] * float(m.perfect) / lx if lx and w > 0 else 0.0)
        out.append(replace(m, pts=round(cfg.max * (p + r + e))))
    return out


def octave_shift(grid: Grid, ref_midi: np.ndarray) -> int:
    both = grid.voiced & ~np.isnan(ref_midi)
    if both.sum() < 10:
        return 0
    return int(round(float(np.median(grid.midi[both] - ref_midi[both])) / 12.0))


def chart(ref: dict, grid: Grid) -> dict:
    notes = [n for line in ref["lines"] for n in line["notes"]]
    starts = np.array([n["t"] for n in notes])
    targets = np.array([n["midi"] for n in notes], dtype=float)
    t_from = max(float(starts.min()) - 0.5, 0.0)
    t_to = float(max(n["t"] + n["d"] for n in notes)) + 0.5
    sel = np.flatnonzero((grid.t >= t_from) & (grid.t <= t_to))[::CHART_STEP]
    sung = []
    for k in sel:
        m = grid.midi[k]
        if np.isnan(m):
            sung.append(None)
            continue
        target = targets[
            int(np.clip(np.searchsorted(starts, grid.t[k], side="right") - 1, 0, len(notes) - 1))
        ]
        sung.append(round(float(m + 12.0 * np.round((target - m) / 12.0)), 2))
    return {"hop_ms": int(CHART_STEP * 10), "t0": round(t_from, 3), "sung": sung}


def score_take(
    ref: dict, track: F0Track, wav_t0: float, cfg: ScoringConfig, difficulty: str, lag_hint_ms: float | None
) -> dict:
    tol = cfg.tol(difficulty)
    raw = to_grid(track, wav_t0, song_duration(ref), cfg)
    ref_mask, ref_midi = ref_arrays(ref, raw.t, cfg)
    latency = estimate_latency(raw, ref_mask, ref_midi, cfg, tol, lag_hint_ms)
    s = steps_for(latency.applied_ms)
    grid = Grid(raw.t, shifted(raw.voiced, s, False), shifted(raw.midi, s, np.nan))
    ordered = [(line["i"], note) for line in ref["lines"] for note in line["notes"]]
    ends = [None] + [note["t"] + note["d"] for _, note in ordered[:-1]]
    measured = [
        (note, measure_note(note["i"], line_i, note, grid, tol, cfg, prev_end))
        for (line_i, note), prev_end in zip(ordered, ends, strict=True)
    ]
    scored = note_points(measured, cfg)
    pairs = [(n, m) for (n, _), m in zip(measured, scored, strict=True)]
    pitch, rhythm, extras = aggregate(pairs, cfg)
    wt = cfg.weights
    total = int(round(cfg.max * (wt.pitch * pitch + wt.rhythm * rhythm + wt.extras * extras)))
    lines: list[LineMetrics] = []
    for line in ref["lines"]:
        lp = [(n, m) for n, m in pairs if m.line == line["i"]]
        p, r, _ = aggregate(lp, cfg)
        cov = float(np.mean([m.coverage for _, m in lp])) if lp else 0.0
        score = round(100 * (0.7 * p + 0.3 * r))
        lines.append(LineMetrics(line["i"], line["text"], score, cfg.line_grade(score), p, r, cov))
    bounds = {x["i"]: (x["t0"], x["t1"]) for x in ref["lines"]}
    return {
        "version": cfg.version,
        "latency": latency.as_dict(),
        "score": {
            "total": total,
            "max": cfg.max,
            "grade": cfg.grade(total),
            "pitch_pct": round(100 * pitch, 1),
            "rhythm_pct": round(100 * rhythm, 1),
            "extras_pct": round(100 * extras, 1),
        },
        "lines": [
            {
                "i": lm.i,
                "t0": bounds[lm.i][0],
                "t1": bounds[lm.i][1],
                "text": lm.text,
                "score": lm.score,
                "grade": lm.grade,
                "pitch_pct": round(100 * lm.pitch),
                "rhythm_pct": round(100 * lm.rhythm),
                "tip": None,
            }
            for lm in lines
        ],
        "notes": [
            {
                "i": m.i,
                "line": m.line,
                "hit": m.hit,
                "cents": m.cents,
                "onset_ms": m.onset_ms,
                "stab_c": m.stab_c,
                "perfect": m.perfect,
                "pts": m.pts,
            }
            for _, m in pairs
        ],
        "chart": chart(ref, grid),
        "tips": [],
        "octave_shift": octave_shift(grid, ref_midi),
    }
