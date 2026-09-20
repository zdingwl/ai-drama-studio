import { apiRequest } from '@/lib/api'

export interface DramaScriptItem {
  id: string
  title: string
  filename: string
  char_count: number
  latest_revision: number
  is_active: boolean
  excerpt: string
}

export interface DramaScriptLibrary {
  project_id: string
  current_document_id: string | null
  scripts: DramaScriptItem[]
}

const base = (projectId: string) => `/projects/${projectId}/script-to-drama/library`

export function listDramaScripts(projectId: string): Promise<DramaScriptLibrary> {
  return apiRequest<DramaScriptLibrary>(base(projectId), { cache: 'no-store' })
}

export function selectDramaScript(projectId: string, scriptId: string, currentDocumentId: string | null): Promise<DramaScriptLibrary> {
  return apiRequest<DramaScriptLibrary>(`${base(projectId)}/select`, {
    method: 'POST',
    body: JSON.stringify({ source_asset_id: scriptId, expected_current_document_id: currentDocumentId }),
  })
}

export function pasteDramaScript(projectId: string, title: string, text: string): Promise<DramaScriptLibrary> {
  return apiRequest<DramaScriptLibrary>(`${base(projectId)}/paste`, {
    method: 'POST', body: JSON.stringify({ title, text }),
  })
}

export function uploadDramaScripts(projectId: string, files: File[]): Promise<DramaScriptLibrary> {
  const body = new FormData()
  for (const file of files) body.append('files', file)
  return apiRequest<DramaScriptLibrary>(`${base(projectId)}/uploads`, { method: 'POST', body })
}
