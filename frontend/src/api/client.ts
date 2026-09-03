import type {
  AssetEntityType,
  AssetSemanticModelStatus,
  AssetWorkspace,
  BackgroundTask,
  BatchShotAssetBindings,
  CharacterGalleryPayload,
  ContentAnalysisRun,
  Episode,
  F05ModelStatus,
  Project,
  ProjectCreatePayload,
  Shot,
  ShotAssetBindings,
  ShotRevision,
} from '../types/studio'

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function isBackgroundTask(value: unknown): value is BackgroundTask {
  if (!isRecord(value)) return false
  return typeof value.id === 'string'
    && value.id.length > 0
    && typeof value.project_id === 'string'
    && typeof value.task_type === 'string'
    && typeof value.title === 'string'
    && typeof value.status === 'string'
}

async function requestProjectTaskSummaries(projectId: string, limit: number): Promise<BackgroundTask[]> {
  const safeLimit = Math.max(1, Math.min(100, Math.trunc(limit || 30)))
  const payload = await request<unknown>(`/api/projects/${encodeURIComponent(projectId)}/task-summaries?limit=${safeLimit}`)
  if (!Array.isArray(payload)) {
    throw new Error('后台任务接口返回格式异常：预期为任务数组')
  }
  for (const [index, task] of payload.entries()) {
    if (!isBackgroundTask(task)) {
      throw new Error(`后台任务接口返回格式异常：第 ${index + 1} 项缺少任务基础字段`)
    }
  }
  return payload
}

/**
 * 创建后台任务后立即通知全局任务中心，避免低频轮询造成“点击没反应”的错觉。
 */
async function requestTask(url: string, options?: RequestInit): Promise<BackgroundTask> {
  const task = await request<BackgroundTask>(url, options)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('studio-task-created', { detail: task }))
  }
  return task
}

/**
 * Final Asset / Binding 写入成功后，以后端返回的 AssetWorkspace 作为最新事实通知项目壳刷新。
 * 这里只通知“事实已变化”，不在 API 层推断任何阶段状态。
 */
async function requestAssetWorkspaceWrite(url: string, options?: RequestInit): Promise<AssetWorkspace> {
  const workspace = await request<AssetWorkspace>(url, options)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('studio-project-truth-changed', {
      detail: { project_id: workspace.project_id },
    }))
  }
  return workspace
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export const api = {
  listProjects: () => request<Project[]>('/api/projects'),
  getProject: (projectId: string) => request<Project>(`/api/projects/${projectId}`),
  createProject: (payload: ProjectCreatePayload) => request<Project>('/api/projects', {
    method: 'POST', headers: jsonHeaders, body: JSON.stringify(payload),
  }),
  uploadEpisodes: (projectId: string, files: File[]) => {
    const body = new FormData()
    files.forEach((file) => body.append('files', file))
    return request<Episode[]>(`/api/projects/${projectId}/episodes/batch`, { method: 'POST', body })
  },
  reorderEpisodes: (projectId: string, episodeIds: string[]) => request<Episode[]>(`/api/projects/${projectId}/episodes/reorder`, {
    method: 'PATCH', headers: jsonHeaders, body: JSON.stringify({ episode_ids: episodeIds }),
  }),
  deleteEpisode: (episodeId: string) => request<void>(`/api/episodes/${episodeId}`, { method: 'DELETE' }),

  // 正式 UI：耗时操作全部立即返回 BackgroundTask，并立刻通知全局任务栏。
  preprocessEpisode: (episodeId: string) => requestTask(`/api/episodes/${episodeId}/tasks/preprocess`, { method: 'POST' }),
  preprocessBatch: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/preprocess-batch`, { method: 'POST' }),
  analyzeEpisodeShots: (episodeId: string) => requestTask(`/api/episodes/${episodeId}/tasks/shots`, { method: 'POST' }),
  analyzeBatchShots: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/shots-batch`, { method: 'POST' }),
  runContentAnalysis: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/assets`, { method: 'POST' }),
  listShots: (episodeId: string) => request<Shot[]>(`/api/episodes/${episodeId}/shots`),

  // Shot 人工修正：修改当前生产 Shot；每次成功修改后后端创建新的 MANUAL Revision。
  adjustShotBoundary: (shotId: string, side: 'start' | 'end', sourceTimeUs: number) => request<Shot[]>(`/api/shots/${shotId}/boundary`, {
    method: 'PATCH', headers: jsonHeaders, body: JSON.stringify({ side, source_time_us: sourceTimeUs }),
  }),
  splitShot: (shotId: string, sourceTimeUs: number) => request<Shot[]>(`/api/shots/${shotId}/split`, {
    method: 'POST', headers: jsonHeaders, body: JSON.stringify({ source_time_us: sourceTimeUs }),
  }),
  mergeShotWithNext: (shotId: string) => request<Shot[]>(`/api/shots/${shotId}/merge-next`, { method: 'POST' }),

  // Shot Revision：历史只读；restore 会创建新的 RESTORE Revision，不覆盖历史。
  listShotRevisions: (episodeId: string) => request<ShotRevision[]>(`/api/episodes/${episodeId}/shot-revisions`),
  getShotRevision: (revisionId: string) => request<ShotRevision>(`/api/shot-revisions/${revisionId}`),
  restoreShotRevision: (revisionId: string) => request<Shot[]>(`/api/shot-revisions/${revisionId}/restore`, { method: 'POST' }),

  // 03 Final Asset 工作台：AI Evidence 与人工 Final Asset 完全分层。
  getAssetWorkspace: (projectId: string) => request<AssetWorkspace>(`/api/projects/${projectId}/assets/workspace`),
  getAssetSemanticModelStatus: () => request<AssetSemanticModelStatus>('/api/assets/models/status'),
  getCharacterGallery: (candidateId: string) => request<CharacterGalleryPayload>(`/api/content-analysis/characters/${candidateId}/gallery`),
  startFullAssetExtractionTask: (projectId: string) => requestTask(`/api/projects/${projectId}/assets/tasks/extract`, { method: 'POST' }),
  applyLatestAssetAnalysis: (projectId: string) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets/apply-analysis`, { method: 'POST' }),
  setShotAssetBindings: (projectId: string, shotId: string, payload: ShotAssetBindings) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets/shots/${shotId}/bindings`, {
    method: 'PUT', headers: jsonHeaders, body: JSON.stringify(payload),
  }),
  batchSetShotAssetBindings: (projectId: string, payload: BatchShotAssetBindings) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets/bindings/batch`, {
    method: 'PUT', headers: jsonHeaders, body: JSON.stringify(payload),
  }),
  createFinalAsset: (projectId: string, entityType: AssetEntityType, name: string, shotId?: string | null) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets`, {
    method: 'POST', headers: jsonHeaders, body: JSON.stringify({ entity_type: entityType, name, shot_id: shotId || null }),
  }),
  renameFinalAsset: (projectId: string, entityType: AssetEntityType, entityId: string, name: string) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets/${entityType}/${entityId}`, {
    method: 'PATCH', headers: jsonHeaders, body: JSON.stringify({ name }),
  }),
  deleteFinalAsset: (projectId: string, entityType: AssetEntityType, entityId: string) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets/${entityType}/${entityId}`, {
    method: 'DELETE',
  }),
  mergeFinalAssets: (projectId: string, entityType: AssetEntityType, entityIds: string[], targetId?: string | null) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets/merge`, {
    method: 'POST', headers: jsonHeaders, body: JSON.stringify({ entity_type: entityType, entity_ids: entityIds, target_id: targetId || null }),
  }),
  splitFinalAsset: (projectId: string, entityType: AssetEntityType, entityId: string, shotIds: string[], newName?: string | null) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets/${entityType}/${entityId}/split`, {
    method: 'POST', headers: jsonHeaders, body: JSON.stringify({ entity_type: entityType, shot_ids: shotIds, new_name: newName || null }),
  }),
  setFinalAssetCover: (projectId: string, entityType: AssetEntityType, entityId: string, coverUrl: string) => requestAssetWorkspaceWrite(`/api/projects/${projectId}/assets/${entityType}/${entityId}/cover`, {
    method: 'PATCH', headers: jsonHeaders, body: JSON.stringify({ cover_url: coverUrl }),
  }),
  restoreAssetRevision: (revisionId: string) => requestAssetWorkspaceWrite(`/api/asset-revisions/${revisionId}/restore`, { method: 'POST' }),

  // 显式 Task API，给各工作区复用。列表使用轻量摘要，单 Task 详情仍返回完整 result。
  startEpisodePreprocessTask: (episodeId: string) => requestTask(`/api/episodes/${episodeId}/tasks/preprocess`, { method: 'POST' }),
  startBatchPreprocessTask: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/preprocess-batch`, { method: 'POST' }),
  startEpisodeShotsTask: (episodeId: string) => requestTask(`/api/episodes/${episodeId}/tasks/shots`, { method: 'POST' }),
  startBatchShotsTask: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/shots-batch`, { method: 'POST' }),
  startAssetExtractionTask: (projectId: string) => requestTask(`/api/projects/${projectId}/tasks/assets`, { method: 'POST' }),
  listProjectTasks: (projectId: string, limit = 30) => requestProjectTaskSummaries(projectId, limit),
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
