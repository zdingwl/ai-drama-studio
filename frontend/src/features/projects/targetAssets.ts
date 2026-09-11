import { apiRequest } from '@/lib/api'

import type { TaskRead } from './types'

export type TargetAssetsResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'
export type CandidateReviewStatus = 'NEEDS_REVIEW' | 'ACCEPTED' | 'REJECTED' | 'SUPERSEDED'
export type TargetAssetType = 'CHARACTER' | 'SCENE' | 'PROP'

export interface TargetCharacterAsset {
  target_asset_id: string
  target_asset_revision: number
  asset_type: 'CHARACTER'
  target_entity_id: string
  target_character_id: string
  display_name: string
  asset_fingerprint: string
  identity_direction: string
  demographic_direction: string
  face_direction: string
  hair_direction: string
  body_direction: string
  wardrobe_baseline: string
  signature_visual_features: string[]
  continuity_constraints: string[]
  generation_guidance: string[]
  negative_constraints: string[]
  reference_media: unknown[]
}

export interface TargetSceneAsset {
  target_asset_id: string
  target_asset_revision: number
  asset_type: 'SCENE'
  target_entity_id: string
  target_scene_id: string
  display_name: string
  asset_fingerprint: string
  spatial_identity: string
  layout: string
  architecture_style: string
  interior_exterior_style: string
  materials_palette: string[]
  fixed_landmarks: string[]
  lighting_baseline: string
  time_of_day_baseline: string
  continuity_constraints: string[]
  generation_guidance: string[]
  negative_constraints: string[]
  reference_media: unknown[]
}

export interface TargetPropAsset {
  target_asset_id: string
  target_asset_revision: number
  asset_type: 'PROP'
  target_entity_id: string
  target_prop_id: string
  display_name: string
  asset_fingerprint: string
  functional_identity: string
  visual_form: string
  materials: string[]
  color_palette: string[]
  scale_reference: string
  signature_visual_features: string[]
  continuity_constraints: string[]
  generation_guidance: string[]
  negative_constraints: string[]
  reference_media: unknown[]
}

export interface ReplicaTargetAssetsContent {
  schema_version: string
  title: string
  target_bible_artifact_id: string
  target_language: string
  target_region: string
  visual_style: string
  characters: TargetCharacterAsset[]
  scenes: TargetSceneAsset[]
  props: TargetPropAsset[]
}

export interface ReplicaTargetAssetsRead {
  project_id: string
  status: TargetAssetsResultStatus
  artifact_id: string | null
  revision: number | null
  input_fingerprint: string | null
  content: ReplicaTargetAssetsContent | null
  provenance?: unknown
}

export interface TargetAssetsCandidateRead {
  id: string
  project_id: string
  target_bible_artifact_id: string
  base_target_assets_artifact_id: string | null
  generated_by_task_id: string | null
  generation_sequence: number
  input_fingerprint: string
  schema_version: string
  review_status: CandidateReviewStatus
  review_reason: string | null
  reviewed_at: string | null
  created_at: string
  content: ReplicaTargetAssetsContent
  provenance?: unknown
}

export interface TargetAssetsReviewCommand {
  expected_target_bible_artifact_id: string
  expected_generation_sequence: number
  reason: string
}

export function getReplicaTargetAssets(projectId: string): Promise<ReplicaTargetAssetsRead> {
  return apiRequest<ReplicaTargetAssetsRead>(`/projects/${projectId}/target-assets`, { cache: 'no-store' })
}

export function listReplicaTargetAssetCandidates(projectId: string): Promise<TargetAssetsCandidateRead[]> {
  return apiRequest<TargetAssetsCandidateRead[]>(`/projects/${projectId}/target-assets/candidates`, { cache: 'no-store' })
}

export function startReplicaTargetAssets(projectId: string, idempotencyKey: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/target-assets`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

export function regenerateReplicaTargetAssets(projectId: string, idempotencyKey: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/target-assets/regenerate`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

export function acceptReplicaTargetAssets(
  projectId: string,
  candidateId: string,
  payload: TargetAssetsReviewCommand,
): Promise<ReplicaTargetAssetsRead> {
  return apiRequest<ReplicaTargetAssetsRead>(
    `/projects/${projectId}/target-assets/candidates/${candidateId}/commands/accept`,
    { method: 'POST', body: JSON.stringify(payload) },
  )
}

export function rejectReplicaTargetAssets(
  projectId: string,
  candidateId: string,
  payload: TargetAssetsReviewCommand,
): Promise<TargetAssetsCandidateRead> {
  return apiRequest<TargetAssetsCandidateRead>(
    `/projects/${projectId}/target-assets/candidates/${candidateId}/commands/reject`,
    { method: 'POST', body: JSON.stringify(payload) },
  )
}
