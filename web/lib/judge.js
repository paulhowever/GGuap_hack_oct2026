import { foldCents, hzToMidi } from './pitch.js'
import { median, round } from './num.js'

const PITCHED = new Set(['normal', 'golden'])

export function judgeNotes(ref) {
  return ref.lines
    .flatMap(l => l.notes.map(n => ({ i: n.i, line: l.i, type: n.type, midi: n.midi, t: n.t, end: n.t + n.d })))
    .filter(n => n.type !== 'free')
    .sort((a, b) => a.t - b.t)
}

export function createJudge(ref, { tolCents = 120, onsetPre = 0.15, slack = 0 } = {}) {
  const notes = judgeNotes(ref)
  const acc = notes.map(() => ({ frames: 0, good: 0, cents: [], run: null, onset: null }))
  const starts = notes.map((n, k) => (k > 0 ? Math.max(n.t - onsetPre, Math.min(notes[k - 1].end, n.t)) : n.t - onsetPre))
  const reach = Math.max(onsetPre, slack)
  let next = 0

  function verdict(k) {
    const n = notes[k]
    const a = acc[k]
    const pitched = PITCHED.has(n.type)
    const hit = a.frames ? Math.min(1, a.good / a.frames) : 0
    return {
      i: n.i,
      line: n.line,
      type: n.type,
      hit: round(hit, 2),
      cents: pitched && a.cents.length ? round(median(a.cents)) : null,
      onset_ms: a.onset === null ? null : round(a.onset * 1000)
    }
  }

  function closeUntil(t) {
    const out = []
    while (next < notes.length && t >= notes[next].end + slack) out.push(verdict(next++))
    return out
  }

  return {
    push(frame) {
      const out = closeUntil(frame.t)
      const voiced = frame.conf > 0 && frame.hz > 0
      for (let k = next; k < notes.length && notes[k].t - reach <= frame.t; k++) {
        const n = notes[k]
        const a = acc[k]
        const pitched = PITCHED.has(n.type)
        const dc = voiced && pitched ? foldCents(100 * (hzToMidi(frame.hz) - n.midi)) : null
        const good = voiced && (!pitched || Math.abs(dc) <= tolCents)
        if (good && frame.t >= n.t - slack && frame.t < n.end + slack) a.good++
        if (frame.t < starts[k] || frame.t >= n.end) continue
        a.run = good ? (a.run ?? frame.t) : null
        if (frame.t < n.t) continue
        if (good && a.onset === null) a.onset = Math.max(a.run - n.t, starts[k] - n.t)
        a.frames++
        if (dc !== null) a.cents.push(dc)
      }
      return out
    },
    flush(t = Infinity) {
      return closeUntil(t)
    },
    get pending() {
      return notes.length - next
    }
  }
}
