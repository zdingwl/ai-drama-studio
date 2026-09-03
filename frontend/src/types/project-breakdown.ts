export type BreakdownStatus =
  | 'not_started'
  | 'queued'
  | 'processing'
  | 'review'
  | 'completed'
  | 'failed'

export type BreakdownTab = 'breakdown' | 'characters' | 'scene-props' | 'dialogue'

export interface BreakdownEpisodeOption {
  id: string
  sort_order: number
  title: string
  filename: string
  duration_seconds: number | null
  source_url: string | null
  current_shot_revision_id: string | null
  shot_count: number
}

export interface BreakdownTaskSummary {
  id: string
  type: string
  status: string
  progress: number | null
  episode_id: string | null
  shot_id: string | null
  current_index: number | null
  total: number | null
  result: Record<string, unknown> | null
  error: string | null
  created_at: string | null
  updated_at: string | null
}

export interface BreakdownShotListItem {
  id: string
  shot_revision_id: string | null
  shot_index: number
  start_seconds: number
  end_seconds: number
  duration_seconds: number
  thumbnail_url: string | null
  reference_clip_url: string | null
  status: BreakdownStatus
  progress: number | null
  error: string | null
  has_breakdown: boolean
  review_required: boolean
}

export interface BreakdownCharacterObservation {
  id: string
  shot_id: string
  track_id: string | null
  face_crop_url: string | null
  body_crop_url: string | null
  mask_url: string | null
  quality_score: number | null
  frontal_score: number | null
  occlusion_score: number | null
  timestamp_seconds: number | null
}

export interface BreakdownCharacter {
  id: string
  display_name: string
  display_image_url: string | null
  speaker: boolean
  position: string | null
  state: string | null
  clothing: string | null
  expression: string | null
  action: string | null
  interaction: string | null
  merge_status: 'resolved' | 'review' | 'unresolved'
  observation_count: number
  observations?: BreakdownCharacterObservation[]
}

export interface BreakdownScene {
  id: string | null
  display_name: string | null
  interior_exterior: string | null
  location: string | null
  time_of_day: string | null
  environment: string | null
  lighting: string | null
  weather: string | null
  confidence: number | null
}

export interface BreakdownProp {
  id: string | null
  name: string
  owner_character_id: string | null
  usage: string | null
  key_prop: boolean
  confidence: number | null
}

export interface BreakdownDialogueEvidence {
  asr_text: string | null
  asr_confidence: number | null
  ocr_text: string | null
  ocr_confidence: number | null
  resolution: 'asr' | 'ocr' | 'fused' | 'manual' | 'unresolved'
}

export interface BreakdownDialogue {
  id: string
  speaker_character_id: string | null
  speaker_name: string | null
  start_seconds: number
  end_seconds: number
  final_text: string
  confidence: number | null
  review_required: boolean
  evidence: BreakdownDialogueEvidence | null
}

export interface BreakdownCameraInfo {
  shot_size: string | null
  angle: string | null
  movement: string | null
  composition: string | null
  lighting: string | null
  continuity: string | null
}

export interface BreakdownH3Facts {
  subject: string | null
  action: string | null
  expression: string | null
  interaction: string | null
  scene: string | null
  prop: string | null
  camera: string | null
  framing: string | null
  composition: string | null
  motion: string | null
  lighting: string | null
  continuity: string | null
}

export interface ShotBreakdownDetail {
  shot_id: string
  shot_revision_id: string | null
  status: BreakdownStatus
  progress: number | null
  error: string | null
  review_required: boolean
  summary: string | null
  characters: BreakdownCharacter[]
  scene: BreakdownScene | null
  props: BreakdownProp[]
  dialogues: BreakdownDialogue[]
  camera: BreakdownCameraInfo
  h3: BreakdownH3Facts
  updated_at: string | null
}

export interface EpisodeBreakdownOverview {
  episode_id: string
  status: BreakdownStatus
  progress: number | null
  total_shots: number
  completed_shots: number
  review_shots: number
  failed_shots: number
  processing_shots: number
  queued_shots: number
}

export interface UpdateShotBoundaryRequest {
  start_seconds: number
  end_seconds: number
  expected_shot_revision_id?: string | null
}

export interface BreakdownCommandResult {
  task_id: string
  task_type: string
  status: string
  episode_id: string
  shot_id?: string | null
}
