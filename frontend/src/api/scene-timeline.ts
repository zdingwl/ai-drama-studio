import type { BreakdownReadModelPayload } from '../types/breakdown-read-model'
import type { SceneTimelinePayload } from '../types/scene-timeline'
import { projectBreakdownReadModelForOrdinaryUi } from '../utils/breakdownReadModelUi'
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

async function requestOrdinaryReadModel(url: string): Promise<SceneTimelinePayload | null> {
  const payload = await request<BreakdownReadModelPayload | null>(url)
  return payload ? projectBreakdownReadModelForOrdinaryUi(payload) : null
}

export const sceneTimelineApi = {
  // Ordinary episode reading goes through P6: frozen G2 Timeline + independent Final Character/Scene/Prop overlays.
  getEpisode: (episodeId: string) => requestOrdinaryReadModel(`/api/episodes/${episodeId}/breakdown-read-model`),
  // Historical/debug run reading remains frozen G2.5 and never projects current Final assets onto history.
  getRun: async (runId: string) => {
    const payload = await request<SceneTimelinePayload>(`/api/breakdown-runs/${runId}/scene-timeline`)
    return sanitizeOrdinarySceneTimelinePayload(payload)
  },
}
