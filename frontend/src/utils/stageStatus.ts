export type StudioStageState = 'not_started' | 'processing' | 'review' | 'completed' | 'blocked' | 'planned'

export interface StageEpisodeLike {
  shot_count: number
  preprocess_status?: string | null
}

export interface StageTaskLike {
  task_type: string
  status: string
  created_at: string
}

export interface StageAnalysisLike {
  status: string
  counts?: Record<string, number>
}

export interface StageStatusContext {
  episodes: StageEpisodeLike[]
  tasks: StageTaskLike[]
  analysis: StageAnalysisLike | null
}

const SHOT_TASK_TYPES = new Set(['EPISODE_SHOTS', 'BATCH_SHOTS'])
const BREAKDOWN_TASK_TYPES = new Set(['EPISODE_BREAKDOWN_P2', 'BATCH_BREAKDOWN_P2'])
const STAGE_TWO_TASK_TYPES = new Set([...SHOT_TASK_TYPES, ...BREAKDOWN_TASK_TYPES])
const ASSET_TASK_TYPES = new Set(['ASSET_EXTRACTION_V3'])
const ACTIVE_STATUSES = new Set(['QUEUED', 'PROCESSING'])

export const stageStateLabels: Record<StudioStageState, string> = {
  not_started: '未开始',
  processing: '处理中',
  review: '待复核',
  completed: '已完成',
  blocked: '阻塞',
  planned: '规划中',
}

function latestTask(tasks: StageTaskLike[], acceptedTypes: Set<string>): StageTaskLike | null {
  return tasks
    .filter((task) => acceptedTypes.has(task.task_type))
    .slice()
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0] ?? null
}

function sourceStageState(episodes: StageEpisodeLike[]): StudioStageState {
  if (!episodes.length) return 'not_started'
  const statuses = episodes.map((episode) => (episode.preprocess_status || '').toUpperCase())
  if (statuses.some((status) => ACTIVE_STATUSES.has(status))) return 'processing'
  if (statuses.some((status) => status === 'FAILED')) return 'blocked'
  if (statuses.some((status) => status === 'READY_WITH_WARNINGS')) return 'review'
  return 'completed'
}

function breakdownStageState(episodes: StageEpisodeLike[], tasks: StageTaskLike[]): StudioStageState {
  const latestStageTask = latestTask(tasks, STAGE_TWO_TASK_TYPES)
  const latestBreakdownTask = latestTask(tasks, BREAKDOWN_TASK_TYPES)
  const hasShots = episodes.some((episode) => episode.shot_count > 0)

  if (latestStageTask && ACTIVE_STATUSES.has(latestStageTask.status)) return 'processing'
  if (latestStageTask?.status === 'FAILED') return 'blocked'
  if (latestStageTask?.status === 'READY_WITH_WARNINGS') return 'review'

  const breakdownIsLatest = Boolean(
    latestBreakdownTask
    && latestStageTask
    && latestBreakdownTask.created_at === latestStageTask.created_at
    && latestBreakdownTask.task_type === latestStageTask.task_type,
  )
  if (breakdownIsLatest && latestBreakdownTask?.status === 'READY' && hasShots) return 'completed'
  if (hasShots) return 'review'
  return 'not_started'
}

function assetStageState(analysis: StageAnalysisLike | null, tasks: StageTaskLike[]): StudioStageState {
  const task = latestTask(tasks, ASSET_TASK_TYPES)
  if (task && ACTIVE_STATUSES.has(task.status)) return 'processing'
  if (task?.status === 'FAILED') return 'blocked'
  if (task?.status === 'READY_WITH_WARNINGS') return 'review'

  if (!analysis) return task?.status === 'READY' ? 'review' : 'not_started'
  const status = analysis.status.toUpperCase()
  if (ACTIVE_STATUSES.has(status)) return 'processing'
  if (status === 'FAILED') return 'blocked'
  if (status === 'READY_WITH_WARNINGS') return 'review'
  if (status !== 'READY') return 'review'

  const unresolved = Number(analysis.counts?.unresolved_character_candidates || 0)
  return unresolved > 0 ? 'review' : 'completed'
}

export function deriveStageStates(context: StageStatusContext): Record<number, StudioStageState> {
  return {
    1: sourceStageState(context.episodes),
    2: breakdownStageState(context.episodes, context.tasks),
    3: assetStageState(context.analysis, context.tasks),
    4: 'planned',
    5: 'planned',
    6: 'planned',
  }
}
