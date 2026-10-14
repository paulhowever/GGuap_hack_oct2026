export async function postTake({ env, url, wav, meta, timeoutMs = 10000 }) {
  const fd = new env.FormData()
  fd.append('audio', new env.Blob([wav], { type: 'audio/wav' }), 'take.wav')
  fd.append('meta', JSON.stringify(meta))
  const ac = new env.AbortController()
  const timer = env.setTimeout(() => ac.abort(), timeoutMs)
  try {
    const r = await env.fetch(url, { method: 'POST', body: fd, signal: ac.signal })
    if (!r.ok) throw new Error(`HTTP ${r.status} ${(await r.text()).slice(0, 200)}`)
    return await r.json()
  } finally {
    env.clearTimeout(timer)
  }
}
