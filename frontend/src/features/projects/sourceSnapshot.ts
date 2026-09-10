import { apiRequest } from '@/lib/api'

export type SourceVideoSnapshotStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'

export interface FrozenArtifactRef {
  artifact_type: string
  artifact_id: string
  revision: number
  input_fingerprint: string
}

export interface SourceVideoSnapshotEpisode {
  episode_id: string
  source_asset_id: string
  episode_order: number
  source_filename: string
  source_asset_sha256: string
  duration_us: number
  width: number
  height: number
  codec_name: string
  avg_frame_rate: string
  has_audio: boolean
  shot_boundary_set_id: string
  shot_boundary_fingerprint: string
  source_evidence_set_id: string
  source_evidence_fingerprint: string
  shot_anchors: Array<{
    shot_anchor_id: string
    shot_number: number
    start_us: number
    end_us: number
    duration_us: number
  }>
  canonical_dialogue: Array<{
    utterance_id: string
    utterance_number: number
    start_us: number
    end_us: number
    text: string
    language: string | null
  }>
  canonical_visual_text: Array<{
    span_id: string
    span_number: number
    start_us: number
    end_us: number
    text: string
    confidence: number | null
  }>
}

interface EntityCollection {
  entities: unknown[]
}

export interface SourceVideoSnapshotContent {
  schema_version: string
  title: string
  source_truth_contract: string
  frozen_artifacts: FrozenArtifactRef[]
  episodes: SourceVideoSnapshotEpisode[]
  source_bible: Record<string, unknown>
  source_shot_facts: Record<string, unknown>
  source_characters: EntityCollection
  source_speakers: EntityCollection
  source_scenes: EntityCollection
  source_props: EntityCollection
}

export interface SourceVideoSnapshotProvenance {
  snapshot_contract: string
  schema_version: string
  source_truth_contract: string
  professional_skill_id: string
  professional_skill_version: string
  publication_mode: 'DETERMINISTIC_FREEZE'
  source_chain_fingerprint: string
  frozen_artifacts: FrozenArtifactRef[]
  episode_inputs: Array<{
    episode_id: string
    source_asset_id: string
    source_asset_sha256: string
    shot_boundary_set_id: string
    shot_boundary_fingerprint: string
    source_evidence_set_id: string
    source_evidence_fingerprint: string
  }>
  provider_jobs: unknown[]
  supersedes_artifact_id: string | null
}

export interface SourceVideoSnapshotRead {
  project_id: string
  status: SourceVideoSnapshotStatus
  artifact_id: string | null
  revision: number | null
  input_fingerprint: string | null
  content: SourceVideoSnapshotContent | null
  provenance: SourceVideoSnapshotProvenance | null
}

export interface SourceVideoSnapshotRevisionSummary {
  artifact_id: string
  revision: number
  status: SourceVideoSnapshotStatus
  input_fingerprint: string
  source_chain_fingerprint: string
  created_at: string
  supersedes_artifact_id: string | null
}

export function getSourceVideoSnapshot(projectId: string): Promise<SourceVideoSnapshotRead> {
  return apiRequest<SourceVideoSnapshotRead>(`/projects/${projectId}/source-video-snapshot`, { cache: 'no-store' })
}

export function listSourceVideoSnapshotRevisions(projectId: string): Promise<SourceVideoSnapshotRevisionSummary[]> {
  return apiRequest<SourceVideoSnapshotRevisionSummary[]>(`/projects/${projectId}/source-video-snapshot/revisions`, { cache: 'no-store' })
}

export function finalizeSourceVideoSnapshot(projectId: string): Promise<SourceVideoSnapshotRead> {
  return apiRequest<SourceVideoSnapshotRead>(`/projects/${projectId}/commands/source-video-snapshot`, {
    method: 'POST',
  })
}
