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

export async function getProjectFlowState(projectId: string): Promise<ProjectFlowState> {
  const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}/flow-state`)
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<ProjectFlowState>
}
