import { apiRequest } from '@/lib/api'
import type { TaskRead } from './types'

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

export interface ScriptStageRead {
  status: 'NOT_BUILT' | 'CURRENT' | 'STALE'
  artifact_id: string | null
  revision: number | null
  content: Record<string, unknown> | null
}

export interface ScriptLocalizationStateRead {
  project_id: string
  analysis: ScriptStageRead
  plan: ScriptStageRead
  target_script: ScriptStageRead
  final_output: ScriptStageRead
}

const endpoint = (projectId: string) => `/projects/${projectId}/script-localization`

export function getScriptSource(projectId: string): Promise<ScriptSourceRead> {
  return apiRequest<ScriptSourceRead>(`${endpoint(projectId)}/source`, { cache: 'no-store' })
}

export function getScriptState(projectId: string): Promise<ScriptLocalizationStateRead> {
  return apiRequest<ScriptLocalizationStateRead>(`${endpoint(projectId)}/state`, { cache: 'no-store' })
}

export function pasteScriptSource(projectId: string, text: string): Promise<ScriptDocumentRead> {
  return apiRequest<ScriptDocumentRead>(`${endpoint(projectId)}/paste`, {
    method: 'POST', body: JSON.stringify({ text }),
  })
}

export function uploadScriptSource(projectId: string, file: File): Promise<ScriptDocumentRead> {
  const body = new FormData()
  body.append('file', file)
  return apiRequest<ScriptDocumentRead>(`/projects/${projectId}/sources/document`, { method: 'POST', body })
}

export function runScriptStage(projectId: string, stage: 'analyze' | 'plan' | 'generate'): Promise<TaskRead> {
  return apiRequest<TaskRead>(`${endpoint(projectId)}/commands/run/${stage}`, {
    method: 'POST', headers: { 'Idempotency-Key': `script-${stage}-${crypto.randomUUID()}` },
  })
}

export function saveLocalizedScript(projectId: string, artifactId: string, scriptText: string): Promise<ScriptStageRead> {
  return apiRequest<ScriptStageRead>(`${endpoint(projectId)}/commands/save`, {
    method: 'POST', body: JSON.stringify({ expected_artifact_id: artifactId, script_text: scriptText }),
  })
}

export function exportLocalizedScript(projectId: string): Promise<ScriptStageRead> {
  return apiRequest<ScriptStageRead>(`${endpoint(projectId)}/commands/export`, { method: 'POST' })
}
