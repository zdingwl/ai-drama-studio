import { apiRequest } from '@/lib/api'

import type { TaskRead } from './types'

export type TargetScriptResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'

export interface TargetScriptDialogueLine {
  utterance_id: string
  utterance_number: number
  source_start_us: number
  source_end_us: number
  source_text: string
  source_language: string | null
  target_character_id: string | null
  translation_text: string
  localization_text: string
  final_target_dialogue: string
  localization_notes: string[]
}

export interface TargetScriptEpisode {
  episode_id: string
  episode_order: number
  dialogue: TargetScriptDialogueLine[]
}

export interface ReplicaTargetScriptContent {
  schema_version: string
  title: string
  target_language: string
  target_region: string
  source_snapshot_artifact_id: string
  adaptation_plan_artifact_id: string
  target_bible_artifact_id: string
  episodes: TargetScriptEpisode[]
}

export interface ReplicaTargetScriptRead {
  project_id: string
  status: TargetScriptResultStatus
  artifact_id: string | null
  revision: number | null
  input_fingerprint: string | null
  content: ReplicaTargetScriptContent | null
  provenance?: unknown
}

export function getReplicaTargetScript(projectId: string): Promise<ReplicaTargetScriptRead> {
  return apiRequest<ReplicaTargetScriptRead>(`/projects/${projectId}/target-script`, { cache: 'no-store' })
}

export function startReplicaTargetScript(projectId: string, idempotencyKey: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/target-script`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}
