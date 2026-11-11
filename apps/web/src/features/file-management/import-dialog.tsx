import { useEffect, useRef, useState } from 'react'
import { uploadDocuments } from './api'
import { Icon, Modal } from './components'
import { candidateError, FILE_ACCEPT, fileType, formatSize, MAX_FILES } from './model'
import type { FileRecord, ImportCandidate, ImportResult } from './types'

export function ImportDialog({
  kbId,
  kbName,
  existing,
  onImported,
  onClose,
}: {
  kbId: string
  kbName: string
  existing: FileRecord[]
  onImported: () => Promise<void>
  onClose: () => void
}) {
  const [candidates, setCandidates] = useState<ImportCandidate[]>([])
  const [results, setResults] = useState<ImportResult[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [refreshWarning, setRefreshWarning] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const folderInput = useRef<HTMLInputElement>(null)
  const doneButton = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (results && !busy) doneButton.current?.focus()
  }, [results, busy])
  const selected = candidates.filter((candidate) => candidate.selected)
  const tooMany = selected.length > MAX_FILES
  const invalidCount = candidates.filter((candidate) =>
    candidateError(candidate, candidates),
  ).length
  const canAdd =
    !busy &&
    selected.length > 0 &&
    !tooMany &&
    selected.every((candidate) => !candidateError(candidate, candidates))
  const failed = results?.filter((result) => result.status === 'failed').length || 0
  const succeeded =
    results?.filter((result) => !['failed', 'skipped'].includes(result.status)).length || 0

  function choose(files: FileList | null) {
    if (busy || !files?.length) return
    const next = Array.from(files).map((file) => ({
      id: crypto.randomUUID(),
      path: file.webkitRelativePath || file.name,
      size: file.size,
      file,
      selected: false,
    }))
    let count = 0
    setCandidates(
      next.map((candidate) => ({
        ...candidate,
        selected: !candidateError(candidate, next) && count++ < MAX_FILES,
      })),
    )
    setError('')
  }

  async function submit() {
    if (!canAdd) return
    setBusy(true)
    setError('')
    setRefreshWarning('')
    try {
      const uploaded = await uploadDocuments(kbId, selected)
      const byPath = new Map(uploaded.map((result) => [result.path, result]))
      setResults(
        candidates.map(
          (candidate) =>
            byPath.get(candidate.path) || {
              path: candidate.path,
              status: 'skipped',
              reason: candidateError(candidate, candidates) || '未勾选，本次未提交',
            },
        ),
      )
      try {
        await onImported()
      } catch {
        setRefreshWarning(
          '后端已返回导入结果，但文件列表刷新失败。请关闭弹窗后点击“刷新列表”核对，避免重复提交。',
        )
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '上传失败，请刷新列表核对后再试。')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={results ? '导入结果' : '添加文件'}
      description={`目标知识库：${kbName}`}
      onClose={onClose}
      wide
      busy={busy}
    >
      <div className="fm-dialog-body" aria-busy={busy}>
        <div className="fm-inline-note">
          <Icon name="info" size={18} />
          <span>
            文件将上传到本地后端并保存。同路径文件按内容更新，未变化时跳过；处理失败不会覆盖旧的可用版本。
          </span>
        </div>
        {error && (
          <p className="fm-error" role="alert">
            {error}
          </p>
        )}
        {results ? (
          <>
            <div className="fm-result-summary">
              <span className="fm-result-icon">
                <Icon name={failed ? 'alert' : 'check'} size={28} />
              </span>
              <div>
                <h3>
                  处理完成：{succeeded} 个成功，{failed} 个失败
                </h3>
                <p>
                  {results.filter((result) => result.status === 'skipped').length} 个未提交 ·
                  结果来自本地后端
                </p>
              </div>
            </div>
            {refreshWarning && (
              <p className="fm-validation" role="alert">
                {refreshWarning}
              </p>
            )}
            <ul className="fm-result-list">
              {results.map((result, index) => (
                <li key={index}>
                  <span className="fm-path" title={result.path}>
                    {result.path}
                  </span>
                  <span
                    className={
                      result.status === 'failed'
                        ? 'fm-error-text'
                        : result.status === 'skipped'
                          ? 'fm-muted'
                          : 'fm-success-text'
                    }
                  >
                    {result.reason}
                    {result.versionNo != null && ` · v${result.versionNo}`}
                  </span>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <>
            <div className="fm-upload-zone">
              <span className="fm-upload-icon">
                <Icon name="upload" size={30} />
              </span>
              <h3>选择要添加的资料</h3>
              <p>支持多选文件，也可以选择目录后勾选部分文件</p>
              <div className="fm-button-row">
                <button
                  className="fm-button fm-primary"
                  disabled={busy}
                  onClick={() => fileInput.current?.click()}
                >
                  <Icon name="plus" size={17} />
                  选择文件
                </button>
                <button
                  className="fm-button"
                  disabled={busy}
                  onClick={() => folderInput.current?.click()}
                >
                  <Icon name="folder" size={17} />
                  选择目录
                </button>
              </div>
              <input
                ref={fileInput}
                className="fm-hidden"
                disabled={busy}
                type="file"
                multiple
                accept={FILE_ACCEPT}
                aria-label="选择本地文件"
                onChange={(event) => {
                  choose(event.target.files)
                  event.target.value = ''
                }}
              />
              <input
                ref={folderInput}
                className="fm-hidden"
                disabled={busy}
                type="file"
                multiple
                aria-label="选择本地目录"
                {...{ webkitdirectory: '' }}
                onChange={(event) => {
                  choose(event.target.files)
                  event.target.value = ''
                }}
              />
            </div>
            <p className="fm-help">
              当前后端支持 UTF-8 的 MD / TXT；每批最多 20 个文件，单文件不超过 5
              MiB。Word、PDF、Excel 暂不支持真实导入。重新选择会替换待添加列表。
            </p>
            {candidates.length > 0 && (
              <>
                <div className="fm-selection-header">
                  <strong>
                    待导入文件 <span>{candidates.length}</span>
                  </strong>
                  <span>
                    已选 {selected.length} / {MAX_FILES} 个
                    {invalidCount > 0 && ` · ${invalidCount} 个校验未通过`}
                  </span>
                </div>
                {candidates.length > MAX_FILES && (
                  <p className="fm-validation" role="status">
                    本次选择超过 20 个文件，默认仅勾选前 20 个通过校验的文件，请分批导入。
                  </p>
                )}
                {tooMany && (
                  <p className="fm-error" role="alert">
                    已选超过 20 个文件，请取消部分勾选后再导入。
                  </p>
                )}
                <div className="fm-candidate-list">
                  {candidates.map((candidate) => {
                    const validation = candidateError(candidate, candidates)
                    const excess = candidate.selected && selected.indexOf(candidate) >= MAX_FILES
                    const update = existing.some((file) => file.path === candidate.path)
                    return (
                      <div className="fm-candidate" key={candidate.id}>
                        <input
                          type="checkbox"
                          aria-label={`选择 ${candidate.path}`}
                          checked={candidate.selected}
                          disabled={busy || !!validation}
                          onChange={(event) =>
                            setCandidates((previous) =>
                              previous.map((item) =>
                                item.id === candidate.id
                                  ? { ...item, selected: event.target.checked }
                                  : item,
                              ),
                            )
                          }
                        />
                        <span
                          className={`fm-file-icon fm-file-${fileType(candidate.path)?.toLowerCase() ?? 'unknown'}`}
                        >
                          <Icon name="files" size={18} />
                        </span>
                        <div className="fm-candidate-copy">
                          <span className="fm-path" title={candidate.path}>
                            {candidate.path}
                          </span>
                          <span className={validation || excess ? 'fm-error-text' : 'fm-muted'}>
                            {validation ||
                              (excess
                                ? '超出本批 20 个文件限制，请取消勾选'
                                : update
                                  ? '已有同路径文件 · 提交后由后端判断更新或跳过'
                                  : '可提交 · 编码和内容由后端校验')}
                          </span>
                        </div>
                        <span className="fm-candidate-size">{formatSize(candidate.size)}</span>
                        <button
                          className="fm-icon-button"
                          disabled={busy}
                          aria-label={`移除 ${candidate.path}`}
                          onClick={() =>
                            setCandidates((previous) =>
                              previous.filter((item) => item.id !== candidate.id),
                            )
                          }
                        >
                          <Icon name="close" size={16} />
                        </button>
                      </div>
                    )
                  })}
                </div>
              </>
            )}
          </>
        )}
        {busy && (
          <p className="fm-upload-pending" role="status">
            正在上传并处理，请稍候…
          </p>
        )}
      </div>
      <footer className="fm-dialog-footer">
        {results ? (
          <button
            ref={doneButton}
            className="fm-button fm-primary"
            disabled={busy}
            onClick={onClose}
          >
            完成
          </button>
        ) : (
          <>
            <button className="fm-button" disabled={busy} onClick={onClose}>
              取消
            </button>
            <button
              className="fm-button fm-primary"
              disabled={!canAdd}
              onClick={() => {
                void submit()
              }}
            >
              {busy ? '正在导入…' : selected.length ? `上传 ${selected.length} 个文件` : '上传文件'}
            </button>
          </>
        )}
      </footer>
    </Modal>
  )
}
