import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { transformWithOxc } from 'vite'

const source = await readFile(new URL('../src/answer-feedback.tsx', import.meta.url), 'utf8')
const { code } = await transformWithOxc(source.split('export function AnswerFeedback')[0], 'feedback.ts')
const { submitFeedback } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`)
const originalFetch = globalThis.fetch
try {
  let sent
  globalThis.fetch = async (path, options) => {
    sent = { path, options }
    return new Response(null, { status: 204 })
  }
  await submitFeedback('kb/a', 'ans?b', 'unhelpful')
  assert.equal(sent.path, '/api/knowledge-bases/kb%2Fa/answers/ans%3Fb/feedback')
  assert.equal(sent.options.method, 'PUT')
  assert.deepEqual(JSON.parse(sent.options.body), { rating: 'unhelpful' })
  assert.ok(sent.options.signal instanceof AbortSignal)

  for (const [status, message] of [[404, /找不到这条回答/], [200, /提交失败/], [500, /提交失败/]]) {
    globalThis.fetch = async () => new Response('{}', { status })
    await assert.rejects(submitFeedback('kb', 'ans', 'helpful'), message)
  }
  globalThis.fetch = async () => { throw new TypeError('offline') }
  await assert.rejects(submitFeedback('kb', 'ans', 'helpful'), TypeError)
} finally {
  globalThis.fetch = originalFetch
}
console.log('回答反馈检查通过：请求编码、204 空响应、错误状态和断网失败')
