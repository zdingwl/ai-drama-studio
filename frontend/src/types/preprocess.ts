export interface SourcePreprocess {
  source_video_id: string
  project_id: string
  status: 'ready'
  profile_version: number
  source_sha256_snapshot: string
  proxy_relative_path: string
  proxy_file_size_bytes: number
  proxy_sha256: string
  proxy_duration_us: number
  proxy_video_time_base_num: number
  proxy_video_time_base_den: number
  proxy_fps_num: number | null
  proxy_fps_den: number | null
  proxy_to_source_offset_us: number
  audio_relative_path: string | null
  audio_file_size_bytes: number | null
  audio_sha256: string | null
  audio_duration_us: number | null
  audio_sample_rate: number | null
  audio_channels: number | null
  audio_to_source_offset_us: number | null
  thumbnail_relative_path: string
  thumbnail_file_size_bytes: number
  thumbnail_sha256: string
  thumbnail_source_time_us: number
  source_video_time_base_num: number
  source_video_time_base_den: number
  created_at: string
  completed_at: string
}
