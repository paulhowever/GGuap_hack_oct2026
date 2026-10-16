import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createVoice } from '../voice.js'

const CID = '01234567-89ab-cdef-0123-456789abcdef'
const SONG = { id: 'demo', audio: { minus: '/media/demo.mp3', duration: 6 }, lines: [] }

function item(take_id, extra = {}) {
  return { take_id, song_id: 'demo', difficulty: 'normal', offset_s: 0.2, offset_source: 'measured', audio: `/api/v1/published/${take_id}/audio`, minus: '/media/demo.mp3', ...extra }
}

function audioEnv({ items = { tk_1: item('tk_1'), tk_2: item('tk_2') }, badMinus = null, publishReply, vocalDecodeFails = false } = {}) {
  const sources = []
  const gains = []
  const posts = []
  const gets = []
  const gates = []
  const store = { 'voice.client_id': CID }
  const ctl = { hold: false }
  class Node {
    constructor() {
      this.gain = { value: 1 }
      this.buffer = null
      this.onended = null
      this.out = null
      this.starts = []
      this.stops = []
    }
    connect(to) {
      this.out = to
    }
    disconnect() {
      this.out = null
    }
    start(...a) {
      this.starts.push(a)
    }
    stop(...a) {
      this.stops.push(a)
    }
  }
  class Ctx extends Node {
    constructor() {
      super()
      this.state = 'suspended'
      this.sampleRate = 16000
      this.currentTime = 0
      this.destination = new Node()
      this.audioWorklet = { addModule: () => Promise.resolve() }
      env.ctx = this
    }
    resume() {
      this.state = 'running'
      return Promise.resolve()
    }
    createMediaStreamSource() {
      return new Node()
    }
    createGain() {
      const n = new Node()
      gains.push(n)
      return n
    }
    createOscillator() {
      const n = new Node()
      n.frequency = { value: 0 }
      return n
    }
    createBufferSource() {
      const n = new Node()
      sources.push(n)
      return n
    }
    decodeAudioData(data) {
      const done = () => (vocalDecodeFails && data.tag === 'vocal' ? Promise.reject(new Error('EncodingError')) : Promise.resolve({ tag: data.tag, duration: data.duration }))
      if (!ctl.hold) return done()
      return new Promise((resolve, reject) => gates.push(() => done().then(resolve, reject)))
    }
  }
  class Tap {
    constructor() {
      this.port = { onmessage: null, postMessage() {} }
      env.taps.push(this)
    }
    connect() {}
  }
  const stream = { getTracks: () => [], getAudioTracks: () => [{ getSettings: () => ({ latency: 0.01 }) }] }
  const json = (body, status = 200) => Promise.resolve({ ok: status < 300, status, json: async () => body, text: async () => JSON.stringify(body) })
  const bytes = body => Promise.resolve({ ok: true, status: 200, arrayBuffer: async () => body })
  const env = {
    setTimeout: fn => fn(),
    clearTimeout: () => {},
    taps: [],
    sources,
    gains,
    posts,
    gets,
    ctl,
    release() {
      while (gates.length) gates.shift()()
    },
    isSecureContext: true,
    performance: { now: () => 0 },
    AudioContext: Ctx,
    AudioWorkletNode: Tap,
    FormData,
    Blob,
    AbortController,
    localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v) } },
    navigator: { userAgent: 'test', mediaDevices: { getUserMedia: () => Promise.resolve(stream) } },
    fetch(u, o) {
      const path = String(u)
      if (o?.method === 'POST') {
        posts.push([path, typeof o.body === 'string' ? JSON.parse(o.body) : null])
        if (path.endsWith('/api/v1/takes')) return json({ take_id: 'tk_1', latency: {} })
        if (path.endsWith('/api/v1/sessions')) return json({ token: 'tok' })
        if (publishReply) return publishReply(path)
        return json({ take_id: posts.at(-1)[1]?.take_id, published: true })
      }
      gets.push(path)
      if (path.endsWith('/api/v1/songs/demo')) return json(SONG)
      if (path.endsWith('/audio')) return bytes({ tag: 'vocal', duration: 4 })
      if (path.endsWith('.mp3')) return path === badMinus ? json({ detail: 'Not Found' }, 404) : bytes({ tag: path, duration: 6 })
      const m = path.match(/\/api\/v1\/published\/([^/]+)$/)
      if (m && items[m[1]]) return json(items[m[1]])
      return json({ detail: 'not_published' }, 404)
    }
  }
  return env
}

function record(voice) {
  const events = []
  voice.subscribe((name, json) => events.push([name, JSON.parse(json)]))
  return events
}

const named = (events, name) => events.filter(e => e[0] === name).map(e => e[1])

async function ready(opts) {
  const env = audioEnv(opts)
  const v = createVoice({}, env)
  const events = record(v)
  await v.unlock()
  await v.load_song('demo')
  return { env, v, events, song: env.sources.length }
}

async function sungAndSubmitted(env, v) {
  v.start()
  env.taps[0].port.onmessage({ data: { pcm: new Float32Array(1600).fill(0.1), F: 4800 } })
  await v.stop()
  assert.equal(await v.submit('Паша', null), true)
}

const vocalOf = env => env.sources.find(n => n.buffer?.tag === 'vocal')

test('publish sends wav_t0 of the last on_result take and null for another take', async () => {
  const { env, v, events } = await ready()
  await sungAndSubmitted(env, v)
  assert.equal(await v.publish('tk_1'), true)
  assert.equal(await v.publish('tk_9'), true)
  const pubs = env.posts.filter(p => p[0].endsWith('/api/v1/published'))
  assert.deepEqual(pubs[0][1], { take_id: 'tk_1', client_id: CID, wav_t0: 0.15 })
  assert.deepEqual(pubs[1][1], { take_id: 'tk_9', client_id: CID, wav_t0: null })
  assert.deepEqual(named(events, 'on_published'), [
    { take_id: 'tk_1', published: true, ok: true, code: null },
    { take_id: 'tk_9', published: true, ok: true, code: null }
  ])
})

test('publish reports the backend error code and a network failure as net', async () => {
  const env = audioEnv({ publishReply: () => Promise.resolve({ ok: false, status: 403, json: async () => ({ detail: 'not_owner' }) }) })
  const v = createVoice({}, env)
  const events = record(v)
  assert.equal(await v.publish('tk_1'), false)
  env.fetch = () => Promise.reject(new TypeError('fetch failed'))
  assert.equal(await v.unpublish('tk_1'), false)
  assert.deepEqual(named(events, 'on_published'), [
    { take_id: 'tk_1', published: true, ok: false, code: 'not_owner' },
    { take_id: 'tk_1', published: false, ok: false, code: 'net' }
  ])
  assert.deepEqual(named(events, 'on_error'), [])
})

test('unpublish posts the client id to the remove route', async () => {
  const env = audioEnv()
  const v = createVoice({}, env)
  const events = record(v)
  assert.equal(await v.unpublish('tk_1'), true)
  assert.deepEqual(env.posts, [['/api/v1/published/tk_1/remove', { client_id: CID }]])
  assert.deepEqual(named(events, 'on_published'), [{ take_id: 'tk_1', published: false, ok: true, code: null }])
})

test('listen before unlock ends with audio_locked and no on_error', async () => {
  const env = audioEnv()
  const v = createVoice({}, env)
  const events = record(v)
  assert.equal(await v.listen('tk_1'), false)
  assert.deepEqual(events, [['on_listen_end', { take_id: 'tk_1', reason: 'error', code: 'audio_locked' }]])
  assert.deepEqual(env.gets, [])
})

test('listen is refused while a song is playing', async () => {
  const { env, v, events, song } = await ready()
  v.start()
  assert.equal(await v.listen('tk_1'), false)
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'error', code: 'audio_locked' }])
  assert.equal(env.sources.length, song + 1)
  assert.deepEqual(named(events, 'on_listen'), [])
})

test('listen is refused while calibrating', async () => {
  const { env, v, events } = await ready()
  const cal = v.calibrate()
  assert.equal(await v.listen('tk_1'), false)
  await cal
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'error', code: 'audio_locked' }])
  assert.equal(vocalOf(env), undefined)
})

test('listen plays the vocal over the loaded minus through the music gain, aligned by offset_s', async () => {
  const { env, v, events, song } = await ready()
  const music = env.gains[1]
  assert.equal(await v.listen('tk_1'), true)
  const fresh = env.sources.slice(song)
  assert.equal(fresh.length, 2)
  const minus = fresh.find(n => n.buffer.tag === '/media/demo.mp3')
  const vocal = vocalOf(env)
  assert.equal(minus.out, music)
  assert.deepEqual(minus.starts, [[0.1]])
  assert.deepEqual(vocal.starts, [[0.1 + 0.2]])
  assert.equal(vocal.out, env.ctx.destination)
  assert.equal(env.gets.filter(g => g.endsWith('.mp3')).length, 1)
  assert.deepEqual(named(events, 'on_listen'), [{ take_id: 'tk_1', duration: 4.2 }])
  v.configure({ music_volume: 0.3 })
  assert.equal(music.gain.value, 0.3)
})

test('a negative offset skips the head of the vocal', async () => {
  const { env, v, events } = await ready({ items: { tk_1: item('tk_1', { offset_s: -0.25 }) } })
  assert.equal(await v.listen('tk_1'), true)
  assert.deepEqual(vocalOf(env).starts, [[0.1, 0.25]])
  assert.deepEqual(named(events, 'on_listen'), [{ take_id: 'tk_1', duration: 3.75 }])
})

test('a cover of another song fetches its own minus and plays the vocal alone when that fails', async () => {
  const other = { tk_1: item('tk_1', { song_id: 'other', minus: '/media/other.mp3' }) }
  const a = await ready({ items: other })
  assert.equal(await a.v.listen('tk_1'), true)
  assert.ok(a.env.gets.includes('/media/other.mp3'))
  assert.equal(a.env.sources.slice(a.song).filter(n => n.starts.length).length, 2)
  const b = await ready({ items: other, badMinus: '/media/other.mp3' })
  assert.equal(await b.v.listen('tk_1'), true)
  const started = b.env.sources.slice(b.song).filter(n => n.starts.length)
  assert.deepEqual(started.map(n => n.buffer.tag), ['vocal'])
  assert.deepEqual(named(b.events, 'on_listen'), [{ take_id: 'tk_1', duration: 4.2 }])
  assert.deepEqual(named(b.events, 'on_error'), [])
})

test('the natural end of the vocal emits on_listen_end ended exactly once', async () => {
  const { env, v, events } = await ready()
  await v.listen('tk_1')
  const vocal = vocalOf(env)
  vocal.onended()
  vocal.onended?.()
  assert.equal(v.listen_stop(), false)
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'ended', code: null }])
})

test('listen_stop stops the nodes and a late onended does not emit a second end', async () => {
  const { env, v, events, song } = await ready()
  await v.listen('tk_1')
  const fresh = env.sources.slice(song)
  const late = vocalOf(env).onended
  assert.equal(v.listen_stop(), true)
  late()
  for (const n of fresh) assert.equal(n.stops.length > 0, true)
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'stopped', code: null }])
})

test('start() during an in-flight listen plays no cover and ends it as stopped', async () => {
  const { env, v, events, song } = await ready()
  env.ctl.hold = true
  const pending = v.listen('tk_1')
  await new Promise(r => setImmediate(r))
  assert.equal(v.start(), true)
  env.ctl.hold = false
  env.release()
  assert.equal(await pending, false)
  const started = env.sources.slice(song).filter(n => n.starts.length)
  assert.equal(started.length, 1)
  assert.equal(started[0].buffer.tag, '/media/demo.mp3')
  assert.equal(vocalOf(env), undefined)
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'stopped', code: null }])
  assert.deepEqual(named(events, 'on_listen'), [])
})

test('two listens in a row keep only the second', async () => {
  const { env, v, events, song } = await ready()
  env.ctl.hold = true
  const first = v.listen('tk_1')
  await new Promise(r => setImmediate(r))
  const second = v.listen('tk_2')
  await new Promise(r => setImmediate(r))
  env.ctl.hold = false
  env.release()
  assert.equal(await first, false)
  assert.equal(await second, true)
  const vocals = env.sources.slice(song).filter(n => n.buffer?.tag === 'vocal' && n.starts.length)
  assert.equal(vocals.length, 1)
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'stopped', code: null }])
  assert.deepEqual(named(events, 'on_listen'), [{ take_id: 'tk_2', duration: 4.2 }])
})

test('load_song and calibrate stop a playing cover first', async () => {
  const { v, events } = await ready()
  await v.listen('tk_1')
  await v.load_song('demo')
  await v.listen('tk_2')
  await v.calibrate()
  assert.deepEqual(named(events, 'on_listen_end'), [
    { take_id: 'tk_1', reason: 'stopped', code: null },
    { take_id: 'tk_2', reason: 'stopped', code: null }
  ])
})

test('a missing cover or a broken vocal ends with an error code and no on_error', async () => {
  const a = await ready()
  assert.equal(await a.v.listen('tk_404'), false)
  assert.deepEqual(named(a.events, 'on_listen_end'), [{ take_id: 'tk_404', reason: 'error', code: 'not_published' }])
  const b = await ready({ vocalDecodeFails: true })
  assert.equal(await b.v.listen('tk_1'), false)
  assert.deepEqual(named(b.events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'error', code: 'decode_failed' }])
  assert.deepEqual([...named(a.events, 'on_error'), ...named(b.events, 'on_error')], [])
  assert.equal(vocalOf(b.env), undefined)
})

test('a context suspended while the cover loads ends with audio_locked and plays nothing', async () => {
  const { env, v, events } = await ready()
  env.ctl.hold = true
  const pending = v.listen('tk_1')
  await new Promise(r => setImmediate(r))
  env.ctx.state = 'suspended'
  env.ctl.hold = false
  env.release()
  assert.equal(await pending, false)
  assert.equal(vocalOf(env), undefined)
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'error', code: 'audio_locked' }])
})

test('listen and publish without a take id fail without a request', async () => {
  const { env, v, events } = await ready()
  const before = env.gets.length
  assert.equal(await v.listen(''), false)
  assert.equal(await v.publish(null), false)
  assert.equal(env.gets.length, before)
  assert.deepEqual(env.posts, [])
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: '', reason: 'error', code: 'not_published' }])
  assert.deepEqual(named(events, 'on_published'), [{ take_id: '', published: true, ok: false, code: 'take_not_found' }])
})

test('start() while a cover is playing stops its nodes before the song starts', async () => {
  const { env, v, events, song } = await ready()
  await v.listen('tk_1')
  const cover = env.sources.slice(song)
  assert.equal(v.start(), true)
  for (const n of cover) assert.equal(n.stops.length > 0, true)
  assert.deepEqual(named(events, 'on_listen_end'), [{ take_id: 'tk_1', reason: 'stopped', code: null }])
})
