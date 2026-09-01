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
