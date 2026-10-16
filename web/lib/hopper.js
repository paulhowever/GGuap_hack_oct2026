import { HOP, WIN } from './timing.js'

export class PitchHopper {
  constructor({ win = WIN, hop = HOP, detect, minRms = 1e-4 }) {
    this.W = win
    this.H = hop
    this.detect = detect
    this.minRms = minRms
    this.ring = new Float32Array(win)
    this.win = new Float32Array(win)
    this.pos = 0
    this.cnt = 0
  }

  push(block, frame, sr, out = []) {
    for (let k = 0; k < block.length; k++) {
      this.ring[this.pos] = block[k]
      this.pos = (this.pos + 1) % this.W
      if (++this.cnt === this.H) {
        this.cnt = 0
        out.push(this.analyze(frame + k + 1, sr))
      }
    }
    return out
  }

  analyze(E, sr) {
    let s = 0
    for (let j = 0; j < this.W; j++) {
      const v = this.ring[(this.pos + j) % this.W]
      this.win[j] = v
      s += v * v
    }
    const rms = Math.sqrt(s / this.W)
    if (rms < this.minRms) return { E, hz: 0, clarity: 0, rms }
    const [hz, clarity] = this.detect(this.win, sr)
    return { E, hz, clarity, rms }
  }
}
