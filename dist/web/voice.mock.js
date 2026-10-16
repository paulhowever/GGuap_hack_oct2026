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
import { parseWavHeader } from './lib/wav.js'

const BASE = new URL('./', import.meta.url).href
const START_DELAY_MS = 150
const SUBMIT_DELAY_MS = 500
const CALIBRATE_DELAY_MS = 1000
const OPPONENT = 'Соперник'
const OPPONENT_TOTAL = 7320
const OPPONENT_LINE = 75
const MOCK_LISTEN_S = 5

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
  const s = { ref: null, state: 'idle', startAt: 0, lastT: 0, timer: null, level: 0, difficulty: cfg.difficulty || 'normal', lag: toMs(cfg.lag_ms) ?? 40, player: null, loadSeq: 0, listenSeq: 0, listening: null, review: null }

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

  // Таймлайн без звука: p = { state: 'loading'|'playing'|'paused'|'ended', pos, startAt, duration, timer }
  const nowS = () => env.performance.now() / 1000
  const posOf = p => (p.state === 'playing' ? Math.min(p.duration, p.pos + nowS() - p.startAt) : p.pos)

  function runTimeline(p, pos, onEnd) {
    env.clearTimeout(p.timer)
    p.pos = Math.max(0, Math.min(pos, p.duration))
    p.startAt = nowS()
    p.state = 'playing'
    p.timer = env.setTimeout(() => onEnd(p), (p.duration - p.pos) * 1000)
  }

  function holdTimeline(p) {
    if (!p || p.state !== 'playing') return false
    p.pos = posOf(p)
    env.clearTimeout(p.timer)
    p.state = 'paused'
    return true
  }

  function seekTimeline(p, t, onEnd) {
    if (!p || p.state === 'loading') return false
    const pos = Math.max(0, Math.min(Number(t) || 0, p.duration))
    if (p.state === 'playing') runTimeline(p, pos, onEnd)
    else {
      p.pos = pos
      p.state = 'paused'
    }
    return true
  }

  const stateOf = (p, extra) => JSON.stringify({ ...extra, state: p.state, t: round(posOf(p), 3), duration: round(p.duration, 3) })

  function endListen(p, reason, code = null) {
    if (!p || s.listening !== p) return false
    s.listening = null
    s.listenSeq++
    env.clearTimeout(p.timer)
    bus.emit('on_listen_end', { take_id: p.take_id, reason, code })
    return false
  }

  const onListenEnded = p => endListen(p, 'ended')

  function stopReview() {
    const r = s.review
    if (r && r.state === 'playing') holdTimeline(r)
  }

  const onReviewEnded = r => {
    if (s.review !== r) return
    r.state = 'ended'
    r.pos = r.duration
  }

  function stopListen(reason) {
    if (!s.listening) {
      s.listenSeq++
      return false
    }
    endListen(s.listening, reason)
    return true
  }

  async function wavSeconds(take_id) {
    const item = await getJson(env, `${api}/api/v1/published/${encodeURIComponent(take_id)}`)
    const audio = typeof item?.audio === 'string' ? (/^https?:\/\//.test(item.audio) ? item.audio : api + item.audio) : `${base}mock/take.wav`
    try {
      const r = await env.fetch(audio)
      return r.ok ? parseWavHeader(await r.arrayBuffer())?.duration ?? null : null
    } catch {
      return null
    }
  }

  function settle(name, payload, value) {
    return new Promise(resolve => {
      env.setTimeout(() => {
        bus.emit(name, payload)
        resolve(value)
      }, 0)
    })
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
      stopListen('stopped')
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
      stopListen('stopped')
      stopReview()
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
          const song_id = s.ref?.id ?? r.song_id
          // мок «записал» дубль: прослушивание без звука, только таймлайн
          if (s.review) env.clearTimeout(s.review.timer)
          s.review = { take_id: r.take_id ?? null, song_id, state: 'paused', pos: 0, startAt: 0, duration: round(s.ref?.audio?.duration || MOCK_LISTEN_S, 3), timer: null }
          bus.emit('on_result', { ...r, song_id, client_id: clientId(env), player: playerName(player), difficulty: s.difficulty, challenge: challengeId ? mockChallenge(challengeId, r) : null })
          resolve(true)
        }, SUBMIT_DELAY_MS)
      })
    },
    client_id() {
      return clientId(env)
    },
    calibrate(mode) {
      stopListen('stopped')
      stopReview()
      const kind = mode === 'headphones' ? 'headphones' : 'speakers'
      return new Promise(resolve => {
        env.setTimeout(() => {
          bus.emit('on_calibrated', { lag_ms: s.lag, hits: CLICKS, mode: kind })
          resolve(true)
        }, CALIBRATE_DELAY_MS)
      })
    },
    publish(id) {
      const take_id = String(id ?? '')
      return settle('on_published', { take_id, published: true, ok: true, code: null }, true)
    },
    unpublish(id) {
      const take_id = String(id ?? '')
      return settle('on_published', { take_id, published: false, ok: true, code: null }, true)
    },
    async listen(id) {
      const take_id = String(id ?? '')
      stopListen('stopped')
      stopReview()
      if (s.state === 'playing') {
        bus.emit('on_listen_end', { take_id, reason: 'error', code: ERR.LOCKED })
        return false
      }
      const p = { take_id, seq: ++s.listenSeq, timer: null, state: 'loading', pos: 0, startAt: 0, duration: 0 }
      s.listening = p
      const seconds = await wavSeconds(take_id)
      if (s.listening !== p || p.seq !== s.listenSeq) return false
      p.duration = round((Number.isFinite(seconds) && seconds > 0 ? seconds : s.ref?.audio?.duration) || MOCK_LISTEN_S, 3)
      runTimeline(p, 0, onListenEnded)
      bus.emit('on_listen', { take_id, duration: p.duration })
      return true
    },
    listen_stop() {
      return stopListen('stopped')
    },
    listen_pause() {
      return holdTimeline(s.listening)
    },
    listen_resume() {
      const p = s.listening
      if (!p || p.state !== 'paused' || s.state === 'playing') return false
      runTimeline(p, p.pos, onListenEnded)
      return true
    },
    listen_seek(t) {
      return seekTimeline(s.listening, t, onListenEnded)
    },
    listen_state() {
      const p = s.listening
      return p ? stateOf(p, { take_id: p.take_id }) : JSON.stringify({ take_id: null, state: 'idle', t: 0, duration: 0 })
    },
    review_play(from = -1) {
      const r = s.review
      if (!r || s.state === 'playing') return false
      stopListen('stopped')
      const f = Number(from)
      let pos = Number.isFinite(f) && f >= 0 ? f : posOf(r)
      if (pos >= r.duration - 0.05) pos = 0
      runTimeline(r, pos, onReviewEnded)
      return true
    },
    review_pause() {
      return holdTimeline(s.review)
    },
    review_seek(t) {
      return seekTimeline(s.review, t, onReviewEnded)
    },
    review_stop() {
      const r = s.review
      if (!r) return false
      env.clearTimeout(r.timer)
      r.state = 'paused'
      r.pos = 0
      return true
    },
    review_state() {
      const r = s.review
      if (!r) return JSON.stringify({ available: false, state: 'idle', t: 0, duration: 0, song_id: null, take_id: null })
      return stateOf(r, { available: true, song_id: r.song_id, take_id: r.take_id })
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
