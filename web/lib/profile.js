export const CLIENT_KEY = 'voice.client_id'
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

export function clientId(env = globalThis) {
  try {
    const saved = env.localStorage?.getItem(CLIENT_KEY)
    if (saved && UUID.test(saved)) return saved
  } catch {}
  const id = typeof env.crypto?.randomUUID === 'function' ? env.crypto.randomUUID() : null
  if (!id) return null
  try {
    env.localStorage?.setItem(CLIENT_KEY, id)
  } catch {}
  return id
}
