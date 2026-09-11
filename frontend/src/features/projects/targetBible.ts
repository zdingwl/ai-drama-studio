import { apiRequest } from '@/lib/api'

import type { TaskRead } from './types'

export type TargetBibleResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'

export interface PreservationLock {
  lock_id: string
  category: string
  source_summary: string
  source_refs: string[]
  constraint: string
}

export interface LocalizationDecision {
  decision_id: string
  category: string
  source_ref: string | null
  source_value: string
  target_value: string
  reason: string
}

export interface ReplicaAdaptationPlanContent {
  schema_version: string
  title: string
  target_language: string
  target_region: string
  source_snapshot_artifact_id: string
  preservation_locks: PreservationLock[]
  localization_decisions: LocalizationDecision[]
  dialogue_localization_strategy: string[]
  scene_strategy: string
  visual_style: string
}

export interface ReplicaTargetCharacter {
  target_character_id: string
  source_character_id: string
  source_display_name: string
  display_name: string
  localized_identity: string
  appearance_direction: string
  personality_constraints: string[]
  continuity_rules: string[]
}

export interface ReplicaTargetScene {
  target_scene_id: string
  source_scene_id: string
  source_display_name: string
  display_name: string
  localized_setting: string
  visual_direction: string
  continuity_rules: string[]
}

export interface ReplicaTargetProp {
  target_prop_id: string
  source_prop_id: string
  source_display_name: string
  display_name: string
  localized_form: string
  continuity_rules: string[]
}

export interface ReplicaTargetBibleContent {
  schema_version: string
  title: string
  target_language: string
  target_region: string
  source_snapshot_artifact_id: string
  target_world: {
    setting_summary: string
    cultural_context: string
    social_context: string
    localization_principles: string[]
  }
  characters: ReplicaTargetCharacter[]
  scenes: ReplicaTargetScene[]
  props: ReplicaTargetProp[]
  visual_style: string
  continuity_rules: string[]
  dialogue_style_rules: string[]
  adaptation_summary: string
}

export interface ReplicaTargetArtifactRead<T> {
  status: TargetBibleResultStatus
  artifact_id: string | null
  revision: number | null
  input_fingerprint: string | null
  content: T | null
  provenance?: unknown
}

export interface ReplicaTargetBibleRead {
  project_id: string
  status: TargetBibleResultStatus
  source_snapshot_artifact_id: string | null
  source_snapshot_revision: number | null
  adaptation_plan: ReplicaTargetArtifactRead<ReplicaAdaptationPlanContent>
  target_bible: ReplicaTargetArtifactRead<ReplicaTargetBibleContent>
}

export function getReplicaTargetBible(projectId: string): Promise<ReplicaTargetBibleRead> {
  return apiRequest<ReplicaTargetBibleRead>(`/projects/${projectId}/target-bible`, { cache: 'no-store' })
}

export function startReplicaTargetBible(projectId: string, idempotencyKey: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/target-bible`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}
