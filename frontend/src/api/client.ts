import type { BackgroundTask, ContentAnalysisRun, Episode, F05ModelStatus, Project, ProjectCreatePayload, Shot } from '../types/studio'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // 非 JSON 错误保持默认文案。
    }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  listProjects: () => request<Project[]>('/api/projects'),
  getProject: (projectId: string) => request<Project>(`/api/projects/${projectId}`),
  createProject: (payload: ProjectCreatePayload) => request<Project>('/api/projects', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
  }),
  uploadEpisodes: (projectId: string, files: File[]) => {
    const body = new FormData()
    files.forEach((file) => body.append('files', file))
    return request<Episode[]>(`/api/projects/${projectId}/episodes/batch`, { method: 'POST', body })
  },
  reorderEpisodes: (projectId: string, episodeIds: string[]) => request<Episode[]>(`/api/projects/${projectId}/episodes/reorder`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ episode_ids: episodeIds }),
  }),
  deleteEpisode: (episodeId: string) => request<void>(`/api/episodes/${episodeId}`, { method: 'DELETE' }),

  // 正式 UI：耗时操作全部立即返回 BackgroundTask，不再让 HTTP 请求一直挂着。
  preprocessEpisode: (episodeId: string) => request<BackgroundTask>(`/api/episodes/${episodeId}/tasks/preprocess`, { method: 'POST' }),
  preprocessBatch: (projectId: string) => request<BackgroundTask>(`/api/projects/${projectId}/tasks/preprocess-batch`, { method: 'POST' }),
  analyzeEpisodeShots: (episodeId: string) => request<BackgroundTask>(`/api/episodes/${episodeId}/tasks/shots`, { method: 'POST' }),
  analyzeBatchShots: (projectId: string) => request<BackgroundTask>(`/api/projects/${projectId}/tasks/shots-batch`, { method: 'POST' }),
  runContentAnalysis: (projectId: string) => request<BackgroundTask>(`/api/projects/${projectId}/tasks/assets`, { method: 'POST' }),
  listShots: (episodeId: string) => request<Shot[]>(`/api/episodes/${episodeId}/shots`),

  // 显式 Task API，给后续独立工作区复用。
  startEpisodePreprocessTask: (episodeId: string) => request<BackgroundTask>(`/api/episodes/${episodeId}/tasks/preprocess`, { method: 'POST' }),
  startBatchPreprocessTask: (projectId: string) => request<BackgroundTask>(`/api/projects/${projectId}/tasks/preprocess-batch`, { method: 'POST' }),
  startEpisodeShotsTask: (episodeId: string) => request<BackgroundTask>(`/api/episodes/${episodeId}/tasks/shots`, { method: 'POST' }),
  startBatchShotsTask: (projectId: string) => request<BackgroundTask>(`/api/projects/${projectId}/tasks/shots-batch`, { method: 'POST' }),
  startAssetExtractionTask: (projectId: string) => request<BackgroundTask>(`/api/projects/${projectId}/tasks/assets`, { method: 'POST' }),
  listProjectTasks: (projectId: string, limit = 30) => request<BackgroundTask[]>(`/api/projects/${projectId}/tasks?limit=${limit}`),
  getTask: (taskId: string) => request<BackgroundTask>(`/api/tasks/${taskId}`),

  // 同步兼容接口仅供测试/调试，不给正式页面使用。
  preprocessEpisodeSync: (episodeId: string) => request(`/api/episodes/${episodeId}/preprocess`, { method: 'POST' }),
  preprocessBatchSync: (projectId: string) => request(`/api/projects/${projectId}/preprocess-batch`, { method: 'POST' }),
  analyzeEpisodeShotsSync: (episodeId: string) => request<Shot[]>(`/api/episodes/${episodeId}/shots/analyze`, { method: 'POST' }),
  analyzeBatchShotsSync: (projectId: string) => request(`/api/projects/${projectId}/shots/analyze-batch`, { method: 'POST' }),
  runContentAnalysisSync: (projectId: string) => request<ContentAnalysisRun>(`/api/projects/${projectId}/content-analysis`, { method: 'POST' }),

  getF05ModelStatus: () => request<F05ModelStatus>('/api/models/f05/status'),
  prepareF05Models: () => request<F05ModelStatus>('/api/models/f05/prepare', { method: 'POST' }),
  getCurrentContentAnalysis: (projectId: string) => request<ContentAnalysisRun | null>(`/api/projects/${projectId}/content-analysis/current`),
  getContentAnalysis: (runId: string) => request<ContentAnalysisRun>(`/api/content-analysis/${runId}`),
}
