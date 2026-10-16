import { hzToMidi } from './pitch.js'

export const DEBUG_PERIOD_MS = 250
const DASH = '—'

export function isDebug(search) {
  return new URLSearchParams(search || '').get('debug') === '1'
}

export function shortSha(sha) {
  if (typeof sha !== 'string' || !sha) return DASH
  const m = sha.match(/^([0-9a-f]{7,40})(-dirty)?$/i)
  return m ? m[1].slice(0, 7) + (m[2] || '') : sha.slice(0, 12)
}

const isNum = v => typeof v === 'number' && Number.isFinite(v)
const fixed = (v, digits) => (isNum(v) ? v.toFixed(digits) : DASH)
const ms = v => (isNum(v) ? `${Math.round(v)} ms` : DASH)
const secondsAsMs = v => (isNum(v) ? `${(v * 1000).toFixed(1)} ms` : DASH)

function apiLine(api) {
  if (!api) return `api ${DASH}`
  return [`api ${api.app ?? DASH} ${shortSha(api.git_sha)}`, api.scoring, api.f0_engine].filter(Boolean).join(' · ')
}

function webLine(web) {
  return web ? `web ${shortSha(web.git_sha)} ${web.built_at ?? ''}`.trim() : `web ${DASH}`
}

function pitchLine(f) {
  if (!f) return `pitch ${DASH}`
  const voiced = isNum(f.hz) && f.hz > 0
  return `pitch ${voiced ? `${f.hz.toFixed(1)} Hz` : DASH} · midi ${voiced ? hzToMidi(f.hz).toFixed(2) : DASH} · conf ${fixed(f.conf, 2)}`
}

function noteLine(v) {
  if (!v) return `note ${DASH}`
  const cents = isNum(v.cents) ? `${v.cents > 0 ? '+' : ''}${v.cents}c` : DASH
  return `note #${v.i} hit ${fixed(v.hit, 2)} · ${cents} · onset ${ms(v.onset_ms)}`
}

function integrityLine(x, ratio, takeId) {
  if (!x?.status && !takeId) return `integrity ${DASH}`
  const flags = Array.isArray(x?.flags) && x.flags.length ? `: ${x.flags.join(', ')}` : ''
  const share = isNum(ratio) ? `${Math.round(ratio * 100)}%` : DASH
  return `integrity ${x?.status || DASH}${flags} · ${share} · ${takeId || DASH}`
}

export function debugText({ mode, api = null, web = null, state = {}, frame = null, fps = 0, clientId = null, verdict = null, integrity = null, ratio = null, takeId = null } = {}) {
  return [
    apiLine(api),
    webLine(web),
    `mode ${mode === 'real' ? 'real' : `mock:${mode}`} · sr ${state.sr || DASH} · ctx ${state.ctx_state ?? DASH}`,
    `lag ${ms(state.lag_ms)} · est ${ms(state.est_lag_ms)} · out ${secondsAsMs(state.output_latency)}`,
    pitchLine(frame),
    `fps ${Math.round(fps)}`,
    `client ${clientId || DASH}`,
    `session ${state.session ?? DASH}`,
    noteLine(verdict),
    integrityLine(integrity, ratio, takeId)
  ].join('\n')
}

function parse(json) {
  try {
    return JSON.parse(json)
  } catch {
    return null
  }
}

export function createDebugTracker(now, windowMs = 1000) {
  const t = { frame: null, verdict: null, integrity: null, takeId: null, ratio: null, state: null, polls: [] }
  const clearTake = () => {
    t.verdict = null
    t.integrity = null
    t.takeId = null
    t.ratio = null
  }
  const fps = () => {
    const at = now()
    while (t.polls.length && at - t.polls[0].at > windowMs) t.polls.shift()
    return (t.polls.reduce((n, p) => n + p.n, 0) * 1000) / windowMs
  }
  return {
    onPoll(json) {
      const p = parse(json)
      if (p?.state === 'playing' && t.state !== 'playing') clearTake()
      if (typeof p?.state === 'string') t.state = p.state
      const frames = Array.isArray(p?.frames) ? p.frames : null
      if (!frames) return
      if (frames.length) t.frame = frames.at(-1)
      t.polls.push({ at: now(), n: frames.length })
      fps()
    },
    onEvent(name, json) {
      const p = parse(json)
      if (name === 'on_note_judged') t.verdict = p
      if (name === 'on_result') {
        t.integrity = p?.integrity ?? null
        t.takeId = typeof p?.take_id === 'string' && p.take_id ? p.take_id : null
        t.ratio = p?.completion?.ratio ?? null
      }
      if (name === 'on_ready') clearTake()
    },
    snapshot() {
      return { frame: t.frame, fps: fps(), verdict: t.verdict, integrity: t.integrity, takeId: t.takeId, ratio: t.ratio }
    }
  }
}

async function fetchJson(win, url) {
  try {
    const r = await win.fetch(url, { cache: 'no-store' })
    return r.ok ? await r.json() : null
  } catch {
    return null
  }
}

const STYLE = {
  position: 'fixed',
  right: '8px',
  bottom: '8px',
  zIndex: '2147483647',
  margin: '0',
  padding: '6px 8px',
  maxWidth: 'calc(100vw - 16px)',
  font: '11px/1.35 ui-monospace, Menlo, Consolas, monospace',
  color: '#d8ffd8',
  background: 'rgba(0, 0, 0, 0.72)',
  borderRadius: '6px',
  whiteSpace: 'pre-wrap',
  pointerEvents: 'none',
  userSelect: 'none'
}

export function attachDebug(win, voice, { apiUrl, versionUrl, periodMs = DEBUG_PERIOD_MS } = {}) {
  const doc = win.document
  const el = doc.createElement('pre')
  el.id = 'voice-debug'
  Object.assign(el.style, STYLE)
  const tracker = createDebugTracker(() => win.performance.now())
  let live = true
  const poll = voice.poll
  const wrapped = (...args) => {
    const out = poll.apply(voice, args)
    if (live) tracker.onPoll(out)
    return out
  }
  voice.poll = wrapped
  const unsubscribe = voice.subscribe((name, json) => {
    if (live) tracker.onEvent(name, json)
  })
  const clientId = voice.client_id?.() ?? null
  const info = { api: null, web: null }
  const render = () => {
    el.textContent = debugText({ mode: voice._mode, api: info.api, web: info.web, state: voice._state?.() ?? {}, clientId, ...tracker.snapshot() })
    return el.textContent
  }
  fetchJson(win, apiUrl).then(v => (info.api = v))
  fetchJson(win, versionUrl).then(v => (info.web = v))
  const mount = () => doc.body.appendChild(el)
  if (doc.body) mount()
  else doc.addEventListener('DOMContentLoaded', mount)
  render()
  const timer = win.setInterval(render, periodMs)
  const onKey = e => {
    if (e.code === 'KeyD' && e.altKey && e.shiftKey && !e.repeat) win.navigator?.clipboard?.writeText(render()).catch(() => {})
  }
  win.addEventListener?.('keydown', onKey, true)
  const stop = () => {
    if (!live) return
    live = false
    win.clearInterval(timer)
    win.removeEventListener?.('keydown', onKey, true)
    doc.removeEventListener('DOMContentLoaded', mount)
    el.remove()
    if (voice.poll === wrapped) voice.poll = poll
    if (typeof unsubscribe === 'function') unsubscribe()
  }
  return { el, render, stop }
}
