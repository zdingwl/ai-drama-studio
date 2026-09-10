import { reactive } from 'vue'

import { apiRequest } from '@/lib/api'

import type {
  DialogueManualAdjudicationPayload,
  EpisodeRead,
  EpisodeShotBoundaryRead,
  EpisodeSourceEvidenceRead,
  ProjectCreatePayload,
  ProjectExecutionPlan,
  ProjectRead,
  ProjectUpdatePayload,
  TaskRead,
} from './types'

export type P4AcceptanceScenario = 'success' | 'retry' | 'resume' | 'dedupe'

type ProjectWithPlanPointer = ProjectRead & {
  current_plan_id?: string | null
}

const projectReadInFlight = new Map<string, Promise<ProjectRead>>()
const projectTaskSnapshots = new Map<string, TaskRead[]>()

function projectTaskSnapshot(projectId: string): TaskRead[] {
  const existing = projectTaskSnapshots.get(projectId)
  if (existing) return existing

  const snapshot = reactive([] as TaskRead[]) as TaskRead[]
  projectTaskSnapshots.set(projectId, snapshot)
  return snapshot
}

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
  const inFlight = projectReadInFlight.get(projectId)
  if (inFlight) return inFlight

  let request: Promise<ProjectRead>
  request = apiRequest<ProjectRead>(`/projects/${projectId}`).finally(() => {
    if (projectReadInFlight.get(projectId) === request) {
      projectReadInFlight.delete(projectId)
    }
  })
  projectReadInFlight.set(projectId, request)
  return request
}

export async function getProjectPlan(projectId: string): Promise<ProjectExecutionPlan | null> {
  // ProjectRead already carries the persisted CURRENT plan pointer. When it is
  // explicitly null, PLAN_NOT_COMPILED is an expected business state rather
  // than an exceptional network request. Reuse the in-flight project read from
  // workspace loading, keep GET read-only, and avoid a noisy /plan 404.
  const project = await getProject(projectId) as ProjectWithPlanPointer
  if (project.current_plan_id === null) return null

  // `undefined` keeps compatibility with older/mock ProjectRead payloads that
  // predate current_plan_id; those callers still use the canonical /plan GET.
  return apiRequest<ProjectExecutionPlan>(`/projects/${projectId}/plan`)
}

export function updateProject(projectId: string, payload: ProjectUpdatePayload): Promise<ProjectRead> {
  return apiRequest<ProjectRead>(`/projects/${projectId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  })
}

export function listProjectEpisodes(projectId: string): Promise<EpisodeRead[]> {
  return apiRequest<EpisodeRead[]>(`/projects/${projectId}/sources/episodes`)
}

export function getEpisodeShotBoundary(projectId: string, episodeId: string): Promise<EpisodeShotBoundaryRead> {
  return apiRequest<EpisodeShotBoundaryRead>(`/projects/${projectId}/episodes/${episodeId}/shot-boundary`)
}

export function startEpisodeShotBoundary(
  projectId: string,
  episodeId: string,
  idempotencyKey: string,
): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/episodes/${episodeId}/commands/shot-boundary`, {
    method: 'POST',
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  })
}

export function getEpisodeSourceEvidence(projectId: string, episodeId: string): Promise<EpisodeSourceEvidenceRead> {
  return apiRequest<EpisodeSourceEvidenceRead>(`/projects/${projectId}/episodes/${episodeId}/source-evidence`)
}

export function startEpisodeSourceEvidence(
  projectId: string,
  episodeId: string,
  idempotencyKey: string,
): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/episodes/${episodeId}/commands/source-evidence`, {
    method: 'POST',
    headers: {
      'Idempotency-Key': idempotencyKey,
    },
  })
}

export function adjudicateEpisodeDialogue(
  projectId: string,
  episodeId: string,
  payload: DialogueManualAdjudicationPayload,
  idempotencyKey: string,
): Promise<EpisodeSourceEvidenceRead> {
  return apiRequest<EpisodeSourceEvidenceRead>(
    `/projects/${projectId}/episodes/${episodeId}/source-evidence/commands/adjudicate-dialogue`,
    {
      method: 'POST',
      headers: {
        'Idempotency-Key': idempotencyKey,
      },
      body: JSON.stringify(payload),
    },
  )
}

export async function listProjectTasks(projectId: string): Promise<TaskRead[]> {
  // P6/P7/P8 acceptance panels and the workspace task card are sibling views.
  // Keep one reactive snapshot per project so any consumer that polls the
  // canonical task endpoint updates every other consumer immediately. The GET
  // is explicitly no-store because task progress is mutable runtime state.
  const rows = await apiRequest<TaskRead[]>(`/projects/${projectId}/tasks`, {
    cache: 'no-store',
  })
  const snapshot = projectTaskSnapshot(projectId)
  snapshot.splice(0, snapshot.length, ...rows)
  return snapshot
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
