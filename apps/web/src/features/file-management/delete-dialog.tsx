import { useEffect, useRef, useState } from 'react'
import { deleteDocument } from './api'
import { Modal } from './components'
import type { FileRecord } from './types'

export function DeleteDialog({
  file,
  onDeleted,
  onClose,
}: {
  file: FileRecord
  onDeleted: () => Promise<void>
  onClose: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [deleted, setDeleted] = useState(false)
  const [error, setError] = useState('')
  const action = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (error && !busy) action.current?.focus()
  }, [error, busy])

  async function remove() {
    if (busy || deleted) return
    setBusy(true)
    setError('')
    try {
      await deleteDocument(file.kbId, file.id)
      setDeleted(true)
      try {
        await onDeleted()
      } catch {
        setError('文件已删除，但列表刷新失败。请关闭弹窗后点击“刷新列表”核对，无需重复删除。')
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除失败，请刷新列表核对后再试。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={deleted ? '文件已删除' : '删除文件'}
      description="从当前知识库移除这份资料"
      busy={busy}
      onClose={onClose}
    >
      <div className="fm-dialog-body" aria-busy={busy}>
        <p className="fm-delete-path">{file.path}</p>
        <p>
          删除后，这份文件不再出现在列表或参与后续问答检索。历史版本和原件仍由后端保留，重新上传同路径文件可以恢复。
        </p>
        {error && (
          <p className="fm-error" role="alert">
            {error}
          </p>
        )}
      </div>
      <footer className="fm-dialog-footer">
        {!deleted && (
          <button className="fm-button" autoFocus disabled={busy} onClick={onClose}>
            取消
          </button>
        )}
        <button
          ref={action}
          className={`fm-button ${deleted ? 'fm-primary' : 'fm-danger'}`}
          disabled={busy}
          onClick={deleted ? onClose : () => { void remove() }}
        >
          {deleted ? '完成' : busy ? '正在删除…' : '确认删除'}
        </button>
      </footer>
    </Modal>
  )
}
