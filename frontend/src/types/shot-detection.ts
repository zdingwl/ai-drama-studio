export interface ShotCandidate {
  id: string
  detection_id: string
  project_id: string
  ordinal: number
  detected_proxy_start_us: number
  detected_proxy_end_us: number
  detected_start_us: number
  detected_end_us: number
  duration_us: number
  end_boundary_kind: 'cut' | 'video_end'
  end_boundary_score: number | null
}

export interface ShotDetection {
  id: string
  project_id: string
  source_video_id: string
  status: 'processing' | 'ready'
  detector_name: string
  detector_profile_version: number
  detector_threshold: number
  min_boundary_gap_us: number
  detector_package_version: string
  torch_version: string | null
  detector_device: string | null
  ffprobe_version: string | null
  preprocess_profile_version: number
  proxy_sha256_snapshot: string
  proxy_to_source_offset_us: number
  proxy_start_us: number | null
  proxy_end_us: number | null
  source_start_us: number | null
  source_end_us: number | null
  analyzed_frame_count: number | null
  detected_cut_count: number | null
  shot_count: number | null
  created_at: string
  completed_at: string | null
  candidates: ShotCandidate[]
}
