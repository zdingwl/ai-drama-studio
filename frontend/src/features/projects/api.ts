import { apiRequest } from '@/lib/api'

import type { ProjectCreatePayload, ProjectExecutionPlan, ProjectRead, TaskRead } from './types'

export type P4AcceptanceScenario = 'success' | 'retry' | 'resume' | 'dedupe'

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

export function startP4AcceptanceTask(
  projectId: string,
  scenario: P4AcceptanceScenario,
  idempotencyKey: string,
): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/p4-acceptance/${scenario}`, {
    method: 'POST',
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  })
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
