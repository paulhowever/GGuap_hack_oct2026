import { median } from './num.js'
import { HOP } from './timing.js'

export const CLICKS = 8
export const MIN_HITS = 5
export const LEAD_IN = 2
export const CLICK_GAP = 0.5
export const CLICK_LEAD = 0.6
export const CLICK_LEN = 0.02
export const SPEAKERS = { gap: CLICK_GAP, late: 0.4, range: [-20, 400] }
export const HEADPHONES = { gap: 0.8, late: 0.7, range: [-20, 700] }

export function clickTimes(start, n = CLICKS, gap = CLICK_GAP) {
  return Array.from({ length: n }, (_, k) => start + k * gap)
}

export function onsetThreshold(floor) {
  return Math.max(0.01, 4 * floor)
}

export function detectOnsets(frames, { sr, threshold, hop = HOP, refractory = 0.25 }) {
  const out = []
  let above = false
  let last = -Infinity
  for (const f of frames) {
    const t = (f.E - hop / 2) / sr
    const on = f.rms > threshold
    if (on && !above && t - last >= refractory) {
      out.push(t)
      last = t
    }
    above = on
  }
  return out
}

export function estimateLag(clicks, onsets, { early = 0.1, late = SPEAKERS.late, outlier = 0.06, minHits = MIN_HITS, range = SPEAKERS.range } = {}) {
  const diffs = []
  for (const c of clicks) {
    const o = onsets.find(t => t >= c - early && t < c + late)
    if (o !== undefined) diffs.push(o - c)
  }
  const m = median(diffs)
  const kept = diffs.filter(d => Math.abs(d - m) <= outlier)
  if (kept.length < minHits) return { lag_ms: null, hits: kept.length }
  const lag = Math.round(median(kept) * 1000)
  if (lag < range[0] || lag > range[1]) return { lag_ms: null, hits: 0 }
  return { lag_ms: lag, hits: kept.length }
}
