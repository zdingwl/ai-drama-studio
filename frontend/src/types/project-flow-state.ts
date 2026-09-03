export type FlowValidity = 'NOT_BUILT' | 'CURRENT' | 'STALE'
export type FlowReadiness = 'READY' | 'BLOCKED_REVIEW' | 'BLOCKED_DEPENDENCY' | 'WAITING_RUNTIME'
export type FlowExecution = 'IDLE' | 'QUEUED' | 'PROCESSING' | 'SUCCEEDED' | 'FAILED' | 'INTERRUPTED'
export type FlowOverallStatus =
  | 'PROCESSING'
  | 'BLOCKED_REVIEW'
  | 'BLOCKED_DEPENDENCY'
  | 'WAITING_RUNTIME'
  | 'READY_TO_CONTINUE'
  | 'FAILED'
  | 'COMPLETE'

export interface ProjectFlowActiveCommand {
  task_id: string
  task_type: string
  execution: FlowExecution
  title: string
  stage_key: string | null
  stage_label: string | null
  progress_mode: string | null
  progress_percent: number | null
  message: string | null
  updated_at: string | null
}

export interface ProjectFlowNextAction {
  action_key: string
  kind: 'NONE' | 'NAVIGATE' | 'COMMAND' | 'WAIT' | 'RETRY'
  label: string
  reason: string
  enabled: boolean
  target_surface: 'PROJECT' | 'REVIEW' | 'OUTPUT' | null
  command_key: 'PREPARE_REMAKE' | 'H3_GENERATE_READY' | 'POSTPRODUCTION' | null
}

export interface ProjectFlowEpisode {
  episode_id: string
  sort_order: number
  title: string
  preprocess_status: string | null
  shot_count: number
  current_shot_revision_id: string | null
  current_breakdown_run_id: string | null
}

export interface ProjectFlowStage {
  stage_key: string
  ordinal: number
  label: string
  validity: FlowValidity
  readiness: FlowReadiness
  execution: FlowExecution
  consumable: boolean
  reason_code: string
  reason: string
  current_input_fingerprint: string | null
  built_input_fingerprint: string | null
  metrics: Record<string, unknown>
  open_review_cases: number
  active_command: ProjectFlowActiveCommand | null
  warnings: string[]
  last_success: string | null
}

export interface ProjectFlowState {
  schema_version: 'project-flow-state-v1'
  project_id: string
  revision: string
  generated_at: string
  overall_status: FlowOverallStatus
  can_continue: boolean
  next_action: ProjectFlowNextAction
  active_command: ProjectFlowActiveCommand | null
  review_summary: {
    open_count: number
    blocking_count: number
    by_type: Record<string, number>
  }
  runtime_summary: {
    blocking_runtime_count: number
    items: Array<{
      key: string
      label: string
      checked: boolean
      ready: boolean | null
      reason_code: string | null
      detail: string | null
    }>
  }
  episodes: ProjectFlowEpisode[]
  stages: ProjectFlowStage[]
}
