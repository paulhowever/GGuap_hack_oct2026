import { test } from 'node:test'
import assert from 'node:assert/strict'
import { encodeWav, parseWavHeader } from '../lib/wav.js'
import { downsample } from '../lib/resample.js'
import { PcmRecorder } from '../lib/recorder.js'

const sine = (hz, sr, n, amp = 0.5) => Float32Array.from({ length: n }, (_, i) => amp * Math.sin(2 * Math.PI * hz * i / sr))
const rms = x => Math.sqrt(x.reduce((s, v) => s + v * v, 0) / x.length)

test('encodeWav writes a 44-byte PCM16 mono header', () => {
  const buf = encodeWav(new Float32Array(16000), 16000)
  const v = new DataView(buf)
  const tag = o => String.fromCharCode(...new Uint8Array(buf, o, 4))
  assert.equal(buf.byteLength, 44 + 32000)
  assert.equal(tag(0), 'RIFF')
  assert.equal(v.getUint32(4, true), 36 + 32000)
  assert.equal(tag(8), 'WAVE')
  assert.equal(tag(12), 'fmt ')
  assert.equal(v.getUint32(16, true), 16)
  assert.equal(v.getUint16(20, true), 1)
  assert.equal(v.getUint16(22, true), 1)
  assert.equal(v.getUint32(24, true), 16000)
  assert.equal(v.getUint32(28, true), 32000)
  assert.equal(v.getUint16(32, true), 2)
  assert.equal(v.getUint16(34, true), 16)
  assert.equal(tag(36), 'data')
  assert.equal(v.getUint32(40, true), 32000)
})

test('encodeWav scales and clamps samples to int16', () => {
  const v = new DataView(encodeWav(Float32Array.from([0, 1, -1, 2, -2, 0.5, NaN]), 16000))
  const at = i => v.getInt16(44 + 2 * i, true)
  assert.deepEqual([0, 1, 2, 3, 4, 5, 6].map(at), [0, 32767, -32768, 32767, -32768, 16383, 0])
})

test('parseWavHeader reads back rate and duration', () => {
  const h = parseWavHeader(encodeWav(new Float32Array(24000), 16000))
  assert.deepEqual(h, { sampleRate: 16000, channels: 1, bits: 16, frames: 24000, duration: 1.5 })
  assert.equal(parseWavHeader(new ArrayBuffer(10)), null)
})

test('downsample 48k to 16k keeps length, pitch and amplitude', () => {
  const out = downsample(sine(440, 48000, 48000), 48000, 16000)
  assert.equal(out.length, 16000)
  const ideal = sine(440, 16000, 16000)
  let worst = 0
  for (let j = 200; j < 15800; j++) worst = Math.max(worst, Math.abs(out[j] - ideal[j]))
  assert.ok(worst < 0.01, `max error ${worst}`)
})

test('downsample 44.1k to 16k handles a fractional ratio', () => {
  const out = downsample(sine(300, 44100, 44100), 44100, 16000)
  assert.equal(out.length, 16000)
  const ideal = sine(300, 16000, 16000)
  let worst = 0
  for (let j = 200; j < 15800; j++) worst = Math.max(worst, Math.abs(out[j] - ideal[j]))
  assert.ok(worst < 0.01, `max error ${worst}`)
})

test('downsample suppresses content above the new Nyquist', () => {
  const out = downsample(sine(10000, 48000, 48000), 48000, 16000)
  assert.ok(rms(out.subarray(200, 15800)) < 0.01)
})

test('downsample returns a copy when no rate change is needed', () => {
  const x = Float32Array.from([0.1, 0.2])
  const y = downsample(x, 16000, 16000)
  assert.deepEqual(Array.from(y), Array.from(x))
  assert.notEqual(y, x)
})

test('PcmRecorder concatenates blocks and remembers the first frame', () => {
  const r = new PcmRecorder(48000)
  r.push(Float32Array.from([1, 2]), 1000)
  r.push(Float32Array.from([3, 4]), 1002)
  assert.equal(r.firstFrame, 1000)
  assert.deepEqual(Array.from(r.samples()), [1, 2, 3, 4])
})

test('PcmRecorder zero-fills gaps and drops overlaps', () => {
  const r = new PcmRecorder(48000)
  r.push(Float32Array.from([1, 1]), 0)
  r.push(Float32Array.from([2, 2]), 4)
  r.push(Float32Array.from([9, 3]), 5)
  assert.deepEqual(Array.from(r.samples()), [1, 1, 0, 0, 2, 2, 3])
})

test('PcmRecorder stops at the maximum duration', () => {
  const r = new PcmRecorder(10, 1)
  r.push(new Float32Array(8), 0)
  r.push(new Float32Array(8), 8)
  assert.equal(r.samples().length, 10)
  assert.equal(r.duration, 1)
})
