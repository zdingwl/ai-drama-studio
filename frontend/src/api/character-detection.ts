import { API_BASE_URL, apiRequest } from './http'
import type { CharacterDetection } from '../types/character-detection'

/** 页面进入/刷新时读取 F06 当前 processing/current ready/最近 failed 状态。 */
export function fetchCharacterDetection(projectId: string): Promise<CharacterDetection | null> {
  return apiRequest<CharacterDetection | null>(`/api/projects/${encodeURIComponent(projectId)}/character-detection`)
}

/** 首次运行 F06 本地人物识别；模型/采样/阈值全部由后端固定 Profile 控制。 */
export function startCharacterDetection(projectId: string): Promise<CharacterDetection> {
  return apiRequest<CharacterDetection>(`/api/projects/${encodeURIComponent(projectId)}/character-detection`, {
    method: 'POST',
  })
}

/** 显式重跑 F06；旧 current ready 在新 Run 完整成功前继续保留。 */
export function rerunCharacterDetection(projectId: string): Promise<CharacterDetection> {
  return apiRequest<CharacterDetection>(`/api/projects/${encodeURIComponent(projectId)}/character-detection/rerun`, {
    method: 'POST',
  })
}

/** Candidate ID 属于一次 ready Run，因此头像 URL 可以长期缓存。 */
export function characterCandidateCoverUrl(projectId: string, candidateId: string): string {
  return `${API_BASE_URL}/api/projects/${encodeURIComponent(projectId)}/character-detection/candidates/${encodeURIComponent(candidateId)}/cover`
}
