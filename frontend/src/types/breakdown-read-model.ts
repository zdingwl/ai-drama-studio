import type { FinalCharacterDisplay, SceneTimelinePayload } from './scene-timeline'

export interface BreakdownReadPerson {
  ref: string
  display_name: string
  character: FinalCharacterDisplay | null
}

export interface BreakdownReadSceneIdentity {
  scene_ordinal: number
  people: BreakdownReadPerson[]
}

export interface BreakdownReadIdentityOverlay {
  asset_revision_id: string | null
  resolved_count: number
  unresolved_count: number
  warnings: string[]
  scenes: BreakdownReadSceneIdentity[]
}

export interface BreakdownReadModelPayload {
  schema_version: 'breakdown-read-model-v1'
  timeline: SceneTimelinePayload
  identity: BreakdownReadIdentityOverlay
}
