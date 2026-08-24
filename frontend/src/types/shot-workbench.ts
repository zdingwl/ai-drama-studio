export interface FinalShot {
  /** 后续人物、对白、Scene、生成统一关联的稳定 Final Shot ID。 */
  id: string
  edit_set_id: string
  project_id: string
  ordinal: number
  /** Source Domain integer microseconds；不等同于播放器 currentTime。 */
  final_start_us: number
  final_end_us: number
  duration_us: number
  origin_kind: 'auto' | 'manual'
  origin_candidate_ids: string[]
  created_at: string
  updated_at: string
}

export interface ShotWorkbench {
  id: string
  project_id: string
  source_detection_id: string
  status: 'editing' | 'confirmed'
  revision: number
  source_start_us: number
  source_end_us: number
  created_at: string
  updated_at: string
  confirmed_at: string | null
  shots: FinalShot[]
}
