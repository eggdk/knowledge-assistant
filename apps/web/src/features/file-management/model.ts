import type { FileType, ImportCandidate } from './types'

export const MAX_FILES = 20
export const MAX_BYTES = 5 * 1024 * 1024
export const PAGE_SIZE = 10

export const FILE_FORMATS: { extension: string; type: FileType; label: string }[] = [
  { extension: 'md', type: 'MD', label: 'Markdown (.md)' },
  { extension: 'txt', type: 'TXT', label: 'TXT 文本 (.txt)' },
  { extension: 'docx', type: 'DOCX', label: 'Word (.docx)' },
  { extension: 'pdf', type: 'PDF', label: 'PDF (.pdf)' },
  { extension: 'xls', type: 'XLS', label: 'Excel (.xls)' },
  { extension: 'xlsx', type: 'XLSX', label: 'Excel (.xlsx)' },
]
export const UPLOAD_FORMATS = FILE_FORMATS.filter(
  (format) => format.type === 'MD' || format.type === 'TXT',
)
export const FILE_ACCEPT = UPLOAD_FORMATS.map((format) => `.${format.extension}`).join(',')

export function fileTypeLabel(type: FileType | null): string {
  return FILE_FORMATS.find((format) => format.type === type)?.label ?? '其他格式'
}

export function fileName(path: string): string {
  return path.split('/').pop() || path
}

export function fileType(path: string): FileType | null {
  const name = fileName(path)
  const extension = name.includes('.') ? name.split('.').pop()?.toLowerCase() : null
  return FILE_FORMATS.find((format) => format.extension === extension)?.type ?? null
}

export function formatSize(bytes: number | null): string {
  if (bytes === null) return '—'
  if (bytes === 0) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MiB`
}

export function formatTime(iso: string): string {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(iso))
}

export function candidateError(
  candidate: ImportCandidate,
  candidates: ImportCandidate[],
): string | null {
  const type = fileType(candidate.path)
  if (!type) return '格式不支持，请选择 UTF-8 的 .md 或 .txt 文件'
  if (type !== 'MD' && type !== 'TXT')
    return '当前后端暂不支持该格式的真实导入，请选择 .md 或 .txt 文件'
  if (candidate.size > MAX_BYTES) return '超过单文件 5 MiB 限制'
  if (
    candidate.path.split('/').some((part) => part === '..' || part === '.' || !part) ||
    candidate.path.includes('\\')
  )
    return '文件路径无效，请重新选择'
  if (candidates.some((other) => other.id !== candidate.id && other.path === candidate.path))
    return '本次选择中路径重复，请移除重复项'
  return null
}
