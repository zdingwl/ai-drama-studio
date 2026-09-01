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
