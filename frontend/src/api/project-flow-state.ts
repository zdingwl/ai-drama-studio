import type { ProjectFlowState } from '../types/project-flow-state'

async function readError(response: Response): Promise<string> {
  try {
    const payload = await response.json() as { detail?: unknown }
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail
    if (payload.detail && typeof payload.detail === 'object') {
      const detail = payload.detail as { message?: unknown }
      if (typeof detail.message === 'string' && detail.message.trim()) return detail.message
    }
  } catch {
    // fall through
  }
  return `请求失败（${response.status}）`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function validateFlowState(value: unknown, projectId: string): ProjectFlowState {
  if (!isRecord(value)) {
    throw new Error('工作流状态接口返回格式异常：预期为对象')
  }
  if (value.schema_version !== 'project-flow-state-v1') {
    throw new Error(`工作流状态接口版本异常：${String(value.schema_version || '缺失')}`)
  }
  if (typeof value.project_id !== 'string' || value.project_id !== projectId) {
    throw new Error('工作流状态接口返回了错误的项目标识')
  }
  if (!Array.isArray(value.stages)) {
    throw new Error('工作流状态接口返回格式异常：stages 不是数组')
  }
  if (!Array.isArray(value.episodes)) {
    throw new Error('工作流状态接口返回格式异常：episodes 不是数组')
  }
  if (!isRecord(value.next_action)) {
    throw new Error('工作流状态接口返回格式异常：缺少 next_action')
  }

  for (const [index, stage] of value.stages.entries()) {
    if (!isRecord(stage) || typeof stage.stage_key !== 'string') {
      throw new Error(`工作流状态接口返回格式异常：第 ${index + 1} 个阶段缺少 stage_key`)
    }
  }
  for (const [index, episode] of value.episodes.entries()) {
    if (!isRecord(episode) || typeof episode.episode_id !== 'string') {
      throw new Error(`工作流状态接口返回格式异常：第 ${index + 1} 个剧集缺少 episode_id`)
    }
  }

  return value as unknown as ProjectFlowState
}

export async function getProjectFlowState(projectId: string): Promise<ProjectFlowState> {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/flow-state`)
  if (!response.ok) throw new Error(await readError(response))
  const payload: unknown = await response.json()
  return validateFlowState(payload, projectId)
}
