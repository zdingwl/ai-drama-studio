export interface SceneTimelineSceneInfo {
  location: string | null
  interior_exterior: string | null
  time_of_day: string | null
  environment: string | null
}

export interface FinalCharacterDisplay {
  id: string
  name: string
  cover_url: string | null
}

export interface FinalSceneDisplay {
  id: string
  name: string
  cover_url: string | null
}

export interface FinalPropDisplay {
  id: string
  name: string
  cover_url: string | null
}

export interface SceneTimelinePerson {
  ref: string
  display_name: string
  appearance: string | null
  /** P6 ordinary-user projection only. Frozen G2 payload never owns this field. */
  final_character?: FinalCharacterDisplay | null
}

export interface SceneTimelinePerformance {
  text: string
  people: string[]
}

export interface SceneTimelinePerformanceDetails {
  expression: string | null
  posture: string | null
  gaze: string | null
  interaction: string | null
}

export interface SceneTimelineDialogue {
  start_us: number
  end_us: number
  text: string
  speakers: string[]
}

export interface SceneTimelineOnScreenText {
  start_us: number
  end_us: number
  text: string
}

export interface SceneTimelineProp {
  label: string
  interaction: string | null
}

export interface SceneTimelineCinematography {
  shot_type: string | null
  composition: string | null
  camera_motion: string | null
  /** H3 directing fact; optional so historical scene-timeline-v1 payloads remain valid. */
  camera_angle?: string | null
  /** H3 lighting fact; optional so historical scene-timeline-v1 payloads remain valid. */
  lighting?: string | null
}

export interface SceneTimelineShot {
  presence_review_id?: string
  ordinal: number
  start_us: number
  end_us: number
  duration_us: number
  thumbnail_url: string | null
  reference_url: string | null
  /** Current-shot summary from G1. Optional for historical scene-timeline-v1 payloads. */
  summary?: string | null
  /** Exact-shot narrative function from G1. Optional for historical payloads. */
  narrative_function?: string | null
  visual_description: string | null
  people: string[]
  performance: SceneTimelinePerformance[]
  /** Structured H3 performance facts; optional for historical payloads. */
  performance_details?: SceneTimelinePerformanceDetails | null
  dialogue: SceneTimelineDialogue[]
  props: SceneTimelineProp[]
  cinematography: SceneTimelineCinematography
  /** Conservative source-shot continuity fact; optional for historical payloads. */
  continuity?: string | null
  on_screen_text: SceneTimelineOnScreenText[]
  /** P6 display-only Final Prop bindings; independent from G2 `props` observations. */
  final_props?: FinalPropDisplay[]
}

export interface SceneTimelineScene {
  ordinal: number
  start_us: number
  end_us: number
  duration_us: number
  title: string
  scene_info: SceneTimelineSceneInfo
  people: SceneTimelinePerson[]
  story_summary: string | null
  shots: SceneTimelineShot[]
  /** P6 display-only Final Scene; frozen G2 `title/scene_info` remain unchanged. */
  final_scene?: FinalSceneDisplay | null
}

export interface SceneTimelinePayload {
  schema_version: 'scene-timeline-v1'
  source_breakdown_run_id: string
  source_shot_revision_id: string
  episode_id: string
  status: string
  is_current: boolean
  scene_count: number
  shot_count: number
  warnings: string[]
  scenes: SceneTimelineScene[]
}
