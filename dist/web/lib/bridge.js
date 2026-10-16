export function createBus({ sticky = [], onError = () => {} } = {}) {
  const subs = []
  const last = new Map()
  const deliver = (cb, name, json) => {
    try {
      cb(name, json)
    } catch (e) {
      onError(e)
    }
  }
  return {
    subscribe(cb) {
      if (typeof cb !== 'function') return
      subs.push(cb)
      for (const [name, json] of last) deliver(cb, name, json)
    },
    emit(name, payload) {
      const json = JSON.stringify(payload ?? {})
      if (sticky.includes(name)) last.set(name, json)
      for (const cb of subs) deliver(cb, name, json)
    }
  }
}

export function parseOptions(json) {
  if (json && typeof json === 'object') return json
  try {
    const o = JSON.parse(json)
    return o && typeof o === 'object' ? o : {}
  } catch {
    return {}
  }
}
