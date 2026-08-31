import type { SceneTimelinePayload } from '../types/scene-timeline'

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

export const sceneTimelineApi = {
  getEpisode: (episodeId: string) => request<SceneTimelinePayload | null>(`/api/episodes/${episodeId}/scene-timeline`),
  getRun: (runId: string) => request<SceneTimelinePayload>(`/api/breakdown-runs/${runId}/scene-timeline`),
}
