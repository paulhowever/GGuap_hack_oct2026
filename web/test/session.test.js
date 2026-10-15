import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { requestSession } from '../lib/session.js'
import { createVoice } from '../voice.js'

const ref = JSON.parse(readFileSync(new URL('../../contracts/fixtures/demo.reference.json', import.meta.url)))
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const timers = { setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms, 5)), clearTimeout }
const reply = body => ({ ok: true, status: 200, json: async () => body })

test('requestSession posts song, client and difficulty and returns the token', async () => {
  let seen
  const env = { AbortController, setTimeout, clearTimeout, fetch: async (url, init) => { seen = { url, init }; return reply({ token: 'tok-1', issued_at: 1, expires_in: 900 }) } }
  const token = await requestSession({ env, url: '/api/v1/sessions', songId: 'demo', clientId: 'c-1', difficulty: 'hard' })
  assert.equal(token, 'tok-1')
  assert.equal(seen.url, '/api/v1/sessions')
  assert.equal(seen.init.method, 'POST')
  assert.equal(seen.init.headers['Content-Type'], 'application/json')
  assert.deepEqual(JSON.parse(seen.init.body), { song_id: 'demo', client_id: 'c-1', difficulty: 'hard' })
})

test('requestSession turns every failure into null', async () => {
  const base = { AbortController, setTimeout, clearTimeout }
  const cases = [
    async () => ({ ok: false, status: 503, json: async () => ({}) }),
    async () => { throw new TypeError('Failed to fetch') },
    async () => ({ ok: true, json: async () => { throw new SyntaxError('bad json') } }),
    async () => reply({ token: '' }),
    async () => reply({})
  ]
  for (const fetch of cases) assert.equal(await requestSession({ env: { ...base, fetch }, url: '/x', songId: 'demo', clientId: null, difficulty: 'normal' }), null)
  assert.equal(await requestSession({ env: {}, url: '/x', songId: 'demo', clientId: null, difficulty: 'normal' }), null)
})

test('requestSession gives up after the timeout', async () => {
  const fetch = (url, init) => new Promise((_, reject) => init.signal.addEventListener('abort', () => reject(new Error('aborted'))))
  assert.equal(await requestSession({ env: { AbortController, setTimeout, clearTimeout, fetch }, url: '/x', songId: 'demo', clientId: null, difficulty: 'normal', timeoutMs: 20 }), null)
})

class AudioStub {
  constructor() {
    this.gain = { value: 1 }
    this.frequency = { value: 440 }
  }
  connect() {}
  disconnect() {}
  start() {}
  stop() {}
}

function studio(sessionReplies, takeReplies = []) {
  const sessions = []
  const takes = []
  const errors = []
  const taps = []
  const store = {}
  class Ctx {
    constructor() {
      this.state = 'suspended'
      this.sampleRate = 48000
      this.currentTime = 0
      this.outputLatency = 0.01
      this.baseLatency = 0.005
      this.destination = new AudioStub()
      this.audioWorklet = { addModule: async () => {} }
    }
    resume() {
      this.state = 'running'
      return Promise.resolve()
    }
    createGain() {
      return new AudioStub()
    }
    createMediaStreamSource() {
      return new AudioStub()
    }
    createBufferSource() {
      return new AudioStub()
    }
    decodeAudioData() {
      return Promise.resolve({ duration: ref.audio.duration })
    }
  }
  class Tap extends AudioStub {
    constructor() {
      super()
      taps.push(this)
      this.port = {
        onmessage: null,
        postMessage: msg => {
          if (msg.rec === false) queueMicrotask(() => this.port.onmessage({ data: { recDone: true } }))
        }
      }
    }
  }
  const track = { stop() {}, getSettings: () => ({}) }
  const env = {
    ...timers,
    isSecureContext: true,
    performance,
    crypto,
    FormData,
    Blob,
    AbortController,
    AudioContext: Ctx,
    AudioWorkletNode: Tap,
    localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v } },
    navigator: { userAgent: 'node', mediaDevices: { getUserMedia: async () => ({ getTracks: () => [track], getAudioTracks: () => [track] }) } },
    async fetch(url, init = {}) {
      const u = String(url)
      if (u.endsWith('/api/v1/songs/demo')) return reply(ref)
      if (u.endsWith(ref.audio.minus)) return { ok: true, arrayBuffer: async () => new ArrayBuffer(8) }
      if (u.endsWith('/api/v1/sessions')) {
        sessions.push(JSON.parse(init.body))
        return sessionReplies.shift()(init)
      }
      if (u.endsWith('/api/v1/takes')) {
        takes.push(JSON.parse(init.body.get('meta')))
        return takeReplies.length ? takeReplies.shift()() : reply({ take_id: `tk_${takes.length}` })
      }
      return { ok: false, status: 404, text: async () => 'not found' }
    }
  }
  const voice = createVoice({ tap_url: './tap.js' }, env)
  voice.subscribe((name, json) => name === 'on_error' && errors.push(JSON.parse(json)))
  const sing = () => taps[0].port.onmessage({ data: { pcm: new Float32Array(4800).fill(0.1), F: 7200 } })
  async function take() {
    assert.equal(voice.start(), true)
    sing()
    assert.equal(await voice.submit('Паша', ''), true)
  }
  return { voice, sessions, takes, errors, take, sing, store }
}

const ok = token => async () => reply({ token, issued_at: 1, expires_in: 900 })

test('start asks for a session and submit sends its token after client_id', async () => {
  const st = studio([ok('tok-1')])
  await st.voice.unlock()
  await st.voice.load_song('demo')
  await st.take()
  assert.equal(st.sessions.length, 1)
  assert.equal(st.sessions[0].song_id, 'demo')
  assert.equal(st.sessions[0].difficulty, 'normal')
  assert.match(st.sessions[0].client_id, UUID)
  assert.equal(st.takes[0].session_token, 'tok-1')
  assert.equal(st.takes[0].client_id, st.sessions[0].client_id)
  assert.deepEqual(Object.keys(st.takes[0]).slice(0, 3), ['song_id', 'client_id', 'session_token'])
  assert.equal(st.voice._state().session, 'ok')
  assert.deepEqual(st.errors, [])
})

test('start does not wait for the session request', async () => {
  const st = studio([() => new Promise(() => {})])
  await st.voice.unlock()
  await st.voice.load_song('demo')
  assert.equal(st.voice.start(), true)
  assert.equal(JSON.parse(st.voice.poll()).state, 'playing')
  assert.equal(st.voice._state().session, 'pending')
})

test('a failed session request leaves the token null without an error event', async () => {
  for (const fail of [async () => ({ ok: false, status: 503, json: async () => ({}) }), async () => { throw new TypeError('Failed to fetch') }]) {
    const st = studio([fail])
    await st.voice.unlock()
    await st.voice.load_song('demo')
    await st.take()
    assert.equal(st.takes[0].session_token, null)
    assert.equal(st.voice._state().session, 'none')
    assert.deepEqual(st.errors, [])
  }
})

test('every start gets its own token', async () => {
  const st = studio([ok('tok-1'), ok('tok-2')])
  await st.voice.unlock()
  await st.voice.load_song('demo')
  await st.take()
  await st.take()
  assert.equal(st.sessions.length, 2)
  assert.deepEqual(st.takes.map(m => m.session_token), ['tok-1', 'tok-2'])
})

const unavailable = async () => ({ ok: false, status: 503, text: async () => 'unavailable' })

test('requestSession stays non-rejecting when the environment cannot clear the timer', async () => {
  const env = { AbortController, setTimeout, fetch: async () => reply({ token: 'tok-1' }) }
  assert.equal(await requestSession({ env, url: '/x', songId: 'demo', clientId: null, difficulty: 'normal' }), 'tok-1')
})

test('a difficulty changed after start does not leak into the take', async () => {
  const st = studio([ok('tok-1')])
  await st.voice.unlock()
  await st.voice.load_song('demo')
  assert.equal(st.voice.start(), true)
  st.voice.configure('{"difficulty":"hard"}')
  st.sing()
  assert.equal(await st.voice.submit('Паша', ''), true)
  assert.equal(st.sessions[0].difficulty, 'normal')
  assert.equal(st.takes[0].difficulty, st.sessions[0].difficulty)
  assert.equal(st.takes[0].session_token, 'tok-1')
})

test('a difficulty configured before start reaches both the session and the take', async () => {
  const st = studio([ok('tok-1')])
  await st.voice.unlock()
  st.voice.configure('{"difficulty":"hard"}')
  await st.voice.load_song('demo')
  await st.take()
  assert.equal(st.sessions[0].difficulty, 'hard')
  assert.equal(st.takes[0].difficulty, 'hard')
})

test('a client id that changes after start does not leak into the take', async () => {
  const st = studio([ok('tok-1')])
  await st.voice.unlock()
  await st.voice.load_song('demo')
  assert.equal(st.voice.start(), true)
  st.store['voice.client_id'] = '00000000-0000-4000-8000-000000000000'
  st.sing()
  assert.equal(await st.voice.submit('Паша', ''), true)
  assert.match(st.sessions[0].client_id, UUID)
  assert.notEqual(st.sessions[0].client_id, '00000000-0000-4000-8000-000000000000')
  assert.equal(st.takes[0].client_id, st.sessions[0].client_id)
})

test('a second submit of the same take sends no token', async () => {
  const st = studio([ok('tok-1')])
  await st.voice.unlock()
  await st.voice.load_song('demo')
  await st.take()
  assert.equal(await st.voice.submit('Паша', ''), true)
  assert.equal(st.takes.length, 2)
  assert.equal(st.takes[0].session_token, 'tok-1')
  assert.equal(st.takes[1].session_token, null)
  assert.equal(st.voice._take().meta.session_token, null)
})

test('a retry after a failed upload sends no token', async () => {
  const st = studio([ok('tok-1')], [unavailable])
  await st.voice.unlock()
  await st.voice.load_song('demo')
  assert.equal(st.voice.start(), true)
  st.sing()
  assert.equal(await st.voice.submit('Паша', ''), false)
  assert.equal(await st.voice.submit('Паша', ''), true)
  assert.deepEqual(st.takes.map(m => m.session_token), ['tok-1', null])
  assert.deepEqual(st.errors.map(e => e.code), ['upload_failed'])
})

test('concurrent submits of one take send the token only once', async () => {
  const st = studio([ok('tok-1')])
  await st.voice.unlock()
  await st.voice.load_song('demo')
  assert.equal(st.voice.start(), true)
  st.sing()
  assert.deepEqual(await Promise.all([st.voice.submit('Паша', ''), st.voice.submit('Паша', '')]), [true, true])
  assert.deepEqual(st.takes.map(m => m.session_token), ['tok-1', null])
})
