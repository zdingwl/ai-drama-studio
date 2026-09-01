export type ScenePolicy = 'AUTO' | 'KEEP' | 'LOCALIZE'

export interface ProjectRemakePolicy {
  project_id: string
  scene_policy: ScenePolicy
  character_policy: 'LOCALIZE'
  generation_engine: 'MINIMAX_H3_LOCAL'
  created_at: string
  updated_at: string
}

export type ReviewIssueStatus = 'OPEN' | 'RESOLVED' | 'IGNORED'
export type ReviewIssueSeverity = 'REVIEW' | 'BLOCKING'

export interface ReviewIssue {
  id: string
  project_id: string
  episode_id: string | null
  shot_id: string | null
  source_key: string
  issue_type: string
  severity: ReviewIssueSeverity
  status: ReviewIssueStatus
  reason: string
  ai_suggestion: unknown
  editable_payload: unknown
  resolution: unknown
  created_at: string
  updated_at: string
  resolved_at: string | null
}

export interface TargetCharacter {
  id: string
  project_id: string
  source_character_id: string
  source_character_name: string
  source_character_signature: string
  source_fingerprint: string
  target_language: string
  target_region: string
  target_name: string
  appearance_profile: string
  generation_prompt: string
  confidence: number | null
  status: 'READY' | 'REVIEW'
  decision_source: 'PROJECT_POLICY' | 'AI' | 'MANUAL'
  reference_assets: string[]
  created_at: string
  updated_at: string
}

export interface SceneLocalizationMapping {
  id: string
  project_id: string
  episode_id: string
  scene_key: string
  source_scene_id: string | null
  source_scene_name: string | null
  source_scene_signature: string
  source_fingerprint: string
  project_policy: ScenePolicy
  decision: 'KEEP' | 'LOCALIZE' | 'REVIEW'
  decision_source: 'PROJECT_POLICY' | 'AI' | 'MANUAL'
  confidence: number | null
  target_label: string | null
  target_description: string | null
  reason: string | null
  status: 'READY' | 'REVIEW'
  created_at: string
  updated_at: string
}

export interface TargetLocalizationBundle {
  schema_version: 'target-localization-v1'
  project_id: string
  source_fingerprint: string
  target_language: string
  target_region: string
  scene_policy: ScenePolicy
  status: 'READY' | 'REVIEW'
  target_character_count: number
  scene_mapping_count: number
  review_count: number
  target_characters: TargetCharacter[]
  scene_mappings: SceneLocalizationMapping[]
}

export interface TargetVoiceProfile {
  id: string
  project_id: string
  target_character_id: string
  source_fingerprint: string
  target_character_signature: string
  target_language: string
  target_region: string
  runtime_profile: 'QWEN3_TTS_VOICE_DESIGN_CLONE_V1'
  voice_design_prompt: string
  reference_text: string
  reference_audio_path: string | null
  voice_fingerprint: string
  status: 'PLANNED' | 'REFERENCE_READY' | 'FAILED'
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface TargetDialogue {
  id: string
  project_id: string
  episode_id: string
  shot_key: string
  source_dialogue_key: string
  source_dialogue_signature: string
  source_fingerprint: string
  source_start_us: number
  source_end_us: number
  source_text: string
  source_character_id: string | null
  target_character_id: string | null
  target_voice_profile_id: string | null
  target_language: string
  target_region: string
  translated_text: string | null
  localized_text: string | null
  final_text: string | null
  translation_confidence: number | null
  decision_source: 'AI' | 'MANUAL'
  status: 'READY' | 'REVIEW'
  audio_status: 'PENDING' | 'READY' | 'NOT_CONFIGURED' | 'UNSUPPORTED_LANGUAGE' | 'FAILED'
  audio_input_signature: string | null
  audio_path: string | null
  speech_duration_us: number | null
  tts_runtime_profile: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface TargetDialogueBundle {
  schema_version: 'target-dialogue-v1'
  project_id: string
  source_fingerprint: string
  target_language: string
  target_region: string
  status: 'READY' | 'REVIEW' | 'TEXT_READY_AUDIO_PENDING'
  voice_profile_count: number
  dialogue_count: number
  review_count: number
  audio_ready_count: number
  voice_profiles: TargetVoiceProfile[]
  dialogues: TargetDialogue[]
}

export interface TtsRuntimeStatus {
  ready: boolean
  reachable: boolean
  base_url: string
  runtime_profile: 'QWEN3_TTS_VOICE_DESIGN_CLONE_V1'
  supported_language_prefixes: string[]
  worker?: Record<string, unknown>
  error?: string
}

export type TimingStrategy = 'KEEP' | 'TRIM' | 'CARRY_OVER_REACTION' | 'EXTEND' | 'REWRITE_SHORTER' | 'HUMAN_REVIEW'

export interface RemakeDialoguePlan {
  target_dialogue_id: string
  source_dialogue_key: string
  source_character_id: string | null
  target_character_id: string | null
  source_start_us: number
  source_end_us: number
  source_window_us: number
  speech_duration_us: number | null
  planned_start_offset_us: number
  planned_end_offset_us: number
  planned_start_us: number
  planned_end_us: number
  strategy: TimingStrategy
  carry_over_shot_key: string | null
  overrun_us: number
  reason: string
}

export interface RemakeShotPlan {
  shot_plan_id: string
  scene_key: string
  shot_key: string
  source_shot_id: string | null
  ordinal: number
  reference_url: string | null
  source_start_us: number
  source_end_us: number
  source_duration_us: number
  planned_start_us: number
  planned_end_us: number
  planned_duration_us: number
  duration_delta_us: number
  strategy: TimingStrategy
  status: 'READY' | 'REVIEW' | 'WAITING_AUDIO'
  decision_source: 'AUTO' | 'MANUAL'
  reason: string
  dialogue_plans: RemakeDialoguePlan[]
}

export interface RemakeEpisodeTimeline {
  schema_version: 'remake-timeline-v1'
  id: string
  project_id: string
  episode_id: string
  source_fingerprint: string
  target_dialogue_fingerprint: string
  status: 'READY' | 'REVIEW' | 'WAITING_AUDIO'
  source_duration_us: number
  planned_duration_us: number
  duration_delta_us: number
  shot_count: number
  review_count: number
  waiting_audio_count: number
  shot_plans: RemakeShotPlan[]
  created_at: string
  updated_at: string
}

export interface RemakeProjectTimeline {
  schema_version: 'remake-project-timeline-v1'
  project_id: string
  source_fingerprint: string
  target_dialogue_fingerprint: string
  status: 'READY' | 'REVIEW' | 'WAITING_AUDIO'
  episode_count: number
  review_count: number
  waiting_audio_count: number
  episodes: RemakeEpisodeTimeline[]
}

export interface GenerationSegmentSummary {
  id: string
  episode_id: string
  shot_ordinal: number
  shot_segment_index: number
  shot_segment_count: number
  status: 'READY' | 'REVIEW' | 'WAITING_AUDIO'
  reason: string
  generation_mode: 'REF2VA' | 'FL2VA'
  target_duration_us: number
  h3_duration_us: number
  post_trim_duration_us: number | null
}

export interface GenerationSegmentEpisode {
  episode_id: string
  status: 'READY' | 'REVIEW' | 'WAITING_AUDIO'
  segment_count: number
  review_count: number
  waiting_audio_count: number
  segments: GenerationSegmentSummary[]
}

export interface GenerationSegmentPlan {
  schema_version: 'generation-segment-plan-v1'
  project_id: string
  status: 'READY' | 'REVIEW' | 'WAITING_AUDIO'
  episode_count: number
  segment_count: number
  review_count: number
  waiting_audio_count: number
  episodes: GenerationSegmentEpisode[]
}

export interface H3RuntimeStatus {
  runtime_profile: string
  ready: boolean
  fl2va: Record<string, unknown>
  ref2va: Record<string, unknown>
}

export type GenerationAttemptStatus = 'PLANNED' | 'SUBMITTED' | 'RUNNING' | 'SUCCEEDED' | 'FAILED' | 'STALE'

export interface GenerationAttempt {
  id: string
  project_id: string
  episode_id: string
  generation_segment_id: string
  attempt_number: number
  segment_input_fingerprint: string
  context_fingerprint: string
  provider: 'MINIMAX_H3_LOCAL'
  mode: 'FL2VA' | 'REF2VA'
  status: GenerationAttemptStatus
  external_job_id: string | null
  provider_status: string | null
  request: Record<string, unknown>
  output_path: string | null
  error_message: string | null
  created_at: string
  submitted_at: string | null
  completed_at: string | null
  updated_at: string
}

export interface GenerationAttemptSummary {
  schema_version: 'generation-attempt-summary-v1'
  project_id: string
  attempt_count: number
  succeeded_count: number
  running_count: number
  failed_count: number
  stale_count: number
  attempts: GenerationAttempt[]
}

export type GenerationQCStatus = 'PASS' | 'RETRY' | 'REVIEW' | 'WAITING_MODEL' | 'STALE'

export interface GenerationStructuralQC {
  expected_duration_us: number
  actual_duration_us: number | null
  duration_delta_us: number | null
  duration_tolerance_us: number
  duration_ok: boolean
  decode_ok: boolean
  has_video: boolean
  width: number | null
  height: number | null
  fps: number | null
  error_message: string | null
}

export interface GenerationSemanticQC {
  visual_integrity: number | null
  target_character_consistency: number | null
  scene_consistency: number | null
  action_camera_consistency: number | null
  continuity_consistency: number | null
  confidence: number | null
  source_actor_leak: boolean
  obvious_visual_artifact: boolean
  reasons: string[]
  retry_instruction: string | null
  raw: Record<string, unknown>
}

export interface GenerationQualityCheck {
  id: string
  project_id: string
  episode_id: string
  generation_segment_id: string
  generation_attempt_id: string
  segment_input_fingerprint: string
  profile_version: string
  status: GenerationQCStatus
  quality_score: number | null
  structural: GenerationStructuralQC
  semantic: GenerationSemanticQC | null
  model_profile: string | null
  reason: string
  retry_instruction: string | null
  created_at: string
  updated_at: string
}

export interface GenerationSelection {
  id: string
  project_id: string
  episode_id: string
  generation_segment_id: string
  segment_input_fingerprint: string
  selected_attempt_id: string
  quality_check_id: string | null
  selection_source: 'AUTO' | 'MANUAL'
  quality_score: number | null
  created_at: string
  updated_at: string
}

export interface GenerationQualitySummary {
  schema_version: 'generation-quality-summary-v1'
  project_id: string
  check_count: number
  pass_count: number
  retry_count: number
  review_count: number
  waiting_model_count: number
  stale_count: number
  selected_count: number
  checks: GenerationQualityCheck[]
  selections: GenerationSelection[]
}

export type PostProductionStatus =
  | 'READY'
  | 'WAITING_SELECTION'
  | 'WAITING_AUDIO'
  | 'WAITING_MODEL'
  | 'REVIEW'
  | 'PROCESSING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'STALE'

export type LipSyncMode =
  | 'SKIP_NO_VISIBLE_DIALOGUE'
  | 'LATENTSYNC_FULL_SEGMENT'
  | 'LATENTSYNC_TARGET_FACE_ROI'
  | 'REVIEW_MULTI_FACE'

export interface PostProductionDialogue {
  target_dialogue_id: string
  target_character_id: string | null
  target_character_name: string | null
  final_text: string | null
  audio_path: string
  audio_trim_start_us: number
  start_offset_us: number
  end_offset_us: number
  speaker_visible: boolean
}

export interface PostProductionSegment {
  id: string
  project_id: string
  episode_id: string
  generation_segment_id: string
  segment_input_fingerprint: string
  selection_id: string | null
  selected_attempt_id: string | null
  postproduction_fingerprint: string
  target_start_us: number
  target_end_us: number
  target_duration_us: number
  status: PostProductionStatus
  reason: string
  lip_sync_mode: LipSyncMode
  visible_character_count: number
  visible_speaker_ids: string[]
  locator_input_fingerprint: string | null
  lip_sync_windows: Array<Record<string, unknown>>
  dialogues: PostProductionDialogue[]
  audio_path: string | null
  output_path: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface PostProductionEpisode {
  episode_id: string
  status: PostProductionStatus
  segment_count: number
  succeeded_count: number
  review_count: number
  waiting_count: number
  segments: PostProductionSegment[]
}

export interface PostProductionPlan {
  schema_version: 'postproduction-plan-v1'
  project_id: string
  status: PostProductionStatus
  episode_count: number
  segment_count: number
  succeeded_count: number
  review_count: number
  waiting_count: number
  episodes: PostProductionEpisode[]
}

export interface LipSyncRuntimeStatus {
  runtime_profile: 'LATENTSYNC_LOCAL_V1_6'
  ready: boolean
  reachable: boolean
  base_url: string
  worker: Record<string, unknown>
  error: string | null
}

export type EpisodeOutputStatus =
  | 'READY'
  | 'WAITING_POSTPRODUCTION'
  | 'PROCESSING'
  | 'SUCCEEDED'
  | 'FAILED'
  | 'STALE'

export interface EpisodeSubtitleEvent {
  target_dialogue_id: string
  start_us: number
  end_us: number
  text: string
  target_character_id: string | null
  target_character_name: string | null
}

export interface EpisodeOutputSegment {
  generation_segment_id: string
  postproduction_status: string
  postproduction_fingerprint: string
  target_start_us: number
  target_end_us: number
  target_duration_us: number
  output_path: string | null
}

export interface EpisodeOutput {
  id: string
  project_id: string
  episode_id: string
  episode_title: string
  input_fingerprint: string
  status: EpisodeOutputStatus
  reason: string
  segment_count: number
  target_duration_us: number
  segments: EpisodeOutputSegment[]
  subtitles: EpisodeSubtitleEvent[]
  subtitle_path: string | null
  output_path: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

export interface EpisodeOutputPlan {
  schema_version: 'episode-output-plan-v1'
  project_id: string
  status: EpisodeOutputStatus
  episode_count: number
  ready_count: number
  succeeded_count: number
  waiting_count: number
  episodes: EpisodeOutput[]
}
