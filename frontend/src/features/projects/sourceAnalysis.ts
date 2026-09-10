import { apiRequest } from '@/lib/api'

export type SourceAnalysisState = 'NOT_READY' | 'RUNNING' | 'READY' | 'NEEDS_REFRESH' | 'FAILED'
export type StoryboardDraftStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'

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
  episode_id: string
  shot_anchor_id: string
  shot_number: number
  start_us: number
  end_us: number
  duration_us: number
  action_summary: string
  visual_description: string
  shot_size: string
  composition: string
  angle_or_type: string
  movement: string
  focal_length_dof: string
  thumbnail_url: string
  reference_clip_url: string
  dialogues: SourceScriptDialogue[]
}

export interface SourceScriptScene {
  scene_number: number
  episode_id: string
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

export interface SourceAssetShotRef {
  episode_id: string
  episode_order: number
  shot_anchor_id: string
  shot_number: number
  thumbnail_url: string
  reference_clip_url: string
}

export interface SourceCharacterAssetCard {
  id: string
  name: string
  related_shots: SourceAssetShotRef[]
  dialogue_count: number
  source_facts: string[]
  representative_frame: SourceAssetShotRef | null
}

export interface SourceSceneAssetCard {
  id: string
  name: string
  shot_ranges: string[]
  related_shots: SourceAssetShotRef[]
  source_facts: string[]
  representative_frame: SourceAssetShotRef | null
}

export interface SourcePropAssetCard {
  id: string
  name: string
  related_shots: SourceAssetShotRef[]
  source_facts: string[]
  representative_frame: SourceAssetShotRef | null
}

export interface SourceScriptRead {
  project_id: string
  state: SourceAnalysisState
  title: string
  scenes: SourceScriptScene[]
  characters: SourceScriptEntity[]
  props: SourceScriptEntity[]
  character_assets: SourceCharacterAssetCard[]
  scene_assets: SourceSceneAssetCard[]
  prop_assets: SourcePropAssetCard[]
}

export interface StoryboardShotOverride {
  shot_anchor_id: string
  visual_description: string
  shot_size: string
  composition: string
  angle_or_type: string
  movement: string
  focal_length_dof: string
}

export interface StoryboardDraftRead {
  project_id: string
  status: StoryboardDraftStatus
  revision: number | null
  base_source_current: boolean
  overrides: StoryboardShotOverride[]
}

export interface StoryboardShotEditPayload {
  expected_revision: number | null
  shot_anchor_id: string
  reset_to_source?: boolean
  visual_description?: string
  shot_size?: string
  composition?: string
  angle_or_type?: string
  movement?: string
  focal_length_dof?: string
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

export function getStoryboardDraft(projectId: string): Promise<StoryboardDraftRead> {
  return apiRequest<StoryboardDraftRead>(`/projects/${projectId}/storyboard-draft`, { cache: 'no-store' })
}

export function editStoryboardShot(
  projectId: string,
  payload: StoryboardShotEditPayload,
): Promise<StoryboardDraftRead> {
  return apiRequest<StoryboardDraftRead>(`/projects/${projectId}/storyboard-draft/commands/edit-shot`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
