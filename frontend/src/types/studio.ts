export interface Episode {
  id: string
  project_id: string
  title: string
  original_filename: string
  sort_order: number
  status: string
  duration_us: number | null
  width: number | null
  height: number | null
  fps: number | null
  preprocess_status: string | null
  shot_count: number
  created_at: string
}

export interface Project {
  id: string
  name: string
  source_language: string
  target_language: string
  target_region: string
  project_format_version: string
  created_at: string
  updated_at: string
  episodes: Episode[]
}

export interface Shot {
  id: string
  episode_id: string
  ordinal: number
  start_us: number
  end_us: number
  duration_us: number
  reference_url: string
  thumbnail_url: string | null
  keyframes: Array<{ kind: string; path: string }>
  short_description: string | null
  shot_type: string | null
  camera_motion: string | null
  status: string
}

export interface ShotRevisionItem {
  id: string
  revision_id: string
  original_shot_id: string
  ordinal: number
  start_us: number
  end_us: number
  duration_us: number
  reference_url: string
  thumbnail_url: string | null
  status: string
}

export interface ShotRevision {
  id: string
  episode_id: string
  revision: number
  kind: 'AUTO' | 'MANUAL' | 'RESTORE' | 'BASELINE' | string
  is_current: boolean
  source_revision_id: string | null
  note: string | null
  shot_count: number
  created_at: string
  shots?: ShotRevisionItem[]
}

export interface CharacterTrackEvidence {
  id: string
  shot_id: string
  start_us: number
  end_us: number
  representative_source_us: number
  bbox: [number, number, number, number]
  sample_count: number
  face_visible: boolean
  mean_face_score: number | null
}

export interface CharacterCandidate {
  id: string
  ordinal: number
  auto_label: string
  track_count: number
  shot_count: number
  confidence: number | null
  cover_url: string | null
  tracks: CharacterTrackEvidence[]
}

export interface SceneCandidate {
  id: string
  ordinal: number
  auto_label: string
  shot_count: number
  cover_url: string | null
  shot_ids: string[]
}

export interface AnalysisDialogue {
  id: string
  episode_id: string
  shot_id: string
  source_start_us: number
  source_end_us: number
  shot_start_us: number
  shot_end_us: number
  ai_text: string
  language: string | null
  speaker_label: string | null
  speaker_candidate_id: string | null
  speaker_mapping_confidence: number | null
  dialogue_type: string
  emotion: string | null
  speaking_style: string | null
}

export interface ContentAnalysisRun {
  id: string
  project_id: string
  status: string
  is_current: boolean
  profile_version: string
  component_status: Record<string, string>
  counts: Record<string, number>
  error_message: string | null
  started_at: string
  completed_at: string | null
  characters: CharacterCandidate[]
  scenes: SceneCandidate[]
  dialogues: AnalysisDialogue[]
  props: unknown[]
}

export interface F05ModelStatus {
  ready: boolean
  models: Array<{
    logical_id: string
    filename: string
    ready: boolean
    path: string
    error: string | null
  }>
}

export type BackgroundTaskStatus = 'QUEUED' | 'PROCESSING' | 'READY' | 'READY_WITH_WARNINGS' | 'FAILED' | 'CANCELLED'

export interface BackgroundTask {
  id: string
  project_id: string
  episode_id: string | null
  task_type: string
  title: string
  status: BackgroundTaskStatus
  progress_mode: 'determinate' | 'indeterminate'
  progress_percent: number | null
  stage_key: string | null
  stage_label: string | null
  current_item: string | null
  current_index: number | null
  total_items: number | null
  message: string | null
  error_message: string | null
  result: unknown
  created_at: string
  started_at: string | null
  updated_at: string
  completed_at: string | null
}

export interface ProjectCreatePayload {
  name: string
  source_language: string
  target_language: string
  target_region: string
}
