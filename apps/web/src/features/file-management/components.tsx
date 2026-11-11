import { useEffect, useRef } from 'react'
import type { ReactNode } from 'react'

type IconName =
  | 'book'
  | 'files'
  | 'check'
  | 'alert'
  | 'plus'
  | 'search'
  | 'close'
  | 'arrow'
  | 'upload'
  | 'folder'
  | 'info'
  | 'chevron'

export function Icon({ name, size = 20 }: { name: IconName; size?: number }) {
  const paths: Record<IconName, ReactNode> = {
    book: (
      <>
        <path d="M12 6c-3-2-6-2-9-1v14c3-1 6-1 9 1 3-2 6-2 9-1V5c-3-1-6-1-9 1Z" />
        <path d="M12 6v14" />
      </>
    ),
    files: (
      <>
        <path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8Z" />
        <path d="M14 3v5h5M9 12h6M9 16h6" />
      </>
    ),
    check: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="m8 12 3 3 5-6" />
      </>
    ),
    alert: (
      <>
        <path d="m12 3 10 17H2Z" />
        <path d="M12 9v4M12 16h.01" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    search: (
      <>
        <circle cx="10.5" cy="10.5" r="6.5" />
        <path d="m16 16 4 4" />
      </>
    ),
    close: <path d="m6 6 12 12M18 6 6 18" />,
    arrow: <path d="m9 5-7 7 7 7M2 12h20" />,
    upload: (
      <>
        <path d="M12 16V3m-5 5 5-5 5 5M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5" />
      </>
    ),
    folder: <path d="M3 20h18V7H11L9 4H3Z" />,
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6M12 7h.01" />
      </>
    ),
    chevron: <path d="m9 5 7 7-7 7" />,
  }
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  )
}

export function Modal({
  title,
  description,
  children,
  onClose,
  side = false,
  wide = false,
  busy = false,
}: {
  title: string
  description?: string
  children: ReactNode
  onClose: () => void
  side?: boolean
  wide?: boolean
  busy?: boolean
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const close = useRef(onClose)
  close.current = onClose
  useEffect(() => {
    const dialog = ref.current!
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null
    dialog.showModal()
    // Native modal dialogs provide focus containment and make the background inert.
    return () => {
      dialog.close()
      const target = opener?.isConnected ? opener : document.getElementById('add-files')
      target?.focus()
    }
  }, [])
  return (
    <dialog
      ref={ref}
      className={`fm-dialog${side ? ' fm-drawer' : ''}${wide ? ' fm-dialog-wide' : ''}`}
      aria-labelledby="fm-dialog-title"
      aria-describedby={description ? 'fm-dialog-description' : undefined}
      onCancel={(event) => {
        // File pickers also emit a bubbling cancel event; only Esc on the dialog closes it.
        if (event.target === event.currentTarget) {
          event.preventDefault()
          if (!busy) close.current()
        }
      }}
      onClick={(event) => {
        if (!busy && event.target === event.currentTarget) close.current()
      }}
      onKeyDown={(event) => {
        if (event.key !== 'Tab') return
        const controls = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]',
          ),
        ).filter((element) => element.getClientRects().length > 0)
        const first = controls[0]
        const last = controls[controls.length - 1]
        if (!first) {
          event.preventDefault()
          return
        }
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault()
          last?.focus()
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault()
          first?.focus()
        }
      }}
    >
      <div className="fm-dialog-inner">
        <header className="fm-dialog-header">
          <div>
            <h2 id="fm-dialog-title">{title}</h2>
            {description && <p id="fm-dialog-description">{description}</p>}
          </div>
          <button
            className="fm-icon-button"
            aria-label={`关闭${title}`}
            disabled={busy}
            onClick={onClose}
          >
            <Icon name="close" />
          </button>
        </header>
        {children}
      </div>
    </dialog>
  )
}

export function Status({ searchable }: { searchable: boolean }) {
  return (
    <span className={`fm-status ${searchable ? 'fm-status-imported' : 'fm-status-failed'}`}>
      <span aria-hidden="true" />
      {searchable ? '可检索' : '待建立文本块'}
    </span>
  )
}
