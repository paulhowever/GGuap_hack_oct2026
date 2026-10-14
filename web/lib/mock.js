import { midiToHz } from './pitch.js'
import { round } from './num.js'

export const MODES = ['perfect', 'offkey', 'octave', 'late200', 'silent']
export const MOCK_HOP = 512 / 48000

export function rng(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function noteAt(ref, t) {
  for (const line of ref.lines) {
    for (const note of line.notes) if (t >= note.t && t < note.t + note.d) return { line, note }
  }
  return null
}

export function mockFrame(ref, mode, t, rand) {
  const shift = mode === 'late200' ? 0.2 : 0
  const hit = mode === 'silent' ? null : noteAt(ref, t - shift)
  if (!hit) return { t: round(t, 3), hz: 0, conf: 0, rms: 0.004 }
  let cents = (rand() * 2 - 1) * 30
  if (mode === 'offkey') cents += 250
  if (mode === 'octave') cents += hit.line.i % 2 ? 1200 : -1200
  return { t: round(t, 3), hz: round(midiToHz(hit.note.midi + cents / 100), 1), conf: 0.95, rms: 0.05 }
}

export function mockFrames(ref, mode, fromT, toT, rand, hop = MOCK_HOP) {
  const out = []
  for (let k = Math.floor(fromT / hop) + 1; k * hop <= toT; k++) out.push(mockFrame(ref, mode, k * hop, rand))
  return out
}
