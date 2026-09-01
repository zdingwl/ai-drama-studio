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
