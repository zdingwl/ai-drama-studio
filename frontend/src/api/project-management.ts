import type { ManagedProject, ProjectManagementPayload } from '../types/project-management'

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
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const jsonHeaders = { 'Content-Type': 'application/json' }
const baseUrl = '/api/project-management/projects'

export const projectManagementApi = {
  listProjects: () => request<ManagedProject[]>(baseUrl),
  getProject: (projectId: string) => request<ManagedProject>(`${baseUrl}/${projectId}`),
  createProject: (payload: ProjectManagementPayload) => request<ManagedProject>(baseUrl, {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  }),
  updateProject: (projectId: string, payload: ProjectManagementPayload) => request<ManagedProject>(`${baseUrl}/${projectId}`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  }),
  deleteProject: (projectId: string) => request<void>(`${baseUrl}/${projectId}`, {
    method: 'DELETE',
  }),
}
