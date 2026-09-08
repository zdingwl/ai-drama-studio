import { apiRequest } from '@/lib/api'

import type { ProjectCreatePayload, ProjectExecutionPlan, ProjectRead } from './types'

export function listProjects(): Promise<ProjectRead[]> {
  return apiRequest<ProjectRead[]>('/projects')
}

export function createProject(payload: ProjectCreatePayload): Promise<ProjectRead> {
  return apiRequest<ProjectRead>('/projects', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function getProject(projectId: string): Promise<ProjectRead> {
  return apiRequest<ProjectRead>(`/projects/${projectId}`)
}

export function getProjectPlan(projectId: string): Promise<ProjectExecutionPlan> {
  return apiRequest<ProjectExecutionPlan>(`/projects/${projectId}/plan`)
}
