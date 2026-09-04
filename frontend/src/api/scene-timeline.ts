import type { BreakdownReadModelPayload } from '../types/breakdown-read-model'
import type { SceneTimelinePayload } from '../types/scene-timeline'
import { projectBreakdownReadModelForOrdinaryUi } from '../utils/breakdownReadModelUi'
import { sanitizeOrdinarySceneTimelinePayload } from '../utils/sceneTimelineUi'

export interface SceneTimelineManualSceneEdit {
  location?: string | null
  interior_exterior?: string | null
  time_of_day?: string | null
  environment?: string | null
}

export interface SceneTimelineManualDialogueEdit {
  index: number
  text: string
}

export interface SceneTimelineManualShotEdit {
  summary?: string | null
  visual_description?: string | null
  narrative_function?: string | null
  performance_text?: string | null
  expression?: string | null
  posture?: string | null
  gaze?: string | null
  interaction?: string | null
  shot_type?: string | null
  camera_angle?: string | null
  composition?: string | null
  camera_motion?: string | null
  lighting?: string | null
  continuity?: string | null
  scene?: SceneTimelineManualSceneEdit
  dialogues?: SceneTimelineManualDialogueEdit[]
}

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
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
  // Ordinary episode reading goes through P6: Scene Timeline + current manual facts + Final Asset overlays.
  getEpisode: (episodeId: string) => requestOrdinaryReadModel(`/api/episodes/${episodeId}/breakdown-read-model`),
  // Historical/debug run reading remains an explicit Run surface.
  getRun: async (runId: string) => {
    const payload = await request<SceneTimelinePayload>(`/api/breakdown-runs/${runId}/scene-timeline`)
    return sanitizeOrdinarySceneTimelinePayload(payload)
  },
  editShot: async (episodeId: string, shotOrdinal: number, payload: SceneTimelineManualShotEdit) => {
    const encodedEpisodeId = encodeURIComponent(episodeId)
    await request<SceneTimelinePayload>(
      `/api/episodes/${encodedEpisodeId}/scene-timeline/shots/${shotOrdinal}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    )
    // PATCH 只返回 G2 Scene Timeline。普通 UI 还需要重新读取 P6，恢复 Final Character / Scene / Prop overlays，
    // 否则一次人工编辑会让页面在刷新前临时丢失正式资产绑定。
    return requestOrdinaryReadModel(`/api/episodes/${encodedEpisodeId}/breakdown-read-model`)
  },
}
