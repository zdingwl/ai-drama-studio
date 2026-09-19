import { apiRequest } from '@/lib/api'

export interface ScriptSourceRead {
  project_id: string
  document_id: string | null
  revision: number | null
  filename: string | null
  text: string | null
}

export interface ScriptDocumentRead {
  id: string
  project_id: string
  revision: number
  char_count: number
  is_current: boolean
}

export function getScriptSource(projectId: string): Promise<ScriptSourceRead> {
  return apiRequest<ScriptSourceRead>(`/projects/${projectId}/script-localization/source`, { cache: 'no-store' })
}

export function pasteScriptSource(projectId: string, text: string): Promise<ScriptDocumentRead> {
  return apiRequest<ScriptDocumentRead>(`/projects/${projectId}/script-localization/paste`, {
    method: 'POST', body: JSON.stringify({ text }),
  })
}

export function uploadScriptSource(projectId: string, file: File): Promise<ScriptDocumentRead> {
  const body = new FormData()
  body.append('file', file)
  return apiRequest<ScriptDocumentRead>(`/projects/${projectId}/sources/document`, { method: 'POST', body })
}
