import { PitchDetector } from './vendor/pitchy.bundle.js'
import { PitchHopper } from './lib/hopper.js'

const CHUNK = 4096

class Tap extends AudioWorkletProcessor {
  constructor() {
    super()
    const det = PitchDetector.forFloat32Array(2048)
    this.hopper = new PitchHopper({ win: 2048, hop: 512, detect: (w, sr) => det.findPitch(w, sr) })
    this.out = []
    this.rec = false
    this.buf = new Float32Array(CHUNK)
    this.n = 0
    this.F = 0
    this.port.onmessage = e => {
      if (e.data.rec === true) {
        this.rec = true
        this.n = 0
      } else if (e.data.rec === false) {
        this.flush()
        this.rec = false
        this.port.postMessage({ recDone: true })
      }
    }
  }

  flush() {
    if (this.n === 0) return
    const pcm = this.buf.slice(0, this.n)
    this.port.postMessage({ pcm, F: this.F }, [pcm.buffer])
    this.n = 0
  }

  process(inputs) {
    const x = inputs[0] && inputs[0][0]
    if (!x) return true
    if (this.rec) {
      for (let k = 0; k < x.length; k++) {
        if (this.n === 0) this.F = currentFrame + k
        this.buf[this.n++] = x[k]
        if (this.n === CHUNK) this.flush()
      }
    }
    this.hopper.push(x, currentFrame, sampleRate, this.out)
    if (this.out.length >= 3) {
      this.port.postMessage({ frames: this.out })
      this.out = []
    }
    return true
  }
}

registerProcessor('tap', Tap)
