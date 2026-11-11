import { useEffect, useState } from 'react'
import { createBase, listBases, listDocuments } from './api'
import { Icon, Modal, Status } from './components'
import { ImportDialog } from './import-dialog'
import { FILE_FORMATS, fileName, fileTypeLabel, formatSize, formatTime, PAGE_SIZE } from './model'
import type { FileRecord, FileStatus, FileType, KnowledgeBase } from './types'

type Overlay = { kind: 'create' } | { kind: 'import' } | { kind: 'detail'; file: FileRecord } | null
const message = (error: unknown) =>
  error instanceof Error ? error.message : '操作失败，请稍后重试。'

function CreateDialog({
  bases,
  onCreate,
  onClose,
}: {
  bases: KnowledgeBase[]
  onCreate: (name: string) => Promise<void>
  onClose: () => void
}) {
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return (
    <Modal
      title="新建知识库"
      description="为一组相关的资料建立独立空间"
      onClose={onClose}
      busy={busy}
    >
      <form
        onSubmit={async (event) => {
          event.preventDefault()
          if (busy) return
          const value = name.trim()
          if (!value) {
            setError('请输入知识库名称')
            return
          }
          if (value.length > 100) {
            setError('知识库名称最多 100 个字符')
            return
          }
          if (bases.some((base) => base.name.toLocaleLowerCase() === value.toLocaleLowerCase())) {
            setError('已存在同名知识库，请重新命名')
            return
          }
          setBusy(true)
          setError('')
          try {
            await onCreate(value)
          } catch (reason) {
            setError(message(reason))
          } finally {
            setBusy(false)
          }
        }}
      >
        <div className="fm-dialog-body">
          <label className="fm-field-label" htmlFor="kb-name">
            知识库名称
          </label>
          <input
            autoFocus
            className="fm-text-input"
            id="kb-name"
            placeholder="例如：团队使用手册"
            maxLength={100}
            disabled={busy}
            value={name}
            onChange={(event) => {
              setName(event.target.value)
              setError('')
            }}
            aria-invalid={!!error}
            aria-describedby={error ? 'kb-error' : undefined}
          />
          {error && (
            <p id="kb-error" className="fm-error" role="alert">
              {error}
            </p>
          )}
          <p className="fm-help">知识库由本地后端保存，刷新页面后仍可继续使用。</p>
        </div>
        <footer className="fm-dialog-footer">
          <button type="button" className="fm-button" disabled={busy} onClick={onClose}>
            取消
          </button>
          <button className="fm-button fm-primary" type="submit" disabled={busy}>
            {busy ? '正在创建…' : '创建知识库'}
          </button>
        </footer>
      </form>
    </Modal>
  )
}

export function FileManagement() {
  const [bases, setBases] = useState<KnowledgeBase[]>([])
  const [files, setFiles] = useState<FileRecord[]>([])
  const [kbId, setKbId] = useState(
    () => new URLSearchParams(window.location.search).get('kbId')?.trim() || '',
  )
  const [baseLoading, setBaseLoading] = useState(true)
  const [baseError, setBaseError] = useState('')
  const [fileLoading, setFileLoading] = useState(false)
  const [fileError, setFileError] = useState('')
  const [loadedKbId, setLoadedKbId] = useState('')
  const [baseRefresh, setBaseRefresh] = useState(0)
  const [fileRefresh, setFileRefresh] = useState(0)
  const [search, setSearch] = useState('')
  const [type, setType] = useState<FileType | ''>('')
  const [status, setStatus] = useState<FileStatus | ''>('')
  const [page, setPage] = useState(1)
  const [overlay, setOverlay] = useState<Overlay>(null)
  const [notice, setNotice] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    setBaseLoading(true)
    setBaseError('')
    listBases(controller.signal)
      .then((data) => {
        setBases(data)
        setKbId((current) =>
          data.some((base) => base.id === current) ? current : data[0]?.id || '',
        )
      })
      .catch((reason) => {
        if (!controller.signal.aborted) {
          setBaseError(message(reason))
          setBases([])
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setBaseLoading(false)
      })
    return () => controller.abort()
  }, [baseRefresh])

  useEffect(() => {
    if (baseLoading || baseError) return
    const url = new URL(window.location.href)
    if (kbId) url.searchParams.set('kbId', kbId)
    else url.searchParams.delete('kbId')
    window.history.replaceState(null, '', url)
  }, [kbId, baseLoading, baseError])

  useEffect(() => {
    const controller = new AbortController()
    setFiles([])
    setFileError('')
    if (!kbId || baseLoading || baseError) {
      setFileLoading(false)
      return () => controller.abort()
    }
    setFileLoading(true)
    listDocuments(kbId, controller.signal)
      .then((data) => {
        setFiles(data)
      })
      .catch((reason) => {
        if (!controller.signal.aborted) setFileError(message(reason))
      })
      .finally(() => {
        if (!controller.signal.aborted) {
          setFileLoading(false)
          setLoadedKbId(kbId)
        }
      })
    return () => controller.abort()
  }, [kbId, baseLoading, baseError, fileRefresh])

  const kb = bases.find((base) => base.id === kbId)
  const currentFiles = files.filter((file) => file.kbId === kbId)
  const loading = baseLoading || (!!kb && (fileLoading || loadedKbId !== kbId))
  const error = baseError || (loadedKbId === kbId ? fileError : '')
  const canUpload = !!kb && !loading && !error
  const searchableCount = currentFiles.filter((file) => file.searchable).length
  const filtered = currentFiles
    .filter(
      (file) =>
        file.path.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()) &&
        (!type || file.type === type) &&
        (!status || (status === 'searchable' ? file.searchable : !file.searchable)),
    )
    .sort(
      (a, b) => b.importedAt.localeCompare(a.importedAt) || a.path.localeCompare(b.path, 'zh-CN'),
    )
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const visible = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
  const hasFilters = !!(search || type || status)
  const chatHref = `./index.html${kb ? `?kbId=${encodeURIComponent(kb.id)}` : ''}`

  function clearFilters() {
    setSearch('')
    setType('')
    setStatus('')
    setPage(1)
  }
  function close() {
    setOverlay(null)
  }
  function selectBase(id: string) {
    setKbId(id)
    clearFilters()
    setNotice('')
  }
  async function afterImport() {
    setFileLoading(true)
    setFileError('')
    try {
      setFiles(await listDocuments(kbId))
      clearFilters()
      setLoadedKbId(kbId)
    } catch (reason) {
      setFileError(message(reason))
      throw reason
    } finally {
      setFileLoading(false)
    }
  }

  return (
    <>
      <header className="fm-topbar">
        <div className="fm-topbar-inner">
          <a className="fm-brand" href={chatHref}>
            <span className="fm-brand-icon">
              <Icon name="book" size={21} />
            </span>
            知识助手
          </a>
          <span className="fm-breadcrumb">/</span>
          <span className="fm-breadcrumb-label">文件管理</span>
          <a className="fm-back-link" href={chatHref}>
            <Icon name="arrow" size={15} />
            前往问答演示
          </a>
        </div>
      </header>
      <main className="fm-main">
        <div className="fm-page-heading">
          <div>
            <div className="fm-eyebrow">KNOWLEDGE WORKSPACE</div>
            <h1>
              文件管理 <span className="fm-prototype-tag">本地知识库</span>
            </h1>
            <p>整理知识来源，让每一份资料都有迹可循。</p>
          </div>
        </div>
        <section className="fm-workspace" aria-label="当前知识库">
          <div className="fm-workspace-title">
            <span className="fm-workspace-icon">
              <Icon name="book" size={22} />
            </span>
            <div>
              <label htmlFor="knowledge-base">当前知识库</label>
              <select
                id="knowledge-base"
                disabled={baseLoading || !!baseError || !bases.length}
                value={kbId}
                onChange={(event) => selectBase(event.target.value)}
              >
                {!bases.length && (
                  <option value="">
                    {baseLoading ? '正在读取知识库…' : baseError ? '未连接后端' : '请先创建知识库'}
                  </option>
                )}
                {bases.map((base) => (
                  <option key={base.id} value={base.id}>
                    {base.name}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button
            className="fm-button fm-create-button"
            disabled={baseLoading || !!baseError}
            onClick={() => setOverlay({ kind: 'create' })}
          >
            <Icon name="plus" size={16} />
            新建知识库
          </button>
          <button
            className="fm-button"
            disabled={loading}
            onClick={() => {
              clearFilters()
              setBaseRefresh((value) => value + 1)
            }}
          >
            刷新列表
          </button>
          <div className="fm-workspace-divider" />
          <div className="fm-workspace-description">
            <span className="fm-live-dot" />
            本地后端存储<p>知识库和文件在刷新后保留</p>
          </div>
        </section>
        <div className="fm-demo-banner">
          <Icon name="info" size={18} />
          <span>
            <strong>{baseLoading ? '正在连接' : baseError ? '连接异常' : '本地后端'}</strong>
            {baseLoading
              ? '正在读取知识库列表…'
              : baseError
                ? '暂时无法读取数据，请检查后端服务并重试。'
                : '支持 UTF-8 的 MD/TXT 真实导入；Word、PDF、Excel 导入及文件删除暂未开放。'}
          </span>
          <span className="fm-demo-label">LOCAL</span>
        </div>
        <section className="fm-stats" aria-label="知识库文件统计">
          {[
            {
              label: '文件总数',
              value: currentFiles.length,
              icon: 'files' as const,
              style: 'blue',
              hint: '当前知识库已保存的文件',
            },
            {
              label: '可检索',
              value: searchableCount,
              icon: 'check' as const,
              style: 'green',
              hint: '当前版本已有可参与检索的文本块',
            },
            {
              label: '待建立文本块',
              value: currentFiles.length - searchableCount,
              icon: 'alert' as const,
              style: 'amber',
              hint: '可重新导入文件以更新检索状态',
            },
          ].map((stat) => (
            <div className="fm-stat" key={stat.label}>
              <span className={`fm-stat-icon fm-stat-${stat.style}`}>
                <Icon name={stat.icon} size={23} />
              </span>
              <div>
                <span className="fm-stat-label">{stat.label}</span>
                <strong>{loading || error ? '—' : stat.value.toString().padStart(2, '0')}</strong>
                <p>{stat.hint}</p>
              </div>
            </div>
          ))}
        </section>
        <section className="fm-list-card" aria-labelledby="file-list-heading" aria-busy={loading}>
          <div className="fm-list-heading">
            <h2 id="file-list-heading">
              全部文件 <span>{loading || error ? '—' : currentFiles.length}</span>
            </h2>
            <span className="fm-sort-note">按导入时间从新到旧</span>
          </div>
          <div className="fm-filters">
            <div className="fm-search">
              <Icon name="search" size={18} />
              <input
                aria-label="搜索文件名或路径"
                placeholder="搜索文件名或路径…"
                disabled={loading || !!error}
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value)
                  setPage(1)
                }}
              />
              {search && (
                <button
                  className="fm-icon-button"
                  aria-label="清除搜索"
                  onClick={() => {
                    setSearch('')
                    setPage(1)
                  }}
                >
                  <Icon name="close" size={15} />
                </button>
              )}
            </div>
            <label className="fm-select-filter">
              类型
              <select
                aria-label="文件类型"
                disabled={loading || !!error}
                value={type}
                onChange={(event) => {
                  setType(event.target.value as FileType | '')
                  setPage(1)
                }}
              >
                <option value="">全部类型</option>
                {FILE_FORMATS.map((format) => (
                  <option key={format.type} value={format.type}>
                    {format.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="fm-select-filter">
              状态
              <select
                aria-label="检索状态"
                disabled={loading || !!error}
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value as FileStatus | '')
                  setPage(1)
                }}
              >
                <option value="">全部状态</option>
                <option value="searchable">可检索</option>
                <option value="not_searchable">待建立文本块</option>
              </select>
            </label>
            {hasFilters && (
              <button className="fm-text-button" onClick={clearFilters}>
                清除筛选
              </button>
            )}
            <button
              id="add-files"
              disabled={!canUpload}
              className="fm-button fm-primary fm-add-button"
              onClick={() => setOverlay({ kind: 'import' })}
            >
              <Icon name="plus" size={18} />
              添加文件
            </button>
          </div>
          <div className="fm-table-wrap">
            <table className="fm-table">
              <colgroup>
                <col className="fm-col-name" />
                <col className="fm-col-type" />
                <col className="fm-col-size" />
                <col className="fm-col-time" />
                <col className="fm-col-status" />
                <col className="fm-col-actions" />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col">文件名 / 相对路径</th>
                  <th scope="col">类型</th>
                  <th scope="col">文件大小</th>
                  <th scope="col">导入时间</th>
                  <th scope="col">检索状态</th>
                  <th scope="col">操作</th>
                </tr>
              </thead>
              <tbody>
                {!loading &&
                  !error &&
                  visible.map((file) => (
                    <tr key={file.id}>
                      <td>
                        <div className="fm-file-cell">
                          <span
                            className={`fm-file-icon fm-file-${file.type?.toLowerCase() ?? 'unknown'}`}
                          >
                            <Icon name="files" size={21} />
                          </span>
                          <div className="fm-file-copy">
                            <button
                              className="fm-filename"
                              title={fileName(file.path)}
                              onClick={() => setOverlay({ kind: 'detail', file })}
                            >
                              {fileName(file.path)}
                            </button>
                            <span className="fm-path" title={file.path}>
                              {file.path}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td>
                        <span className="fm-type-tag">{file.type || '其他'}</span>
                      </td>
                      <td className="fm-cell-muted" title="后端暂未提供文件大小">
                        {formatSize(file.size)}
                      </td>
                      <td className="fm-cell-muted fm-time">{formatTime(file.importedAt)}</td>
                      <td>
                        <Status searchable={file.searchable} />
                      </td>
                      <td>
                        <div className="fm-row-actions">
                          <button
                            className="fm-text-button"
                            aria-label={`查看 ${fileName(file.path)} 详情`}
                            onClick={() => setOverlay({ kind: 'detail', file })}
                          >
                            详情
                          </button>
                          <span aria-hidden="true" />
                          <button
                            className="fm-text-button fm-delete-link"
                            disabled
                            title="后端暂未提供删除接口"
                            aria-label={`删除 ${fileName(file.path)}（暂未开放）`}
                          >
                            删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
          {error ? (
            <div className="fm-empty fm-load-error" role="alert">
              <span className="fm-empty-icon">
                <Icon name="alert" size={32} />
              </span>
              <h3>暂时无法读取数据</h3>
              <p>{error}</p>
              <button
                className="fm-button"
                onClick={() =>
                  baseError
                    ? setBaseRefresh((value) => value + 1)
                    : setFileRefresh((value) => value + 1)
                }
              >
                重试
              </button>
            </div>
          ) : loading ? (
            <div className="fm-empty" role="status">
              <h3>正在读取文件…</h3>
              <p>请稍候，正在连接本地后端。</p>
            </div>
          ) : (
            visible.length === 0 && (
              <div className="fm-empty">
                <span className="fm-empty-icon">
                  <Icon name={currentFiles.length ? 'search' : 'folder'} size={32} />
                </span>
                <h3>
                  {!kb
                    ? '先创建一个知识库'
                    : currentFiles.length
                      ? '没有找到匹配的文件'
                      : '从第一份资料开始'}
                </h3>
                <p>
                  {!kb
                    ? '创建知识库后，即可上传并保存你的资料。'
                    : currentFiles.length
                      ? '试试其他关键词，或清除筛选条件。'
                      : '添加 UTF-8 编码的 Markdown 或 TXT 文件，开始整理这个知识库。'}
                </p>
                <button
                  className={`fm-button ${currentFiles.length ? '' : 'fm-primary'}`}
                  onClick={
                    !kb
                      ? () => setOverlay({ kind: 'create' })
                      : currentFiles.length
                        ? clearFilters
                        : () => setOverlay({ kind: 'import' })
                  }
                >
                  {!kb ? '新建知识库' : currentFiles.length ? '清除筛选' : '添加文件'}
                </button>
              </div>
            )
          )}
          <footer className="fm-list-footer">
            <span aria-live="polite">
              {loading
                ? '正在读取…'
                : error
                  ? '数据读取失败'
                  : hasFilters
                    ? `找到 ${filtered.length} 个文件 · 共 ${currentFiles.length} 个`
                    : `共 ${currentFiles.length} 个文件`}
              {!loading && !error && filtered.length > 0 && (
                <span className="fm-footer-range">
                  显示 {(currentPage - 1) * PAGE_SIZE + 1}–
                  {Math.min(currentPage * PAGE_SIZE, filtered.length)} 条
                </span>
              )}
            </span>
            <nav className="fm-pagination" aria-label="文件列表分页">
              <button
                className="fm-page-arrow"
                aria-label="上一页"
                disabled={loading || !!error || currentPage <= 1}
                onClick={() => setPage(currentPage - 1)}
              >
                <span className="fm-rotate">
                  <Icon name="chevron" size={15} />
                </span>
              </button>
              <span className="fm-page-number" aria-current="page">
                {currentPage}
              </span>
              <span className="fm-page-total">/ {pageCount}</span>
              <button
                className="fm-page-arrow"
                aria-label="下一页"
                disabled={loading || !!error || currentPage >= pageCount}
                onClick={() => setPage(currentPage + 1)}
              >
                <Icon name="chevron" size={15} />
              </button>
            </nav>
          </footer>
        </section>
        <p className="fm-bottom-note">
          <Icon name="info" size={14} />
          可检索表示当前版本已有文本块，不代表模型已配置或回答一定正确；文件大小及删除能力待后端提供。
        </p>
      </main>
      <div className="fm-notice" role="status" aria-live="polite">
        {notice && (
          <span>
            <Icon name="check" size={17} />
            {notice}
            <button
              className="fm-icon-button"
              aria-label="关闭操作提示"
              onClick={() => setNotice('')}
            >
              <Icon name="close" size={15} />
            </button>
          </span>
        )}
      </div>
      {overlay?.kind === 'create' && (
        <CreateDialog
          bases={bases}
          onClose={close}
          onCreate={async (name) => {
            const created = await createBase(name)
            setBases((previous) => [...previous, created])
            selectBase(created.id)
            close()
            setNotice(`已创建知识库「${created.name}」`)
          }}
        />
      )}
      {overlay?.kind === 'import' && kb && (
        <ImportDialog
          kbId={kbId}
          kbName={kb.name}
          existing={currentFiles}
          onClose={close}
          onImported={afterImport}
        />
      )}
      {overlay?.kind === 'detail' && (
        <Modal title="文件详情" description="后端保存的当前版本信息" side onClose={close}>
          <div className="fm-dialog-body">
            <div className="fm-detail-title">
              <span
                className={`fm-file-icon fm-file-${overlay.file.type?.toLowerCase() ?? 'unknown'}`}
              >
                <Icon name="files" size={26} />
              </span>
              <h3>{fileName(overlay.file.path)}</h3>
            </div>
            <Status searchable={overlay.file.searchable} />
            <dl className="fm-detail-list">
              {[
                ['所属知识库', kb?.name || overlay.file.kbId],
                ['文件 ID', overlay.file.id],
                ['相对路径', overlay.file.path],
                ['文件类型', fileTypeLabel(overlay.file.type)],
                ['文件大小', '后端暂未提供'],
                ['导入时间', formatTime(overlay.file.importedAt)],
                ['当前版本', `v${overlay.file.versionNo}`],
                ['SHA-256', overlay.file.sha256],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
            <div className="fm-inline-note">
              <Icon name="info" size={18} />
              <span>
                展示已保存的元信息；原文预览和文件删除暂未开放。需要更新时，可重新上传同路径文件。
              </span>
            </div>
          </div>
          <footer className="fm-dialog-footer">
            <button className="fm-button" onClick={close}>
              关闭
            </button>
          </footer>
        </Modal>
      )}
    </>
  )
}
