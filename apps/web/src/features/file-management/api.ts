import { fileType } from './model'
import type { FileRecord, ImportCandidate, ImportResult, KnowledgeBase } from './types'

const BASE_PATH = '/api/knowledge-bases'
const BAD_RESPONSE = '后端返回的数据格式异常，请刷新列表核对实际结果后再操作。'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number | null = null,
  ) {
    super(message)
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

async function request(path: string, options: RequestInit = {}): Promise<unknown> {
  const timeout = new AbortController()
  const timer = window.setTimeout(() => timeout.abort(), 60_000)
  const signal = options.signal ? AbortSignal.any([options.signal, timeout.signal]) : timeout.signal
  try {
    const response = await fetch(path, { ...options, signal })
    if (!response.ok) {
      if ([500, 502, 503, 504].includes(response.status))
        throw new ApiError(
          '后端暂时不可用，请确认本地 8000 端口的服务已启动，然后重试。',
          response.status,
        )
      if (response.status === 404) throw new ApiError('知识库不存在，请刷新知识库列表。', 404)
      if (response.status === 413) throw new ApiError('上传内容过大，请减少文件数量或大小。', 413)
      let detail = ''
      try {
        const body: unknown = await response.json()
        if (isObject(body) && typeof body.detail === 'string') detail = body.detail
      } catch {
        /* A proxy may return HTML rather than the API error shape. */
      }
      throw new ApiError(
        detail
          ? `请求被拒绝：${detail}`
          : `请求失败（HTTP ${response.status}），请检查输入后重试。`,
        response.status,
      )
    }
    try {
      return (await response.json()) as unknown
    } catch {
      throw new ApiError(BAD_RESPONSE)
    }
  } catch (error) {
    if (options.signal?.aborted || error instanceof ApiError) throw error
    if (timeout.signal.aborted)
      throw new ApiError('等待后端超时，请先刷新列表核对结果，避免重复提交。')
    throw new ApiError(
      '无法连接本地后端，请确认 8000 端口服务已启动。若操作中断，请先刷新列表核对结果。',
    )
  } finally {
    window.clearTimeout(timer)
  }
}

function parseBase(value: unknown): KnowledgeBase {
  if (
    !isObject(value) ||
    typeof value.id !== 'string' ||
    !value.id ||
    typeof value.name !== 'string'
  )
    throw new ApiError(BAD_RESPONSE)
  return { id: value.id, name: value.name }
}

export async function listBases(signal?: AbortSignal): Promise<KnowledgeBase[]> {
  const data = await request(BASE_PATH, { signal })
  if (!Array.isArray(data)) throw new ApiError(BAD_RESPONSE)
  return data.map(parseBase)
}

export async function createBase(name: string): Promise<KnowledgeBase> {
  return parseBase(
    await request(BASE_PATH, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),
  )
}

export async function listDocuments(kbId: string, signal?: AbortSignal): Promise<FileRecord[]> {
  const data = await request(`${BASE_PATH}/${encodeURIComponent(kbId)}/documents`, { signal })
  if (!Array.isArray(data)) throw new ApiError(BAD_RESPONSE)
  return data.map((value: unknown): FileRecord => {
    if (
      !isObject(value) ||
      typeof value.id !== 'string' ||
      typeof value.relative_path !== 'string' ||
      typeof value.version_no !== 'number' ||
      !Number.isInteger(value.version_no) ||
      value.version_no < 1 ||
      typeof value.sha256 !== 'string' ||
      typeof value.imported_at !== 'string' ||
      !Number.isFinite(Date.parse(value.imported_at)) ||
      typeof value.searchable !== 'boolean'
    )
      throw new ApiError(BAD_RESPONSE)
    return {
      id: value.id,
      kbId,
      path: value.relative_path,
      type: fileType(value.relative_path),
      size: null,
      importedAt: value.imported_at,
      versionNo: value.version_no,
      sha256: value.sha256,
      searchable: value.searchable,
    }
  })
}

export async function uploadDocuments(
  kbId: string,
  candidates: ImportCandidate[],
): Promise<ImportResult[]> {
  const form = new FormData()
  for (const candidate of candidates) {
    form.append('files', candidate.file)
    form.append('relative_paths', candidate.path)
  }
  const data = await request(`${BASE_PATH}/${encodeURIComponent(kbId)}/documents/import`, {
    method: 'POST',
    body: form,
  })
  if (
    !isObject(data) ||
    !Array.isArray(data.files) ||
    data.files.length !== candidates.length ||
    typeof data.failed !== 'number'
  )
    throw new ApiError(BAD_RESPONSE)
  const pending = new Set(candidates.map((candidate) => candidate.path))
  const results = data.files.map((value: unknown): ImportResult => {
    if (
      !isObject(value) ||
      typeof value.relative_path !== 'string' ||
      !pending.delete(value.relative_path) ||
      !['created', 'updated', 'unchanged', 'failed'].includes(String(value.status)) ||
      typeof value.searchable !== 'boolean' ||
      !(value.version_no === null || typeof value.version_no === 'number')
    )
      throw new ApiError(BAD_RESPONSE)
    const status = value.status as 'created' | 'updated' | 'unchanged' | 'failed'
    const labels = {
      created: '新增成功',
      updated: '更新成功',
      unchanged: '内容未变化',
      failed: '导入失败',
    }
    return {
      path: value.relative_path,
      status,
      versionNo: value.version_no as number | null,
      searchable: value.searchable,
      reason:
        status === 'failed'
          ? typeof value.error === 'string'
            ? value.error
            : '后端未返回具体失败原因'
          : `${labels[status]} · ${value.searchable ? '可检索' : '待建立文本块'}`,
    }
  })
  if (pending.size || results.filter((result) => result.status === 'failed').length !== data.failed)
    throw new ApiError(BAD_RESPONSE)
  return results
}
