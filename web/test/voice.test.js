import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createVoice, installVoice } from '../voice.js'
import { createMockVoice } from '../voice.mock.js'
import { parseWavHeader } from '../lib/wav.js'

const BRIDGE = ['subscribe', 'unlock', 'configure', 'load_song', 'start', 'stop', 'poll', 'submit', 'calibrate', 'client_id']

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

function recordingEnv({ sampleRate = 16000, takes, offline = false } = {}) {
  const taps = []
  class Node {
    constructor() {
      this.gain = { value: 1 }
      this.buffer = null
    }
    connect() {}
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
      return new Node()
    }
    createBufferSource() {
      return new Node()
    }
    decodeAudioData() {
      return Promise.resolve({})
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

function calibrationEnv(store) {
  const env = recordingEnv()
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

async function calibrated(mode, claps) {
  const store = memoryStore()
  const env = calibrationEnv(store)
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
