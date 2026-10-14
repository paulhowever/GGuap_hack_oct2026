export class PcmRecorder {
  constructor(sr, maxSeconds = 60) {
    this.sr = sr
    this.max = Math.floor(sr * maxSeconds)
    this.chunks = []
    this.n = 0
    this.firstFrame = null
  }

  push(block, frame) {
    if (this.firstFrame === null) this.firstFrame = frame
    const gap = frame - (this.firstFrame + this.n)
    if (gap > 0) this.append(new Float32Array(gap))
    this.append(gap < 0 ? block.subarray(Math.min(block.length, -gap)) : block)
  }

  append(block) {
    const take = Math.min(block.length, this.max - this.n)
    if (take <= 0) return
    this.chunks.push(take === block.length ? block : block.subarray(0, take))
    this.n += take
  }

  get duration() {
    return this.n / this.sr
  }

  samples() {
    const out = new Float32Array(this.n)
    let o = 0
    for (const c of this.chunks) {
      out.set(c, o)
      o += c.length
    }
    return out
  }
}
