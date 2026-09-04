import type { BreakdownDraftPayload, BreakdownRunSummary } from '../types/breakdown'
import type { BackgroundTask } from '../types/studio'

/**
 * P3 Breakdown Draft 请求入口。
 *
 * 读取仍然只消费已持久化结果；运行按钮只调用正式 P2 task endpoint，
 * 不在前端复制 ASR/OCR/VLM/Fusion 逻辑。
 */
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

async function requestTask(url: string): Promise<BackgroundTask> {
  const task = await request<BackgroundTask>(url, { method: 'POST' })
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('studio-task-created', { detail: task }))
  }
  return task
}

export const breakdownApi = {
  listRuns: (episodeId: string) => request<BreakdownRunSummary[]>(`/api/episodes/${episodeId}/breakdown-runs`),
  getCurrent: (episodeId: string) => request<BreakdownDraftPayload | null>(`/api/episodes/${episodeId}/breakdown-current`),
  getRun: (runId: string) => request<BreakdownDraftPayload>(`/api/breakdown-runs/${runId}`),
  startEpisode: (episodeId: string) => requestTask(`/api/episodes/${episodeId}/tasks/breakdown`),
  startShot: (episodeId: string, shotOrdinal: number) => requestTask(`/api/episodes/${episodeId}/shots/${shotOrdinal}/tasks/breakdown`),
  startBatch: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/breakdown-batch`),
}
