import { apiRequest } from '@/lib/api'

import type { ProjectCreatePayload, ProjectExecutionPlan, ProjectRead, TaskRead } from './types'

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

export function listProjectTasks(projectId: string): Promise<TaskRead[]> {
  return apiRequest<TaskRead[]>(`/projects/${projectId}/tasks`)
}

export function cancelProjectTask(projectId: string, taskId: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/tasks/${taskId}/commands/cancel`, {
    method: 'POST',
  })
}

export function retryProjectTask(projectId: string, taskId: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/tasks/${taskId}/commands/retry`, {
    method: 'POST',
  })
}

export function resumeProjectTask(projectId: string, taskId: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/tasks/${taskId}/commands/resume`, {
    method: 'POST',
  })
}
