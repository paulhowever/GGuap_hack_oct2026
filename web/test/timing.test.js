import { test } from 'node:test'
import assert from 'node:assert/strict'
import { frameTime, contextNow, estimateLagMs, isBtSuspect, toMs, resolveLagMs, noiseFloor, gateFrom, toDb, classifyFrame } from '../lib/timing.js'

test('frameTime uses the window centre, t0 and lag', () => {
  assert.equal(frameTime(48000 + 1024, 48000, 0.15, 0), 0.85)
  assert.equal(Math.round(frameTime(96000 + 1024, 48000, 0.5, 0.1) * 1e9) / 1e9, 1.4)
})

test('contextNow prefers getOutputTimestamp', () => {
  const t = contextNow({ currentTime: 9, outputLatency: 0.02, baseLatency: 0.01, ts: { contextTime: 10, performanceTime: 5000 }, perfNow: 5250 })
  assert.equal(t, 10.25)
})

test('contextNow falls back to currentTime minus latencies', () => {
  assert.equal(contextNow({ currentTime: 10, outputLatency: 0.02, baseLatency: 0.01, ts: null, perfNow: 0 }), 9.97)
  assert.equal(contextNow({ currentTime: 10, outputLatency: undefined, baseLatency: 0.01, ts: { contextTime: 0, performanceTime: 0 }, perfNow: 0 }), 9.99)
})

test('estimateLagMs sums latencies with a 20 ms default for the mic track', () => {
  assert.equal(estimateLagMs({ outputLatency: 0.012, baseLatency: 0.005, trackLatency: undefined }), 37)
  assert.equal(estimateLagMs({ outputLatency: 0.012, baseLatency: 0.005, trackLatency: 0.01 }), 27)
  assert.equal(estimateLagMs({ outputLatency: NaN, baseLatency: undefined, trackLatency: NaN }), 20)
  assert.equal(estimateLagMs({ outputLatency: Infinity, baseLatency: 0.005, trackLatency: 0.01 }), 0)
})

test('estimateLagMs adds 200 ms instead of the mic track for Bluetooth output', () => {
  assert.equal(estimateLagMs({ outputLatency: 0.15, baseLatency: 0.01, trackLatency: 0.01, bt: true }), 360)
  assert.equal(estimateLagMs({ outputLatency: 0.15, baseLatency: 0.01, trackLatency: undefined, bt: true }), 360)
  assert.equal(estimateLagMs({ outputLatency: 0.15, baseLatency: 0.01, trackLatency: 0.01, bt: false }), 170)
})

test('isBtSuspect triggers above 100 ms output latency', () => {
  assert.equal(isBtSuspect(0.15), true)
  assert.equal(isBtSuspect(0.1), false)
  assert.equal(isBtSuspect(undefined), false)
})

test('toMs parses stored strings and rejects junk', () => {
  assert.equal(toMs('48'), 48)
  assert.equal(toMs(47.6), 48)
  assert.equal(toMs(''), null)
  assert.equal(toMs(null), null)
  assert.equal(toMs('abc'), null)
})

test('resolveLagMs priority is session, pinned, stored, estimated', () => {
  assert.equal(resolveLagMs({ session: 10, pinned: 20, stored: 30, estimated: 40 }), 10)
  assert.equal(resolveLagMs({ session: null, pinned: 20, stored: 30, estimated: 40 }), 20)
  assert.equal(resolveLagMs({ session: null, pinned: null, stored: 30, estimated: 40 }), 30)
  assert.equal(resolveLagMs({ session: null, pinned: null, stored: null, estimated: 40 }), 40)
  assert.equal(resolveLagMs({ session: 0, pinned: 20, stored: 30, estimated: 40 }), 0)
  assert.equal(resolveLagMs({ session: NaN, pinned: Infinity, stored: undefined, estimated: 40 }), 40)
  assert.equal(resolveLagMs({ session: NaN, pinned: null, stored: null, estimated: NaN }), 0)
  assert.equal(resolveLagMs({ session: null, pinned: null, stored: null, estimated: undefined }), 0)
})

test('noise floor, gate and dB', () => {
  assert.equal(noiseFloor([0.001, 0.002, 0.5]), 0.002)
  assert.equal(gateFrom(0.001), 0.01)
  assert.equal(gateFrom(0.01), 0.03)
  assert.equal(gateFrom(0.2), 0.05)
  assert.equal(toDb(0.01), -40)
  assert.equal(toDb(0), -120)
})

test('classifyFrame keeps voiced frames and zeroes the rest', () => {
  const p = { sr: 48000, t0: 0.15, lagS: 0.05, gate: 0.01, clarityMin: 0.85 }
  const E = 48000 + 1024
  assert.deepEqual(classifyFrame({ E, hz: 261.63, clarity: 0.97, rms: 0.04217 }, p), { t: 0.8, hz: 261.6, conf: 0.97, rms: 0.0422 })
  assert.equal(classifyFrame({ E, hz: 261.63, clarity: 0.8, rms: 0.04 }, p).hz, 0)
  assert.equal(classifyFrame({ E, hz: 261.63, clarity: 0.97, rms: 0.005 }, p).hz, 0)
  assert.equal(classifyFrame({ E, hz: 40, clarity: 0.97, rms: 0.04 }, p).hz, 0)
  assert.equal(classifyFrame({ E, hz: 1500, clarity: 0.97, rms: 0.04 }, p).conf, 0)
})
