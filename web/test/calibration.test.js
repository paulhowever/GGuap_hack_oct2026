import { test } from 'node:test'
import assert from 'node:assert/strict'
import { clickTimes, onsetThreshold, detectOnsets, estimateLag } from '../lib/calibration.js'

const SR = 48000
const HOP = 512

function framesFor(onsetTimes, seconds) {
  const frames = []
  for (let E = HOP; E / SR < seconds; E += HOP) {
    const t = (E - HOP / 2) / SR
    const loud = onsetTimes.some(o => t >= o && t < o + 0.08)
    frames.push({ E, rms: loud ? 0.3 : 0.003 })
  }
  return frames
}

test('clickTimes spaces 8 clicks by 500 ms', () => {
  assert.deepEqual(clickTimes(1), [1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5])
})

test('onsetThreshold is 4x the floor with a 0.01 minimum', () => {
  assert.equal(onsetThreshold(0.001), 0.01)
  assert.equal(onsetThreshold(0.005), 0.02)
})

test('detectOnsets finds rising edges once per clap', () => {
  const onsets = detectOnsets(framesFor([1.0, 1.5, 2.0], 3), { sr: SR, threshold: 0.02 })
  assert.equal(onsets.length, 3)
  onsets.forEach((t, i) => assert.ok(Math.abs(t - [1.0, 1.5, 2.0][i]) < HOP / SR))
})

test('estimateLag returns the median lag in ms with outliers rejected', () => {
  const clicks = clickTimes(1)
  const jitter = [0.004, -0.006, 0.002, 0, -0.003, 0.005, 0.18, -0.001]
  const onsets = clicks.map((c, i) => c + 0.12 + jitter[i])
  assert.deepEqual(estimateLag(clicks, onsets), { lag_ms: 120, hits: 7 })
})

test('estimateLag needs at least 5 hits', () => {
  const clicks = clickTimes(1)
  const onsets = clicks.slice(0, 4).map(c => c + 0.1)
  assert.deepEqual(estimateLag(clicks, onsets), { lag_ms: null, hits: 4 })
  assert.deepEqual(estimateLag(clicks, []), { lag_ms: null, hits: 0 })
})

test('estimateLag works end to end from frames', () => {
  const clicks = clickTimes(1)
  const frames = framesFor(clicks.map(c => c + 0.2), 6)
  const r = estimateLag(clicks, detectOnsets(frames, { sr: SR, threshold: 0.02 }))
  assert.equal(r.hits, 8)
  assert.ok(Math.abs(r.lag_ms - 200) <= 11, `lag ${r.lag_ms}`)
})

test('estimateLag rejects lags that alias into the neighbouring click window', () => {
  const clicks = clickTimes(1)
  for (const lag of [0.41, 0.45]) {
    const r = estimateLag(clicks, clicks.map(c => c + lag))
    assert.equal(r.lag_ms, null, `lag ${lag}`)
  }
})
