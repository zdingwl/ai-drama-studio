export type ProjectRedrawRule = 'CHARACTER' | 'SCENE' | 'LANGUAGE'

export interface ManagedProjectEpisode {
  id: string
  title: string
  sort_order: number
}

export interface ManagedProject {
  id: string
  name: string
  source_language: string
  target_language: string
  target_region: string
  project_format_version: string
  redraw_rules: ProjectRedrawRule[]
  created_at: string
  updated_at: string
  episodes: ManagedProjectEpisode[]
}

export interface ProjectManagementPayload {
  name: string
  source_language: string
  target_language: string
  target_region: string
  redraw_rules: ProjectRedrawRule[]
}
