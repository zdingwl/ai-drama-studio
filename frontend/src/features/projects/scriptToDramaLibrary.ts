import { apiRequest } from '@/lib/api'
import type { TaskRead } from './types'

export interface DramaScriptItem {
  id: string
  title: string
  filename: string
  char_count: number
  latest_revision: number
  is_active: boolean
  excerpt: string
}

export interface DramaScriptDetail extends DramaScriptItem {
  text: string
  sha256: string
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

export function getDramaScript(projectId: string, scriptId: string): Promise<DramaScriptDetail> {
  return apiRequest<DramaScriptDetail>(`${base(projectId)}/${encodeURIComponent(scriptId)}`, { cache: 'no-store' })
}

export function updateDramaScript(projectId: string, scriptId: string, expectedRevision: number, title: string, text: string): Promise<DramaScriptDetail> {
  return apiRequest<DramaScriptDetail>(`${base(projectId)}/${encodeURIComponent(scriptId)}`, {
    method: 'PUT', body: JSON.stringify({ expected_revision: expectedRevision, title, text }),
  })
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

export function extractDramaAssets(projectId: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/script-to-drama/commands/extract-assets`, {
    method: 'POST',
    headers: { 'Idempotency-Key': `asset-extract-${crypto.randomUUID()}` },
  })
}
