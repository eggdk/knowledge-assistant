import { useEffect, useRef, useState } from 'react'
import type { Ref } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'

type IconName = 'chat' | 'close' | 'spark' | 'send' | 'book'

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
const messageType = 'knowledge-assistant:state'

function Launcher({ open, buttonRef, onToggle }: { open: boolean; buttonRef: Ref<HTMLButtonElement>; onToggle: () => void }) {
  return <button ref={buttonRef} className="launcher" type="button" aria-label={open ? '收起知识助手' : '打开知识助手'} aria-expanded={open} onClick={onToggle}>
    <Icon name={open ? 'close' : 'chat'} size={26} />
  </button>
}

function WelcomeState() {
  return <main className="panel-content">
    <div className="welcome-icon"><Icon name="book" size={30} /></div>
    <h2>你好，欢迎使用知识助手</h2>
    <p>在这里，你可以围绕知识内容提出问题，开启探索与学习。</p>
  </main>
}

function Composer() {
  return <div className="composer">
    <label htmlFor="question">你的问题</label>
    <div className="input-box">
      <textarea id="question" rows={2} placeholder="输入你想了解的问题…" />
      <button type="button" className="send-button" disabled aria-label="发送问题（暂不可用）"><Icon name="send" size={18} /></button>
    </div>
    <p className="preview-note">当前为界面预览，暂不支持提问</p>
  </div>
}

function ChatPanel({ closeButtonRef, onClose }: { closeButtonRef: Ref<HTMLButtonElement>; onClose: () => void }) {
  return <section className="panel" aria-label="知识助手">
    <header className="panel-header">
      <div className="header-icon"><Icon name="spark" size={22} /></div>
      <div className="header-copy"><h1>知识助手</h1><p>为你的学习与探索提供帮助</p></div>
      <button ref={closeButtonRef} className="close-button" type="button" aria-label="关闭知识助手" onClick={onClose}><Icon name="close" size={20} /></button>
    </header>
    <WelcomeState />
    <Composer />
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
