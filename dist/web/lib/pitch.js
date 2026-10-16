export function hzToMidi(hz) {
  return hz > 0 ? 69 + 12 * Math.log2(hz / 440) : null
}

export function midiToHz(m) {
  return 440 * 2 ** ((m - 69) / 12)
}

export function foldToNote(m, target) {
  return m + 12 * Math.round((target - m) / 12)
}

export function foldCents(c) {
  return ((((c + 600) % 1200) + 1200) % 1200) - 600
}

export function isHit(hz, midi, tolCents) {
  const m = hzToMidi(hz)
  if (m === null) return false
  return Math.abs(foldCents(100 * (m - midi))) <= tolCents
}
