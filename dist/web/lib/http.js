export async function getJson(env, url, init) {
  try {
    const r = await env.fetch(url, init)
    return r.ok ? await r.json() : null
  } catch {
    return null
  }
}
