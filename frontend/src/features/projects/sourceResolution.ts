import { apiRequest } from '@/lib/api'

import { getShotBreakdown } from './shotBreakdown'
import type { TaskRead } from './types'

export type SourceResolutionKind = 'CHARACTER' | 'SPEAKER' | 'SCENE' | 'PROP'
export type ResolutionStatus = 'RESOLVED' | 'UNKNOWN' | 'UNRESOLVED' | 'MANUAL_CONFIRMED'
export type SourceResolutionResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'
export type ManualResolutionOperation = 'CONFIRM' | 'MERGE' | 'SPLIT' | 'MARK_UNKNOWN' | 'REASSIGN'

export interface EvidenceRef {
  ref_type: string
  ref_id: string
  episode_id: string | null
  shot_anchor_id: string | null
  utterance_id: string | null
  note: string | null
}

export interface StableEntity {
  entity_id: string
  display_name: string
  aliases: string[]
  source_candidate_ids: string[]
  episode_ids: string[]
  shot_anchor_ids: string[]
  evidence_refs: EvidenceRef[]
  confidence: number
  resolution_status: ResolutionStatus
  notes: string[]
}

export interface CharacterEntity extends StableEntity {
  character_id: string
}

export interface CharacterObservation {
  shot_anchor_id: string
  source_candidate_id: string
  character_id: string | null
  resolution_status: ResolutionStatus
  reason: string | null
}

export interface CharacterResolutionContent {
  schema_version: string
  title: string
  entities: CharacterEntity[]
  observations: CharacterObservation[]
}

export interface SpeakerEntity extends StableEntity {
  speaker_id: string
  character_id: string | null
  utterance_ids: string[]
  source_candidate_character_ids: string[]
}

export interface SpeakerAttribution {
  episode_id: string
  utterance_id: string
  utterance_number: number
  start_us: number
  end_us: number
  text: string
  speaker_id: string | null
  resolution_status: ResolutionStatus
  reason: string | null
}

export interface SpeakerResolutionContent {
  schema_version: string
  title: string
  entities: SpeakerEntity[]
  attributions: SpeakerAttribution[]
}

export interface SceneEntity extends StableEntity {
  scene_id: string
  disambiguation_notes: string[]
}

export interface SceneAssignment {
  episode_id: string
  shot_anchor_id: string
  shot_number: number
  start_us: number
  end_us: number
  source_candidate_ids: string[]
  scene_id: string | null
  resolution_status: ResolutionStatus
  reason: string | null
}

export interface SceneResolutionContent {
  schema_version: string
  title: string
  entities: SceneEntity[]
  assignments: SceneAssignment[]
}

export interface PropEntity extends StableEntity {
  prop_id: string
  instance_notes: string[]
}

export interface PropObservation {
  shot_anchor_id: string
  source_candidate_id: string
  prop_id: string | null
  resolution_status: ResolutionStatus
  reason: string | null
}

export interface PropResolutionContent {
  schema_version: string
  title: string
  entities: PropEntity[]
  observations: PropObservation[]
}

export interface SourceResolutionProvenance {
  resolution_kind: SourceResolutionKind
  source_video_artifact_id: string
  source_video_fingerprint: string
  source_bible_artifact_id: string
  source_bible_fingerprint: string
  source_shot_facts_artifact_id: string
  source_shot_facts_fingerprint: string
  shot_anchors_artifact_id: string
  shot_anchors_fingerprint: string
  source_dialogue_artifact_id: string | null
  source_dialogue_fingerprint: string | null
  source_characters_artifact_id: string | null
  source_characters_fingerprint: string | null
  provider_jobs: Array<{
    provider_job_id: string
    provider: string
    model: string
    capability: string
    professional_skill_id: string
    payload_fingerprint: string
    remote_job_id: string | null
  }>
  provider: string | null
  model: string | null
  prompt_version: string
  schema_version: string
  professional_skill_id: string
  professional_skill_version: string
  source_truth_contract: string
  generated_by_task_id: string | null
  supersedes_artifact_id: string | null
  adjudication: {
    mode: 'MANUAL'
    operation: ManualResolutionOperation
    reason: string
  } | null
}

export interface ResolutionRead<T> {
  status: SourceResolutionResultStatus
  artifact_id: string | null
  revision: number | null
  input_fingerprint: string | null
  content: T | null
  provenance: SourceResolutionProvenance | null
}

export interface SourceResolutionRead {
  project_id: string
  characters: ResolutionRead<CharacterResolutionContent>
  speakers: ResolutionRead<SpeakerResolutionContent>
  scenes: ResolutionRead<SceneResolutionContent>
  props: ResolutionRead<PropResolutionContent>
}

export interface SourceResolutionRevisionSummary {
  resolution_kind: SourceResolutionKind
  artifact_id: string
  revision: number
  status: SourceResolutionResultStatus
  input_fingerprint: string
  created_at: string
  supersedes_artifact_id: string | null
  adjudication: {
    mode: 'MANUAL'
    operation: ManualResolutionOperation
    reason: string
  } | null
}

export interface ManualResolutionCommand {
  expected_revision: number
  operation: ManualResolutionOperation
  entity_ids?: string[]
  target_entity_id?: string | null
  reference_ids?: string[]
  split_groups?: string[][]
  character_id?: string | null
  display_name?: string | null
  reason: string
}

export function getSourceResolution(projectId: string): Promise<SourceResolutionRead> {
  return apiRequest<SourceResolutionRead>(`/projects/${projectId}/source-resolution`, { cache: 'no-store' })
}

export function listSourceResolutionRevisions(projectId: string): Promise<SourceResolutionRevisionSummary[]> {
  return apiRequest<SourceResolutionRevisionSummary[]>(`/projects/${projectId}/source-resolution/revisions`, { cache: 'no-store' })
}

export async function startSourceResolution(projectId: string, idempotencyKey: string): Promise<TaskRead> {
  const p8 = await getShotBreakdown(projectId)
  if (p8.status !== 'CURRENT') {
    const detail = p8.status === 'STALE'
      ? `P8 SOURCE_SHOT_FACTS 当前为 STALE${p8.revision == null ? '' : `（rev ${p8.revision}）`}`
      : 'P8 SOURCE_SHOT_FACTS 尚未生成'
    throw new Error(`P9 前置未就绪：${detail}。请先完成上方 P8 逐镜精细拉片并得到 CURRENT 结果。`)
  }
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/source-resolution`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

export function adjudicateSourceResolution(
  projectId: string,
  kind: SourceResolutionKind,
  payload: ManualResolutionCommand,
): Promise<SourceResolutionRead> {
  return apiRequest<SourceResolutionRead>(`/projects/${projectId}/source-resolution/${kind}/commands/adjudicate`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
