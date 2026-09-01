export type LocalizationDraftStatus = 'DRAFT' | 'IN_REVIEW' | 'FINAL'
export type LocalizationDraftDecision = 'PENDING' | 'LOCALIZE' | 'KEEP_SOURCE' | 'OMIT'
export type LocalizationDraftEntryKind = 'dialogue' | 'on_screen_text'

export interface LocalizationDisplayCharacter {
  id: string
  name: string
  cover_url: string | null
}

export interface LocalizationDisplayPerson {
  display_name: string
  character: LocalizationDisplayCharacter | null
}

export interface LocalizationDraftEntry {
  source_key: string
  kind: LocalizationDraftEntryKind
  scene_ordinal: number
  shot_ordinal: number
  start_us: number
  end_us: number
  source_text: string
  speakers: LocalizationDisplayPerson[]
  decision: LocalizationDraftDecision
  translated_text: string | null
  localized_text: string | null
  final_text: string | null
  effective_final_text: string | null
  note: string | null
}

export interface LocalizationDraftShot {
  ordinal: number
  start_us: number
  end_us: number
  reference_url: string | null
  thumbnail_url: string | null
  visual_description: string | null
  people: LocalizationDisplayPerson[]
  entries: LocalizationDraftEntry[]
}

export interface LocalizationDraftScene {
  ordinal: number
  title: string
  story_summary: string | null
  shots: LocalizationDraftShot[]
}

export interface LocalizationDraftProgress {
  total: number
  pending: number
  localized: number
  keep_source: number
  omitted: number
}

export interface LocalizationDraftView {
  schema_version: 'localization-draft-v1'
  revision_id: string
  revision: number
  kind: string
  status: LocalizationDraftStatus
  is_current: boolean
  stale: boolean
  project_id: string
  episode_id: string
  source_schema_version: string
  source_breakdown_run_id: string
  source_shot_revision_id: string
  source_asset_revision_id: string | null
  source_fingerprint: string
  source_language: string
  target_language: string
  target_region: string
  progress: LocalizationDraftProgress
  scenes: LocalizationDraftScene[]
  warnings: string[]
  note: string | null
  created_at: string
}

export interface LocalizationRevisionSummary {
  id: string
  episode_id: string
  revision: number
  kind: string
  status: LocalizationDraftStatus
  is_current: boolean
  source_breakdown_run_id: string
  source_shot_revision_id: string
  source_asset_revision_id: string | null
  source_fingerprint: string
  note: string | null
  created_at: string
}

export interface LocalizationDraftEditPayload {
  source_key: string
  decision: LocalizationDraftDecision
  translated_text: string | null
  localized_text: string | null
  final_text: string | null
  note?: string | null
}
