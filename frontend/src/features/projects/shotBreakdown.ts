import { apiRequest } from '@/lib/api'

import type { TaskRead } from './types'

export type ShotBreakdownResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'
export type DialogueDelivery = 'DIALOGUE' | 'VOICEOVER' | 'OFFSCREEN' | 'UNKNOWN'

export interface CameraLanguage {
  shot_size: string
  composition: string
  angle_or_type: string
  movement: string
  focal_length_dof: string
}

export interface BoundSubjectRef {
  id: string
  label: string
}

export interface CanonicalDialogueBinding {
  utterance_id: string
  utterance_number: number
  utterance_start_us: number
  utterance_end_us: number
  overlap_start_us: number
  overlap_end_us: number
  text: string
  language: string | null
  delivery: DialogueDelivery
}

export interface SourceShotBindings {
  characters: BoundSubjectRef[]
  scenes: BoundSubjectRef[]
  props: BoundSubjectRef[]
  unresolved_subject_notes: string[]
}

export interface SourceShotFact {
  shot_anchor_id: string
  shot_number: number
  start_us: number
  end_us: number
  duration_us: number
  visual_description: string
  camera_language: CameraLanguage
  bindings: SourceShotBindings
  dialogue: CanonicalDialogueBinding[]
  sound_effects: string[]
  ambience: string[]
  visual_text_evidence_ids: string[]
}

export interface SourceShotFactsEpisode {
  episode_id: string
  episode_order: number
  source_filename: string
  shots: SourceShotFact[]
}

export interface SourceShotFactsContent {
  schema_version: string
  title: string
  episodes: SourceShotFactsEpisode[]
}

export interface ShotBreakdownProvenance {
  source_video_artifact_id: string
  source_video_fingerprint: string
  source_bible_artifact_id: string
  source_bible_fingerprint: string
  shot_anchors_artifact_id: string
  shot_anchors_fingerprint: string
  source_dialogue_artifact_id: string
  source_dialogue_fingerprint: string
  episode_inputs: Array<{
    episode_id: string
    shot_boundary_set_id: string
    shot_boundary_fingerprint: string
    source_evidence_set_id: string
    source_evidence_fingerprint: string
  }>
  provider_jobs: Array<{
    provider_job_id: string
    episode_id: string
    provider: string
    model: string
    payload_fingerprint: string
    remote_job_id: string | null
  }>
  provider: string | null
  model: string | null
  prompt_version: string
  schema_version: string
  professional_skill_id: string
  professional_skill_version: string | null
  source_truth_contract: string
  generated_by_task_id: string | null
  supersedes_artifact_id: string | null
}

export interface ShotBreakdownRead {
  project_id: string
  status: ShotBreakdownResultStatus
  artifact_id: string | null
  revision: number | null
  input_fingerprint: string | null
  content: SourceShotFactsContent | null
  provenance: ShotBreakdownProvenance | null
}

export interface ShotBreakdownRevisionSummary {
  artifact_id: string
  revision: number
  status: ShotBreakdownResultStatus
  input_fingerprint: string
  created_at: string
  supersedes_artifact_id: string | null
}

export function getShotBreakdown(projectId: string): Promise<ShotBreakdownRead> {
  return apiRequest<ShotBreakdownRead>(`/projects/${projectId}/shot-breakdown`)
}

export function listShotBreakdownRevisions(projectId: string): Promise<ShotBreakdownRevisionSummary[]> {
  return apiRequest<ShotBreakdownRevisionSummary[]>(`/projects/${projectId}/shot-breakdown/revisions`)
}

export function startShotBreakdown(projectId: string, idempotencyKey: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/shot-breakdown`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}
