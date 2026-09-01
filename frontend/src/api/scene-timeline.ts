import type { SceneTimelinePayload } from '../types/scene-timeline'
import { sanitizeOrdinarySceneTimelinePayload } from '../utils/sceneTimelineUi'

async function request<T>(url: string): Promise<T> {
  const response = await fetch(url)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json() as { detail?: string }
      message = payload.detail || message
    } catch {
      // 非 JSON 错误保持默认文案。
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

async function requestOrdinaryTimeline(url: string): Promise<SceneTimelinePayload | null> {
  const payload = await request<SceneTimelinePayload | null>(url)
  return payload ? sanitizeOrdinarySceneTimelinePayload(payload) : null
}

export const sceneTimelineApi = {
  getEpisode: (episodeId: string) => requestOrdinaryTimeline(`/api/episodes/${episodeId}/scene-timeline`),
  getRun: async (runId: string) => {
    const payload = await request<SceneTimelinePayload>(`/api/breakdown-runs/${runId}/scene-timeline`)
    return sanitizeOrdinarySceneTimelinePayload(payload)
  },
}
