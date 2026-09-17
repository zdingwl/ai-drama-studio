import { apiRequest } from '@/lib/api'
import type { TaskRead } from './types'

export type ReviewStatus = 'NEEDS_REVIEW' | 'ACCEPTED' | 'REJECTED' | 'SUPERSEDED'
export type ResultStatus = 'NOT_BUILT' | 'CURRENT' | 'STALE'

export interface StoryboardShot {
  storyboard_shot_id: string
  episode_id: string
  episode_order: number
  shot_number: number
  start_us: number
  end_us: number
  duration_us: number
  target_visual_description: string
  target_scene_ids: string[]
  target_character_ids: string[]
  target_prop_ids: string[]
  dialogue_refs: Array<{ utterance_number: number; final_target_dialogue: string }>
}

export interface GenerationSegment {
  generation_segment_id: string
  episode_id: string
  episode_order: number
  segment_number: number
  start_us: number
  end_us: number
  duration_us: number
  continuation_index: number
  continuation_count: number
  requires_lip_sync: boolean
  output_ratio: string
}

export interface StoryboardCandidate {
  id: string
  generation_sequence: number
  review_status: ReviewStatus
  content: {
    storyboard: {
      source_snapshot_artifact_id: string
      target_bible_artifact_id: string
      target_script_artifact_id: string
      target_assets_artifact_id: string
      audio_generation_mode: 'NATIVE_AUDIO_VIDEO' | 'INDEPENDENT_AUDIO'
      target_audio_artifact_id: string | null
      timing_plan_artifact_id: string | null
      shots: StoryboardShot[]
    }
    generation_segments: { segments: GenerationSegment[] }
  }
}

export interface TargetStoryboardRead {
  status: ResultStatus
  artifact_id: string | null
  content: { shots: StoryboardShot[] } | null
}

export interface GenerationSegmentsRead {
  status: ResultStatus
  artifact_id: string | null
  content: { segments: GenerationSegment[] } | null
}

export interface GenerationAttempt {
  id: string
  generation_segment_id: string
  attempt_number: number
  media_url: string
  actual_duration_us: number
  width: number
  height: number
  codec_name: string
  technical_qc_status: 'PASS' | 'FAIL'
  technical_qc_issues: string[]
}

export interface SelectedClip {
  generation_segment_id: string
  episode_id: string
  episode_order: number
  segment_number: number
  planned_start_us: number
  planned_end_us: number
  planned_duration_us: number
  requires_lip_sync: boolean
  selected_attempt_id: string
  provider_job_id?: string
  media_url: string
  media_sha256?: string
  mime_type?: string
  actual_duration_us: number
  width: number
  height: number
  codec_name?: string
}

export interface GeneratedVideoRead {
  status: ResultStatus
  artifact_id: string | null
  revision?: number | null
  content: {
    target_storyboard_artifact_id: string
    generation_segments_artifact_id: string
    target_assets_artifact_id: string
    clips: SelectedClip[]
  } | null
}

export interface GenerationCandidate {
  id: string
  generation_sequence: number
  review_status: ReviewStatus
  content: {
    target_storyboard_artifact_id: string
    generation_segments_artifact_id: string
    target_assets_artifact_id: string
    clips: SelectedClip[]
  }
}

export interface GenerationSelectionRead {
  status: ResultStatus
  artifact_id: string | null
  content: { selections: Array<{ generation_segment_id: string; selected_attempt_id: string }> } | null
}

export type H3RuntimeReadinessState = 'READY' | 'UNAVAILABLE' | 'WARMING_UP' | 'INCOMPATIBLE' | 'MODEL_MISMATCH' | 'NOT_CONFIGURED'

export interface H3RuntimeReadinessRead {
  runtime_mode: 'LOCAL_COMFYUI' | 'LOCAL_SGLANG' | 'MINIMAX_CLOUD' | string
  state: H3RuntimeReadinessState
  ready: boolean
  provider: string
  model: string
  base_url: string
  message: string
}

export interface FinalEpisodeOutput {
  episode_id: string
  episode_order: number
  video_url: string
  duration_us: number
  width: number
  height: number
  subtitle_url: string
  lip_synced_segment_count: number
  segment_count: number
}

export interface PostCandidate {
  id: string
  generation_sequence: number
  review_status: ReviewStatus
  content: {
    generation_selection_artifact_id: string
    audio_generation_mode: 'NATIVE_AUDIO_VIDEO' | 'INDEPENDENT_AUDIO'
    target_audio_artifact_id: string | null
    target_script_artifact_id: string
    timing_plan_artifact_id: string | null
    episodes: FinalEpisodeOutput[]
  }
}

export interface FinalOutputRead {
  status: ResultStatus
  artifact_id: string | null
  content: { episodes: FinalEpisodeOutput[] } | null
}

export const getTargetStoryboard = (projectId: string) => apiRequest<TargetStoryboardRead>(`/projects/${projectId}/target-storyboard`, { cache: 'no-store' })
export const getGenerationSegments = (projectId: string) => apiRequest<GenerationSegmentsRead>(`/projects/${projectId}/generation-segments`, { cache: 'no-store' })
export const listStoryboardCandidates = (projectId: string) => apiRequest<StoryboardCandidate[]>(`/projects/${projectId}/target-storyboard/candidates`, { cache: 'no-store' })
export const startStoryboard = (projectId: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/replica-storyboard`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } })
export const reviewStoryboard = (projectId: string, candidate: StoryboardCandidate, accept: boolean, reason: string) => apiRequest(`/projects/${projectId}/target-storyboard/candidates/${candidate.id}/commands/${accept ? 'accept' : 'reject'}`, {
  method: 'POST',
  body: JSON.stringify({
    expected_source_snapshot_artifact_id: candidate.content.storyboard.source_snapshot_artifact_id,
    expected_target_bible_artifact_id: candidate.content.storyboard.target_bible_artifact_id,
    expected_target_script_artifact_id: candidate.content.storyboard.target_script_artifact_id,
    expected_target_assets_artifact_id: candidate.content.storyboard.target_assets_artifact_id,
    expected_target_audio_artifact_id: candidate.content.storyboard.target_audio_artifact_id,
    expected_timing_plan_artifact_id: candidate.content.storyboard.timing_plan_artifact_id,
    expected_generation_sequence: candidate.generation_sequence,
    reason,
  }),
})

export const getVideoGenerationRuntimeReadiness = (projectId: string) => apiRequest<H3RuntimeReadinessRead>(`/projects/${projectId}/video-generation/runtime-readiness`, { cache: 'no-store' })
export const listGenerationAttempts = (projectId: string) => apiRequest<GenerationAttempt[]>(`/projects/${projectId}/video-generation/attempts`, { cache: 'no-store' })
export const listGenerationCandidates = (projectId: string) => apiRequest<GenerationCandidate[]>(`/projects/${projectId}/video-generation/candidates`, { cache: 'no-store' })
export const getGeneratedVideo = (projectId: string) => apiRequest<GeneratedVideoRead>(`/projects/${projectId}/generated-video`, { cache: 'no-store' })
export const getGenerationSelection = (projectId: string) => apiRequest<GenerationSelectionRead>(`/projects/${projectId}/generation-selection`, { cache: 'no-store' })
export const startVideoGeneration = (projectId: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/video-generation`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } })
export const regenerateVideoSegment = (projectId: string, generationSegmentId: string) => apiRequest<TaskRead>(`/projects/${projectId}/video-generation/segments/${encodeURIComponent(generationSegmentId)}/commands/regenerate`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } })
export const reviewGeneration = (projectId: string, candidate: GenerationCandidate, accept: boolean, reason: string) => apiRequest(`/projects/${projectId}/video-generation/candidates/${candidate.id}/commands/${accept ? 'accept' : 'reject'}`, {
  method: 'POST',
  body: JSON.stringify({
    expected_target_storyboard_artifact_id: candidate.content.target_storyboard_artifact_id,
    expected_generation_segments_artifact_id: candidate.content.generation_segments_artifact_id,
    expected_target_assets_artifact_id: candidate.content.target_assets_artifact_id,
    expected_generation_sequence: candidate.generation_sequence,
    reason,
  }),
})

export const listPostCandidates = (projectId: string) => apiRequest<PostCandidate[]>(`/projects/${projectId}/post-production/candidates`, { cache: 'no-store' })
export const getFinalOutput = (projectId: string) => apiRequest<FinalOutputRead>(`/projects/${projectId}/final-output`, { cache: 'no-store' })
export const startPostProduction = (projectId: string) => apiRequest<TaskRead>(`/projects/${projectId}/commands/post-production`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } })
export const reviewPost = (projectId: string, candidate: PostCandidate, accept: boolean, reason: string) => apiRequest(`/projects/${projectId}/post-production/candidates/${candidate.id}/commands/${accept ? 'accept' : 'reject'}`, {
  method: 'POST',
  body: JSON.stringify({
    expected_generation_selection_artifact_id: candidate.content.generation_selection_artifact_id,
    expected_target_audio_artifact_id: candidate.content.target_audio_artifact_id,
    expected_target_script_artifact_id: candidate.content.target_script_artifact_id,
    expected_timing_plan_artifact_id: candidate.content.timing_plan_artifact_id,
    expected_generation_sequence: candidate.generation_sequence,
    reason,
  }),
})
