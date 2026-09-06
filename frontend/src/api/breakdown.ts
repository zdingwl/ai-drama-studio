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

const pendingCommands = new Map<string, { key: string; command: unknown }>()
async function requestTask(url: string, contextUrl: string): Promise<BackgroundTask> {
  let pending = pendingCommands.get(url)
  if (!pending) {
    pending = {key: crypto.randomUUID(), command: await request(contextUrl)}
    pendingCommands.set(url, pending)
  }
  const response = await fetch(url, { method: 'POST', headers: {'Content-Type':'application/json','Idempotency-Key':pending.key},
                                     body:JSON.stringify(pending.command) })
  if (!response.ok) {
    // 明确拒绝后允许刷新版本；网络中断保留相同标识，避免重复启动模型。
    if (response.status >= 400 && response.status < 500) pendingCommands.delete(url)
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `任务提交失败（${response.status}）`)
  }
  const task = await response.json() as BackgroundTask
  pendingCommands.delete(url)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('studio-task-created', { detail: task }))
  }
  return task
}

export const breakdownApi = {
  listRuns: (episodeId: string) => request<BreakdownRunSummary[]>(`/api/episodes/${episodeId}/breakdown-runs`),
  getCurrent: (episodeId: string) => request<BreakdownDraftPayload | null>(`/api/episodes/${episodeId}/breakdown-current`),
  getRun: (runId: string) => request<BreakdownDraftPayload>(`/api/breakdown-runs/${runId}`),
  startEpisode: (episodeId: string) => requestTask(`/api/episodes/${episodeId}/tasks/breakdown`, `/api/episodes/${episodeId}/breakdown-command-context`),
  startShot: (episodeId: string, shotOrdinal: number) => requestTask(`/api/episodes/${episodeId}/shots/${shotOrdinal}/tasks/breakdown`, `/api/episodes/${episodeId}/breakdown-command-context?shot_ordinal=${shotOrdinal}`),
  startBatch: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/breakdown-batch`, `/api/projects/${projectId}/breakdown-command-context`),
}
