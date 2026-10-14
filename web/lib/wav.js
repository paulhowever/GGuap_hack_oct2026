function writeAscii(view, offset, s) {
  for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i))
}

export function encodeWav(samples, sampleRate) {
  const n = samples.length
  const buf = new ArrayBuffer(44 + n * 2)
  const v = new DataView(buf)
  writeAscii(v, 0, 'RIFF')
  v.setUint32(4, 36 + n * 2, true)
  writeAscii(v, 8, 'WAVE')
  writeAscii(v, 12, 'fmt ')
  v.setUint32(16, 16, true)
  v.setUint16(20, 1, true)
  v.setUint16(22, 1, true)
  v.setUint32(24, sampleRate, true)
  v.setUint32(28, sampleRate * 2, true)
  v.setUint16(32, 2, true)
  v.setUint16(34, 16, true)
  writeAscii(v, 36, 'data')
  v.setUint32(40, n * 2, true)
  for (let i = 0; i < n; i++) {
    const s = Math.max(-1, Math.min(1, samples[i] || 0))
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true)
  }
  return buf
}

export function parseWavHeader(buf) {
  const v = new DataView(buf)
  const tag = o => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3))
  if (buf.byteLength < 44 || tag(0) !== 'RIFF' || tag(8) !== 'WAVE') return null
  const sampleRate = v.getUint32(24, true)
  const channels = v.getUint16(22, true)
  const bits = v.getUint16(34, true)
  const dataBytes = v.getUint32(40, true)
  const frames = dataBytes / (channels * bits / 8)
  return { sampleRate, channels, bits, frames, duration: frames / sampleRate }
}
