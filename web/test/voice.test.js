import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createVoice, installVoice } from '../voice.js'
import { createMockVoice } from '../voice.mock.js'
import { parseWavHeader } from '../lib/wav.js'
import { frameTime } from '../lib/timing.js'

const BRIDGE = ['subscribe', 'unlock', 'configure', 'load_song', 'start', 'stop', 'poll', 'submit', 'calibrate', 'client_id', 'publish', 'unpublish', 'listen', 'listen_stop']

function listen(voice) {
  const events = []
  voice.subscribe((name, json) => events.push([name, JSON.parse(json)]))
  return events
}

class SuspendedCtx {
  constructor() {
    this.state = 'suspended'
    this.sampleRate = 48000
  }
  resume() {
    return Promise.resolve()
  }
}

class RunningCtx extends SuspendedCtx {
  resume() {
    this.state = 'running'
    return Promise.resolve()
  }
}

class HangingCtx extends SuspendedCtx {
  resume() {
    return new Promise(() => {})
  }
}

const idle = { setTimeout: () => 0 }
const instant = { setTimeout: fn => fn() }
const denied = () => Promise.reject(Object.assign(new Error('Permission denied'), { name: 'NotAllowedError' }))

test('real and mock engines expose the same bridge methods', () => {
  for (const v of [createVoice({}, {}), createMockVoice('perfect', {}, {})]) {
    for (const k of BRIDGE) assert.equal(typeof v[k], 'function', k)
  }
})

test('poll before unlock is an idle frame-less JSON string', () => {
  const p = createVoice({}, {}).poll()
  assert.equal(typeof p, 'string')
  assert.deepEqual(JSON.parse(p), { t_now: 0, state: 'idle', level: 0, frames: [] })
})

test('unlock outside a secure context reports insecure_context', async () => {
  const v = createVoice({}, { isSecureContext: false, navigator: {} })
  const events = listen(v)
  assert.equal(await v.unlock(), false)
  assert.deepEqual(events[0], ['on_error', { code: 'insecure_context', msg: 'getUserMedia unavailable: use https or localhost' }])
})

test('a suspended AudioContext reports audio_locked', async () => {
  const v = createVoice({}, { ...idle, isSecureContext: true, AudioContext: SuspendedCtx, navigator: { mediaDevices: { getUserMedia: denied } } })
  const events = listen(v)
  await v.unlock()
  assert.equal(events[0][1].code, 'audio_locked')
})

test('a resume that never settles reports audio_locked instead of hanging', async () => {
  const v = createVoice({}, { ...instant, isSecureContext: true, AudioContext: HangingCtx, navigator: { mediaDevices: { getUserMedia: denied } } })
  const events = listen(v)
  assert.equal(await v.unlock(), false)
  assert.deepEqual(events[0], ['on_error', { code: 'audio_locked', msg: 'AudioContext suspended' }])
})

test('a denied microphone reports mic_denied and unlock can be retried', async () => {
  let calls = 0
  const getUserMedia = () => {
    calls++
    return denied()
  }
  const v = createVoice({}, { ...idle, isSecureContext: true, AudioContext: RunningCtx, navigator: { mediaDevices: { getUserMedia } } })
  const events = listen(v)
  await v.unlock()
  await v.unlock()
  assert.equal(calls, 2)
  assert.deepEqual(events.map(e => e[1].code), ['mic_denied', 'mic_denied'])
})

test('methods that need audio report audio_locked or upload_failed before unlock', async () => {
  const v = createVoice({}, {})
  const events = listen(v)
  await v.load_song('demo')
  v.start()
  await v.calibrate()
  await v.submit('Паша', '')
  assert.deepEqual(events.map(e => e[1].code), ['audio_locked', 'audio_locked', 'audio_locked', 'upload_failed'])
})

test('configure persists lag_ms and survives junk input', () => {
  const store = {}
  const localStorage = { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v } }
  const v = createVoice({}, { localStorage })
  v.configure('not json')
  v.configure('{"lag_ms": 55, "difficulty": "hard", "music_volume": 0.5}')
  assert.equal(store['voice.lag_ms'], '55')
  assert.equal(v._state().lag_ms, 55)
})

test('stored lag is used when config does not pin one', () => {
  const localStorage = { getItem: () => '77', setItem() {} }
  assert.equal(createVoice({}, { localStorage })._state().lag_ms, 77)
  assert.equal(createVoice({ lag_ms: 33 }, { localStorage })._state().lag_ms, 33)
})

function memoryStore(init = {}) {
  const store = { ...init }
  return { store, localStorage: { getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = String(v) } } }
}

test('lag_source follows where the applied lag came from', () => {
  const { store, localStorage } = memoryStore()
  const v = createVoice({}, { localStorage })
  assert.equal(v._state().lag_source, 'estimated')
  v.configure({ lag_ms: 55 })
  assert.equal(v._state().lag_source, 'config')
  assert.equal(store['voice.lag_src'], 'config')
  assert.equal(createVoice({}, { localStorage })._state().lag_source, 'config')
  assert.equal(createVoice({ lag_ms: 33 }, memoryStore({ 'voice.lag_ms': '77', 'voice.lag_src': 'calibrated' }))._state().lag_source, 'config')
  assert.equal(createVoice({}, memoryStore({ 'voice.lag_ms': '77', 'voice.lag_src': 'calibrated' }))._state().lag_source, 'calibrated')
  assert.equal(createVoice({}, memoryStore({ 'voice.lag_ms': '77' }))._state().lag_source, 'calibrated')
  assert.equal(createVoice({}, memoryStore({ 'voice.lag_ms': '77', 'voice.lag_src': 'auto' }))._state().lag_source, 'auto')
  assert.equal(createVoice({}, memoryStore({ 'voice.lag_src': 'calibrated' }))._state().lag_source, 'estimated')
})

test('broken localStorage does not break the engine', () => {
  const localStorage = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } }
  const v = createVoice({}, { localStorage })
  v.configure({ lag_ms: 10 })
  assert.equal(v._state().lag_ms, 10)
})

test('installVoice picks the mock by ?mock= and the real engine otherwise', () => {
  const win = search => ({ location: { search }, VOICE_CONFIG: {}, addEventListener() {} })
  assert.equal(installVoice(win('?mock=octave'))._mode, 'octave')
  assert.equal(installVoice(win('?mock'))._mode, 'perfect')
  assert.equal(installVoice(win(''))._mode, 'real')
})

function recordingEnv({ sampleRate = 16000, takes, offline = false, decodeFails = false } = {}) {
  const taps = []
  const sources = []
  const gains = []
  class Node {
    constructor() {
      this.gain = { value: 1 }
      this.buffer = null
      this.onended = null
    }
    connect(to) {
      this.out = to
    }
    disconnect() {}
    start() {}
    stop() {}
  }
  class Ctx extends Node {
    constructor() {
      super()
      this.state = 'suspended'
      this.sampleRate = sampleRate
      this.currentTime = 0
      this.destination = new Node()
      this.audioWorklet = { addModule: () => Promise.resolve() }
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
    createBufferSource() {
      const n = new Node()
      sources.push(n)
      return n
    }
    decodeAudioData(data) {
      if (decodeFails) return Promise.reject(Object.assign(new Error('EncodingError'), { name: 'EncodingError' }))
      return Promise.resolve({ tag: data?.tag })
    }
  }
  class Tap {
    constructor() {
      this.port = { onmessage: null, postMessage() {} }
      taps.push(this)
    }
    connect() {}
  }
  const stream = { getTracks: () => [], getAudioTracks: () => [{ getSettings: () => ({ latency: 0.01 }) }] }
  const reply = body => Promise.resolve({ ok: true, status: 200, json: async () => body, arrayBuffer: async () => new ArrayBuffer(8) })
  const env = {
    ...instant,
    taps,
    sources,
    gains,
    isSecureContext: true,
    performance: { now: () => 0 },
    AudioContext: Ctx,
    AudioWorkletNode: Tap,
    FormData,
    Blob,
    AbortController,
    clearTimeout: () => {},
    navigator: { userAgent: 'test', mediaDevices: { getUserMedia: () => Promise.resolve(stream) } },
    fetch: (u, o) => (o?.method === 'POST' ? takes() : reply({ id: 'demo', audio: { minus: '/media/demo.mp3' }, lines: [] }))
  }
  if (offline) env.OfflineAudioContext = undefined
  return env
}

async function recordedTake(env) {
  const v = createVoice({}, env)
  const events = listen(v)
  await v.unlock()
  await v.load_song('demo')
  v.start()
  env.taps[0].port.onmessage({ data: { pcm: new Float32Array(1600).fill(0.1), F: 4800 } })
  await v.stop()
  return { v, events }
}

const errorCodes = events => events.filter(e => e[0] === 'on_error').map(e => e[1].code)

test('submit maps a network failure or timeout to net', async () => {
  for (const err of [new TypeError('fetch failed'), Object.assign(new Error('aborted'), { name: 'AbortError' })]) {
    const { v, events } = await recordedTake(recordingEnv({ takes: () => Promise.reject(err) }))
    assert.equal(await v.submit('Паша', ''), false)
    assert.deepEqual(errorCodes(events), ['net'], err.name)
  }
})

test('submit maps a non-2xx response to upload_failed', async () => {
  const takes = () => Promise.resolve({ ok: false, status: 422, text: async () => '{"detail":"bad_meta"}' })
  const { v, events } = await recordedTake(recordingEnv({ takes }))
  assert.equal(await v.submit('Паша', ''), false)
  assert.deepEqual(errorCodes(events), ['upload_failed'])
})

test('submit emits on_result for a 2xx response', async () => {
  const takes = () => Promise.resolve({ ok: true, status: 200, json: async () => ({ total: 1 }) })
  const { v, events } = await recordedTake(recordingEnv({ takes }))
  assert.equal(await v.submit('Паша', ''), true)
  assert.deepEqual(events.at(-1), ['on_result', { total: 1 }])
})

test('the js resampler labels the wav with the real rate when the context is below 16 kHz', async () => {
  const { v } = await recordedTake(recordingEnv({ sampleRate: 8000, takes: () => Promise.reject(new TypeError('x')), offline: true }))
  const take = v._take()
  assert.equal(take.resampler, 'js')
  assert.equal(take.meta.wav_sr, 8000)
  assert.equal(parseWavHeader(take.wav).sampleRate, 8000)
})

test('the js resampler downsamples to 16 kHz from a faster context', async () => {
  const { v } = await recordedTake(recordingEnv({ sampleRate: 48000, takes: () => Promise.reject(new TypeError('x')), offline: true }))
  const take = v._take()
  assert.equal(take.resampler, 'js')
  assert.equal(take.meta.wav_sr, 16000)
  assert.equal(parseWavHeader(take.wav).sampleRate, 16000)
})

test('an AudioContext constructor that throws reports audio_locked and a later unlock retries', async () => {
  const env = recordingEnv()
  const Working = env.AudioContext
  let attempts = 0
  env.AudioContext = function () {
    attempts++
    if (attempts === 1) throw new Error('no audio hardware')
    return new Working()
  }
  const v = createVoice({}, env)
  const events = listen(v)
  assert.equal(await v.unlock(), false)
  assert.deepEqual(events, [['on_error', { code: 'audio_locked', msg: 'no audio hardware' }]])
  assert.equal(await v.unlock(), true)
  assert.equal(attempts, 2)
  assert.equal(events.at(-1)[0], 'on_unlocked')
  assert.deepEqual(errorCodes(events), ['audio_locked'])
})

test('an unexpected throw while wiring the graph reports worklet_failed and a later unlock retries', async () => {
  const env = recordingEnv()
  const Base = env.AudioContext
  let sources = 0
  env.AudioContext = class extends Base {
    createMediaStreamSource() {
      sources++
      if (sources === 1) throw new Error('graph broke')
      return super.createMediaStreamSource()
    }
  }
  const v = createVoice({}, env)
  const events = listen(v)
  assert.equal(await v.unlock(), false)
  assert.deepEqual(events, [['on_error', { code: 'worklet_failed', msg: 'graph broke' }]])
  assert.equal(await v.unlock(), true)
  assert.equal(sources, 2)
  assert.equal(events.at(-1)[0], 'on_unlocked')
  assert.deepEqual(errorCodes(events), ['worklet_failed'])
})

function calibrationEnv(store, env = recordingEnv()) {
  const Base = env.AudioContext
  env.oscillators = []
  env.AudioContext = class extends Base {
    createOscillator() {
      const osc = Object.assign(this.createGain(), { frequency: { value: 0 }, starts: [] })
      osc.start = t => osc.starts.push(t)
      env.oscillators.push(osc)
      return osc
    }
  }
  env.localStorage = store.localStorage
  return env
}

function clapFrames(sr, claps, seconds) {
  const frames = []
  for (let E = 512; E / sr < seconds; E += 512) {
    const t = (E - 256) / sr
    frames.push({ E, rms: claps.some(c => t >= c && t < c + 0.08) ? 0.3 : 0.003, hz: 0, clarity: 0 })
  }
  return frames
}

async function calibrated(mode, claps, store = memoryStore(), env = calibrationEnv(store)) {
  const v = createVoice({}, env)
  const events = listen(v)
  await v.unlock()
  env.setTimeout = () => 0
  const run = mode === undefined ? v.calibrate() : v.calibrate(mode)
  const starts = env.oscillators.map(o => o.starts[0])
  env.taps[0].port.onmessage({ data: { frames: clapFrames(16000, claps(starts), starts.at(-1) + 1.2) } })
  return { ok: await run, v, store, starts, result: events.filter(e => e[0] === 'on_calibrated').at(-1)[1] }
}

test('speakers calibration plays 8 clicks and reports the mode', async () => {
  const { ok, v, store, starts, result } = await calibrated(undefined, s => s.map(c => c + 0.2))
  assert.equal(ok, true)
  assert.equal(starts.length, 8)
  assert.equal(result.mode, 'speakers')
  assert.equal(result.hits, 8)
  assert.ok(Math.abs(result.lag_ms - 200) <= 33, `lag ${result.lag_ms}`)
  assert.deepEqual(Object.keys(result), ['lag_ms', 'hits', 'mode'])
  assert.equal(v._state().lag_source, 'calibrated')
  assert.equal(store.store['voice.lag_src'], 'calibrated')
})

test('headphones calibration adds two lead-in clicks and ignores their claps', async () => {
  const { ok, v, starts, result } = await calibrated('headphones', s => [s[0] + 0.05, s[1] + 0.35, ...s.slice(2).map(c => c + 0.2)])
  assert.equal(ok, true)
  assert.equal(starts.length, 10)
  assert.equal(result.mode, 'headphones')
  assert.equal(result.hits, 8)
  assert.ok(Math.abs(result.lag_ms - 200) <= 33, `lag ${result.lag_ms}`)
  assert.equal(v._state().lag_source, 'calibrated')
})

test('headphones calibration spaces clicks by 0.8 s and measures long Bluetooth chains', async () => {
  for (const lag of [0.55, 0.25]) {
    const { ok, starts, result } = await calibrated('headphones', s => s.map(c => c + lag))
    assert.equal(ok, true)
    assert.ok(Math.abs(starts[1] - starts[0] - 0.8) < 1e-9)
    assert.equal(result.hits, 8)
    assert.ok(Math.abs(result.lag_ms - lag * 1000) <= 33, `lag ${lag}: ${result.lag_ms}`)
  }
})

test('speakers calibration keeps the 0.5 s gap', async () => {
  const { ok, starts, result } = await calibrated(undefined, s => s.map(c => c + 0.3))
  assert.ok(Math.abs(starts[1] - starts[0] - 0.5) < 1e-9)
  assert.equal(ok, true)
  assert.ok(Math.abs(result.lag_ms - 300) <= 33, `lag ${result.lag_ms}`)
})

test('a stray clap just before the first measured click does not shift the headphones result', async () => {
  const { ok, result } = await calibrated('headphones', s => [s[0] + 0.25, s[1] + 0.25, s[2] - 0.05, ...s.slice(2).map(c => c + 0.25)])
  assert.equal(ok, true)
  assert.ok(result.hits >= 7)
  assert.ok(Math.abs(result.lag_ms - 250) <= 33, `lag ${result.lag_ms}`)
})

test('a failed calibration keeps the previous lag source', async () => {
  const { ok, v, result } = await calibrated('headphones', () => [])
  assert.equal(ok, false)
  assert.equal(result.mode, 'headphones')
  assert.equal(result.hits, 0)
  assert.equal(v._state().lag_source, 'estimated')
})

test('the take meta carries lag_source right after lag_ms', async () => {
  const { v } = await recordedTake(recordingEnv({ takes: () => Promise.reject(new TypeError('x')) }))
  const meta = v._take().meta
  assert.equal(meta.lag_source, 'estimated')
  const keys = Object.keys(meta)
  assert.equal(keys[keys.indexOf('lag_ms') + 1], 'lag_source')
})

const at = ms => ({ estimated_ms: ms, confidence: 0.8 })
const AUTO = { 'voice.lag_ms': '200', 'voice.lag_src': 'auto' }

function tuningEnv(store, latencies, gate = Promise.resolve()) {
  const env = recordingEnv({ takes: () => Promise.resolve({ ok: false, status: 503, text: async () => '' }) })
  const base = env.fetch
  env.fetch = (u, o) => {
    if (!u.endsWith('/api/v1/takes')) return base(u, o)
    const body = { latency: latencies.shift() }
    return gate.then(() => ({ ok: true, status: 200, json: async () => body }))
  }
  env.localStorage = store.localStorage
  return env
}

async function sing(v, env) {
  v.start()
  env.taps[0].port.onmessage({ data: { pcm: new Float32Array(1600).fill(0.1), F: 4800 } })
  await v.stop()
}

async function tuned(latencies, init = {}, cfg = {}) {
  const store = memoryStore(init)
  const env = tuningEnv(store, latencies)
  const v = createVoice(cfg, env)
  const lags = []
  v.subscribe(name => {
    if (name === 'on_result') lags.push(v._state().lag_ms)
  })
  await v.unlock()
  await v.load_song('demo')
  for (let k = 0, n = latencies.length; k < n; k++) {
    await sing(v, env)
    assert.equal(await v.submit('Паша', ''), true)
  }
  return { v, env, store, lags }
}

test('a confident result tunes the lag before on_result and the next take sends it as auto', async () => {
  const { v, env, store, lags } = await tuned([{ estimated_ms: 240, confidence: 0.2 }])
  assert.deepEqual(lags, [240])
  assert.equal(v._state().lag_source, 'auto')
  assert.equal(store.store['voice.lag_ms'], '240')
  assert.equal(store.store['voice.lag_src'], 'auto')
  await sing(v, env)
  const meta = v._take().meta
  assert.deepEqual([meta.lag_ms, meta.lag_source], [240, 'auto'])
  assert.equal(createVoice({}, { localStorage: store.localStorage })._state().lag_source, 'auto')
})

test('a low-confidence or missing latency leaves the lag alone', async () => {
  const { v, store, lags } = await tuned([{ estimated_ms: 240, confidence: 0.19 }, undefined, { estimated_ms: null, confidence: 0.9 }, { estimated_ms: 240 }])
  assert.deepEqual(lags, [10, 10, 10, 10])
  assert.equal(v._state().lag_source, 'estimated')
  assert.equal(store.store['voice.lag_src'], undefined)
})

test('a new auto lag is averaged with the previous auto lag', async () => {
  assert.deepEqual((await tuned([at(260), at(300)], AUTO)).lags, [230, 265])
})

test('an outlier moves the auto lag only when the next result agrees with it', async () => {
  assert.deepEqual((await tuned([at(400), at(420)], AUTO)).lags, [200, 410])
  assert.deepEqual((await tuned([at(400), at(250), at(420)], AUTO)).lags, [200, 225, 225])
  assert.deepEqual((await tuned([at(400), at(0), at(20)], AUTO)).lags, [200, 200, 10])
})

test('auto lag beats the browser estimate but never config or calibration', async () => {
  const { v } = await tuned([], AUTO)
  assert.deepEqual([v._state().lag_ms, v._state().lag_source], [200, 'auto'])
  v.configure({ lag_ms: 77 })
  assert.deepEqual([v._state().lag_ms, v._state().lag_source], [77, 'config'])
  const pinned = await tuned([at(300)], AUTO, { lag_ms: 33 })
  assert.deepEqual(pinned.lags, [33])
  assert.equal(pinned.v._state().lag_source, 'config')
  assert.equal(pinned.store.store['voice.lag_ms'], '200')
  const calib = await tuned([at(300)], { 'voice.lag_ms': '120', 'voice.lag_src': 'calibrated' })
  assert.deepEqual(calib.lags, [120])
  assert.equal(calib.store.store['voice.lag_src'], 'calibrated')
})

test('calibration replaces the auto lag and later results keep it', async () => {
  const store = memoryStore(AUTO)
  const env = calibrationEnv(store, tuningEnv(store, [at(400)]))
  const { ok, v } = await calibrated(undefined, s => s.map(c => c + 0.25), store, env)
  assert.equal(ok, true)
  env.setTimeout = instant.setTimeout
  const lag = v._state().lag_ms
  assert.notEqual(lag, 200)
  assert.equal(v._state().lag_source, 'calibrated')
  await v.load_song('demo')
  await sing(v, env)
  assert.equal(await v.submit('Паша', ''), true)
  assert.deepEqual([v._state().lag_ms, v._state().lag_source], [lag, 'calibrated'])
  assert.equal(store.store['voice.lag_src'], 'calibrated')
})

test('a result that lands mid-song changes the lag only from the next song', async () => {
  let open
  const store = memoryStore()
  const env = tuningEnv(store, [at(240), at(260)], new Promise(r => (open = r)))
  const v = createVoice({}, env)
  const lag = () => [v._state().lag_ms, v._state().lag_source]
  await v.unlock()
  await v.load_song('demo')
  await sing(v, env)
  const sent = v.submit('Паша', '')
  v.start()
  open()
  assert.equal(await sent, true)
  assert.deepEqual(lag(), [10, 'estimated'])
  assert.deepEqual([store.store['voice.lag_ms'], store.store['voice.lag_src']], ['240', 'auto'])
  env.taps[0].port.onmessage({ data: { pcm: new Float32Array(1600).fill(0.1), F: 4800 } })
  await v.stop()
  const meta = v._take().meta
  assert.deepEqual([meta.lag_ms, meta.lag_source], [10, 'estimated'])
  assert.deepEqual(lag(), [240, 'auto'])
  assert.equal(await v.submit('Паша', ''), true)
  assert.deepEqual(lag(), [250, 'auto'])
  v.start()
  assert.deepEqual(lag(), [250, 'auto'])
})

test('auto lag works within the session when localStorage is unavailable', async () => {
  const env = tuningEnv({ localStorage: undefined }, [at(240)])
  const v = createVoice({}, env)
  await v.unlock()
  await v.load_song('demo')
  await sing(v, env)
  assert.equal(await v.submit('Паша', ''), true)
  assert.deepEqual([v._state().lag_ms, v._state().lag_source], [240, 'auto'])
})

function bluetoothEnv(store) {
  const env = recordingEnv()
  const Base = env.AudioContext
  env.AudioContext = class extends Base {
    constructor() {
      super()
      this.outputLatency = 0.15
      this.baseLatency = 0.01
    }
  }
  env.localStorage = store.localStorage
  return env
}

test('Bluetooth output starts from the browser estimate plus 200 ms', async () => {
  const v = createVoice({}, bluetoothEnv(memoryStore()))
  const events = listen(v)
  await v.unlock()
  const unlocked = events.find(e => e[0] === 'on_unlocked')[1]
  assert.deepEqual([unlocked.lag_ms, unlocked.bt_suspect], [360, true])
  assert.deepEqual([v._state().est_lag_ms, v._state().lag_source], [360, 'estimated'])
})

test('a stored lag still beats the Bluetooth estimate', async () => {
  const v = createVoice({}, bluetoothEnv(memoryStore(AUTO)))
  await v.unlock()
  assert.deepEqual([v._state().lag_ms, v._state().lag_source, v._state().est_lag_ms], [200, 'auto', 360])
})

function judgedEnv(store) {
  const env = recordingEnv()
  const song = { id: 'demo', audio: { minus: '/media/demo.mp3' }, lines: [{ i: 0, t0: 0.5, t1: 0.9, notes: [{ i: 0, t: 0.5, d: 0.4, midi: 69, type: 'normal' }] }] }
  const base = env.fetch
  env.fetch = (u, o) => (u.includes('/api/v1/songs/') ? Promise.resolve({ ok: true, status: 200, json: async () => song }) : base(u, o))
  env.localStorage = store.localStorage
  return env
}

async function lateNoteHit(init) {
  const env = judgedEnv(memoryStore(init))
  const v = createVoice({}, env)
  const events = listen(v)
  await v.unlock()
  await v.load_song('demo')
  v.start()
  const lagS = v._state().lag_ms / 1000
  const frames = []
  for (let t = 0; t < 1.4; t += 512 / 16000) {
    const sung = t >= 0.65 && t < 1.05
    frames.push({ E: Math.round((t + 0.15 + lagS) * 16000 + 1024), hz: sung ? 440 : 0, clarity: sung ? 0.99 : 0, rms: sung ? 0.1 : 0.001 })
  }
  env.taps[0].port.onmessage({ data: { frames } })
  return events.filter(e => e[0] === 'on_note_judged').map(e => e[1].hit)
}

test('the live judge gives an estimated lag 150 ms of slack and a tuned lag none', async () => {
  const [soft] = await lateNoteHit({})
  assert.ok(soft >= 0.8, `estimated ${soft}`)
  for (const src of ['auto', 'calibrated', 'config']) {
    const [strict] = await lateNoteHit({ 'voice.lag_ms': '200', 'voice.lag_src': src })
    assert.ok(strict < 0.8, `${src} ${strict}`)
  }
})

function gate() {
  let open
  const p = new Promise(r => (open = r))
  return { p, open }
}

const song = id => ({ id, audio: { minus: `/media/${id}/minus.mp3`, duration: 10 }, lines: [{ i: 0, t0: 1, t1: 2, notes: [{ i: 0, t: 1, d: 0.5, midi: 69, type: 'normal' }] }] })

function songsEnv(songs, opts) {
  const env = recordingEnv(opts)
  env.posted = []
  env.fetch = async (u, o) => {
    if (o?.method === 'POST' && u.endsWith('/api/v1/sessions')) return { ok: true, status: 200, json: async () => ({ token: 'tok' }) }
    if (o?.method === 'POST') {
      env.posted.push(JSON.parse(o.body.get('meta')))
      return { ok: true, status: 200, json: async () => ({ take_id: 'tk' }) }
    }
    for (const [id, sg] of Object.entries(songs)) {
      if (u.endsWith(`/api/v1/songs/${id}`)) {
        if (sg.wait) await sg.wait
        if (sg.status) return { ok: false, status: sg.status }
        return { ok: true, status: 200, json: async () => sg.ref }
      }
      if (u.endsWith(sg.ref.audio.minus)) return { ok: true, status: 200, arrayBuffer: async () => Object.assign(new ArrayBuffer(8), { tag: id }) }
    }
    return { ok: false, status: 404 }
  }
  return env
}

async function unlockedVoice(env, cfg = {}) {
  const v = createVoice(cfg, env)
  const events = listen(v)
  assert.equal(await v.unlock(), true)
  return { v, events }
}

const readyIds = events => events.filter(e => e[0] === 'on_ready').map(e => e[1].id)
const pushPcm = (env, n, F, value = 0.1) => env.taps[0].port.onmessage({ data: { pcm: new Float32Array(n).fill(value), F } })

test('a slower, older load_song never replaces the newer song', async () => {
  const g = gate()
  const env = songsEnv({ a: { ref: song('a'), wait: g.p }, b: { ref: song('b') } })
  const { v, events } = await unlockedVoice(env)
  const pa = v.load_song('a')
  assert.equal(await v.load_song('b'), true)
  g.open()
  assert.equal(await pa, false)
  assert.deepEqual(readyIds(events), ['b'])
  assert.equal(v.start(), true)
  assert.equal(env.sources.at(-1).buffer.tag, 'b')
  pushPcm(env, 1600, 4800)
  await v.stop()
  assert.equal(await v.submit('P', null), true)
  assert.equal(env.posted.at(-1).song_id, 'b')
  assert.deepEqual(errorCodes(events), [])
})

test('a stale load_song that fails after the newer one succeeded reports nothing', async () => {
  const g = gate()
  const env = songsEnv({ a: { ref: song('a'), wait: g.p, status: 500 }, b: { ref: song('b') } })
  const { v, events } = await unlockedVoice(env)
  const pa = v.load_song('a')
  assert.equal(await v.load_song('b'), true)
  g.open()
  assert.equal(await pa, false)
  assert.deepEqual(errorCodes(events), [])
  assert.deepEqual(readyIds(events), ['b'])
})

test('a stale load_song landing mid-song leaves the playing take alone', async () => {
  const g = gate()
  const env = songsEnv({ a: { ref: song('a'), wait: g.p }, b: { ref: song('b') } })
  const { v, events } = await unlockedVoice(env)
  const pa = v.load_song('a')
  await v.load_song('b')
  v.start()
  g.open()
  assert.equal(await pa, false)
  assert.equal(JSON.parse(v.poll()).state, 'playing')
  pushPcm(env, 1600, 4800)
  env.sources.at(-1).onended()
  assert.equal(events.filter(e => e[0] === 'on_song_end').length, 1)
  assert.equal(await v.submit('P', null), true)
  assert.equal(env.posted.at(-1).song_id, 'b')
  assert.deepEqual(errorCodes(events), [])
})

test('a double load_song of the same song with start on on_ready keeps the take', async () => {
  const env = songsEnv({ a: { ref: song('a') } })
  const { v, events } = await unlockedVoice(env)
  let started = 0
  v.subscribe(name => {
    if (name === 'on_ready' && !started++) v.start()
  })
  await Promise.all([v.load_song('a'), v.load_song('a')])
  assert.equal(JSON.parse(v.poll()).state, 'playing')
  pushPcm(env, 1600, 4800)
  env.sources.at(-1).onended()
  assert.deepEqual(events.filter(e => e[0] === 'on_note_judged').map(e => e[1].i), [0])
  assert.equal(await v.submit('P', null), true)
  assert.equal(env.posted.at(-1).song_id, 'a')
  assert.deepEqual(errorCodes(events), [])
})

test('a natural song end flushes the judge, emits on_song_end and submits the take', async () => {
  const env = songsEnv({ a: { ref: song('a') } })
  const { v, events } = await unlockedVoice(env)
  assert.equal(await v.load_song('a'), true)
  assert.equal(v.start(), true)
  pushPcm(env, 8000, 0)
  env.sources.at(-1).onended()
  const tail = events.slice(-2)
  assert.deepEqual(tail.map(e => e[0]), ['on_note_judged', 'on_song_end'])
  assert.deepEqual(Object.keys(tail[1][1]), ['t'])
  assert.equal(JSON.parse(v.poll()).state, 'ended')
  assert.equal(await v.submit('P', null), true)
  assert.deepEqual(events.at(-1), ['on_result', { take_id: 'tk' }])
  assert.equal(env.posted.at(-1).song_id, 'a')
})

test('a manual stop emits no on_song_end even if onended fires later', async () => {
  const env = songsEnv({ a: { ref: song('a') } })
  const { v, events } = await unlockedVoice(env)
  await v.load_song('a')
  v.start()
  const src = env.sources.at(-1)
  await v.stop()
  src.onended()
  assert.equal(events.filter(e => e[0] === 'on_song_end').length, 0)
  assert.equal(events.filter(e => e[0] === 'on_note_judged').length, 0)
})

test('load_song reports net for a 404 and decode_failed for a bad minus', async () => {
  const gone = await unlockedVoice(songsEnv({ a: { ref: song('a') }, gone: { ref: song('gone'), status: 404 } }))
  assert.equal(await gone.v.load_song('gone'), false)
  assert.deepEqual(errorCodes(gone.events), ['net'])
  const bad = await unlockedVoice(songsEnv({ a: { ref: song('a') } }, { decodeFails: true }))
  assert.equal(await bad.v.load_song('a'), false)
  assert.deepEqual(errorCodes(bad.events), ['decode_failed'])
  assert.deepEqual(readyIds([...gone.events, ...bad.events]), [])
})

test('the real on_unlocked and on_ready payloads carry the bridge keys', async () => {
  const env = songsEnv({ a: { ref: song('a') } })
  const { v, events } = await unlockedVoice(env)
  assert.deepEqual(Object.keys(events.find(e => e[0] === 'on_unlocked')[1]), ['sr', 'noise_db', 'lag_ms', 'bt_suspect'])
  await v.load_song('a')
  const ready = events.find(e => e[0] === 'on_ready')[1]
  assert.deepEqual(ready.scoring, { tol_cents: 120 })
  assert.equal(typeof ready.lag_ms, 'number')
  assert.equal(ready.id, 'a')
})

test('music_volume is clamped into the music gain and an aec toggle reopens the mic', async () => {
  const env = songsEnv({ a: { ref: song('a') } })
  const opens = []
  const gum = env.navigator.mediaDevices.getUserMedia
  env.navigator.mediaDevices.getUserMedia = c => {
    opens.push(c.audio.echoCancellation)
    return gum(c)
  }
  const { v } = await unlockedVoice(env)
  await v.load_song('a')
  v.start()
  const music = env.sources.at(-1).out
  assert.ok(env.gains.includes(music))
  v.configure({ music_volume: 3 })
  assert.equal(music.gain.value, 1)
  v.configure({ music_volume: 0.4 })
  assert.equal(music.gain.value, 0.4)
  v.configure({ music_volume: -1 })
  assert.equal(music.gain.value, 0)
  v.configure({ aec: true })
  await new Promise(r => setImmediate(r))
  assert.deepEqual(opens, [false, true])
  assert.equal(JSON.parse(v.poll()).state, 'playing')
})

test('a restart right after stop keeps the old tail in the old take', async () => {
  const env = songsEnv({ a: { ref: song('a') } })
  const { v } = await unlockedVoice(env)
  await v.load_song('a')
  env.setTimeout = () => 0
  const port = env.taps[0].port
  v.start()
  pushPcm(env, 1600, 4800, 0.1)
  const first = v.stop()
  v.start()
  pushPcm(env, 400, 6400, 0.9)
  port.onmessage({ data: { recDone: true } })
  pushPcm(env, 1600, 8000, 0.2)
  const old = await first
  assert.equal(old.samples, 2000)
  assert.equal(v._take(), null)
  const second = v.stop()
  port.onmessage({ data: { recDone: true } })
  const take = await second
  assert.equal(take.samples, 1600)
  assert.ok(Math.abs(new DataView(take.wav).getInt16(44, true) / 32767 - 0.2) < 1e-3)
  assert.equal(v._take().meta.wav_t0, take.wav_t0)
})

test('a lag configured mid-song applies from the next take only', async () => {
  const env = songsEnv({ a: { ref: song('a') } })
  const { v } = await unlockedVoice(env)
  await v.load_song('a')
  const frame = E => env.taps[0].port.onmessage({ data: { frames: [{ E, hz: 440, clarity: 0.99, rms: 0.1 }] } })
  v.start()
  const A = v._state().lag_ms
  frame(16000 + 1024)
  v.configure({ lag_ms: A + 100 })
  assert.deepEqual([v._state().lag_ms, v._state().lag_source], [A, 'estimated'])
  frame(32000 + 1024)
  await v.stop()
  const meta = v._take().meta
  assert.equal(meta.lag_ms, A)
  assert.equal(meta.lag_source, 'estimated')
  assert.deepEqual(meta.frames.map(f => f.t), [16000 + 1024, 32000 + 1024].map(E => Math.round(frameTime(E, 16000, 0.15, A / 1000) * 1000) / 1000))
  assert.deepEqual([v._state().lag_ms, v._state().lag_source], [A + 100, 'config'])
  v.start()
  frame(16000 + 1024)
  await v.stop()
  const next = v._take().meta
  assert.deepEqual([next.lag_ms, next.lag_source], [A + 100, 'config'])
  assert.equal(next.frames[0].t, Math.round(frameTime(16000 + 1024, 16000, 0.15, (A + 100) / 1000) * 1000) / 1000)
})
