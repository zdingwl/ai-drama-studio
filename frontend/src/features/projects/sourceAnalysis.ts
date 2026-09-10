import { apiRequest } from '@/lib/api'

export type SourceAnalysisState = 'NOT_READY' | 'RUNNING' | 'READY' | 'NEEDS_REFRESH' | 'FAILED'

export interface SourceAnalysisStatusRead {
  project_id: string
  state: SourceAnalysisState
  progress_percent: number
  current_stage: string | null
  task_id: string | null
  can_retry: boolean
  message: string
}

export interface SourceScriptDialogue {
  utterance_id: string
  utterance_number: number
  start_us: number
  end_us: number
  speaker_id: string | null
  speaker_name: string
  text: string
  delivery: string
}

export interface SourceScriptShot {
  shot_anchor_id: string
  shot_number: number
  start_us: number
  end_us: number
  duration_us: number
  visual_description: string
  shot_size: string
  composition: string
  angle_or_type: string
  movement: string
  focal_length_dof: string
  dialogues: SourceScriptDialogue[]
}

export interface SourceScriptScene {
  scene_number: number
  scene_id: string | null
  scene_name: string
  start_us: number
  end_us: number
  character_names: string[]
  shots: SourceScriptShot[]
}

export interface SourceScriptEntity {
  id: string
  name: string
}

export interface SourceScriptRead {
  project_id: string
  state: SourceAnalysisState
  title: string
  scenes: SourceScriptScene[]
  characters: SourceScriptEntity[]
  props: SourceScriptEntity[]
}

export function getSourceAnalysisStatus(projectId: string): Promise<SourceAnalysisStatusRead> {
  return apiRequest<SourceAnalysisStatusRead>(`/projects/${projectId}/source-analysis`, { cache: 'no-store' })
}

export function startSourceAnalysis(projectId: string, idempotencyKey: string): Promise<SourceAnalysisStatusRead> {
  return apiRequest<SourceAnalysisStatusRead>(`/projects/${projectId}/commands/source-analysis`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

export function getSourceScript(projectId: string): Promise<SourceScriptRead> {
  return apiRequest<SourceScriptRead>(`/projects/${projectId}/source-script`, { cache: 'no-store' })
}
