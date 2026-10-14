import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const read = p => readFileSync(new URL(p, import.meta.url), 'utf8')

function loadConfig() {
  const sandbox = { window: {} }
  vm.runInNewContext(read('../config.js'), sandbox)
  return JSON.parse(JSON.stringify(sandbox.window.VOICE_CONFIG))
}

test('config.js defines VOICE_CONFIG as a classic script', () => {
  const cfg = loadConfig()
  assert.equal(typeof cfg, 'object')
  assert.ok(cfg.difficulty in cfg.tol_cents)
  assert.equal(cfg.clarity_min, 0.85)
  assert.ok(cfg.lag_ms === null || (cfg.lag_ms >= -100 && cfg.lag_ms <= 500))
})

test('tolerances mirror contracts/scoring.json', () => {
  const scoring = JSON.parse(read('../../contracts/scoring.json'))
  assert.deepEqual(loadConfig().tol_cents, scoring.tol_cents)
})
