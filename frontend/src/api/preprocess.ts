import { apiRequest } from './http'
import type { SourcePreprocess } from '../types/preprocess'

/** 页面进入、刷新或应用重启后读取当前项目已经 ready 的 F03 预处理结果。 */
export function fetchSourcePreprocess(projectId: string): Promise<SourcePreprocess | null> {
  return apiRequest<SourcePreprocess | null>(`/api/projects/${encodeURIComponent(projectId)}/preprocess`)
}

/**
 * 启动 F03 预处理。
 *
 * POST 不上传原视频；后端会根据 Project ID 找到 F02 已冻结 Source，并完成
 * Source Integrity → Proxy/WAV/Thumbnail → Timeline Mapping → ready。
 */
export function startSourcePreprocess(projectId: string): Promise<SourcePreprocess> {
  return apiRequest<SourcePreprocess>(`/api/projects/${encodeURIComponent(projectId)}/preprocess`, {
    method: 'POST',
  })
}
