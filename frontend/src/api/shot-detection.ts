import { apiRequest } from './http'
import type { ShotDetection } from '../types/shot-detection'

/** 页面进入、刷新或应用重启后读取当前项目已有的 F04 自动拉片结果。 */
export function fetchShotDetection(projectId: string): Promise<ShotDetection | null> {
  return apiRequest<ShotDetection | null>(`/api/projects/${encodeURIComponent(projectId)}/shot-detection`)
}

/**
 * 启动 F04 本地自动拉片。
 * 前端不允许提交 threshold / device / model path；这些都由 Detector Profile V1 固定。
 */
export function startShotDetection(projectId: string): Promise<ShotDetection> {
  return apiRequest<ShotDetection>(`/api/projects/${encodeURIComponent(projectId)}/shot-detection`, {
    method: 'POST',
  })
}

/**
 * 显式重新执行 F04。
 * 后端会先完整计算新结果，再原子替换旧 READY Auto Evidence；失败时旧结果继续保留。
 */
export function rerunShotDetection(projectId: string): Promise<ShotDetection> {
  return apiRequest<ShotDetection>(`/api/projects/${encodeURIComponent(projectId)}/shot-detection/rerun`, {
    method: 'POST',
  })
}
