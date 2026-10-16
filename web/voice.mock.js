import { createBus, parseOptions } from './lib/bridge.js'
import { FrameQueue } from './lib/queue.js'
import { ERR, errorPayload } from './lib/errors.js'
import { MODES, MOCK_HOP, rng, mockFrames } from './lib/mock.js'
import { postTake } from './lib/upload.js'
import { round } from './lib/num.js'
import { toMs } from './lib/timing.js'
import { createJudge } from './lib/judge.js'
import { clientId } from './lib/profile.js'
import { getJson } from './lib/http.js'
import { playerName } from './lib/meta.js'
import { DEFAULT_TOL } from './lib/scoring.js'
import { CLICKS } from './lib/calibration.js'

const BASE = new URL('./', import.meta.url).href
const START_DELAY_MS = 150
const SUBMIT_DELAY_MS = 500
const CALIBRATE_DELAY_MS = 1000
const OPPONENT = 'Соперник'
const OPPONENT_TOTAL = 7320
const OPPONENT_LINE = 75

function mockChallenge(id, r) {
  const delta = r.score.total - OPPONENT_TOTAL
  return {
    id: String(id),
    opponent: OPPONENT,
    opponent_total: OPPONENT_TOTAL,
    delta,
    verdict: delta > 0 ? 'win' : delta < 0 ? 'lose' : 'draw',
    lines_won: r.lines.filter(l => l.score > OPPONENT_LINE).length,
    lines_lost: r.lines.filter(l => l.score < OPPONENT_LINE).length
  }
}

export function createMockVoice(mode, cfg = {}, env = globalThis) {
  const m = MODES.includes(mode) ? mode : 'perfect'
  const bus = createBus({ sticky: ['on_unlocked'] })
  const queue = new FrameQueue(2000)
  const rand = rng(7)
  const api = cfg.api || ''
  const base = cfg.mock_base || BASE
  const s = { ref: null, state: 'idle', startAt: 0, lastT: 0, timer: null, level: 0, difficulty: cfg.difficulty || 'normal', lag: toMs(cfg.lag_ms) ?? 40, player: null, loadSeq: 0 }

  const tNow = () => (s.state === 'idle' ? 0 : (env.performance.now() - s.startAt) / 1000)
  const tolTable = cfg.tol_cents || DEFAULT_TOL
  const tol = () => tolTable[s.difficulty] ?? 120
  const fail = (code, err) => {
    bus.emit('on_error', errorPayload(code, err))
    return false
  }

  async function firstJson(urls) {
    for (const u of urls) {
      const j = await getJson(env, u)
      if (j !== null) return j
    }
    return null
  }

  function finish() {
    if (s.state !== 'playing') return
    s.state = 'ended'
    for (const j of s.judge?.flush() ?? []) bus.emit('on_note_judged', j)
    bus.emit('on_song_end', { t: round(tNow(), 3) })
  }

  return {
    _mode: m,
    subscribe(cb) {
      bus.subscribe(cb)
    },
    unlock() {
      bus.emit('on_unlocked', { sr: 48000, noise_db: -62, lag_ms: s.lag, bt_suspect: false })
      return Promise.resolve(true)
    },
    configure(json) {
      const o = parseOptions(json)
      if (typeof o.difficulty === 'string' && Object.hasOwn(tolTable, o.difficulty)) s.difficulty = o.difficulty
      const lag = toMs(o.lag_ms)
      if (lag !== null) s.lag = lag
    },
    async load_song(id) {
      const seq = ++s.loadSeq
      const ref = await firstJson([`${api}/api/v1/songs/${encodeURIComponent(id)}`, `${base}mock/${id}.reference.json`])
      if (seq !== s.loadSeq) return false
      if (!ref) return fail(ERR.NET, `song ${id} not found`)
      env.clearTimeout(s.timer)
      s.ref = ref
      s.state = 'idle'
      bus.emit('on_ready', { ...ref, scoring: { tol_cents: tol() }, lag_ms: s.lag })
      return true
    },
    start() {
      if (!s.ref) return fail(ERR.LOCKED, 'start before load_song')
      if (s.state === 'playing') return true
      s.state = 'playing'
      s.startAt = env.performance.now() + START_DELAY_MS
      s.lastT = -START_DELAY_MS / 1000
      queue.drain()
      s.judge = createJudge(s.ref, { tolCents: tol() })
      s.timer = env.setTimeout(finish, START_DELAY_MS + s.ref.audio.duration * 1000)
      return true
    },
    stop() {
      env.clearTimeout(s.timer)
      if (s.state === 'playing') s.state = 'ended'
      return Promise.resolve(null)
    },
    poll() {
      const t = tNow()
      if (s.state === 'playing') {
        const frames = mockFrames(s.ref, m, Math.max(s.lastT, t - 2000 * MOCK_HOP), t, rand)
        queue.push(...frames)
        for (const f of frames) for (const j of s.judge.push(f)) bus.emit('on_note_judged', j)
        if (frames.length) s.level = frames.at(-1).rms
        s.lastT = t
      }
      return JSON.stringify({ t_now: round(t, 3), state: s.state, level: s.level, frames: queue.drain() })
    },
    submit(player, challengeId) {
      s.player = player || null
      return new Promise(resolve => {
        env.setTimeout(async () => {
          const r = await firstJson([`${base}mock/result.${m}.json`, `${base}mock/result.perfect.json`])
          if (!r) return resolve(fail(ERR.NET, 'mock result not found'))
          bus.emit('on_result', { ...r, song_id: s.ref?.id ?? r.song_id, client_id: clientId(env), player: playerName(player), difficulty: s.difficulty, challenge: challengeId ? mockChallenge(challengeId, r) : null })
          resolve(true)
        }, SUBMIT_DELAY_MS)
      })
    },
    client_id() {
      return clientId(env)
    },
    calibrate(mode) {
      const kind = mode === 'headphones' ? 'headphones' : 'speakers'
      return new Promise(resolve => {
        env.setTimeout(() => {
          bus.emit('on_calibrated', { lag_ms: s.lag, hits: CLICKS, mode: kind })
          resolve(true)
        }, CALIBRATE_DELAY_MS)
      })
    },
    async _planB() {
      const wav = await env.fetch(`${base}mock/take.wav`).then(r => (r.ok ? r.arrayBuffer() : null)).catch(() => null)
      const meta = await firstJson([`${base}mock/take.meta.json`])
      if (!wav || !meta) return fail(ERR.UPLOAD, 'mock/take.wav or mock/take.meta.json missing')
      meta.player = playerName(s.player ?? meta.player)
      meta.client_id = clientId(env)
      meta.session_token = null
      try {
        bus.emit('on_result', await postTake({ env, url: `${api}/api/v1/takes`, wav, meta }))
        return true
      } catch (e) {
        return fail(ERR.UPLOAD, e)
      }
    },
    _take() {
      return null
    },
    _state() {
      return { sr: 48000, lag_ms: s.lag, lag_source: 'config', mode: m, session: 'none' }
    }
  }
}

export function attachPlanB(voice, win) {
  win.addEventListener?.('keydown', e => {
    if (e.code === 'KeyR' && e.altKey && e.shiftKey && !e.repeat) voice._planB()
  }, true)
}
