import { apiRequest } from '@/lib/api'

import type { TaskRead } from './types'

export type ReplicaProductAction =
  | 'UPLOAD_SOURCE'
  | 'ANALYZE_SOURCE'
  | 'GENERATE_ADAPTATION'
  | 'REVIEW_ADAPTATION'
  | 'CAST_VOICES'
  | 'REVIEW_AUDIO'
  | 'FIX_DIALOGUE_DURATION'
  | 'GENERATE_VIDEO'
  | 'REVIEW_VIDEO'
  | 'BUILD_FINAL'
  | 'REVIEW_FINAL'
  | 'COMPLETE'

export type ReplicaProductStepStatus = 'WAITING' | 'READY' | 'WORKING' | 'NEEDS_ACTION' | 'COMPLETE' | 'FAILED'

export interface ReplicaProductStep {
  key: string
  title: string
  status: ReplicaProductStepStatus
  summary: string
}

export interface ReplicaProductWorkflow {
  project_id: string
  next_action: ReplicaProductAction
  headline: string
  description: string
  progress_percent: number
  active_task: TaskRead | null
  last_error: string | null
  steps: ReplicaProductStep[]
  pending: {
    target_assets_candidate_id: string | null
    target_audio_candidate_id: string | null
    timing_candidate_id: string | null
    video_candidate_id: string | null
    final_candidate_id: string | null
    timing_overflow_count: number
  }
}

export function getReplicaWorkflow(projectId: string): Promise<ReplicaProductWorkflow> {
  return apiRequest<ReplicaProductWorkflow>(`/projects/${projectId}/replica-workflow`, { cache: 'no-store' })
}

function startReplicaProductCommand(projectId: string, command: string): Promise<TaskRead> {
  return apiRequest<TaskRead>(`/projects/${projectId}/commands/${command}`, {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
  })
}

export const startReplicaAdaptation = (projectId: string) => startReplicaProductCommand(projectId, 'replica-adaptation')
export const startReplicaGeneration = (projectId: string) => startReplicaProductCommand(projectId, 'replica-generation')
export const startReplicaFinalOutput = (projectId: string) => startReplicaProductCommand(projectId, 'replica-final-output')
