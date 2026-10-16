export const ERR = Object.freeze({
  INSECURE: 'insecure_context',
  DENIED: 'mic_denied',
  NOT_FOUND: 'mic_not_found',
  LOCKED: 'audio_locked',
  WORKLET: 'worklet_failed',
  DECODE: 'decode_failed',
  NET: 'net',
  UPLOAD: 'upload_failed'
})

const DENIED_NAMES = new Set(['NotAllowedError', 'SecurityError', 'PermissionDeniedError'])

export function micErrorCode(err) {
  return DENIED_NAMES.has(err && err.name) ? ERR.DENIED : ERR.NOT_FOUND
}

export function errorPayload(code, err) {
  const msg = err && err.message ? err.message : String(err ?? code)
  return { code, msg }
}
