export async function requestSession({ env, url, songId, clientId, difficulty, timeoutMs = 5000 }) {
  let timer = null
  try {
    const ac = new env.AbortController()
    timer = env.setTimeout(() => ac.abort(), timeoutMs)
    const r = await env.fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ song_id: songId, client_id: clientId || null, difficulty }),
      signal: ac.signal
    })
    if (!r.ok) return null
    const body = await r.json()
    return typeof body?.token === 'string' && body.token ? body.token : null
  } catch {
    return null
  } finally {
    if (timer !== null) env.clearTimeout(timer)
  }
}
