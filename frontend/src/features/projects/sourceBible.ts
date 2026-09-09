import { apiRequest } from '@/lib/api'

import type { TaskRead } from './types'

export type SourceBibleResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'

export interface TimeRange {
  start_us: number
  end_us: number
}

export interface MaterialBaseline {
  episode_id: string
  episode_order: number
  source_filename: string
  media_duration_us: number
  width: number
  height: number
  aspect_ratio: string
  avg_frame_rate: string
  codec_name: string
  has_audio: boolean
  effective_content_range: TimeRange | null
  visual_format_notes: string[]
}

export interface OverallAnalysis {
  story_summary: string
  story_background: string
  genre: string[]
  world_rules: string[]
  narrative_structure: string
  audiovisual_style: string
  rhythm_overview: string
}

export interface TimedStorySegment {
  segment_number: number
  time_range: TimeRange
  visual_description: string
  story_summary: string
  narrative_function: string
  dialogue_evidence_ids: string[]
  visual_text_evidence_ids: string[]
}

export interface CharacterProfile {
  character_id: string
  name: string
  story_function: string
  appearance_baseline: string
  states: Array<{ time_range: TimeRange; state: string }>
}

export interface CharacterRelationship {
  source_character_id: string
  target_character_id: string
  relationship: string
  change_summary: string | null
}

export interface SceneProfile {
  scene_id: string
  name: string
  time_ranges: TimeRange[]
  spatial_relationship: string
  environment_details: string
}

export interface PropProfile {
  prop_id: string
  name: string
  time_ranges: TimeRange[]
  appearance_state: string
  story_function: string
}

export interface StoryEvent {
  event_id: string
  time_range: TimeRange
  summary: string
  participants: string[]
  consequences: string
}

export interface EmotionBeat {
  time_range: TimeRange
  subject: string
  emotion: string
  change: string
}

export interface StoryBeat {
  beat_type: string
  time_range: TimeRange
  summary: string
  importance: number
}

export interface StorySkeleton {
  premise: string
  central_conflict: string
  beats: StoryBeat[]
}

export interface RhythmPhase {
  time_range: TimeRange
  pace: string
  scene_rhythm: string
  dialogue_reaction_rhythm: string
  cut_timing_notes: string
  key_beat_refs: string[]
  allowable_deviation_ms: number
}

export interface RhythmSkeleton {
  overall_pace: string
  phases: RhythmPhase[]
}

export interface SourceBibleEpisode {
  material_baseline: MaterialBaseline
  overall_analysis: OverallAnalysis
  timed_script: TimedStorySegment[]
  characters: CharacterProfile[]
  relationships: CharacterRelationship[]
  scenes: SceneProfile[]
  key_props: PropProfile[]
  story_events: StoryEvent[]
  emotion_timeline: EmotionBeat[]
  story_skeleton: StorySkeleton
  rhythm_skeleton: RhythmSkeleton
}

export interface SourceBibleContent {
  schema_version: string
  title: string
  episodes: SourceBibleEpisode[]
}

export interface SourceBibleProvenance {
  source_video_artifact_id: string
  source_video_fingerprint: string
  source_dialogue_artifact_id: string
  source_dialogue_fingerprint: string
  shot_anchors_artifact_id: string | null
  shot_anchors_fingerprint: string | null
  episode_evidence_sets: Array<{
    episode_id: string
    source_evidence_set_id: string
    evidence_fingerprint: string
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
  generated_by_task_id: string | null
  edit_parent_artifact_id: string | null
}

export interface SourceBibleRead {
  project_id: string
  status: SourceBibleResultStatus
  artifact_id: string | null
  revision: number | null
  input_fingerprint: string | null
  content: SourceBibleContent | null
  provenance: SourceBibleProvenance | null
  story_skeleton_artifact_id: string | null
  rhythm_skeleton_artifact_id: string | null
}

export interface SourceBibleRevisionSummary {
  artifact_id: string
  revision: number
  status: SourceBibleResultStatus
  input_fingerprint: string
  created_at: string
  edit_parent_artifact_id: string | null
}

export interface DoubaoRuntimeConfig {
  api_key: string
  model: string
  base_url: string
  request_timeout_seconds: number
  video_fps: number
}

export interface LocalQwenRuntimeConfig {
  api_key: string
  model: string
  base_url: string
}

export interface P7RuntimeConfig {
  doubao: DoubaoRuntimeConfig
  qwen38: LocalQwenRuntimeConfig
  qwen3_vl_8b: LocalQwenRuntimeConfig
  qwen_request_timeout_seconds: number
}

export function getP7RuntimeConfig(): Promise<P7RuntimeConfig> {
  return apiRequest<P7RuntimeConfig>('/source-understanding/runtime-config')
}

export function updateP7RuntimeConfig(payload: P7RuntimeConfig): Promise<P7RuntimeConfig> {
  return apiRequest<P7RuntimeConfig>('/source-understanding/runtime-config', {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function getSourceBible(projectId: string): Promise<SourceBibleRead> {
  return apiRequest<SourceBibleRead>(`/projects/${projectId}/source-bible`)
}

export function listSourceBibleRevisions(projectId: string): Promise<SourceBibleRevisionSummary[]> {
  return apiRequest<SourceBibleRevisionSummary[]>(`/projects/${projectId}/source-bible/revisions`)
}

export function startSourceBible(projectId: string, idempotencyKey: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/source-bible`, {
    method: 'POST',
    headers: { 'Idempotency-Key': idempotencyKey },
  })
}

export function editSourceBible(projectId: string, content: SourceBibleContent): Promise<SourceBibleRead> {
  return apiRequest<SourceBibleRead>(`/projects/${projectId}/source-bible/commands/edit`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  })
}
