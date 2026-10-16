import { test } from 'node:test'
import assert from 'node:assert/strict'
import { getJson } from '../lib/http.js'

test('getJson returns the body of an ok response and passes init through', async () => {
  const seen = []
  const env = { fetch: async (url, init) => (seen.push([url, init]), { ok: true, json: async () => ({ a: 1 }) }) }
  assert.deepEqual(await getJson(env, '/x', { cache: 'no-store' }), { a: 1 })
  assert.deepEqual(seen, [['/x', { cache: 'no-store' }]])
})

test('getJson returns null for a failed status', async () => {
  assert.equal(await getJson({ fetch: async () => ({ ok: false, status: 404, json: async () => ({}) }) }, '/x'), null)
})

test('getJson returns null when fetch or json throws', async () => {
  assert.equal(await getJson({ fetch: async () => { throw new TypeError('offline') } }, '/x'), null)
  assert.equal(await getJson({ fetch: async () => ({ ok: true, json: async () => { throw new SyntaxError('bad') } }) }, '/x'), null)
})
