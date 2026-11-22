import assert from 'node:assert/strict'
import { test } from 'node:test'
import { moduleUrl } from './load-module.mjs'

const api = await moduleUrl('lib/api.ts')
const { api: send } = await import(api)
const { deleteSource, updateKnowledge, updateSource } = await import(await moduleUrl('lib/library.ts', { './api': api }))
const { exportBackup, importBackup, getPreferences, patchPreferences } = await import(await moduleUrl('lib/backup.ts', { './api': api }))

test('sends explicit PATCH methods for all editable records and accepts source deletion without a body', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({ url, method: init.method, body: init.body && JSON.parse(init.body) })
    return init.method === 'DELETE' ? new Response(null, { status: 204 }) : Response.json({ id: 7 })
  })
  assert.deepEqual(await updateKnowledge('word', 7, { status: 'ignored', hsk_level: null }), { id: 7 })
  await updateKnowledge('pattern', 8, { title_vi: 'Câu hỏi' })
  await updateKnowledge('sentence', 9, { meaning_vi: 'Tôi đã học rồi.' })
  await updateSource(10, { title: 'Bài mới', summary_note: '' })
  assert.equal(await deleteSource(10), undefined)
  assert.deepEqual(calls, [
    { url: '/api/words/7', method: 'PATCH', body: { status: 'ignored', hsk_level: null } },
    { url: '/api/patterns/8', method: 'PATCH', body: { title_vi: 'Câu hỏi' } },
    { url: '/api/sentences/9', method: 'PATCH', body: { meaning_vi: 'Tôi đã học rồi.' } },
    { url: '/api/sources/10', method: 'PATCH', body: { title: 'Bài mới', summary_note: '' } },
    { url: '/api/sources/10', method: 'DELETE', body: undefined },
  ])
})

test('downloads the snapshot, uploads the file unchanged, and syncs preference patches', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    calls.push({ url, ...init })
    if (url.endsWith('/export')) return new Response('{"schema_version":1}', {
      headers: { 'Content-Disposition': 'attachment; filename="chinese-study-backup-20261122-123456.json"' },
    })
    if (url.endsWith('/import')) return Response.json({ preferences: { theme: 'dark', pinyin: true }, cards_created: 2 })
    return Response.json(init.method === 'GET' ? null : { theme: 'dark', pinyin: false })
  })
  const exported = await exportBackup()
  assert.match(exported.headers.get('Content-Disposition'), /chinese-study-backup-20261122/)
  assert.deepEqual(await exported.json(), { schema_version: 1 })
  const restored = await importBackup(new File(['{"schema_version":1}'], 'backup.json', { type: 'application/json' }))
  assert.deepEqual(restored.preferences, { theme: 'dark', pinyin: true })
  assert.equal(await getPreferences(), null)
  assert.deepEqual(await patchPreferences({ theme: 'dark' }), { theme: 'dark', pinyin: false })
  assert.deepEqual(calls.map(({ url, method }) => [url, method]), [
    ['/api/backup/export', 'GET'],
    ['/api/backup/import', 'POST'],
    ['/api/backup/preferences', 'GET'],
    ['/api/backup/preferences', 'PATCH'],
  ])
  assert.equal(calls[1].headers, undefined)
  assert.equal(calls[1].body.get('file').name, 'backup.json')
  assert.equal(await calls[1].body.get('file').text(), '{"schema_version":1}')
  assert.deepEqual(JSON.parse(calls[3].body), { theme: 'dark' })
})

test('shows degraded health details while keeping ordinary HTTP 503 responses as errors', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json({
    status: 'degraded',
    database: 'unavailable',
    hsk_word_count: null,
    tts_cache_count: 4,
  }, { status: 503 }))
  const health = await send('/health', { acceptStatus: 503 })
  assert.equal(health.database, 'unavailable')
  assert.equal(health.tts_cache_count, 4)
  await assert.rejects(() => send('/backup/export'), { status: 503 })
})
