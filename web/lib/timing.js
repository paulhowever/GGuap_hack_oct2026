import { median, round } from './num.js'

export const WIN = 2048
export const HOP = 512
export const FMIN = 65
export const FMAX = 1100
export const GATE_MIN = 0.01
export const GATE_MAX = 0.05
export const BT_EXTRA_S = 0.2

export function frameTime(E, sr, t0, lagS, win = WIN) {
  return (E - win / 2) / sr - t0 - lagS
}

export function contextNow({ currentTime, outputLatency, baseLatency, ts, perfNow }) {
  if (ts && ts.contextTime > 0 && ts.performanceTime > 0) return ts.contextTime + (perfNow - ts.performanceTime) / 1000
  return currentTime - (outputLatency || 0) - (baseLatency || 0)
}

export function estimateLagMs({ outputLatency, baseLatency, trackLatency, bt = false }) {
  const tail = bt ? BT_EXTRA_S : trackLatency || 0.02
  const ms = Math.round(1000 * ((outputLatency || 0) + (baseLatency || 0) + tail))
  return Number.isFinite(ms) ? ms : 0
}

export function isBtSuspect(outputLatency) {
  return (outputLatency || 0) > 0.1
}

export function toMs(v) {
  if (v === null || v === undefined || v === '') return null
  const n = Number(v)
  return Number.isFinite(n) ? Math.round(n) : null
}

export function resolveLagMs({ session, pinned, stored, estimated }) {
  for (const v of [session, pinned, stored]) if (Number.isFinite(v)) return v
  return Number.isFinite(estimated) ? estimated : 0
}

export function noiseFloor(rmsList) {
  return median(rmsList)
}

export function gateFrom(floor) {
  return Math.min(GATE_MAX, Math.max(GATE_MIN, 3 * floor))
}

export function toDb(x) {
  return x > 0 ? round(20 * Math.log10(x), 1) : -120
}

export function classifyFrame(raw, { sr, t0, lagS, gate, clarityMin }) {
  const voiced = raw.clarity >= clarityMin && raw.rms > gate && raw.hz >= FMIN && raw.hz <= FMAX
  return {
    t: round(frameTime(raw.E, sr, t0, lagS), 3),
    hz: voiced ? round(raw.hz, 1) : 0,
    conf: voiced ? round(raw.clarity, 2) : 0,
    rms: round(raw.rms, 4)
  }
}
