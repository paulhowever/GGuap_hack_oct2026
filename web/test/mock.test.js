import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { MODES, rng, noteAt, mockFrame, mockFrames } from '../lib/mock.js'
import { hzToMidi, foldCents } from '../lib/pitch.js'

const ref = JSON.parse(readFileSync(new URL('../../contracts/fixtures/demo.reference.json', import.meta.url)))
const cents = (hz, midi) => 100 * (hzToMidi(hz) - midi)

test('rng is deterministic and in [0, 1)', () => {
  const a = rng(42)
  const b = rng(42)
  const xs = Array.from({ length: 100 }, a)
  assert.deepEqual(xs, Array.from({ length: 100 }, b))
  assert.ok(xs.every(x => x >= 0 && x < 1))
})

test('noteAt finds the note under a time', () => {
  assert.equal(noteAt(ref, 2.6).note.i, 0)
  assert.equal(noteAt(ref, 6.1).line.i, 1)
  assert.equal(noteAt(ref, 3.4), null)
})

test('perfect frames stay within 30 cents of the note', () => {
  const rand = rng(1)
  for (let t = 2.5; t < 3.3; t += 0.01) {
    const f = mockFrame(ref, 'perfect', t, rand)
    assert.ok(Math.abs(cents(f.hz, 60)) <= 30.5, `t=${t} hz=${f.hz}`)
    assert.equal(f.conf, 0.95)
  }
})

test('gaps between notes are unvoiced', () => {
  assert.deepEqual(mockFrame(ref, 'perfect', 3.4, rng(1)), { t: 3.4, hz: 0, conf: 0, rms: 0.004 })
})

test('offkey misses even the easy tolerance', () => {
  const f = mockFrame(ref, 'offkey', 2.6, rng(1))
  assert.ok(Math.abs(foldCents(cents(f.hz, 60))) > 200)
})

test('octave mode sings an octave away and folds back onto the note', () => {
  const low = mockFrame(ref, 'octave', 2.6, rng(1))
  const high = mockFrame(ref, 'octave', 6.1, rng(1))
  assert.ok(Math.abs(cents(low.hz, 60) + 1200) <= 30.5)
  assert.ok(Math.abs(cents(high.hz, 65) - 1200) <= 30.5)
  assert.ok(Math.abs(foldCents(cents(low.hz, 60))) <= 30.5)
})

test('late200 starts every note 200 ms late', () => {
  assert.equal(mockFrame(ref, 'late200', 2.6, rng(1)).hz, 0)
  assert.ok(mockFrame(ref, 'late200', 2.75, rng(1)).hz > 0)
})

test('silent mode never voices', () => {
  assert.ok(mockFrames(ref, 'silent', 0, 12, rng(1)).every(f => f.hz === 0))
})

test('mockFrames covers (from, to] on a fixed hop grid without duplicates', () => {
  const a = mockFrames(ref, 'perfect', 0, 1, rng(1), 0.01)
  const b = mockFrames(ref, 'perfect', 1, 2, rng(1), 0.01)
  assert.equal(a.length, 100)
  assert.equal(b.length, 100)
  assert.equal(a.at(-1).t, 1)
  assert.equal(b[0].t, 1.01)
})

test('all modes from the design are supported', () => {
  assert.deepEqual(MODES, ['perfect', 'offkey', 'octave', 'late200', 'silent'])
})
