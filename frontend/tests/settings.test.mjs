import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { stripTypeScriptTypes } from 'node:module'
import test from 'node:test'
import { CODEC_OPTIONS, CONTAINER_OPTIONS, SETTING_FIELDS, SPLIT_OPTIONS, settingsChanges, settingsEtag, settingsValues } from '../src/api/settings-values.ts'

const saved = {
  quality: 'best', codec: 'avc1', container: 'mp4', audio_codec: 'best',
  proxy_enabled: false, proxy_url: 'http://proxy.example:3128', keyboard: '2x3',
  subs_enabled: false, subs_auto: false, subs_always_ask: false, subs_lang: 'en',
  split_size: 2043000000, nsfw_blur: true, mediainfo: false, send_as_file: false,
  gallery_zip: false, use_pool_cookies: true, youtube_auth_mode: 'cookies',
}

test('GET projection excludes metadata and future response-only fields', () => {
  assert.deepEqual(settingsValues({ ...saved, user_id: 42, updated_at: 'now', has_pool_access: true, future: 'read-only' }), saved)
})

test('NSFW save sends only the changed boolean, not unrelated audio/proxy preferences', () => {
  assert.deepEqual(settingsChanges({ ...saved, nsfw_blur: false }, saved), { nsfw_blur: false })
  assert.deepEqual(settingsChanges(saved, saved), {})
  assert.deepEqual(settingsChanges({ ...saved, audio_codec: 'opus' }, saved), { audio_codec: 'opus' })
})

test('proxy clear is explicit null, omission preserves it and undo removes the patch', () => {
  assert.deepEqual(settingsChanges({ ...saved, proxy_url: null }, saved), { proxy_url: null })
  assert.deepEqual(settingsChanges({ ...saved, proxy_enabled: true }, saved), { proxy_enabled: true })
  assert.deepEqual(settingsChanges({ ...saved, proxy_url: saved.proxy_url }, saved), {})
})

test('settings requests require an exact server ETag without timestamp precision loss', () => {
  assert.equal(settingsEtag({ etag: '"9223372036854775806"' }), '"9223372036854775806"')
  for (const etag of [undefined, '', '123', 'W/"123"', '"-1"', 123]) {
    assert.throws(() => settingsEtag({ etag }))
  }
})

test('format controls use canonical supported values and byte-exact split presets', () => {
  assert.deepEqual(CODEC_OPTIONS.map(option => option.value), ['avc1', 'av01', 'vp09'])
  assert.deepEqual(CONTAINER_OPTIONS.map(option => option.value), ['mp4', 'mkv'])
  assert.deepEqual(SPLIT_OPTIONS.map(option => Number(option.value)), [524288000, 1073741824, 1610612736, 2043000000])
})

const calls = []
globalThis.__settingsTransport = {
  patch: (url, body, config) => {
    calls.push({ url, body, config })
    return Promise.resolve({ data: { ...saved, ...body }, headers: { etag: '"2"' } })
  },
}
const apiSource = readFileSync(new URL('../src/api/settings.ts', import.meta.url), 'utf8')
  .replace("import { apiClient } from '@core/lib/api-client'", 'const apiClient = globalThis.__settingsTransport')
const { dlSettingsApi } = await import(`data:text/javascript;base64,${Buffer.from(stripTypeScriptTypes(apiSource)).toString('base64')}`)

test('real typed API carries If-Match and successive saves use canonical response state', async () => {
  const first = await dlSettingsApi.patchMine(settingsChanges({ ...saved, nsfw_blur: false }, saved), '"1"')
  assert.deepEqual(calls.at(-1), { url: '/dl/settings', body: { nsfw_blur: false }, config: { headers: { 'If-Match': '"1"' } } })
  const baseline = settingsValues(first.data)
  await dlSettingsApi.patchMine(settingsChanges({ ...baseline, proxy_url: null }, baseline), settingsEtag(first.headers))
  assert.deepEqual(calls.at(-1), { url: '/dl/settings', body: { proxy_url: null }, config: { headers: { 'If-Match': '"2"' } } })
  assert.equal(SETTING_FIELDS.includes('audio_codec'), true)
})
