import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createVoice, installVoice } from '../voice.js'
import { createMockVoice } from '../voice.mock.js'

const BRIDGE = ['subscribe', 'unlock', 'configure', 'load_song', 'start', 'stop', 'poll', 'submit', 'calibrate']

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
