import { test } from 'node:test'
import assert from 'node:assert/strict'

const registered = {}
globalThis.AudioWorkletProcessor = class {
  constructor() {
    this.sent = []
    const sent = this.sent
    this.port = {
      onmessage: null,
      postMessage(m) {
        sent.push(m)
      }
    }
  }
}
globalThis.registerProcessor = (name, cls) => {
  registered[name] = cls
}
globalThis.sampleRate = 48000
globalThis.currentFrame = 0

await import('../tap.js')

const Q = 128
const CHUNK = 4096

function tone() {
  const b = new Float32Array(Q)
  for (let k = 0; k < Q; k++) b[k] = 0.3 * Math.sin((2 * Math.PI * 220 * (globalThis.currentFrame + k)) / globalThis.sampleRate)
  return b
}

function processor() {
  globalThis.currentFrame = 0
  return new registered.tap()
}

function run(p, quanta, inputs = () => [[tone()]]) {
  for (let q = 0; q < quanta; q++) {
    assert.equal(p.process(inputs()), true)
    globalThis.currentFrame += Q
  }
}

const send = (p, data) => p.port.onmessage({ data })
const chunks = p => p.sent.filter(m => m.pcm).map(m => [m.F, m.pcm.length])
const toneAt = F => 0.3 * Math.sin((2 * Math.PI * 220 * F) / globalThis.sampleRate)

test('the worklet registers itself as tap', () => {
  assert.equal(typeof registered.tap, 'function')
})

test('recording posts 4096-sample chunks stamped with the frame of their first sample', () => {
  const p = processor()
  run(p, 10)
  assert.deepEqual(chunks(p), [])
  const recStart = globalThis.currentFrame
  send(p, { rec: true })
  run(p, 70)
  assert.deepEqual(chunks(p), [[recStart, CHUNK], [recStart + CHUNK, CHUNK]])
  const first = p.sent.find(m => m.pcm)
  assert.ok(Math.abs(first.pcm[0] - toneAt(recStart)) < 1e-6)
  assert.ok(Math.abs(first.pcm[CHUNK - 1] - toneAt(recStart + CHUNK - 1)) < 1e-6)
})

test('stopping posts the partial tail before recDone and then records nothing', () => {
  const p = processor()
  send(p, { rec: true })
  run(p, 70)
  send(p, { rec: false })
  const tail = p.sent.at(-2)
  assert.deepEqual([tail.F, tail.pcm.length], [2 * CHUNK, 70 * Q - 2 * CHUNK])
  assert.deepEqual(p.sent.at(-1), { recDone: true })
  const n = chunks(p).length
  run(p, 40)
  assert.equal(chunks(p).length, n)
})

test('pitch frames come in batches of at least three, one per 512-sample hop, near 220 Hz', () => {
  const p = processor()
  run(p, 120)
  const batches = p.sent.filter(m => m.frames)
  assert.ok(batches.length > 0)
  for (const b of batches) assert.ok(b.frames.length >= 3)
  const frames = batches.flatMap(b => b.frames)
  assert.equal(frames[0].E, 512)
  for (let k = 1; k < frames.length; k++) assert.equal(frames[k].E - frames[k - 1].E, 512)
  for (const f of frames.filter(f => f.E >= 2048)) assert.ok(Math.abs(f.hz - 220) < 2, `hz ${f.hz}`)
})

test('a quantum without input mid-recording flushes the chunk so the next one keeps its true frame', () => {
  const p = processor()
  run(p, 10)
  const recStart = globalThis.currentFrame
  send(p, { rec: true })
  run(p, 10)
  run(p, 1, () => [[]])
  run(p, 1, () => [])
  const resume = globalThis.currentFrame
  run(p, 5)
  send(p, { rec: false })
  assert.deepEqual(chunks(p), [[recStart, 10 * Q], [resume, 5 * Q]])
  const after = p.sent.filter(m => m.pcm)[1]
  assert.ok(Math.abs(after.pcm[0] - toneAt(resume)) < 1e-6)
  assert.deepEqual(p.sent.at(-1), { recDone: true })
})
