import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createMockVoice } from '../voice.mock.js'
import { encodeWav } from '../lib/wav.js'

const fixture = name => JSON.parse(readFileSync(new URL(`../../contracts/fixtures/${name}`, import.meta.url)))
const ref = fixture('demo.reference.json')
const result = fixture('result.perfect.json')
const CFG = { tol_cents: { easy: 200, normal: 120, hard: 60 }, mock_base: 'http://x/' }

function fakeEnv(files) {
  let now = 0
  const timers = []
  return {
    performance: { now: () => now },
    setTimeout(fn, ms) {
      timers.push({ at: now + ms, fn, done: false })
      return timers.length
    },
    clearTimeout(id) {
      if (timers[id - 1]) timers[id - 1].done = true
    },
    async fetch(url) {
      const key = Object.keys(files).find(k => String(url).endsWith(k))
      return key ? { ok: true, json: async () => structuredClone(files[key]) } : { ok: false, status: 404 }
    },
    async advance(ms) {
      now += ms
      for (const t of timers) {
        if (!t.done && t.at <= now) {
          t.done = true
          await t.fn()
        }
      }
    }
  }
}

function setup(mode = 'perfect', files = { 'mock/demo.reference.json': ref, 'mock/result.perfect.json': result }) {
  const env = fakeEnv(files)
  const voice = createMockVoice(mode, CFG, env)
  const events = []
  voice.subscribe((name, json) => events.push([name, JSON.parse(json)]))
  return { env, voice, events, last: name => events.filter(e => e[0] === name).at(-1)?.[1] }
}

test('unlock emits on_unlocked with the contract fields', async () => {
  const { voice, last } = setup()
  await voice.unlock()
  assert.deepEqual(Object.keys(last('on_unlocked')), ['sr', 'noise_db', 'lag_ms', 'bt_suspect'])
})

test('load_song falls back to the fixture and adds scoring and lag', async () => {
  const { voice, last } = setup()
  voice.configure('{"difficulty":"hard","lag_ms":55}')
  await voice.load_song('demo')
  const ready = last('on_ready')
  assert.equal(ready.id, 'demo')
  assert.deepEqual(ready.scoring, { tol_cents: 60 })
  assert.equal(ready.lag_ms, 55)
})

test('unknown song emits net error', async () => {
  const { voice, last } = setup()
  await voice.load_song('nope')
  assert.equal(last('on_error').code, 'net')
})

test('poll streams frames on the song clock and ends the song', async () => {
  const { env, voice, last } = setup()
  await voice.load_song('demo')
  assert.deepEqual(JSON.parse(voice.poll()), { t_now: 0, state: 'idle', level: 0, frames: [] })
  voice.start()
  await env.advance(150 + 2700)
  const p = JSON.parse(voice.poll())
  assert.equal(p.state, 'playing')
  assert.equal(p.t_now, 2.7)
  assert.ok(p.frames.length > 200 && p.frames.length <= 2000)
  const voiced = p.frames.filter(f => f.t > 2.55 && f.t < 2.7)
  assert.ok(voiced.length > 5 && voiced.every(f => Math.abs(f.hz - 261.6) < 5))
  assert.equal(JSON.parse(voice.poll()).frames.length, 0)
  await env.advance(ref.audio.duration * 1000)
  assert.equal(JSON.parse(voice.poll()).state, 'ended')
  assert.ok(last('on_song_end').t >= ref.audio.duration - 0.01)
})

test('frame backlog is capped at 2000', async () => {
  const long = { ...ref, audio: { ...ref.audio, duration: 40 } }
  const { env, voice } = setup('perfect', { 'mock/demo.reference.json': long })
  await voice.load_song('demo')
  voice.start()
  await env.advance(150 + 30000)
  assert.equal(JSON.parse(voice.poll()).frames.length, 2000)
})

test('submit returns the mock result after 500 ms with the player name', async () => {
  const { env, voice, last } = setup('octave')
  await voice.load_song('demo')
  voice.submit('Паша', '')
  await env.advance(499)
  assert.equal(last('on_result'), undefined)
  await env.advance(1)
  assert.equal(last('on_result').player, 'Паша')
  assert.equal(last('on_result').challenge, null)
})

test('calibrate reports the current lag with 8 hits and echoes the mode', async () => {
  const { env, voice, last } = setup()
  voice.calibrate()
  await env.advance(1000)
  assert.deepEqual(last('on_calibrated'), { lag_ms: 40, hits: 8, mode: 'speakers' })
  voice.calibrate('headphones')
  await env.advance(1000)
  assert.deepEqual(last('on_calibrated'), { lag_ms: 40, hits: 8, mode: 'headphones' })
})

test('mock reports its lag as config', () => {
  assert.equal(setup().voice._state().lag_source, 'config')
})

test('unknown mode falls back to perfect', () => {
  assert.equal(createMockVoice('bogus', CFG, fakeEnv({}))._mode, 'perfect')
})

test('mock emits on_note_judged for every note and exposes client_id', async () => {
  let now = 0
  const env = {
    performance: { now: () => now },
    setTimeout: () => 0,
    clearTimeout() {},
    fetch: async () => ({ ok: true, json: async () => ref }),
    localStorage: { getItem: () => null, setItem() {} },
    crypto
  }
  const v = createMockVoice('perfect', { tol_cents: { normal: 120 }, mock_base: 'http://x/' }, env)
  const events = []
  v.subscribe((name, json) => events.push([name, JSON.parse(json)]))
  await v.load_song('demo')
  v.start()
  for (now = 0; now <= (ref.audio.duration + 1) * 1000; now += 50) v.poll()
  const judged = events.filter(([n]) => n === 'on_note_judged').map(([, p]) => p)
  assert.deepEqual(judged.map(j => j.i), [0, 1, 2, 3, 4, 5])
  assert.ok(judged.every(j => j.hit >= 0.8))
  assert.match(v.client_id(), /^[0-9a-f-]{36}$/)
})

test('on_result carries the same client_id as client_id()', async () => {
  const env = fakeEnv({ 'mock/demo.reference.json': ref, 'mock/result.perfect.json': result })
  env.crypto = crypto
  const voice = createMockVoice('perfect', CFG, env)
  const events = []
  voice.subscribe((name, json) => events.push([name, JSON.parse(json)]))
  await voice.load_song('demo')
  voice.submit('Паша', '')
  await env.advance(500)
  const id = voice.client_id()
  assert.match(id, /^[0-9a-f-]{36}$/)
  assert.equal(events.filter(e => e[0] === 'on_result').at(-1)[1].client_id, id)
})

test('plan b uploads the saved take without a session token', async () => {
  let sent
  const env = {
    ...fakeEnv({}),
    FormData,
    Blob,
    AbortController,
    async fetch(url, init) {
      const u = String(url)
      if (u.endsWith('mock/take.wav')) return { ok: true, arrayBuffer: async () => new ArrayBuffer(44) }
      if (u.endsWith('mock/take.meta.json')) return { ok: true, json: async () => ({ song_id: 'demo', client_id: null, session_token: 'used-token', player: 'dev' }) }
      if (u.endsWith('/api/v1/takes')) {
        sent = JSON.parse(init.body.get('meta'))
        return { ok: true, json: async () => ({ take_id: 'tk_b' }) }
      }
      return { ok: false, status: 404 }
    }
  }
  const voice = createMockVoice('perfect', CFG, env)
  assert.equal(await voice._planB(), true)
  assert.equal(sent.session_token, null)
  assert.deepEqual(Object.keys(sent).slice(0, 3), ['song_id', 'client_id', 'session_token'])
  assert.equal(voice._state().session, 'none')
})

const webMock = name => JSON.parse(readFileSync(new URL(`../mock/${name}`, import.meta.url)))
const CHALLENGE_KEYS = ['id', 'opponent', 'opponent_total', 'delta', 'verdict', 'lines_won', 'lines_lost']

test('submit with a challenge id compares against a synthetic owner like the backend', async () => {
  for (const [mode, file, verdict] of [['perfect', 'result.perfect.json', 'win'], ['offkey', 'result.offkey.json', 'lose']]) {
    const r = webMock(file)
    const { env, voice, last } = setup(mode, { 'mock/demo.reference.json': ref, [`mock/${file}`]: r })
    await voice.load_song('demo')
    voice.submit('Паша', 'ab12cd')
    await env.advance(500)
    const c = last('on_result').challenge
    assert.deepEqual(Object.keys(c), CHALLENGE_KEYS)
    assert.equal(c.id, 'ab12cd')
    assert.equal(c.opponent, 'Соперник')
    assert.equal(c.opponent_total, 7320)
    assert.equal(c.delta, r.score.total - 7320)
    assert.equal(c.verdict, verdict)
    assert.equal(Math.sign(c.delta), verdict === 'win' ? 1 : -1)
    assert.equal(c.lines_won, r.lines.filter(l => l.score > 75).length)
    assert.equal(c.lines_lost, r.lines.filter(l => l.score < 75).length)
  }
})

test('mock results carry a leaderboard except the incomplete silent take', () => {
  for (const m of ['offkey', 'octave', 'late200']) assert.deepEqual(webMock(`result.${m}.json`).leaderboard, { rank: 2, of: 5, personal_best: false }, m)
  const silent = webMock('result.silent.json')
  assert.equal(silent.integrity.status, 'incomplete')
  assert.equal(silent.completion.ratio, 0)
  assert.equal(silent.leaderboard, null)
  assert.equal(silent.latency.estimated_ms, 0)
})

test('submit and calibrate return promises that settle when the event fires', async () => {
  const { env, voice, last } = setup()
  await voice.load_song('demo')
  const sent = voice.submit('Паша', '')
  assert.equal(typeof sent?.then, 'function')
  await env.advance(500)
  assert.equal(await sent, true)
  assert.ok(last('on_result'))
  const cal = voice.calibrate('speakers')
  assert.equal(typeof cal?.then, 'function')
  await env.advance(1000)
  assert.equal(await cal, true)
  const missing = setup('perfect', { 'mock/demo.reference.json': ref })
  await missing.voice.load_song('demo')
  const failed = missing.voice.submit('Паша', '')
  await missing.env.advance(500)
  assert.equal(await failed, false)
  assert.equal(missing.last('on_error').code, 'net')
})

test('a superseded load_song returns false and emits nothing', async () => {
  const { voice, events } = setup('perfect', { 'mock/a.reference.json': { ...ref, id: 'a' }, 'mock/b.reference.json': { ...ref, id: 'b' } })
  const [a, b] = await Promise.all([voice.load_song('a'), voice.load_song('b')])
  assert.equal(a, false)
  assert.equal(b, true)
  assert.deepEqual(events.map(([n, p]) => [n, p.id]), [['on_ready', 'b']])
  const gone = setup('perfect', { 'mock/b.reference.json': { ...ref, id: 'b' } })
  const [x, y] = await Promise.all([gone.voice.load_song('nope'), gone.voice.load_song('b')])
  assert.equal(x, false)
  assert.equal(y, true)
  assert.deepEqual(gone.events.map(([n]) => n), ['on_ready'])
})

test('on_result reports the loaded song, the difficulty and the cleaned name', async () => {
  const { env, voice, last } = setup('perfect', { 'mock/other.reference.json': { ...ref, id: 'other' }, 'mock/result.perfect.json': result })
  voice.configure('{"difficulty":"hard"}')
  await voice.load_song('other')
  voice.submit('', '')
  await env.advance(500)
  assert.equal(last('on_result').difficulty, 'hard')
  assert.equal(last('on_result').song_id, 'other')
  assert.equal(last('on_result').player, 'Игрок')
  voice.submit('я'.repeat(30), '')
  await env.advance(500)
  assert.equal(Array.from(last('on_result').player).length, 24)
  assert.deepEqual(Object.keys(last('on_result')), Object.keys(result))
})

test('configure ignores an unknown difficulty', async () => {
  const { env, voice, last } = setup()
  voice.configure('{"difficulty":"hard"}')
  voice.configure('{"difficulty":"bogus"}')
  voice.configure('{"difficulty":"constructor"}')
  await voice.load_song('demo')
  assert.deepEqual(last('on_ready').scoring, { tol_cents: 60 })
  voice.submit('Паша', '')
  await env.advance(500)
  assert.equal(last('on_result').difficulty, 'hard')
})

test('plan b posts the current client id and the cleaned name', async () => {
  for (const stored of ['11111111-2222-4333-8444-555555555555', null]) {
    let sent
    const env = {
      ...fakeEnv({}),
      crypto,
      FormData,
      Blob,
      AbortController,
      async fetch(url, init) {
        const u = String(url)
        if (u.endsWith('mock/take.wav')) return { ok: true, arrayBuffer: async () => new ArrayBuffer(44) }
        if (u.endsWith('mock/take.meta.json')) return { ok: true, json: async () => ({ song_id: 'demo', client_id: stored, session_token: 'used-token', player: '  ' }) }
        if (u.endsWith('/api/v1/takes')) {
          sent = JSON.parse(init.body.get('meta'))
          return { ok: true, json: async () => ({ take_id: 'tk_b' }) }
        }
        return { ok: false, status: 404 }
      }
    }
    const voice = createMockVoice('perfect', CFG, env)
    assert.equal(await voice._planB(), true)
    assert.match(voice.client_id(), /^[0-9a-f-]{36}$/)
    assert.equal(sent.client_id, voice.client_id())
    assert.equal(sent.session_token, null)
    assert.equal(sent.player, 'Игрок')
  }
})

test('publish and unpublish settle true and emit on_published after a tick', async () => {
  const { env, voice, events } = setup()
  const pub = voice.publish('tk_1')
  assert.equal(typeof pub?.then, 'function')
  assert.equal(events.some(e => e[0] === 'on_published'), false)
  await env.advance(0)
  assert.equal(await pub, true)
  const un = voice.unpublish('tk_1')
  await env.advance(0)
  assert.equal(await un, true)
  assert.deepEqual(events.filter(e => e[0] === 'on_published').map(e => e[1]), [
    { take_id: 'tk_1', published: true, ok: true, code: null },
    { take_id: 'tk_1', published: false, ok: true, code: null }
  ])
})

test('listen takes the duration from the downloaded wav and ends on a timer', async () => {
  const wav = encodeWav(new Float32Array(32000), 16000)
  const env = {
    ...fakeEnv({}),
    async fetch(url) {
      const u = String(url)
      if (u.endsWith('/api/v1/published/tk_1')) return { ok: true, json: async () => ({ take_id: 'tk_1', audio: '/api/v1/published/tk_1/audio' }) }
      if (u.endsWith('/api/v1/published/tk_1/audio')) return { ok: true, arrayBuffer: async () => wav }
      return { ok: false, status: 404 }
    }
  }
  const voice = createMockVoice('perfect', CFG, env)
  const events = []
  voice.subscribe((name, json) => events.push([name, JSON.parse(json)]))
  assert.equal(await voice.listen('tk_1'), true)
  assert.deepEqual(events, [['on_listen', { take_id: 'tk_1', duration: 2 }]])
  await env.advance(1999)
  assert.equal(events.length, 1)
  await env.advance(1)
  assert.deepEqual(events.at(-1), ['on_listen_end', { take_id: 'tk_1', reason: 'ended', code: null }])
  assert.equal(voice.listen_stop(), false)
  assert.equal(events.length, 2)
})

test('listen falls back to the song duration and listen_stop cancels the timer', async () => {
  const { env, voice, events } = setup()
  await voice.load_song('demo')
  assert.equal(await voice.listen('tk_1'), true)
  assert.deepEqual(events.filter(e => e[0] === 'on_listen').map(e => e[1]), [{ take_id: 'tk_1', duration: ref.audio.duration }])
  assert.equal(voice.listen_stop(), true)
  await env.advance(ref.audio.duration * 1000 + 1)
  assert.deepEqual(events.filter(e => e[0] === 'on_listen_end').map(e => e[1]), [{ take_id: 'tk_1', reason: 'stopped', code: null }])
})

test('mock listen is refused while playing and start() stops a cover', async () => {
  const { env, voice, events } = setup()
  await voice.load_song('demo')
  await voice.listen('tk_1')
  voice.start()
  assert.equal(await voice.listen('tk_2'), false)
  await env.advance(ref.audio.duration * 1000 + 200)
  assert.deepEqual(events.filter(e => e[0] === 'on_listen_end').map(e => e[1]), [
    { take_id: 'tk_1', reason: 'stopped', code: null },
    { take_id: 'tk_2', reason: 'error', code: 'audio_locked' }
  ])
  assert.equal(events.some(e => e[0] === 'on_error'), false)
})
