import { apiRequest } from '@/lib/api'

import type { TaskRead } from './types'

export type TargetAssetResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'
export type TargetAssetCandidateStatus = 'READY_FOR_REVIEW' | 'PUBLISHED' | 'REJECTED' | 'STALE'
export type TargetAssetKind = 'CHARACTER' | 'SCENE' | 'PROP'

export interface TargetAssetReference {
  reference_asset_id: string
  role: 'REFERENCE_SHEET'
  media_type: 'image/png' | 'image/jpeg'
  relative_path: string
  sha256: string
  size_bytes: number
  width: number
  height: number
  provider_job_id: string
  provider: string
  model: string
}

export interface TargetCharacterAsset {
  target_asset_id: string
  asset_kind: 'CHARACTER'
  asset_revision: number
  target_character_id: string
  display_name: string
  localized_identity: string
  appearance_direction: string
  face_identity: string
  hair_identity: string
  body_silhouette: string
  wardrobe_baseline: string
  signature_features: string[]
  palette_materials: string[]
  continuity_constraints: string[]
  generation_guidance: string[]
  negative_constraints: string[]
  reference_assets: TargetAssetReference[]
}

export interface TargetSceneAsset {
  target_asset_id: string
  asset_kind: 'SCENE'
  asset_revision: number
  target_scene_id: string
  display_name: string
  localized_setting: string
  visual_direction: string
  spatial_identity: string
  layout: string
  architecture_style: string
  materials_palette: string[]
  fixed_landmarks: string[]
  lighting_baseline: string
  time_of_day_baseline: string
  continuity_constraints: string[]
  generation_guidance: string[]
  negative_constraints: string[]
  reference_assets: TargetAssetReference[]
}

export interface TargetPropAsset {
  target_asset_id: string
  asset_kind: 'PROP'
  asset_revision: number
  target_prop_id: string
  display_name: string
  localized_form: string
  visual_form: string
  materials: string[]
  color_palette: string[]
  scale: string
  functional_identity: string
  signature_details: string[]
  continuity_constraints: string[]
  generation_guidance: string[]
  negative_constraints: string[]
  reference_assets: TargetAssetReference[]
}

export interface ReplicaTargetAssetsContent {
  schema_version: string
  title: string
  target_bible_artifact_id: string
  target_bible_revision: number
  target_language: string
  target_region: string
  visual_style: string
  global_continuity_constraints: string[]
  character_assets: TargetCharacterAsset[]
  scene_assets: TargetSceneAsset[]
  prop_assets: TargetPropAsset[]
}

export interface TargetAssetsCandidateRead {
  candidate_id: string
  status: TargetAssetCandidateStatus
  target_bible_artifact_id: string
  target_bible_revision: number
  input_fingerprint: string
  scope_target_asset_ids: string[]
  content: ReplicaTargetAssetsContent
  provenance: unknown
  published_artifact_id: string | null
  created_at: string
  approved_at: string | null
}

export interface ReplicaTargetAssetsRead {
  project_id: string
  status: TargetAssetResultStatus
  artifact_id: string | null
  revision: number | null
  input_fingerprint: string | null
  content: ReplicaTargetAssetsContent | null
  provenance?: unknown
  latest_candidate: TargetAssetsCandidateRead | null
}

export function getReplicaTargetAssets(projectId: string): Promise<ReplicaTargetAssetsRead> {
  return apiRequest<ReplicaTargetAssetsRead>(`/projects/${projectId}/target-assets`, { cache: 'no-store' })
}

export function startReplicaTargetAssets(
  projectId: string,
  idempotencyKey: string,
  targetAssetIds: string[] = [],
): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/target-assets`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
    body: JSON.stringify({ target_asset_ids: targetAssetIds }),
  })
}

export function approveReplicaTargetAssets(
  projectId: string,
  candidateId: string,
  idempotencyKey: string,
): Promise<ReplicaTargetAssetsRead> {
  return apiRequest<ReplicaTargetAssetsRead>(`/projects/${projectId}/commands/target-assets/${candidateId}/approve`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

export function targetAssetReferenceUrl(projectId: string, referenceAssetId: string): string {
  const base = import.meta.env.VITE_API_BASE_URL ?? '/api/v3'
  return `${base}/projects/${projectId}/target-assets/references/${encodeURIComponent(referenceAssetId)}`
}
