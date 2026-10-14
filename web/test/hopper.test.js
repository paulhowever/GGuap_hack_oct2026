import { test } from 'node:test'
import assert from 'node:assert/strict'
import { PitchDetector } from '../vendor/pitchy.bundle.js'
import { PitchHopper } from '../lib/hopper.js'

const SR = 48000

function run(signal, startFrame = 0, detect) {
  const det = PitchDetector.forFloat32Array(2048)
  const hopper = new PitchHopper({ detect: detect ?? ((w, sr) => det.findPitch(w, sr)) })
  const out = []
  for (let i = 0; i < signal.length; i += 128) hopper.push(signal.subarray(i, i + 128), startFrame + i, SR, out)
  return out
}

const sine = (hz, n, amp = 0.5) => Float32Array.from({ length: n }, (_, i) => amp * Math.sin(2 * Math.PI * hz * i / SR))

test('emits one frame per 512-sample hop with the hop end index', () => {
  const frames = run(sine(220, SR / 2))
  assert.equal(frames.length, Math.floor(SR / 2 / 512))
  assert.deepEqual(frames.slice(0, 3).map(f => f.E), [512, 1024, 1536])
})

test('hop end index follows the absolute context frame', () => {
  const frames = run(sine(220, 4096), 1000)
  assert.equal(frames[0].E, 1512)
})

test('pitchy finds 220 Hz once the window is full', () => {
  const full = run(sine(220, SR / 2)).filter(f => f.E >= 2048)
  for (const f of full) {
    assert.ok(Math.abs(f.hz - 220) < 2, `hz ${f.hz}`)
    assert.ok(f.clarity > 0.9, `clarity ${f.clarity}`)
    assert.ok(Math.abs(f.rms - 0.3536) < 0.01, `rms ${f.rms}`)
  }
})

test('pitchy tracks a sung range from 80 to 1000 Hz', () => {
  for (const hz of [80, 150, 440, 1000]) {
    const f = run(sine(hz, 8192)).at(-1)
    assert.ok(Math.abs(1200 * Math.log2(f.hz / hz)) < 10, `${hz} -> ${f.hz}`)
  }
})

test('silence skips the detector', () => {
  let calls = 0
  const frames = run(new Float32Array(8192), 0, () => { calls++; return [100, 1] })
  assert.equal(calls, 0)
  assert.ok(frames.every(f => f.hz === 0 && f.clarity === 0))
})

test('analysis fits the render budget', () => {
  const det = PitchDetector.forFloat32Array(2048)
  const hopper = new PitchHopper({ detect: (w, sr) => det.findPitch(w, sr) })
  hopper.push(sine(330, 2048), 0, SR)
  const t = performance.now()
  for (let i = 0; i < 200; i++) hopper.analyze(2048 + i * 512, SR)
  const avg = (performance.now() - t) / 200
  assert.ok(avg < 1, `avg ${avg} ms per analysis`)
})
