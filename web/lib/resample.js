function lowpassKernel(ratio) {
  const half = Math.ceil(8 * ratio)
  const fc = 0.45 / ratio
  const k = new Float32Array(2 * half + 1)
  let sum = 0
  for (let i = -half; i <= half; i++) {
    const x = 2 * Math.PI * fc * i
    const sinc = i === 0 ? 1 : Math.sin(x) / x
    const w = 0.5 + 0.5 * Math.cos(Math.PI * i / (half + 1))
    k[i + half] = sinc * w
    sum += sinc * w
  }
  for (let i = 0; i < k.length; i++) k[i] /= sum
  return { k, half }
}

export function downsample(input, fromRate, toRate) {
  if (!(toRate < fromRate)) return Float32Array.from(input)
  const ratio = fromRate / toRate
  const { k, half } = lowpassKernel(ratio)
  const last = input.length - 1
  const filtered = i => {
    let acc = 0
    const lo = Math.max(0, i - half)
    const hi = Math.min(last, i + half)
    for (let m = lo; m <= hi; m++) acc += input[m] * k[m - i + half]
    return acc
  }
  const out = new Float32Array(Math.ceil(input.length / ratio))
  for (let j = 0; j < out.length; j++) {
    const c = j * ratio
    const i = Math.floor(c)
    const f = c - i
    out[j] = f < 1e-9 ? filtered(i) : filtered(i) * (1 - f) + filtered(Math.min(i + 1, last)) * f
  }
  return out
}
