/** F02 已导入完成的 Source Video DTO。时间字段以整数微秒从后端返回。 */
export interface SourceVideo {
  id: string
  project_id: string
  original_filename: string
  relative_path: string
  file_size_bytes: number
  sha256: string
  status: 'ready'
  container_format: string
  duration_us: number
  source_start_time_us: number | null
  video_stream_index: number
  video_codec: string
  width: number
  height: number
  fps_num: number | null
  fps_den: number | null
  audio_stream_index: number | null
  audio_codec: string | null
  audio_sample_rate: number | null
  audio_channels: number | null
  created_at: string
}

/** 浏览器把原视频发送给本地 FastAPI 时用于 UI 展示的上传进度。 */
export interface SourceVideoUploadProgress {
  loaded: number
  total: number
  percent: number
}
