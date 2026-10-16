import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import { DEFAULT_TOL, RHO_MIN } from '../lib/scoring.js'

const read = p => readFileSync(new URL(p, import.meta.url), 'utf8')

function loadConfig() {
  const sandbox = { window: {} }
  vm.runInNewContext(read('../config.js'), sandbox)
  return JSON.parse(JSON.stringify(sandbox.window.VOICE_CONFIG))
}

const scoring = () => JSON.parse(read('../../contracts/scoring.json'))

test('config.js defines VOICE_CONFIG as a classic script', () => {
  const cfg = loadConfig()
  const [lo, hi] = scoring().lag_range_ms
  assert.equal(typeof cfg, 'object')
  assert.ok(cfg.difficulty in cfg.tol_cents)
  assert.equal(cfg.clarity_min, 0.85)
  assert.ok(cfg.lag_ms === null || (cfg.lag_ms >= lo && cfg.lag_ms <= hi))
})

test('tolerances mirror contracts/scoring.json', () => {
  assert.deepEqual(loadConfig().tol_cents, scoring().tol_cents)
})

test('engine scoring defaults mirror contracts/scoring.json', () => {
  assert.deepEqual(DEFAULT_TOL, scoring().tol_cents)
  assert.equal(RHO_MIN, scoring().rho_min)
})
