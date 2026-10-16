export function round(x, digits = 0) {
  const k = 10 ** digits
  return Math.round(x * k) / k
}

export function median(xs) {
  if (!xs.length) return 0
  const a = [...xs].sort((p, q) => p - q)
  const m = a.length >> 1
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2
}

export function clamp(x, lo, hi) {
  return Math.min(hi, Math.max(lo, x))
}
