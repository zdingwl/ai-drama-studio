import { apiRequest } from '@/lib/api'
import type { TaskRead } from './types'

export interface ScriptToDramaSource {
  project_id: string
  document_id: string | null
  revision: number | null
  filename: string | null
  text: string | null
}

export interface PreproductionStage {
  status: 'NOT_BUILT' | 'CURRENT' | 'STALE'
  artifact_id: string | null
  revision: number | null
  content: Record<string, unknown> | null
}

export interface ScriptToDramaState {
  project_id: string
  analysis: PreproductionStage
  world: PreproductionStage
  assets: PreproductionStage
  storyboard: PreproductionStage
  asset_images: PreproductionStage
  prompts: PreproductionStage
  generated_video: PreproductionStage
  selection: PreproductionStage
  final_output: PreproductionStage
  video_runtime_status: string
}

const endpoint = (projectId: string) => `/projects/${projectId}/script-to-drama`

export function getDramaSource(projectId: string): Promise<ScriptToDramaSource> {
  return apiRequest<ScriptToDramaSource>(`${endpoint(projectId)}/source`, { cache: 'no-store' })
}

export function getDramaState(projectId: string): Promise<ScriptToDramaState> {
  return apiRequest<ScriptToDramaState>(`${endpoint(projectId)}/state`, { cache: 'no-store' })
}

export function pasteDramaSource(projectId: string, text: string) {
  return apiRequest(`${endpoint(projectId)}/paste`, {
    method: 'POST', body: JSON.stringify({ text }),
  })
}

export function uploadDramaSource(projectId: string, file: File) {
  const body = new FormData()
  body.append('file', file)
  return apiRequest(`/projects/${projectId}/sources/document`, { method: 'POST', body })
}

export function runDramaStage(projectId: string, stage: 'analyze' | 'world' | 'storyboard'): Promise<TaskRead> {
  return apiRequest<TaskRead>(`${endpoint(projectId)}/commands/run/${stage}`, {
    method: 'POST', headers: { 'Idempotency-Key': `script-to-drama-${stage}-${crypto.randomUUID()}` },
  })
}


export type ScriptToDramaProductionStage = 'asset_images' | 'prompts' | 'generate' | 'post'

export function runDramaProductionStage(projectId: string, stage: ScriptToDramaProductionStage): Promise<TaskRead> {
  return apiRequest<TaskRead>(`${endpoint(projectId)}/commands/production/${stage}`, {
    method: 'POST',
    headers: { 'Idempotency-Key': `script-to-drama-production-${stage}-${crypto.randomUUID()}` },
  })
}

export function acceptDramaGenerated(
  projectId: string,
  expectedGeneratedVideoArtifactId: string,
  selectedSegmentIds: string[],
  reason: string,
): Promise<ScriptToDramaState> {
  return apiRequest<ScriptToDramaState>(`${endpoint(projectId)}/commands/accept-generated`, {
    method: 'POST',
    body: JSON.stringify({
      expected_generated_video_artifact_id: expectedGeneratedVideoArtifactId,
      selected_segment_ids: selectedSegmentIds,
      reason,
    }),
  })
}

export function dramaMediaUrl(projectId: string, referenceId: string): string {
  return `/api/v3${endpoint(projectId)}/media/${encodeURIComponent(referenceId)}`
}
