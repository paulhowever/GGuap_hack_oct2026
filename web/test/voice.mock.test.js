import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createMockVoice } from '../voice.mock.js'

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

test('calibrate reports the current lag with 8 hits', async () => {
  const { env, voice, last } = setup()
  voice.calibrate()
  await env.advance(1000)
  assert.deepEqual(last('on_calibrated'), { lag_ms: 40, hits: 8 })
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
