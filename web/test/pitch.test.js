import { test } from 'node:test'
import assert from 'node:assert/strict'
import { hzToMidi, midiToHz, foldToNote, foldCents, isHit } from '../lib/pitch.js'
import { round, median, clamp } from '../lib/num.js'

test('hzToMidi maps A4 and C4 and rejects silence', () => {
  assert.equal(hzToMidi(440), 69)
  assert.equal(round(hzToMidi(261.6256), 3), 60)
  assert.equal(hzToMidi(0), null)
  assert.equal(hzToMidi(-5), null)
})

test('midiToHz is the inverse of hzToMidi', () => {
  assert.equal(round(midiToHz(60), 2), 261.63)
  assert.equal(round(hzToMidi(midiToHz(57.3)), 6), 57.3)
})

test('foldToNote moves the sung pitch into the octave of the note', () => {
  assert.equal(round(foldToNote(48.2, 60), 6), 60.2)
  assert.equal(round(foldToNote(71.9, 60), 6), 59.9)
  assert.equal(foldToNote(60, 60), 60)
})

test('foldCents matches the backend python modulo convention', () => {
  assert.equal(foldCents(1150), -50)
  assert.equal(foldCents(-1150), 50)
  assert.equal(foldCents(1200), 0)
  assert.equal(foldCents(-30), -30)
})

test('isHit uses folded cents against the tolerance', () => {
  assert.equal(isHit(midiToHz(60.5), 60, 120), true)
  assert.equal(isHit(midiToHz(48.5), 60, 120), true)
  assert.equal(isHit(midiToHz(61.5), 60, 120), false)
  assert.equal(isHit(0, 60, 120), false)
})

test('num helpers', () => {
  assert.equal(round(1.23456, 3), 1.235)
  assert.equal(median([3, 1, 2]), 2)
  assert.equal(median([4, 1, 3, 2]), 2.5)
  assert.equal(median([]), 0)
  assert.equal(clamp(5, 0, 1), 1)
})
