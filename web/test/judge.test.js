import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createJudge, judgeNotes } from '../lib/judge.js'
import { midiToHz } from '../lib/pitch.js'

const ref = JSON.parse(readFileSync(new URL('../../contracts/fixtures/demo.reference.json', import.meta.url)))
const HOP = 512 / 48000

function sing({ cents = 0, delay = 0, mute = new Set(), source = ref } = {}) {
  const notes = judgeNotes(source)
  const frames = []
  for (let t = 0; t < source.audio.duration; t += HOP) {
    const n = notes.find(x => t - delay >= x.t && t - delay < x.end && !mute.has(x.i))
    frames.push(n ? { t, hz: midiToHz(n.midi) * 2 ** (cents / 1200), conf: 1, rms: 0.1 } : { t, hz: 0, conf: 0, rms: 0.001 })
  }
  return frames
}

function run(frames, opts, source = ref) {
  const j = createJudge(source, opts)
  return [...frames.flatMap(f => j.push(f)), ...j.flush()]
}

test('perfect singing hits every note in order', () => {
  const v = run(sing())
  assert.deepEqual(v.map(x => x.i), [0, 1, 2, 3, 4, 5])
  assert.ok(v.every(x => x.hit >= 0.9 && Math.abs(x.cents) <= 5 && x.onset_ms >= 0 && x.onset_ms <= 15))
})

test('verdict arrives right after the note ends', () => {
  const j = createJudge(ref)
  const first = judgeNotes(ref)[0]
  assert.equal(sing().filter(f => f.t < first.end).flatMap(f => j.push(f)).length, 0)
  assert.deepEqual(j.push({ t: first.end + 0.001, hz: 0, conf: 0, rms: 0 }).map(x => x.i), [0])
})

test('150 cents sharp misses on normal and passes on easy', () => {
  assert.ok(run(sing({ cents: 150 }), { tolCents: 120 }).every(x => x.hit === 0 && x.cents === 150))
  assert.ok(run(sing({ cents: 150 }), { tolCents: 200 }).every(x => x.hit >= 0.9))
})

test('octave below is not a miss', () => {
  assert.ok(run(sing().map(f => (f.hz ? { ...f, hz: f.hz / 2 } : f))).every(x => x.hit >= 0.9))
})

test('silent line gives zero hit and nulls', () => {
  const v = run(sing({ mute: new Set([3, 4, 5]) }))
  assert.ok(v.filter(x => x.line === 1).every(x => x.hit === 0 && x.cents === null && x.onset_ms === null))
  assert.ok(v.filter(x => x.line === 0).every(x => x.hit >= 0.9))
})

test('late singing shows up in onset_ms even on repeated pitches', () => {
  assert.ok(run(sing({ delay: 0.1 })).every(x => x.onset_ms >= 90 && x.onset_ms <= 115))
})

test('flush emits the rest at song end', () => {
  const j = createJudge(ref)
  j.push({ t: 0, hz: 0, conf: 0, rms: 0 })
  assert.equal(j.flush().length, 6)
  assert.equal(j.pending, 0)
})

test('contiguous notes do not borrow the previous note frames for onset', () => {
  const contiguous = structuredClone(ref)
  contiguous.lines[1].notes = [
    { i: 3, t: 6.0, d: 1.0, beat: 70, len: 20, midi: 65, pc: 5, type: 'normal', syl: 'фа ' },
    { i: 4, t: 7.0, d: 1.0, beat: 90, len: 20, midi: 65, pc: 5, type: 'normal', syl: 'соль ' },
    { i: 5, t: 8.0, d: 0.9, beat: 110, len: 18, midi: 66, pc: 6, type: 'normal', syl: 'ля' }
  ]
  const v = run(sing({ source: contiguous }), {}, contiguous)
  assert.deepEqual(v.map(x => x.i), [0, 1, 2, 3, 4, 5])
  assert.ok(v.every(x => x.hit >= 0.9))
  assert.ok(v.every(x => x.onset_ms !== null && Math.abs(x.onset_ms) <= 80))
})
