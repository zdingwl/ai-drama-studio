import type { ProjectRemakePolicy, ReviewIssue, ReviewIssueStatus, ScenePolicy } from '../types/remake'

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json()
      message = payload.detail || message
    } catch {
      // Keep the default message for non-JSON errors.
    }
    throw new Error(message)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const jsonHeaders = { 'Content-Type': 'application/json' }

export const remakeApi = {
  getPolicy: (projectId: string) => request<ProjectRemakePolicy>(`/api/projects/${projectId}/remake-policy`),
  updatePolicy: (projectId: string, scenePolicy: ScenePolicy) => request<ProjectRemakePolicy>(`/api/projects/${projectId}/remake-policy`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify({ scene_policy: scenePolicy, generation_engine: 'MINIMAX_H3_LOCAL' }),
  }),
  listReviewIssues: (projectId: string, status: ReviewIssueStatus | '' = 'OPEN') => request<ReviewIssue[]>(
    `/api/projects/${projectId}/review-issues${status ? `?status=${status}` : '?status='}`,
  ),
  setReviewIssueStatus: (issueId: string, status: ReviewIssueStatus, resolution: unknown = null) => request<ReviewIssue>(`/api/review-issues/${issueId}`, {
    method: 'PATCH',
    headers: jsonHeaders,
    body: JSON.stringify({ status, resolution }),
  }),
}
