import { API_BASE_URL, apiRequest } from './http'
import type { ShotWorkbench } from '../types/shot-workbench'

export function fetchShotWorkbench(projectId: string): Promise<ShotWorkbench | null> {
  return apiRequest<ShotWorkbench | null>(`/api/projects/${encodeURIComponent(projectId)}/shot-workbench`)
}

export function initializeShotWorkbench(projectId: string): Promise<ShotWorkbench> {
  return apiRequest<ShotWorkbench>(`/api/projects/${encodeURIComponent(projectId)}/shot-workbench/initialize`, {
    method: 'POST',
  })
}

export function updateShotBoundary(projectId: string, leftShotId: string, boundaryUs: number): Promise<ShotWorkbench> {
  return apiRequest<ShotWorkbench>(`/api/projects/${encodeURIComponent(projectId)}/shot-workbench/boundary`, {
    method: 'POST',
    body: JSON.stringify({ left_shot_id: leftShotId, boundary_us: boundaryUs }),
  })
}

export function splitShot(projectId: string, shotId: string, splitUs: number): Promise<ShotWorkbench> {
  return apiRequest<ShotWorkbench>(`/api/projects/${encodeURIComponent(projectId)}/shot-workbench/split`, {
    method: 'POST',
    body: JSON.stringify({ shot_id: shotId, split_us: splitUs }),
  })
}

export function mergeShots(projectId: string, leftShotId: string): Promise<ShotWorkbench> {
  return apiRequest<ShotWorkbench>(`/api/projects/${encodeURIComponent(projectId)}/shot-workbench/merge`, {
    method: 'POST',
    body: JSON.stringify({ left_shot_id: leftShotId }),
  })
}

export function confirmShotWorkbench(projectId: string): Promise<ShotWorkbench> {
  return apiRequest<ShotWorkbench>(`/api/projects/${encodeURIComponent(projectId)}/shot-workbench/confirm`, {
    method: 'POST',
  })
}

/**
 * 浏览器播放器读取 F03 Proxy 的本地 HTTP URL。
 * 不能直接把 Windows 本地文件路径塞给 <video>，浏览器会受 file:// 安全边界限制。
 */
export function shotWorkbenchProxyUrl(projectId: string): string {
  return `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/shot-workbench/media/proxy`
}

/** Source Domain 时间直接作为 query；后端负责映射成媒体相对时间并抽帧。 */
export function shotWorkbenchFrameUrl(projectId: string, sourceTimeUs: number): string {
  return `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/shot-workbench/frame?source_time_us=${Math.trunc(sourceTimeUs)}`
}
