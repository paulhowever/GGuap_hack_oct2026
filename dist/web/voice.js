import { createBus, parseOptions } from './lib/bridge.js'
import { FrameQueue } from './lib/queue.js'
import { ERR, errorPayload, micErrorCode } from './lib/errors.js'
import { classifyFrame, contextNow, estimateLagMs, gateFrom, isBtSuspect, noiseFloor, resolveLagMs, toDb, toMs } from './lib/timing.js'
import { PcmRecorder } from './lib/recorder.js'
import { downsample } from './lib/resample.js'
import { encodeWav } from './lib/wav.js'
import { buildMeta } from './lib/meta.js'
import { postTake } from './lib/upload.js'
import { createJudge } from './lib/judge.js'
import { clientId } from './lib/profile.js'
import { requestSession } from './lib/session.js'
import { attachDebug, isDebug } from './lib/debug.js'
import { CLICK_LEAD, CLICK_LEN, CLICKS, HEADPHONES, LEAD_IN, SPEAKERS, clickTimes, detectOnsets, estimateLag, onsetThreshold } from './lib/calibration.js'
import { clamp, round } from './lib/num.js'
import { DEFAULT_TOL, RHO_MIN } from './lib/scoring.js'
import { createMockVoice, attachPlanB } from './voice.mock.js'

const LAG_KEY = 'voice.lag_ms'
const LAG_SRC_KEY = 'voice.lag_src'
const TARGET_SR = 16000
const START_DELAY = 0.15
const NOISE_SECONDS = 1
const MAX_TAKE_SECONDS = 60
const MAX_TAKE_FRAMES = 8000
const UPLOAD_TIMEOUT_MS = 10000
const REC_FLUSH_TIMEOUT_MS = 500
const RESUME_TIMEOUT_MS = 1000
const SESSION_TIMEOUT_MS = 2000
const AUTO_OUTLIER_MS = 150
const ESTIMATED_SLACK_S = 0.15
const PUBLISH_TIMEOUT_MS = 5000
const LISTEN_LEAD = 0.1
const WAV_T0_MAX = 5

export function createVoice(cfg = {}, env = globalThis) {
  const bus = createBus({ sticky: ['on_unlocked'] })
  const queue = new FrameQueue(2000)
  const api = cfg.api || ''
  const tolTable = cfg.tol_cents || DEFAULT_TOL
  const s = {
    ctx: null, stream: null, mic: null, tap: null, music: null, src: null, unlocking: null, calibrating: false,
    sr: 0, floor: 0, gate: 0.01, level: 0,
    difficulty: cfg.difficulty || 'normal', aec: !!cfg.aec, volume: cfg.music_volume ?? 1,
    sessionLag: null, sessionSource: null, estLag: 20, lag: 20, lagSource: 'estimated', saved: null, outlier: null,
    ref: null, buffer: null, state: 'idle', t0: 0, loadSeq: 0, judge: null,
    rec: null, flushRec: null, takeFrames: [], take: null, takeJob: null, recDone: null,
    tokenJob: null, identity: null, tokenState: 'none',
    listenSeq: 0, listening: null, lastPub: null, reviewing: null, lastApplied: null,
    listeners: new Set()
  }

  bus.subscribe((name, json) => {
    if (name !== 'on_result') return
    try {
      const r = JSON.parse(json)
      const w = s.take?.wav_t0
      s.lastPub = { take_id: r?.take_id ?? null, wav_t0: Number.isFinite(w) && Math.abs(w) <= WAV_T0_MAX ? round(w, 3) : null }
      const applied = r?.latency?.applied_ms
      s.lastApplied = Number.isFinite(applied) ? applied : null
    } catch {}
  })

  const fail = (code, err) => {
    bus.emit('on_error', errorPayload(code, err))
    return false
  }
  const url = p => (/^https?:\/\//.test(p) ? p : api + p)
  const tol = () => tolTable[s.difficulty] ?? tolTable.normal

  function readKey(key) {
    try {
      return env.localStorage?.getItem(key) ?? null
    } catch {
      return null
    }
  }

  function writeStored(v, source) {
    s.saved = { ms: v, src: source }
    try {
      env.localStorage?.setItem(LAG_KEY, String(v))
      env.localStorage?.setItem(LAG_SRC_KEY, source)
    } catch {}
  }

  function setSessionLag(v, source) {
    s.sessionLag = v
    s.sessionSource = source
    writeStored(v, source)
    if (s.state !== 'playing') refreshLag()
  }

  function resolveLag() {
    const r = resolveLagMs({ session: s.sessionLag, sessionSource: s.sessionSource, pinned: toMs(cfg.lag_ms), stored: s.saved.ms, storedSource: s.saved.src, estimated: s.estLag })
    return { lag: r.ms, lagSource: r.source }
  }

  function refreshLag() {
    Object.assign(s, resolveLag())
  }

  function autoLag(latency) {
    const est = toMs(latency?.estimated_ms)
    if (est === null || !(latency.confidence >= RHO_MIN)) return
    const { lag: prev, lagSource } = resolveLag()
    if (lagSource !== 'estimated' && lagSource !== 'auto') return
    let next = est
    if (lagSource === 'auto') {
      if (Math.abs(est - prev) > AUTO_OUTLIER_MS) {
        const first = s.outlier
        s.outlier = est
        if (first === null || Math.abs(est - first) > AUTO_OUTLIER_MS) return
        next = Math.round((first + est) / 2)
      } else {
        next = Math.round((prev + est) / 2)
      }
    }
    s.outlier = null
    writeStored(next, 'auto')
    if (s.state !== 'playing') refreshLag()
  }

  s.saved = { ms: toMs(readKey(LAG_KEY)), src: readKey(LAG_SRC_KEY) }
  refreshLag()

  function songNow() {
    const ctx = s.ctx
    if (!ctx) return 0
    let ts = null
    try {
      ts = typeof ctx.getOutputTimestamp === 'function' ? ctx.getOutputTimestamp() : null
    } catch {}
    return contextNow({ currentTime: ctx.currentTime, outputLatency: ctx.outputLatency, baseLatency: ctx.baseLatency, ts, perfNow: env.performance.now() }) - s.t0
  }

  function collect(seconds) {
    return new Promise(resolve => {
      const out = []
      const end = s.ctx.currentTime + seconds
      const done = () => {
        s.listeners.delete(fn)
        resolve(out)
      }
      const fn = f => {
        out.push(f)
        if (f.E / s.sr >= end) done()
      }
      s.listeners.add(fn)
      env.setTimeout(done, seconds * 1000 + 1500)
    })
  }

  function onFrame(raw) {
    for (const fn of s.listeners) fn(raw)
    const f = classifyFrame(raw, { sr: s.sr, t0: s.t0, lagS: s.lag / 1000, gate: s.gate, clarityMin: cfg.clarity_min ?? 0.85 })
    s.level = f.rms
    queue.push(f)
    if (s.state === 'playing' && s.takeFrames.length < MAX_TAKE_FRAMES) s.takeFrames.push(f)
    if (s.state === 'playing' && s.judge) for (const j of s.judge.push(f)) bus.emit('on_note_judged', j)
  }

  function onTap(d) {
    if (d.frames) for (const f of d.frames) onFrame(f)
    else if (d.pcm) (s.flushRec ?? s.rec)?.push(d.pcm, d.F)
    else if (d.recDone && s.recDone) {
      s.recDone()
      s.recDone = null
    }
  }

  async function openMic() {
    let stream
    try {
      stream = await env.navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: s.aec, noiseSuppression: false, autoGainControl: false, channelCount: 1 } })
    } catch (e) {
      return fail(micErrorCode(e), e)
    }
    s.mic?.disconnect()
    s.stream?.getTracks().forEach(t => t.stop())
    s.stream = stream
    s.mic = s.ctx.createMediaStreamSource(stream)
    if (s.tap) s.mic.connect(s.tap)
    return true
  }

  async function createTap() {
    const ctx = s.ctx
    try {
      await ctx.audioWorklet.addModule(new URL(cfg.tap_url || './tap.js', import.meta.url))
      s.tap = new env.AudioWorkletNode(ctx, 'tap', { numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1], channelCount: 1, channelCountMode: 'explicit' })
    } catch (e) {
      return fail(ERR.WORKLET, e)
    }
    s.tap.port.onmessage = e => onTap(e.data)
    const mute = ctx.createGain()
    mute.gain.value = 0
    s.tap.connect(mute)
    mute.connect(ctx.destination)
    s.music = ctx.createGain()
    s.music.gain.value = s.volume
    s.music.connect(ctx.destination)
    s.mic.connect(s.tap)
    return true
  }

  async function finishUnlock(resumed) {
    const ctx = s.ctx
    await Promise.race([resumed.catch(() => {}), new Promise(r => env.setTimeout(r, RESUME_TIMEOUT_MS))])
    if (ctx.state !== 'running') return fail(ERR.LOCKED, `AudioContext ${ctx.state}`)
    if (!(await openMic())) return false
    if (!s.tap && !(await createTap())) return false
    const frames = await collect(NOISE_SECONDS)
    s.floor = noiseFloor(frames.map(f => f.rms))
    s.gate = gateFrom(s.floor)
    const track = s.stream.getAudioTracks()[0]
    const bt = isBtSuspect(ctx.outputLatency)
    s.estLag = estimateLagMs({ outputLatency: ctx.outputLatency, baseLatency: ctx.baseLatency, trackLatency: track?.getSettings?.().latency, bt })
    refreshLag()
    bus.emit('on_unlocked', { sr: s.sr, noise_db: toDb(s.floor), lag_ms: s.lag, bt_suspect: bt })
    return true
  }

  function openContext() {
    const AC = env.AudioContext || env.webkitAudioContext
    s.ctx = new AC({ latencyHint: 'interactive' })
    s.sr = s.ctx.sampleRate
    env.document?.addEventListener('pointerdown', () => {
      if (s.ctx.state !== 'running') s.ctx.resume().catch(() => {})
    })
  }

  async function runUnlock() {
    if (!s.ctx) {
      try {
        openContext()
      } catch (e) {
        return fail(ERR.LOCKED, e)
      }
    }
    try {
      return await finishUnlock(s.ctx.resume())
    } catch (e) {
      return fail(ERR.WORKLET, e)
    }
  }

  function unlock() {
    if (s.unlocking) return s.unlocking
    if (!env.isSecureContext || !env.navigator?.mediaDevices?.getUserMedia) return Promise.resolve(fail(ERR.INSECURE, 'getUserMedia unavailable: use https or localhost'))
    s.unlocking = runUnlock().then(ok => {
      if (!ok) s.unlocking = null
      return ok
    })
    return s.unlocking
  }

  function configure(json) {
    const o = parseOptions(json)
    if (typeof o.difficulty === 'string' && o.difficulty in tolTable) s.difficulty = o.difficulty
    const lag = toMs(o.lag_ms)
    if (lag !== null) setSessionLag(lag, 'config')
    if (typeof o.music_volume === 'number') {
      s.volume = clamp(o.music_volume, 0, 1)
      if (s.music) s.music.gain.value = s.volume
    }
    if (typeof o.aec === 'boolean' && o.aec !== s.aec) {
      s.aec = o.aec
      if (s.stream) openMic()
    }
  }

  async function load_song(id) {
    stopListen('stopped')
    stopReview()
    if (!s.ctx || s.ctx.state !== 'running') return fail(ERR.LOCKED, 'load_song before unlock')
    if (s.state === 'playing') stop()
    const seq = ++s.loadSeq
    const stale = () => seq !== s.loadSeq
    let ref
    let data
    try {
      const r = await env.fetch(url(`/api/v1/songs/${encodeURIComponent(id)}`))
      if (stale()) return false
      if (!r.ok) throw new Error(`songs/${id}: HTTP ${r.status}`)
      ref = await r.json()
      if (stale()) return false
      const a = await env.fetch(url(ref.audio.minus))
      if (stale()) return false
      if (!a.ok) throw new Error(`${ref.audio.minus}: HTTP ${a.status}`)
      data = await a.arrayBuffer()
      if (stale()) return false
    } catch (e) {
      if (stale()) return false
      return fail(ERR.NET, e)
    }
    let buffer
    try {
      buffer = await s.ctx.decodeAudioData(data)
    } catch (e) {
      return stale() ? false : fail(ERR.DECODE, e)
    }
    if (stale()) return false
    s.buffer = buffer
    s.ref = ref
    s.state = 'idle'
    s.take = null
    s.takeJob = null
    bus.emit('on_ready', { ...ref, scoring: { tol_cents: tol() }, lag_ms: s.lag })
    return true
  }

  function start() {
    stopListen('stopped')
    stopReview()
    if (!s.buffer || !s.tap) return fail(ERR.LOCKED, 'start before load_song')
    if (s.state === 'playing') return true
    const ctx = s.ctx
    if (ctx.state !== 'running') ctx.resume().catch(() => {})
    const src = ctx.createBufferSource()
    src.buffer = s.buffer
    src.connect(s.music)
    src.onended = () => {
      if (s.src !== src) return
      const t = songNow()
      for (const j of s.judge?.flush() ?? []) bus.emit('on_note_judged', j)
      stop()
      bus.emit('on_song_end', { t: round(t, 3) })
    }
    s.t0 = ctx.currentTime + START_DELAY
    s.rec = new PcmRecorder(s.sr, MAX_TAKE_SECONDS)
    s.takeFrames = []
    s.judge = createJudge(s.ref, { tolCents: tol(), slack: s.lagSource === 'estimated' ? ESTIMATED_SLACK_S : 0 })
    s.take = null
    s.takeJob = null
    queue.drain()
    s.tap.port.postMessage({ rec: true })
    src.start(s.t0)
    s.src = src
    s.state = 'playing'
    openSession()
    return true
  }

  function openSession() {
    const identity = { songId: s.ref.id, clientId: clientId(env), difficulty: s.difficulty }
    const job = requestSession({ env, url: url('/api/v1/sessions'), ...identity, timeoutMs: SESSION_TIMEOUT_MS })
    s.tokenJob = job
    s.identity = identity
    s.tokenState = 'pending'
    job.then(token => {
      if (s.tokenJob === job) s.tokenState = token ? 'ok' : 'none'
    })
  }

  async function resample16k(pcm, sr) {
    if (sr === TARGET_SR) return { data: pcm, rate: sr, resampler: 'none' }
    try {
      const OAC = env.OfflineAudioContext || env.webkitOfflineAudioContext
      const off = new OAC(1, Math.ceil(pcm.length * TARGET_SR / sr), TARGET_SR)
      const buf = off.createBuffer(1, pcm.length, sr)
      buf.copyToChannel(pcm, 0)
      const node = off.createBufferSource()
      node.buffer = buf
      node.connect(off.destination)
      node.start(0)
      const out = await off.startRendering()
      return { data: out.getChannelData(0), rate: TARGET_SR, resampler: 'offline' }
    } catch {
      const rate = Math.min(sr, TARGET_SR)
      return { data: downsample(pcm, sr, rate), rate, resampler: 'js' }
    }
  }

  async function buildTake(rec, info) {
    const pcm = rec.samples()
    const { data, rate, resampler } = await resample16k(pcm, rec.sr)
    return {
      ...info,
      wav: encodeWav(data, rate),
      wav_sr: rate,
      wav_t0: rec.firstFrame === null ? 0 : rec.firstFrame / rec.sr - info.t0,
      samples: data.length,
      resampler
    }
  }

  function stop() {
    if (s.state !== 'playing') return s.takeJob
    s.state = 'ended'
    const src = s.src
    s.src = null
    try {
      src.stop()
    } catch {}
    const rec = s.rec
    s.flushRec = rec
    const flushed = new Promise(resolve => {
      const done = () => {
        if (s.flushRec === rec) s.flushRec = null
        resolve()
      }
      s.recDone = done
      env.setTimeout(done, REC_FLUSH_TIMEOUT_MS)
    })
    s.tap.port.postMessage({ rec: false })
    const tokenJob = s.tokenJob
    const { songId, clientId: takeClientId, difficulty } = s.identity
    const info = { t0: s.t0, frames: s.takeFrames, lag_ms: s.lag, lag_source: s.lagSource, difficulty, song_id: songId, client_id: takeClientId }
    refreshLag()
    const job = flushed
      .then(() => buildTake(rec, info))
      .then(async take => {
        const t = { ...take, session_token: await tokenJob }
        if (s.takeJob === job) s.take = t
        return t
      })
      .catch(e => {
        fail(ERR.UPLOAD, e)
        return null
      })
    s.takeJob = job
    return job
  }

  function metaFor(take, player, challengeId) {
    const ctx = s.ctx
    return buildMeta({
      songId: take.song_id,
      clientId: take.client_id,
      sessionToken: take.token_spent ? null : take.session_token,
      player,
      difficulty: take.difficulty,
      challengeId,
      wavT0: take.wav_t0,
      wavSr: take.wav_sr,
      lagMs: take.lag_ms,
      lagSource: take.lag_source,
      frames: take.frames,
      client: { ua: env.navigator?.userAgent ?? '', sr: s.sr, base_latency: round(ctx?.baseLatency || 0, 4), output_latency: round(ctx?.outputLatency || 0, 4), aec: s.aec }
    })
  }

  async function submit(player, challengeId) {
    const take = await (s.takeJob || stop())
    if (!take || !take.samples) return fail(ERR.UPLOAD, 'no recorded take')
    try {
      const meta = metaFor(take, player, challengeId)
      take.token_spent = true
      const result = await postTake({ env, url: url('/api/v1/takes'), wav: take.wav, meta, timeoutMs: UPLOAD_TIMEOUT_MS })
      autoLag(result?.latency)
      bus.emit('on_result', result)
      return true
    } catch (e) {
      return fail(e?.name === 'TypeError' || e?.name === 'AbortError' ? ERR.NET : ERR.UPLOAD, e)
    }
  }

  async function calibrate(mode) {
    stopListen('stopped')
    stopReview()
    if (s.calibrating) return false
    if (!s.tap || s.state === 'playing') return fail(ERR.LOCKED, 'calibrate needs unlock and no song playing')
    s.calibrating = true
    const ctx = s.ctx
    const kind = mode === 'headphones' ? 'headphones' : 'speakers'
    const plan = kind === 'headphones' ? HEADPHONES : SPEAKERS
    const lead = kind === 'headphones' ? LEAD_IN : 0
    const all = clickTimes(ctx.currentTime + CLICK_LEAD, lead + CLICKS, plan.gap)
    const clicks = all.slice(lead)
    for (const c of all) {
      const osc = ctx.createOscillator()
      const g = ctx.createGain()
      osc.frequency.value = 1000
      g.gain.value = 0.5
      osc.connect(g)
      g.connect(ctx.destination)
      osc.start(c)
      osc.stop(c + CLICK_LEN)
    }
    const frames = await collect(clicks.at(-1) - ctx.currentTime + plan.late + 0.2)
    s.calibrating = false
    const r = estimateLag(clicks, detectOnsets(frames, { sr: s.sr, threshold: onsetThreshold(s.floor) }), { late: plan.late, range: plan.range })
    if (r.lag_ms !== null) setSessionLag(r.lag_ms, 'calibrated')
    bus.emit('on_calibrated', { lag_ms: s.lag, hits: r.hits, mode: kind })
    return r.lag_ms !== null
  }

  const takeIdOf = id => (typeof id === 'string' ? id : String(id ?? ''))

  async function requestJson(path, body) {
    const ac = new env.AbortController()
    const timer = env.setTimeout(() => ac.abort(), PUBLISH_TIMEOUT_MS)
    try {
      const r = await env.fetch(url(path), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: ac.signal })
      if (r.ok) return null
      const detail = await r.json().then(b => b?.detail, () => null)
      return typeof detail === 'string' && detail ? detail : `http_${r.status}`
    } catch {
      return ERR.NET
    } finally {
      env.clearTimeout?.(timer)
    }
  }

  async function setPublished(id, published) {
    const take_id = takeIdOf(id)
    let code = 'take_not_found'
    if (take_id) {
      const cid = clientId(env)
      code = published
        ? await requestJson('/api/v1/published', { take_id, client_id: cid, wav_t0: s.lastPub?.take_id === take_id ? s.lastPub.wav_t0 : null })
        : await requestJson(`/api/v1/published/${encodeURIComponent(take_id)}/remove`, { client_id: cid })
    }
    bus.emit('on_published', { take_id, published, ok: code === null, code })
    return code === null
  }

  // --- Транспорт прослушивания: вокал поверх минуса, пауза и перемотка ---
  // p = { vocal, minus, offset, duration, state: 'loading'|'playing'|'paused'|'ended', pos, at, nodes }
  // pos — позиция в секундах от начала прослушивания (song-time минуса), at — ctx-время позиции 0.

  function haltNodes(p) {
    for (const n of p.nodes) {
      n.onended = null
      try {
        n.stop()
      } catch {}
      try {
        n.disconnect()
      } catch {}
    }
    p.nodes = []
  }

  function transportPos(p) {
    if (p.state !== 'playing' || !p.vocal || !s.ctx) return p.pos
    return clamp(s.ctx.currentTime - p.at, p.pos, p.duration)
  }

  function playFrom(p, pos, onEnd) {
    haltNodes(p)
    const ctx = s.ctx
    const at = ctx.currentTime + LISTEN_LEAD
    const from = clamp(pos, 0, p.duration)
    p.pos = from
    p.at = at - from
    p.state = 'playing'
    const voiceSrc = ctx.createBufferSource()
    voiceSrc.buffer = p.vocal
    voiceSrc.connect(ctx.destination)
    p.nodes.push(voiceSrc)
    voiceSrc.onended = () => onEnd(p)
    if (p.minus) {
      let out = s.music
      if (!out) {
        out = ctx.createGain()
        out.gain.value = s.volume
        out.connect(ctx.destination)
        p.nodes.push(out)
      }
      const minusSrc = ctx.createBufferSource()
      minusSrc.buffer = p.minus
      minusSrc.connect(out)
      p.nodes.push(minusSrc)
      if (from > 0) minusSrc.start(at, from)
      else minusSrc.start(at)
      minusSrc.stop(at + p.duration - from)
    }
    const lead = p.offset - from
    if (lead >= 0) voiceSrc.start(at + lead)
    else voiceSrc.start(at, -lead)
  }

  function pauseTransport(p) {
    if (!p || p.state !== 'playing') return false
    p.pos = transportPos(p)
    haltNodes(p)
    p.state = 'paused'
    return true
  }

  function seekTransport(p, t, onEnd) {
    if (!p) return false
    const pos = clamp(Number(t) || 0, 0, p.duration || 0)
    if (p.state === 'playing' && p.vocal && audioReady()) {
      playFrom(p, pos, onEnd)
    } else {
      p.pos = pos
      if (p.state === 'ended') p.state = 'paused'
    }
    return true
  }

  function endListen(p, reason, code = null) {
    if (!p || s.listening !== p) return false
    s.listening = null
    s.listenSeq++
    haltNodes(p)
    bus.emit('on_listen_end', { take_id: p.take_id, reason, code })
    return false
  }

  const onListenEnded = p => {
    if (s.listening === p && p.seq === s.listenSeq) endListen(p, 'ended')
  }

  function stopListen(reason) {
    if (!s.listening) {
      s.listenSeq++
      return false
    }
    endListen(s.listening, reason)
    return true
  }

  function listenError(code, message) {
    const e = new Error(message)
    e.code = code
    return e
  }

  async function fetchBuffer(path) {
    let data
    try {
      const r = await env.fetch(url(path))
      if (!r.ok) throw listenError(ERR.NET, `${path}: HTTP ${r.status}`)
      data = await r.arrayBuffer()
    } catch (e) {
      throw e?.code ? e : listenError(ERR.NET, e?.message)
    }
    try {
      return await s.ctx.decodeAudioData(data)
    } catch (e) {
      throw listenError(ERR.DECODE, e?.message)
    }
  }

  async function fetchItem(take_id) {
    let r
    try {
      r = await env.fetch(url(`/api/v1/published/${encodeURIComponent(take_id)}`))
    } catch (e) {
      throw listenError(ERR.NET, e?.message)
    }
    const body = await r.json().catch(() => null)
    if (!r.ok) throw listenError(typeof body?.detail === 'string' && body.detail ? body.detail : `http_${r.status}`, `published/${take_id}`)
    if (!body || typeof body.audio !== 'string') throw listenError(ERR.NET, `published/${take_id}: no audio`)
    return body
  }

  function minusFor(item) {
    if (s.buffer && s.ref?.id === item.song_id) return Promise.resolve(s.buffer)
    if (typeof item.minus !== 'string' || !item.minus) return Promise.resolve(null)
    return fetchBuffer(item.minus).catch(() => null)
  }

  const audioReady = () => !!s.ctx && s.ctx.state === 'running' && s.state !== 'playing' && !s.calibrating

  async function listen(id) {
    const take_id = takeIdOf(id)
    stopListen('stopped')
    stopReview()
    const refused = !audioReady() ? ERR.LOCKED : take_id ? null : 'not_published'
    if (refused) {
      bus.emit('on_listen_end', { take_id, reason: 'error', code: refused })
      return false
    }
    const p = { take_id, seq: ++s.listenSeq, nodes: [], state: 'loading', pos: 0, at: 0, vocal: null, minus: null, offset: 0, duration: 0 }
    s.listening = p
    const live = () => s.listening === p && p.seq === s.listenSeq && audioReady()
    const bail = () => (s.ctx.state === 'running' ? endListen(p, 'stopped') : endListen(p, 'error', ERR.LOCKED))
    let item
    let vocal
    let minus
    try {
      item = await fetchItem(take_id)
      if (!live()) return bail()
      ;[vocal, minus] = await Promise.all([fetchBuffer(item.audio), minusFor(item)])
      if (!live()) return bail()
    } catch (e) {
      return live() ? endListen(p, 'error', e?.code || ERR.NET) : bail()
    }
    p.vocal = vocal
    p.minus = minus
    p.offset = Number.isFinite(item.offset_s) ? item.offset_s : 0
    p.duration = Math.max(0, p.offset + vocal.duration)
    playFrom(p, 0, onListenEnded)
    bus.emit('on_listen', { take_id, duration: round(p.duration, 3) })
    return true
  }

  function listen_pause() {
    return pauseTransport(s.listening)
  }

  function listen_resume() {
    const p = s.listening
    if (!p || p.state !== 'paused' || !audioReady()) return false
    playFrom(p, p.pos, onListenEnded)
    return true
  }

  function listen_seek(t) {
    const p = s.listening
    return p?.vocal ? seekTransport(p, t, onListenEnded) : false
  }

  function listen_state() {
    const p = s.listening
    if (!p) return JSON.stringify({ take_id: null, state: 'idle', t: 0, duration: 0 })
    return JSON.stringify({ take_id: p.take_id, state: p.state, t: round(transportPos(p), 3), duration: round(p.duration, 3) })
  }

  // --- Прослушивание своего последнего дубля (s.take) на экране результата ---
  // Дубль живёт только в памяти страницы. Буферы декодируются один раз и переживают паузу и конец.

  function reviewInfo() {
    const take = s.take
    if (!take?.wav || !take.samples || !take.wav_sr) return null
    const applied = Number.isFinite(s.lastApplied) ? s.lastApplied : Number(take.lag_ms) || 0
    const offset = (Number(take.wav_t0) || 0) - applied / 1000
    return { take, offset, duration: Math.max(0, offset + take.samples / take.wav_sr) }
  }

  function stopReview() {
    const p = s.reviewing
    if (!p) return
    haltNodes(p)
    if (p.state !== 'ended') p.state = 'paused'
  }

  const onReviewEnded = p => {
    if (s.reviewing !== p) return
    haltNodes(p)
    p.state = 'ended'
    p.pos = p.duration
  }

  function ensureReview() {
    const info = reviewInfo()
    if (!info || !s.ctx) return null
    if (s.reviewing?.take === info.take) return s.reviewing
    if (s.reviewing) haltNodes(s.reviewing)
    const minus = s.buffer && s.ref?.id === info.take.song_id ? s.buffer : null
    const p = { take: info.take, nodes: [], state: 'paused', pos: 0, at: 0, vocal: null, minus, offset: info.offset, duration: info.duration }
    s.reviewing = p
    s.ctx.decodeAudioData(info.take.wav.slice(0)).then(
      vocal => {
        if (s.reviewing !== p) return
        p.vocal = vocal
        if (p.state === 'playing' && audioReady()) playFrom(p, p.pos, onReviewEnded)
        else if (p.state === 'playing') p.state = 'paused'
      },
      () => {
        if (s.reviewing === p) s.reviewing = null
      }
    )
    return p
  }

  function review_play(from = -1) {
    if (!audioReady()) return false
    const p = ensureReview()
    if (!p) return false
    stopListen('stopped')
    const f = Number(from)
    let pos = Number.isFinite(f) && f >= 0 ? f : transportPos(p)
    if (pos >= p.duration - 0.05) pos = 0
    if (p.vocal) playFrom(p, pos, onReviewEnded)
    else {
      p.pos = clamp(pos, 0, p.duration)
      p.state = 'playing'
    }
    return true
  }

  function review_pause() {
    const p = s.reviewing
    if (!p) return false
    if (!p.vocal && p.state === 'playing') {
      p.state = 'paused'
      return true
    }
    return pauseTransport(p)
  }

  function review_seek(t) {
    const p = ensureReview()
    return p ? seekTransport(p, t, onReviewEnded) : false
  }

  function review_stop() {
    const p = s.reviewing
    if (!p) return false
    haltNodes(p)
    p.state = 'paused'
    p.pos = 0
    return true
  }

  function review_state() {
    const info = reviewInfo()
    if (!info || !s.ctx) return JSON.stringify({ available: false, state: 'idle', t: 0, duration: 0, song_id: null, take_id: null })
    const p = s.reviewing?.take === info.take ? s.reviewing : null
    const take_id = s.lastPub?.take_id ?? null
    return JSON.stringify({
      available: true,
      state: p ? p.state : 'paused',
      t: p ? round(transportPos(p), 3) : 0,
      duration: round(info.duration, 3),
      song_id: info.take.song_id ?? null,
      take_id
    })
  }

  function poll() {
    return JSON.stringify({ t_now: s.state === 'idle' ? 0 : round(songNow(), 3), state: s.state, level: round(s.level, 4), frames: queue.drain() })
  }

  return {
    _mode: 'real',
    subscribe: cb => bus.subscribe(cb),
    unlock,
    configure,
    load_song,
    start,
    stop,
    poll,
    submit,
    calibrate,
    client_id() {
      return clientId(env)
    },
    publish: id => setPublished(id, true),
    unpublish: id => setPublished(id, false),
    listen,
    listen_stop: () => stopListen('stopped'),
    listen_pause,
    listen_resume,
    listen_seek,
    listen_state,
    review_play,
    review_pause,
    review_seek,
    review_stop,
    review_state,
    _take() {
      const take = s.take
      return take ? { wav: take.wav, meta: metaFor(take, 'dev', null), resampler: take.resampler } : null
    },
    _state() {
      return { sr: s.sr, floor: s.floor, gate: s.gate, lag_ms: s.lag, lag_source: s.lagSource, est_lag_ms: s.estLag, output_latency: s.ctx?.outputLatency ?? null, base_latency: s.ctx?.baseLatency ?? null, ctx_state: s.ctx?.state ?? null, session: s.tokenState }
    }
  }
}

export function installVoice(win) {
  const cfg = win.VOICE_CONFIG || {}
  const mode = new URLSearchParams(win.location?.search || '').get('mock')
  if (mode !== null) {
    win.voice = createMockVoice(mode, cfg, win)
    attachPlanB(win.voice, win)
  } else {
    win.voice = createVoice(cfg, win)
  }
  if (isDebug(win.location?.search) && win.document) {
    attachDebug(win, win.voice, { apiUrl: `${cfg.api || ''}/api/v1/version`, versionUrl: new URL('./version.json', import.meta.url).href })
  }
  return win.voice
}

if (typeof window !== 'undefined' && !window.voice) installVoice(window)
