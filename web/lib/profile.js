export const CLIENT_KEY = 'voice.client_id'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const resolved = new WeakMap()

function isObject(v) {
  return v !== null && (typeof v === 'object' || typeof v === 'function')
}

export function clientId(env = globalThis) {
  try {
    const saved = env.localStorage?.getItem(CLIENT_KEY)
    if (saved && UUID.test(saved)) return saved
  } catch {}
  if (isObject(env) && resolved.has(env)) return resolved.get(env)
  const id = typeof env.crypto?.randomUUID === 'function' ? env.crypto.randomUUID() : null
  if (!id) return null
  if (isObject(env)) resolved.set(env, id)
  try {
    env.localStorage?.setItem(CLIENT_KEY, id)
  } catch {}
  return id
}
