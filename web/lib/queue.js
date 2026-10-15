export class FrameQueue {
  constructor(cap = 2000) {
    this.cap = cap
    this.items = []
  }

  push(...frames) {
    for (const f of frames) this.items.push(f)
    if (this.items.length > this.cap) this.items.splice(0, this.items.length - this.cap)
  }

  drain() {
    const out = this.items
    this.items = []
    return out
  }

  get size() {
    return this.items.length
  }
}
