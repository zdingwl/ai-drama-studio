import { apiRequest } from './http'
import type { CreateProjectPayload, Project } from '../types/project'

/** 首页读取 ready 项目列表。 */
export function fetchProjects(): Promise<Project[]> {
  return apiRequest<Project[]>('/api/projects')
}

/** 提交 F01 新建项目表单。 */
export function createProject(payload: CreateProjectPayload): Promise<Project> {
  return apiRequest<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

/** 真正进入项目；后端会检查 Workspace/project.json 并更新最近打开时间。 */
export function openProjectRequest(projectId: string): Promise<Project> {
  return apiRequest<Project>(`/api/projects/${encodeURIComponent(projectId)}/open`, {
    method: 'POST',
  })
}
