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

export interface ProjectCreatePayload {
  name: string
  source_language: string
  target_language: string
  target_region: string
}
