// Exercise the real view model and request helpers without adding a test framework.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { transformWithOxc } from 'vite'

async function moduleUrl(source) {
  const { code } = await transformWithOxc(source, 'check.ts')
  return `data:text/javascript;base64,${Buffer.from(code).toString('base64')}`
}

const root = new URL('../src/features/file-management/', import.meta.url)
const modelUrl = await moduleUrl(await readFile(new URL('model.ts', root), 'utf8'))
const model = await import(modelUrl)
const api = await import(
  await moduleUrl(
    (await readFile(new URL('api.ts', root), 'utf8')).replace("from './model'", `from '${modelUrl}'`),
  )
)
const candidate = (path, size = 10) => ({
  id: path,
  path,
  size,
  selected: true,
  file: new File(['test'], path.split('/').pop()),
})

assert.equal(model.FILE_ACCEPT, '.md,.txt,.docx,.pdf,.xlsx')
for (const path of ['guide.MD', 'notes.txt', 'nested/manual.DOCX', 'table.XLSX', 'text.PDF']) {
  const file = candidate(path, model.MAX_BYTES)
  assert.equal(model.candidateError(file, [file]), null, path)
}
for (const path of ['old.xls', 'old.doc', 'image.png', '../unsafe.md', 'a\\b.txt', 'a//b.pdf']) {
  const file = candidate(path)
  assert.ok(model.candidateError(file, [file]), path)
}
const oversized = candidate('large.docx', model.MAX_BYTES + 1)
assert.ok(model.candidateError(oversized, [oversized]))
const repeated = [candidate('repeat.pdf'), { ...candidate('repeat.pdf'), id: 'second' }]
assert.ok(model.candidateError(repeated[0], repeated))

const originalFetch = globalThis.fetch
const originalWindow = globalThis.window
globalThis.window = globalThis
try {
  let sent
  globalThis.fetch = async (path, options) => {
    sent = { path, options }
    return new Response(null, { status: 204 })
  }
  await api.deleteDocument('kb/a', 'doc?b')
  assert.equal(sent.path, '/api/knowledge-bases/kb%2Fa/documents/doc%3Fb')
  assert.equal(sent.options.method, 'DELETE')
  assert.equal(sent.options.body, undefined)

  for (const [status, expected] of [
    [200, /数据格式异常/],
    [404, /文件或知识库不存在/],
    [500, /后端暂时不可用/],
  ]) {
    globalThis.fetch = async () => new Response('{}', { status })
    await assert.rejects(api.deleteDocument('kb', 'doc'), expected)
  }
  globalThis.fetch = async () => {
    throw new TypeError('offline')
  }
  await assert.rejects(api.deleteDocument('kb', 'doc'), /无法连接本地后端/)

  const upload = candidate('folder/nested/manual.docx')
  globalThis.fetch = async (path, options) => {
    sent = { path, options }
    return Response.json({
      files: [{ relative_path: upload.path, status: 'unchanged', version_no: 2, searchable: true }],
      failed: 0,
    })
  }
  const results = await api.uploadDocuments('kb', [upload])
  assert.equal(sent.options.body.get('files').name, 'manual.docx')
  assert.equal(await sent.options.body.get('files').text(), 'test')
  assert.equal(sent.options.body.get('relative_paths'), upload.path)
  assert.equal(results[0].status, 'unchanged')
  assert.equal(results[0].versionNo, 2)

  const broken = candidate('broken.docx')
  globalThis.fetch = async () => Response.json({
    files: [
      { relative_path: upload.path, status: 'created', version_no: 1, searchable: true },
      {
        relative_path: broken.path,
        status: 'failed',
        version_no: null,
        searchable: false,
        error: 'Cannot parse DOCX',
      },
    ],
    failed: 1,
  })
  const partial = await api.uploadDocuments('kb', [upload, broken])
  assert.deepEqual(partial.map((file) => file.status), ['created', 'failed'])
  assert.equal(partial[1].reason, 'Cannot parse DOCX')
  globalThis.fetch = async () => Response.json({ files: [], failed: 0 })
  await assert.rejects(api.uploadDocuments('kb', [upload]), /数据格式异常/)
} finally {
  globalThis.fetch = originalFetch
  if (originalWindow === undefined) delete globalThis.window
  else globalThis.window = originalWindow
}
console.log('文件管理回归检查通过：格式、大小、路径、204 删除、失败响应、目录文件名及逐文件结果')
