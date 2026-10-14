import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createBus, parseOptions } from '../lib/bridge.js'
import { postTake } from '../lib/upload.js'
import { FrameQueue } from '../lib/queue.js'
import { ERR, micErrorCode, errorPayload } from '../lib/errors.js'
import { buildMeta } from '../lib/meta.js'

test('bus delivers name and JSON string to every subscriber', () => {
  const bus = createBus()
  const got = []
  bus.subscribe((n, j) => got.push(['a', n, j]))
  bus.subscribe((n, j) => got.push(['b', n, j]))
  bus.emit('on_ready', { x: 1 })
  assert.deepEqual(got, [['a', 'on_ready', '{"x":1}'], ['b', 'on_ready', '{"x":1}']])
})

test('bus replays sticky events to late subscribers', () => {
  const bus = createBus({ sticky: ['on_unlocked'] })
  bus.emit('on_unlocked', { sr: 48000 })
  bus.emit('on_error', { code: 'net' })
  const got = []
  bus.subscribe((n, j) => got.push([n, j]))
  assert.deepEqual(got, [['on_unlocked', '{"sr":48000}']])
})

test('a throwing subscriber does not break the others', () => {
  const errors = []
  const bus = createBus({ onError: e => errors.push(e) })
  const got = []
  bus.subscribe(() => { throw new Error('boom') })
  bus.subscribe(n => got.push(n))
  bus.subscribe('not a function')
  bus.emit('on_song_end', { t: 1 })
  assert.deepEqual(got, ['on_song_end'])
  assert.equal(errors.length, 1)
})

test('FrameQueue keeps the newest 2000 frames and drains', () => {
  const q = new FrameQueue(2000)
  q.push(...Array.from({ length: 2500 }, (_, i) => ({ i })))
  assert.equal(q.size, 2000)
  const out = q.drain()
  assert.equal(out.length, 2000)
  assert.equal(out[0].i, 500)
  assert.equal(out[1999].i, 2499)
  assert.equal(q.size, 0)
  assert.deepEqual(q.drain(), [])
})

test('error codes match the contract', () => {
  assert.deepEqual(Object.values(ERR).sort(), ['audio_locked', 'decode_failed', 'insecure_context', 'mic_denied', 'mic_not_found', 'net', 'upload_failed', 'worklet_failed'])
  assert.equal(micErrorCode({ name: 'NotAllowedError' }), 'mic_denied')
  assert.equal(micErrorCode({ name: 'SecurityError' }), 'mic_denied')
  assert.equal(micErrorCode({ name: 'NotFoundError' }), 'mic_not_found')
  assert.equal(micErrorCode({ name: 'NotReadableError' }), 'mic_not_found')
  assert.deepEqual(errorPayload('net', new Error('HTTP 500')), { code: 'net', msg: 'HTTP 500' })
  assert.deepEqual(errorPayload('audio_locked', 'suspended'), { code: 'audio_locked', msg: 'suspended' })
})

test('buildMeta produces the contract 3.3 shape', () => {
  const meta = buildMeta({
    songId: 'demo', player: '  Паша ', difficulty: 'normal', challengeId: '', wavT0: -0.15349, wavSr: 16000, lagMs: 47.6,
    frames: [{ t: 1, hz: 0, conf: 0, rms: 0.001 }], client: { ua: 'x', sr: 48000, base_latency: 0.005, output_latency: 0.012, aec: false }
  })
  assert.deepEqual(Object.keys(meta), ['song_id', 'player', 'difficulty', 'challenge_id', 'wav_t0', 'wav_sr', 'lag_ms', 'frames', 'client'])
  assert.equal(meta.player, 'Паша')
  assert.equal(meta.challenge_id, null)
  assert.equal(meta.wav_t0, -0.153)
  assert.equal(meta.lag_ms, 48)
  assert.equal(buildMeta({ player: '', challengeId: 'ab12cd', wavT0: 0, lagMs: 0 }).challenge_id, 'ab12cd')
  assert.equal(buildMeta({ player: '', wavT0: 0, lagMs: 0 }).player, 'Игрок')
})

test('buildMeta cuts the nickname by code points', () => {
  const cut = buildMeta({ player: 'a' + '😀'.repeat(13), wavT0: 0, lagMs: 0 }).player
  assert.equal(cut.isWellFormed(), true)
  assert.ok(Array.from(cut).length <= 24)
  assert.equal(Array.from(cut).length, 14)
  const full = buildMeta({ player: '😀'.repeat(24), wavT0: 0, lagMs: 0 }).player
  assert.equal(Array.from(full).length, 24)
  assert.equal(full, '😀'.repeat(24))
  assert.equal(Array.from(buildMeta({ player: '😀'.repeat(30), wavT0: 0, lagMs: 0 }).player).length, 24)
})

test('parseOptions accepts JSON strings and objects and ignores junk', () => {
  assert.deepEqual(parseOptions('{"lag_ms":40}'), { lag_ms: 40 })
  assert.deepEqual(parseOptions({ aec: true }), { aec: true })
  assert.deepEqual(parseOptions('not json'), {})
  assert.deepEqual(parseOptions('5'), {})
  assert.deepEqual(parseOptions(undefined), {})
})

const uploadEnv = fetch => ({ FormData, Blob, AbortController, setTimeout, clearTimeout, fetch })

test('postTake sends audio and meta as multipart and returns the result', async () => {
  let seen
  const env = uploadEnv(async (url, init) => {
    seen = { url, init }
    return { ok: true, json: async () => ({ take_id: 'tk_1' }) }
  })
  const result = await postTake({ env, url: '/api/v1/takes', wav: new ArrayBuffer(46), meta: { song_id: 'demo' } })
  assert.deepEqual(result, { take_id: 'tk_1' })
  assert.equal(seen.url, '/api/v1/takes')
  assert.equal(seen.init.method, 'POST')
  const audio = seen.init.body.get('audio')
  assert.equal(audio.type, 'audio/wav')
  assert.equal(audio.name, 'take.wav')
  assert.equal(audio.size, 46)
  assert.deepEqual(JSON.parse(seen.init.body.get('meta')), { song_id: 'demo' })
})

test('postTake rejects on HTTP errors', async () => {
  const env = uploadEnv(async () => ({ ok: false, status: 422, text: async () => 'bad meta' }))
  await assert.rejects(postTake({ env, url: '/x', wav: new ArrayBuffer(4), meta: {} }), /HTTP 422 bad meta/)
})

test('postTake aborts after the timeout', async () => {
  const env = uploadEnv((url, init) => new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted')))))
  await assert.rejects(postTake({ env, url: '/x', wav: new ArrayBuffer(4), meta: {}, timeoutMs: 20 }), /aborted/)
})
