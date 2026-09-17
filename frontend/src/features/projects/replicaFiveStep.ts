import { apiRequest } from '@/lib/api'
import type { TaskRead } from './types'

export type PipelineResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'
export type CandidateStatus = 'NEEDS_REVIEW' | 'ACCEPTED' | 'REJECTED' | 'SUPERSEDED'

export interface LocalizedDialogue {
  utterance_id: string
  utterance_number: number
  source_text: string
  target_character_id: string | null
  target_dialogue: string
  target_dialogue_zh: string
}

export interface LocalizedShotDialogue {
  utterance_id: string
  utterance_number: number
  target_character_id: string | null
  target_dialogue: string
  target_dialogue_zh: string
}

export interface LocalizedStoryboardShot {
  storyboard_shot_id: string
  episode_id: string
  episode_order: number
  source_shot_anchor_id: string
  shot_number: number
  start_us: number
  end_us: number
  duration_us: number
  output_ratio: string
  source_visual_description: string
  localized_visual_description_zh: string
  camera_description_zh: string
  target_character_ids: string[]
  target_scene_ids: string[]
  target_prop_ids: string[]
  dialogue: LocalizedShotDialogue[]
  sound_effects: string[]
  ambience: string[]
}

export interface LocalizedStoryboardContent {
  source_snapshot_artifact_id: string
  target_language: string
  target_region: string
  characters: Array<{ source_character_id: string; target_character_id: string; source_name: string; display_name: string; identity_description_zh: string; appearance_description_zh: string }>
  scenes: Array<{ source_scene_id: string; target_scene_id: string; source_name: string; display_name: string; setting_description_zh: string; visual_description_zh: string }>
  props: Array<{ source_prop_id: string; target_prop_id: string; source_name: string; display_name: string; function_description_zh: string; visual_description_zh: string }>
  dialogue: LocalizedDialogue[]
  shots: LocalizedStoryboardShot[]
}

export interface LocalizedStoryboardRead {
  project_id: string
  status: PipelineResultStatus
  artifact_id: string | null
  revision: number | null
  content: LocalizedStoryboardContent | null
}

export interface LocalizedStoryboardCandidate {
  id: string
  project_id: string
  generation_sequence: number
  review_status: CandidateStatus
  review_reason: string | null
  content: LocalizedStoryboardContent
}

export interface ReferenceMedia {
  reference_id: string
  role: string
  uri: string
  mime_type: string
  sha256: string
  width: number
  height: number
  storage_relpath: string | null
}

export interface AssetImageEntity {
  target_asset_id: string
  target_asset_revision: number
  asset_type: 'CHARACTER' | 'SCENE' | 'PROP'
  target_entity_id: string
  display_name: string
  review_description_zh: string
  image_prompt: string
  negative_prompt: string
  prompt_review_zh: string | null
  image_model_id: string | null
  prompt_skill_id: string | null
  prompt_skill_version: string | null
  prompt_contract: string | null
  reference_media: ReferenceMedia[]
}

export interface AssetImagesContent {
  target_storyboard_artifact_id: string
  target_language: string
  target_region: string
  visual_style: string
  assets: AssetImageEntity[]
}

export interface AssetImagesRead {
  project_id: string
  status: PipelineResultStatus
  artifact_id: string | null
  revision: number | null
  content: AssetImagesContent | null
}

export interface AssetWorkspaceGeneration {
  generation_id: string
  task_id: string
  created_at: string
  reference_media: ReferenceMedia[]
}

export interface AssetWorkspaceEntity {
  target_asset_id: string
  asset_type: 'CHARACTER' | 'SCENE' | 'PROP'
  target_entity_id: string
  display_name: string
  review_description_zh: string
  width: number
  height: number
  image_prompt: string | null
  negative_prompt: string
  prompt_review_zh: string | null
  image_model_id: string | null
  prompt_skill_id: string | null
  prompt_skill_version: string | null
  prompt_contract: string | null
  prompt_status: 'NOT_STARTED' | 'QUEUED' | 'GENERATING' | 'READY' | 'FAILED'
  image_status: 'NOT_STARTED' | 'QUEUED' | 'GENERATING' | 'READY' | 'FAILED'
  last_error: string | null
  active_generation_id: string | null
  generations: AssetWorkspaceGeneration[]
}

export interface AssetWorkspaceRead {
  project_id: string
  status: 'EMPTY' | 'READY'
  revision: number | null
  content: { target_storyboard_artifact_id: string; target_language: string; target_region: string; visual_style: string; assets: AssetWorkspaceEntity[] } | null
}

export interface AssetImageCandidate {
  id: string
  project_id: string
  generation_sequence: number
  review_status: CandidateStatus
  review_reason: string | null
  content: AssetImagesContent
}

export interface H3ReferenceCondition {
  picture_index: number
  target_asset_id: string
  target_entity_id: string
  asset_type: string
  reference_id: string
  reference_role: string
  reference_uri: string
  reference_sha256: string
}

export interface H3PromptSegment {
  generation_segment_id: string
  episode_id: string
  episode_order: number
  segment_number: number
  start_us: number
  end_us: number
  duration_us: number
  output_ratio: string
  generation_prompt: string
  negative_prompt: string
  prompt_skill_id: string | null
  prompt_skill_version: string | null
  prompt_contract: string | null
  model_id: string | null
  review_prompt_zh: string | null
  reference_conditions: H3ReferenceCondition[]
  dialogue_refs: Array<{ utterance_id: string; utterance_number: number; final_target_dialogue: string; target_dialogue_zh: string | null }>
  ambience: string[]
  sound_effects: string[]
}

export interface H3PromptsRead {
  project_id: string
  status: PipelineResultStatus
  artifact_id: string | null
  revision: number | null
  content: { target_storyboard_artifact_id: string; target_assets_artifact_id: string; segments: H3PromptSegment[] } | null
  provenance: { professional_skill_id: string; professional_skill_version: string; model_id: string; prompt_contract: string; prompt_provider: string; prompt_model: string } | null
}

function key(prefix: string): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`
  return `${prefix}-${suffix}`.slice(0, 128)
}

export const getLocalizedStoryboard = (projectId: string) => apiRequest<LocalizedStoryboardRead>(`/projects/${projectId}/localized-storyboard`, { cache: 'no-store' })
export const listLocalizedStoryboardCandidates = (projectId: string) => apiRequest<LocalizedStoryboardCandidate[]>(`/projects/${projectId}/localized-storyboard/candidates`, { cache: 'no-store' })
export const startLocalizedStoryboard = (projectId: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/localized-storyboard`, { method: 'POST', headers: { 'Idempotency-Key': key('localized-storyboard') } })
export const reviewLocalizedStoryboard = (projectId: string, candidate: LocalizedStoryboardCandidate, accept: boolean, reason: string) => apiRequest<LocalizedStoryboardRead | LocalizedStoryboardCandidate>(`/projects/${projectId}/localized-storyboard/candidates/${candidate.id}/commands/${accept ? 'accept' : 'reject'}`, {
  method: 'POST',
  body: JSON.stringify({ expected_upstream_artifact_id: candidate.content.source_snapshot_artifact_id, expected_generation_sequence: candidate.generation_sequence, reason }),
})
export const updateLocalizedStoryboardShot = (projectId: string, payload: {
  candidate_id: string | null
  expected_current_artifact_id: string | null
  expected_source_snapshot_artifact_id: string
  storyboard_shot_id: string
  localized_visual_description_zh: string
  camera_description_zh: string
  dialogue: Array<{ utterance_id: string; target_dialogue: string; target_dialogue_zh: string }>
}) => apiRequest<LocalizedStoryboardCandidate>(`/projects/${projectId}/localized-storyboard/commands/update-shot`, {
  method: 'POST',
  body: JSON.stringify(payload),
})

export const getAssetImages = (projectId: string) => apiRequest<AssetImagesRead>(`/projects/${projectId}/asset-images`, { cache: 'no-store' })
export const getAssetWorkspace = (projectId: string) => apiRequest<AssetWorkspaceRead>(`/projects/${projectId}/asset-workspace`, { cache: 'no-store' })
export const extractAssetWorkspace = (projectId: string) => apiRequest<AssetWorkspaceRead>(`/projects/${projectId}/asset-workspace/commands/extract`, { method: 'POST' })
export const generateAssetPrompts = (projectId: string, targetAssetIds: string[]) => apiRequest<TaskRead>(`/projects/${projectId}/asset-workspace/commands/prompts`, { method: 'POST', headers: { 'Idempotency-Key': key('asset-prompts') }, body: JSON.stringify({ target_asset_ids: targetAssetIds }) })
export const generateAssetImages = (projectId: string, targetAssetIds: string[]) => apiRequest<TaskRead>(`/projects/${projectId}/asset-workspace/commands/images`, { method: 'POST', headers: { 'Idempotency-Key': key('asset-images-queue') }, body: JSON.stringify({ target_asset_ids: targetAssetIds }) })
export const listAssetImageCandidates = (projectId: string) => apiRequest<AssetImageCandidate[]>(`/projects/${projectId}/asset-images/candidates`, { cache: 'no-store' })
export const startAssetImages = (projectId: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/asset-images`, { method: 'POST', headers: { 'Idempotency-Key': key('asset-images') } })
export const regenerateAssetImages = (projectId: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/asset-images/regenerate`, { method: 'POST', headers: { 'Idempotency-Key': key('asset-images-regenerate') } })
export const reviewAssetImages = (projectId: string, candidate: AssetImageCandidate, accept: boolean, reason: string) => apiRequest<AssetImagesRead | AssetImageCandidate>(`/projects/${projectId}/asset-images/candidates/${candidate.id}/commands/${accept ? 'accept' : 'reject'}`, {
  method: 'POST',
  body: JSON.stringify({ expected_upstream_artifact_id: candidate.content.target_storyboard_artifact_id, expected_generation_sequence: candidate.generation_sequence, reason }),
})

export const getH3Prompts = (projectId: string) => apiRequest<H3PromptsRead>(`/projects/${projectId}/h3-prompts`, { cache: 'no-store' })
export const startH3Prompts = (projectId: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/h3-prompts`, { method: 'POST', headers: { 'Idempotency-Key': key('h3-prompts') } })
