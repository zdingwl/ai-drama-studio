export interface CharacterTrackSample {
  source_time_us: number
  bbox: number[]
  detection_score: number
  face_quality: number
}

export interface CharacterTrack {
  id: string
  run_id: string
  project_id: string
  final_shot_id: string
  final_shot_ordinal: number
  candidate_id: string
  track_ordinal_in_shot: number
  start_us: number
  end_us: number
  representative_source_us: number
  representative_bbox: number[]
  sample_count: number
  mean_face_quality: number
  max_face_quality: number
  samples: CharacterTrackSample[]
}

export interface CharacterCandidate {
  id: string
  run_id: string
  project_id: string
  ordinal: number
  track_count: number
  shot_count: number
  first_seen_us: number
  last_seen_us: number
  cover_track_id: string
  cover_source_us: number
  cover_bbox: number[]
  cluster_score: number | null
  tracks: CharacterTrack[]
}

export interface CharacterDetection {
  id: string
  project_id: string
  source_edit_set_id: string
  source_edit_set_revision: number
  source_start_us: number
  source_end_us: number
  status: 'processing' | 'ready' | 'failed'
  is_current: boolean
  profile_version: string
  sampling_profile: Record<string, unknown>
  detector_model_id: string
  detector_model_sha256: string
  recognizer_model_id: string
  recognizer_model_sha256: string
  opencv_version: string
  runtime_device: string
  sampled_frame_count: number
  face_observation_count: number
  track_count: number
  candidate_count: number
  started_at: string
  completed_at: string | null
  error_code: string | null
  error_message: string | null
  candidates: CharacterCandidate[]
}
