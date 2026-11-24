export type FeedbackRating = 'helpful' | 'unhelpful'

export async function submitFeedback(kbId: string, answerId: string, rating: FeedbackRating): Promise<void> {
  const response = await fetch(
    `/api/knowledge-bases/${encodeURIComponent(kbId)}/answers/${encodeURIComponent(answerId)}/feedback`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
      signal: AbortSignal.timeout(15000),
    },
  )
  if (response.status === 204) return
  if (response.status === 404) throw new Error('找不到这条回答，请刷新页面后重新提问。')
  throw new Error('反馈提交失败，请稍后重试。')
}

export function AnswerFeedback({ rating, busy, error, onRate }: {
  rating?: FeedbackRating
  busy: boolean
  error?: string
  onRate: (rating: FeedbackRating) => void
}) {
  return <div className="answer-feedback">
    <div className="feedback-actions" role="group" aria-label="评价这条回答" aria-busy={busy}>
      <button type="button" aria-pressed={rating === 'helpful'} disabled={busy} onClick={() => onRate('helpful')}>有帮助</button>
      <button type="button" aria-pressed={rating === 'unhelpful'} disabled={busy} onClick={() => onRate('unhelpful')}>没帮助</button>
    </div>
    {busy && <p className="feedback-status" role="status">正在提交反馈…</p>}
    {!busy && !error && rating && <p className="feedback-status" role="status">反馈已保存</p>}
    {error && <p className="response-error" role="alert">{error}</p>}
  </div>
}
