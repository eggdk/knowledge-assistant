export type KnowledgeBase = { id: string; name: string }
export type FileType = 'MD' | 'TXT' | 'DOCX' | 'PDF' | 'XLS' | 'XLSX'
export type FileStatus = 'searchable' | 'not_searchable'

// The list endpoint does not currently return original file sizes.
export type FileRecord = {
  id: string
  kbId: string
  path: string
  type: FileType | null
  size: number | null
  importedAt: string
  searchable: boolean
  versionNo: number
  sha256: string
}

export type ImportCandidate = {
  id: string
  path: string
  size: number
  selected: boolean
  file: File
}

export type ImportResult = {
  path: string
  status: 'created' | 'updated' | 'unchanged' | 'failed' | 'skipped'
  reason: string
  versionNo?: number | null
  searchable?: boolean
}
