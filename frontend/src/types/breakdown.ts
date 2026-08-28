export interface BreakdownShotRevisionSummary {
  id: string
  episode_id: string
  revision: number
  kind: string
  is_current: boolean
  source_revision_id: string | null
  note: string | null
  created_at: string | null
  item_count: number
}

export interface BreakdownRunSummary {
  id: string
  project_id: string
  episode_id: string
  source_shot_revision_id: string
  source_shot_revision: BreakdownShotRevisionSummary | null
  status: string
  is_current: boolean
  schema_version: string
  pipeline_profile: string
  component_status: Record<string, unknown>
  provider_metadata: Record<string, unknown>
  counts: Record<string, number>
  warnings: unknown
  error_message: string | null
  started_at: string | null
  completed_at: string | null
}

export interface BreakdownRevisionItem {
  id: string
  revision_id: string
  original_shot_id: string
  ordinal: number
  start_us: number
  end_us: number
  duration_us: number
  shot_status: string
  short_description: string | null
  shot_type: string | null
  camera_motion: string | null
  keyframes: unknown[]
  reference_url: string | null
  thumbnail_url: string | null
}

export interface BreakdownSubjectRef {
  id: string
  display_label: string | null
  ordinal: number | null
}

export interface BreakdownLocalSubject {
  id: string
  run_id: string
  scene_segment_id: string
  ordinal: number
  display_label: string
  role_hint: string | null
  appearance_summary: string | null
  appearance: Record<string, unknown>
  first_seen_us: number
  last_seen_us: number
  speaking_state_summary: string | null
  confidence: number | null
}

export interface BreakdownShotSubject {
  id: string
  run_id: string
  shot_draft_id: string
  local_subject_id: string
  subject: BreakdownSubjectRef
  first_seen_us: number
  last_seen_us: number
  screen_position: string | null
  visibility: string | null
  speaking_state: string | null
  activity_summary: string | null
  confidence: number | null
  search_hint: Record<string, unknown>
}

export interface BreakdownEventParticipant {
  id: string
  event_id: string
  local_subject_id: string
  subject: BreakdownSubjectRef
  role: string
  confidence: number | null
}

export interface BreakdownTimelineEvent {
  id: string
  run_id: string
  shot_draft_id: string
  ordinal: number
  event_type: string
  source_start_us: number
  source_end_us: number
  shot_relative_start_us: number
  shot_relative_end_us: number
  content_text: string | null
  language: string | null
  emotion_hint: string | null
  speaking_style_hint: string | null
  confidence: number | null
  origin: string
  metadata: Record<string, unknown>
  participants: BreakdownEventParticipant[]
}

export interface BreakdownPropHint {
  id: string
  run_id: string
  scene_segment_id: string
  ordinal: number
  label_hint: string
  normalized_hint: string | null
  importance: string | null
  narrative_reason: string | null
  first_seen_us: number
  last_seen_us: number
  confidence: number | null
  metadata: Record<string, unknown>
}

export interface BreakdownPropRef {
  id: string
  label_hint: string | null
  normalized_hint: string | null
  importance: string | null
}

export interface BreakdownPropOccurrence {
  id: string
  prop_hint_id: string
  prop_hint: BreakdownPropRef
  shot_draft_id: string
  source_start_us: number
  source_end_us: number
  screen_position_hint: string | null
  interaction_summary: string | null
  confidence: number | null
  search_region_hint: Record<string, unknown>
}

export interface BreakdownShotDraft {
  id: string
  run_id: string
  scene_segment_id: string
  source_shot_revision_item_id: string
  source_shot_id_snapshot: string
  shot_ordinal_snapshot: number
  source_start_us: number
  source_end_us: number
  summary: string | null
  visual_description: string | null
  shot_language: string | null
  shot_type_hint: string | null
  camera_motion_hint: string | null
  narrative_function_hint: string | null
  confidence: number | null
  model_metadata: Record<string, unknown>
  source_shot_revision_item: BreakdownRevisionItem | null
  subjects: BreakdownShotSubject[]
  events: BreakdownTimelineEvent[]
  prop_occurrences: BreakdownPropOccurrence[]
}

export interface BreakdownSceneSegment {
  id: string
  run_id: string
  episode_id: string
  ordinal: number
  source_start_us: number
  source_end_us: number
  location_hint: string | null
  interior_exterior: string | null
  time_of_day: string | null
  scene_function_hint: string | null
  summary: string | null
  environment_description: string | null
  confidence: number | null
  metadata: Record<string, unknown>
  subjects: BreakdownLocalSubject[]
  prop_hints: BreakdownPropHint[]
  shots: BreakdownShotDraft[]
}

export interface BreakdownEvidenceLink {
  id: string
  run_id: string
  owner_type: string
  owner_id: string
  source_type: string
  source_id: string
  source_uri: string | null
  role: string
  confidence: number | null
  metadata: Record<string, unknown>
}

export interface BreakdownUnassigned {
  shots: BreakdownShotDraft[]
  subjects: BreakdownLocalSubject[]
  subject_presences: BreakdownShotSubject[]
  events: BreakdownTimelineEvent[]
  event_participants: BreakdownEventParticipant[]
  prop_hints: BreakdownPropHint[]
  prop_occurrences: BreakdownPropOccurrence[]
}

export interface BreakdownDraftPayload {
  run: BreakdownRunSummary
  scene_segments: BreakdownSceneSegment[]
  evidence_links: BreakdownEvidenceLink[]
  unassigned: BreakdownUnassigned
}
