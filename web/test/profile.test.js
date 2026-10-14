import { test } from 'node:test'
import assert from 'node:assert/strict'
import { CLIENT_KEY, clientId } from '../lib/profile.js'

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

function storage(init = {}) {
  const store = { ...init }
  return { store, getItem: k => store[k] ?? null, setItem: (k, v) => { store[k] = v } }
}

test('reuses a saved id', () => {
  const localStorage = storage({ [CLIENT_KEY]: '7b1e2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d' })
  assert.equal(clientId({ localStorage, crypto }), '7b1e2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d')
})

test('generates and saves a new uuid', () => {
  const localStorage = storage()
  const id = clientId({ localStorage, crypto })
  assert.match(id, UUID)
  assert.equal(localStorage.store[CLIENT_KEY], id)
})

test('replaces a corrupted saved id', () => {
  const localStorage = storage({ [CLIENT_KEY]: 'garbage' })
  const id = clientId({ localStorage, crypto })
  assert.match(id, UUID)
  assert.equal(localStorage.store[CLIENT_KEY], id)
})

test('broken storage still yields an id, no crypto yields null', () => {
  const broken = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } }
  assert.match(clientId({ localStorage: broken, crypto }), UUID)
  assert.equal(clientId({ localStorage: storage() }), null)
})

test('unusable storage keeps one id per env, a fresh env gets its own', () => {
  const broken = { getItem() { throw new Error('denied') }, setItem() { throw new Error('denied') } }
  const env = { localStorage: broken, crypto }
  const first = clientId(env)
  assert.match(first, UUID)
  assert.equal(clientId(env), first)
  assert.equal(clientId(env), first)
  assert.notEqual(clientId({ localStorage: broken, crypto }), first)

  const blocked = { crypto }
  Object.defineProperty(blocked, 'localStorage', { get() { throw new Error('blocked') } })
  const second = clientId(blocked)
  assert.match(second, UUID)
  assert.equal(clientId(blocked), second)
})

test('a missing id is not cached so a later call can retry', () => {
  const env = { localStorage: storage() }
  assert.equal(clientId(env), null)
  env.crypto = crypto
  assert.match(clientId(env), UUID)
})
