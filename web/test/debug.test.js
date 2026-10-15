import { test } from 'node:test'
import assert from 'node:assert/strict'
import { attachDebug, createDebugTracker, debugText, isDebug, shortSha } from '../lib/debug.js'
import { installVoice } from '../voice.js'

const SHA = '4f1c2d3e5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d'
const CID = '7b1e2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d'
const flush = () => new Promise(r => setImmediate(r))

test('isDebug reacts only to debug=1', () => {
  assert.equal(isDebug('?debug=1'), true)
  assert.equal(isDebug('?mock=perfect&debug=1'), true)
  assert.equal(isDebug('?debug=0'), false)
  assert.equal(isDebug(''), false)
  assert.equal(isDebug(undefined), false)
})

test('shortSha keeps 7 hex chars and the dirty mark', () => {
  assert.equal(shortSha(SHA), '4f1c2d3')
  assert.equal(shortSha('4f1c2d3'), '4f1c2d3')
  assert.equal(shortSha(`${SHA}-dirty`), '4f1c2d3-dirty')
  assert.equal(shortSha('dev'), 'dev')
  assert.equal(shortSha(''), '—')
  assert.equal(shortSha(null), '—')
})

test('debugText formats a full snapshot', () => {
  const text = debugText({
    mode: 'real',
    api: { app: '0.3.1', git_sha: '4f1c2d3', scoring: 'score-v1', f0_engine: 'swiftf0-0.3.0' },
    web: { git_sha: SHA, built_at: '2026-10-15T09:30:00Z' },
    state: { sr: 48000, lag_ms: 48, est_lag_ms: 52, output_latency: 0.0123, ctx_state: 'running', session: 'ok' },
    frame: { t: 12.301, hz: 220, conf: 0.97, rms: 0.042 },
    fps: 93.75,
    clientId: CID,
    verdict: { i: 3, line: 1, type: 'normal', hit: 0.82, cents: 12, onset_ms: 35 },
    integrity: { status: 'suspect', flags: ['playback', 'flat_pitch'] }
  })
  assert.equal(text, [
    'api 0.3.1 4f1c2d3 · score-v1 · swiftf0-0.3.0',
    'web 4f1c2d3 2026-10-15T09:30:00Z',
    'mode real · sr 48000 · ctx running',
    'lag 48 ms · est 52 ms · out 12.3 ms',
    'pitch 220.0 Hz · midi 57.00 · conf 0.97',
    'fps 94',
    `client ${CID}`,
    'session ok',
    'note #3 hit 0.82 · +12c · onset 35 ms',
    'integrity suspect: playback, flat_pitch'
  ].join('\n'))
})

test('debugText shows dashes before anything is known', () => {
  assert.equal(debugText({ mode: 'perfect', state: { sr: 48000, lag_ms: 40, mode: 'perfect', session: 'none' } }), [
    'api —',
    'web —',
    'mode mock:perfect · sr 48000 · ctx —',
    'lag 40 ms · est — · out —',
    'pitch —',
    'fps 0',
    'client —',
    'session none',
    'note —',
    'integrity —'
  ].join('\n'))
})

test('debugText handles silence, missing cents and an ok integrity', () => {
  const text = debugText({
    mode: 'real',
    frame: { t: 1, hz: 0, conf: 0, rms: 0.003 },
    verdict: { i: 0, hit: 0, cents: null, onset_ms: null },
    integrity: { status: 'ok', flags: [] }
  }).split('\n')
  assert.equal(text[4], 'pitch — · midi — · conf 0.00')
  assert.equal(text[8], 'note #0 hit 0.00 · — · onset —')
  assert.equal(text[9], 'integrity ok')
})

test('tracker keeps the last frame and counts frames per second', () => {
  let now = 0
  const tr = createDebugTracker(() => now)
  const poll = n => JSON.stringify({ t_now: 0, state: 'playing', level: 0, frames: Array.from({ length: n }, (_, i) => ({ t: i, hz: 100 + i, conf: 1, rms: 0.1 })) })
  tr.onPoll(poll(10))
  now = 500
  tr.onPoll(poll(20))
  now = 700
  tr.onPoll(poll(0))
  tr.onPoll('not json')
  now = 900
  assert.equal(tr.snapshot().fps, 30)
  assert.equal(tr.snapshot().frame.hz, 119)
  now = 1200
  assert.equal(tr.snapshot().fps, 20)
  now = 1800
  assert.equal(tr.snapshot().fps, 0)
  assert.equal(tr.snapshot().frame.hz, 119)
})

test('tracker remembers the last verdict and integrity and resets them on a new song', () => {
  const tr = createDebugTracker(() => 0)
  tr.onEvent('on_note_judged', JSON.stringify({ i: 0, hit: 1 }))
  tr.onEvent('on_note_judged', JSON.stringify({ i: 1, hit: 0.4 }))
  tr.onEvent('on_result', JSON.stringify({ take_id: 'tk_1', integrity: { status: 'unverified', flags: ['no_session'] } }))
  assert.equal(tr.snapshot().verdict.i, 1)
  assert.equal(tr.snapshot().integrity.status, 'unverified')
  tr.onEvent('on_result', JSON.stringify({ take_id: 'tk_2' }))
  assert.equal(tr.snapshot().integrity, null)
  tr.onEvent('on_note_judged', JSON.stringify({ i: 2, hit: 1 }))
  tr.onEvent('on_ready', JSON.stringify({ id: 'demo' }))
  assert.equal(tr.snapshot().verdict, null)
})

function fakeWindow(search = '') {
  const children = []
  const listeners = {}
  const copied = []
  const fetched = []
  const win = {
    location: { search },
    VOICE_CONFIG: { api: '' },
    performance: { now: () => 0 },
    tick: null,
    copied,
    fetched,
    listeners,
    document: {
      body: { appendChild: el => children.push(el) },
      createElement: tag => ({ tagName: tag.toUpperCase(), id: '', style: {}, textContent: '' }),
      addEventListener() {}
    },
    children,
    setInterval(fn, ms) {
      win.tick = fn
      win.period = ms
      return 1
    },
    clearInterval() {},
    addEventListener: (type, fn) => {
      listeners[type] = fn
    },
    navigator: { clipboard: { writeText: async t => copied.push(t) } },
    async fetch(url, init) {
      fetched.push([String(url), init?.cache])
      if (String(url).endsWith('/api/v1/version')) return { ok: true, json: async () => ({ app: '0.3.1', git_sha: '4f1c2d3', scoring: 'score-v1', f0_engine: 'swiftf0-0.3.0' }) }
      if (String(url).endsWith('version.json')) return { ok: true, json: async () => ({ git_sha: SHA, built_at: '2026-10-15T09:30:00Z' }) }
      return { ok: false, status: 404 }
    }
  }
  return win
}

function stubVoice() {
  const subs = []
  return {
    _mode: 'perfect',
    subscribe: cb => subs.push(cb),
    emit: (name, payload) => subs.forEach(cb => cb(name, JSON.stringify(payload))),
    poll: () => JSON.stringify({ t_now: 2.6, state: 'playing', level: 0.05, frames: [{ t: 2.59, hz: 261.6, conf: 0.95, rms: 0.05 }] }),
    _state: () => ({ sr: 48000, lag_ms: 40, mode: 'perfect', session: 'none' }),
    client_id: () => CID
  }
}

test('attachDebug mounts a click-through overlay and refreshes it on a timer', async () => {
  const win = fakeWindow('?debug=1')
  const voice = stubVoice()
  const d = attachDebug(win, voice, { apiUrl: '/api/v1/version', versionUrl: 'http://x/version.json' })
  assert.equal(win.children.length, 1)
  assert.equal(d.el.tagName, 'PRE')
  assert.equal(d.el.id, 'voice-debug')
  assert.equal(d.el.style.position, 'fixed')
  assert.equal(d.el.style.pointerEvents, 'none')
  assert.equal(win.period, 250)
  assert.deepEqual(win.fetched, [['/api/v1/version', 'no-store'], ['http://x/version.json', 'no-store']])
  const raw = voice.poll()
  assert.equal(JSON.parse(raw).frames.length, 1)
  voice.emit('on_note_judged', { i: 4, hit: 0.9, cents: -8, onset_ms: 20 })
  await flush()
  win.tick()
  const lines = d.el.textContent.split('\n')
  assert.equal(lines[0], 'api 0.3.1 4f1c2d3 · score-v1 · swiftf0-0.3.0')
  assert.equal(lines[1], 'web 4f1c2d3 2026-10-15T09:30:00Z')
  assert.equal(lines[2], 'mode mock:perfect · sr 48000 · ctx —')
  assert.equal(lines[4], 'pitch 261.6 Hz · midi 60.00 · conf 0.95')
  assert.equal(lines[6], `client ${CID}`)
  assert.equal(lines[8], 'note #4 hit 0.90 · -8c · onset 20 ms')
})

test('Alt+Shift+D copies the overlay text', async () => {
  const win = fakeWindow('?debug=1')
  const d = attachDebug(win, stubVoice(), { apiUrl: '/api/v1/version', versionUrl: 'http://x/version.json' })
  await flush()
  win.listeners.keydown({ code: 'KeyD', altKey: true, shiftKey: true, repeat: false })
  win.listeners.keydown({ code: 'KeyD', altKey: false, shiftKey: true, repeat: false })
  await flush()
  assert.equal(win.copied.length, 1)
  assert.equal(win.copied[0], d.el.textContent)
})

test('installVoice adds the overlay only with ?debug=1', () => {
  const plain = fakeWindow('?mock=perfect')
  installVoice(plain)
  assert.equal(plain.children.length, 0)
  const debug = fakeWindow('?mock=perfect&debug=1')
  installVoice(debug)
  assert.equal(debug.children.length, 1)
  assert.ok(debug.fetched.some(([u]) => u.endsWith('/version.json')))
})
