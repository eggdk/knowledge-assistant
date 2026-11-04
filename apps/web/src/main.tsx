import { useEffect, useRef, useState } from 'react'
import type { Ref } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type IconName = 'chat' | 'close' | 'spark' | 'send' | 'book'
type Source = { label?: string; relative_path: string; start_line: number; end_line: number; content: string }
type Reply = { question: string; answer: string; status: 'generated' | 'not_generated' | 'insufficient_evidence'; sources: Source[] }

async function postQuestion(path: string, question: string): Promise<Response> {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
}

async function readError(response: Response): Promise<string> {
  if (response.status === 404) return '知识库不存在。请检查网址中的 kbId。'
  if (response.status === 502) return '模型暂时无法回答，请稍后重试。'
  if (response.status === 422) return '问题格式不正确，请修改后重试。'
  return `请求失败（HTTP ${response.status}），请查看后端终端。`
}

async function ask(question: string): Promise<Reply> {
  const path = `/api/knowledge-bases/${encodeURIComponent(kbId!)}`
  const answerResponse = await postQuestion(`${path}/answers`, question)
  if (answerResponse.ok) {
    const data = await answerResponse.json() as { answer: string; answer_status: Reply['status']; citations: Source[] }
    return { question, answer: data.answer, status: data.answer_status, sources: data.citations }
  }
  if (answerResponse.status !== 503) throw new Error(await readError(answerResponse))

  // The model key may be absent during local development. Retrieval still works.
  const retrievalResponse = await postQuestion(`${path}/questions`, question)
  if (!retrievalResponse.ok) throw new Error(await readError(retrievalResponse))
  const data = await retrievalResponse.json() as { matches: Source[] }
  return {
    question,
    answer: data.matches.length ? '尚未生成答案。以下是知识库中检索到的相关原文：' : '尚未生成答案，也没有找到相关原文。',
    status: 'not_generated',
    sources: data.matches,
  }
}

function Icon({ name, size = 24 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, React.ReactNode> = {
    chat: <><path d="M20 11.4a7.6 7.6 0 0 1-7.8 7.4 8.7 8.7 0 0 1-3.1-.6L5 19.4l1.1-3.6a7.1 7.1 0 0 1-1.7-4.4A7.6 7.6 0 0 1 12.2 4 7.6 7.6 0 0 1 20 11.4Z"/><path d="M8.8 11.4h6.8M8.8 14.2h4.3"/></>,
    close: <path d="m6 6 12 12M18 6 6 18"/>,
    spark: <><path d="m12 3 1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3ZM19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z"/></>,
    send: <><path d="m4 11 15-7-5.5 16-2.8-6.7L4 11ZM10.7 13.3 19 4"/></>,
    book: <><path d="M12 19c-2-1.5-4.7-1.8-7-1V5.5c2.3-.8 5-.5 7 1v12.5ZM12 19c2-1.5 4.7-1.8 7-1V5.5c-2.3-.8-5-.5-7 1v12.5Z"/></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

function getHostOrigin(): string | null {
  const value = new URLSearchParams(window.location.search).get('hostOrigin')
  if (!value) return null
  try {
    const url = new URL(value)
    return (url.protocol === 'http:' || url.protocol === 'https:') && url.origin === value ? value : null
  } catch {
    return null
  }
}

const hostOrigin = getHostOrigin()
const kbId = new URLSearchParams(window.location.search).get('kbId')?.trim() || null
const messageType = 'knowledge-assistant:state'

function Launcher({ open, buttonRef, onToggle }: { open: boolean; buttonRef: Ref<HTMLButtonElement>; onToggle: () => void }) {
  return <button ref={buttonRef} className="launcher" type="button" aria-label={open ? '收起知识助手' : '打开知识助手'} aria-expanded={open} onClick={onToggle}>
    <Icon name={open ? 'close' : 'chat'} size={26} />
  </button>
}

function WelcomeState() {
  return <div className="welcome-state">
    <div className="welcome-icon"><Icon name="book" size={30} /></div>
    <h2>你好，欢迎使用知识助手</h2>
    <p>在这里，你可以围绕知识内容提出问题，开启探索与学习。</p>
  </div>
}

function Composer({ busy, onSend }: { busy: boolean; onSend: (question: string) => void }) {
  const [draft, setDraft] = useState('')
  function submit() {
    const question = draft.trim()
    if (!kbId || busy || !question) return
    onSend(question)
    setDraft('')
  }
  return <div className="composer">
    <label htmlFor="question">你的问题</label>
    <div className="input-box">
      <textarea id="question" rows={2} maxLength={1000} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => {
        if (event.key === 'Enter' && event.ctrlKey && !event.nativeEvent.isComposing) { event.preventDefault(); submit() }
      }} placeholder="输入你想了解的问题…" />
      <button type="button" className="send-button" disabled={!kbId || busy || !draft.trim()} onClick={submit} aria-label="发送问题"><Icon name="send" size={18} /></button>
    </div>
    <p className="preview-note">{kbId ? '点击发送，或按 Ctrl+Enter' : '未配置知识库，请在演示页网址中加入 ?kbId=你的知识库ID'}</p>
  </div>
}

function ChatPanel({ closeButtonRef, onClose }: { closeButtonRef: Ref<HTMLButtonElement>; onClose: () => void }) {
  const [replies, setReplies] = useState<Reply[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const content = useRef<HTMLElement>(null)

  useEffect(() => { content.current?.scrollTo({ top: content.current.scrollHeight, behavior: 'smooth' }) }, [replies, busy, error])

  async function send(question: string) {
    setBusy(true)
    setError('')
    try {
      const reply = await ask(question)
      setReplies((previous) => [...previous, reply])
    } catch (reason) {
      setError(reason instanceof TypeError ? '无法连接后端，请确认 8000 端口的服务已启动。' : reason instanceof Error ? reason.message : '连接失败，请确认后端已启动。')
    } finally {
      setBusy(false)
    }
  }
  return <section className="panel" aria-label="知识助手">
    <header className="panel-header">
      <div className="header-icon"><Icon name="spark" size={22} /></div>
      <div className="header-copy"><h1>知识助手</h1><p>为你的学习与探索提供帮助</p></div>
      <button ref={closeButtonRef} className="close-button" type="button" aria-label="关闭知识助手" onClick={onClose}><Icon name="close" size={20} /></button>
    </header>
    <main ref={content} className="panel-content" aria-live="polite">
      {replies.length === 0 && <WelcomeState />}
      {replies.map((reply, index) => <div className="exchange" key={index}>
        <p className="question-bubble">{reply.question}</p>
        <div className="answer-bubble">
          <span className="answer-status">{reply.status === 'generated' ? '千问生成的回答' : reply.status === 'not_generated' ? '尚未生成答案' : '资料不足'}</span>
          <p>{reply.answer}</p>
          {reply.sources.length > 0 && <details className="sources" open={reply.status === 'not_generated'}>
            <summary>查看引用原文（{reply.sources.length}）</summary>
            {reply.sources.map((source, sourceIndex) => <div className="source" key={sourceIndex}>
              <strong>{source.label || `片段 ${sourceIndex + 1}`} · {source.relative_path} · 第 {source.start_line}–{source.end_line} 行</strong>
              <p>{source.content}</p>
            </div>)}
          </details>}
        </div>
      </div>)}
      {busy && <p className="response-notice">正在检索资料并生成回答…</p>}
      {error && <p className="response-error" role="alert">{error}</p>}
    </main>
    <Composer busy={busy} onSend={send} />
  </section>
}

function App() {
  const [open, setOpen] = useState(false)
  const launcher = useRef<HTMLButtonElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (hostOrigin && window.parent !== window) {
      window.parent.postMessage({ type: messageType, open }, hostOrigin)
    }
  }, [open])

  useEffect(() => {
    function receive(event: MessageEvent) {
      if (!hostOrigin || event.origin !== hostOrigin || event.source !== window.parent) return
      const data: unknown = event.data
      if (!data || typeof data !== 'object' || !('type' in data) || data.type !== messageType || !('open' in data) || typeof data.open !== 'boolean') return
      setOpen(data.open)
    }
    window.addEventListener('message', receive)
    return () => window.removeEventListener('message', receive)
  }, [])

  function show() {
    setOpen(true)
    requestAnimationFrame(() => closeButton.current?.focus())
  }

  function hide() {
    setOpen(false)
    requestAnimationFrame(() => launcher.current?.focus())
  }

  return <div className={`widget ${open ? 'is-open' : ''}`} onKeyDown={(event) => {
    if (event.key === 'Escape' && open) {
      event.preventDefault()
      hide()
    }
  }}>
    {open && <ChatPanel closeButtonRef={closeButton} onClose={hide} />}
    <Launcher open={open} buttonRef={launcher} onToggle={open ? hide : show} />
  </div>
}

createRoot(document.getElementById('root')!).render(<App />)
