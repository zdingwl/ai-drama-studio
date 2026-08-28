import type { BreakdownDraftPayload, BreakdownRunSummary } from '../types/breakdown'

/**
 * P3 Breakdown Draft 只读请求入口。
 *
 * 与现有正式 Studio 一样使用相对 `/api`，由 Vite dev proxy 或生产同源服务转发。
 * 本模块不暴露任何 create/publish/inference 写接口，避免 UI 读取历史 Draft 时改变业务状态。
 */
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

export const breakdownApi = {
  listRuns: (episodeId: string) => request<BreakdownRunSummary[]>(`/api/episodes/${episodeId}/breakdown-runs`),
  getCurrent: (episodeId: string) => request<BreakdownDraftPayload | null>(`/api/episodes/${episodeId}/breakdown-current`),
  getRun: (runId: string) => request<BreakdownDraftPayload>(`/api/breakdown-runs/${runId}`),
}
