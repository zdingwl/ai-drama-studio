<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { projectManagementApi } from '../api/project-management'
import {
  listProjectSourceVideos,
  replaceEpisodeWithProgress,
  uploadEpisodeWithProgress,
  type SourceVideoEpisode,
} from '../api/source-video-management'
import { projectLanguageLabel, projectRegionLabel } from '../constants/projectOptions'
import type { ManagedProject, ProjectRedrawRule } from '../types/project-management'
import type { ProjectFlowStage, ProjectFlowState } from '../types/project-flow-state'
import type { BackgroundTask } from '../types/studio'

type ProcessState = 'not_started' | 'blocked' | 'queued' | 'processing' | 'completed' | 'failed' | 'review'
type UploadItemStatus = 'pending' | 'uploading' | 'failed'
type StageVisualState = 'active' | 'complete' | 'processing' | 'review' | 'blocked' | 'ready' | 'waiting'

interface UploadItem {
  id: string
  file: File
  progress: number
  status: UploadItemStatus
  error: string
}

interface ProcessStatusDisplay {
  state: ProcessState
  label: string
  detail: string
}

interface StageGroupDisplay {
  number: number
  label: string
  description: string
  statusLabel: string
  reason: string
  state: StageVisualState
  active: boolean
}

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))

const videos = ref<SourceVideoEpisode[]>([])
const managedProject = ref<ManagedProject | null>(null)
const flowState = ref<ProjectFlowState | null>(null)
const tasks = ref<BackgroundTask[]>([])
const loading = ref(true)
const pageError = ref('')
const actionError = ref('')

const uploadOpen = ref(false)
const uploadItems = ref<UploadItem[]>([])
const uploadRunning = ref(false)
const uploadDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const replaceTarget = ref<SourceVideoEpisode | null>(null)
const replaceFile = ref<File | null>(null)
const replaceProgress = ref(0)
const replaceRunning = ref(false)
const replaceError = ref('')
const replaceFileInput = ref<HTMLInputElement | null>(null)

const deleteTarget = ref<SourceVideoEpisode | null>(null)
const deleting = ref(false)
const detectingEpisodeId = ref<string | null>(null)
const batchDetecting = ref(false)
const optimisticQueuedEpisodeIds = ref<Set<string>>(new Set())
const draggingEpisodeId = ref<string | null>(null)
const dragOverEpisodeId = ref<string | null>(null)
const reorderSaving = ref(false)

let pollingTimer: ReturnType<typeof setTimeout> | null = null
let refreshInFlight = false
let disposed = false

const redrawRuleLabels: Record<ProjectRedrawRule, string> = {
  CHARACTER: '人物',
  SCENE: '场景',
  LANGUAGE: '语言',
}

const episodes = computed(() => [...videos.value].sort((a, b) => a.sort_order - b.sort_order))
const totalDurationUs = computed(() => episodes.value.reduce((sum, item) => sum + Math.max(0, item.duration_us || 0), 0))
const currentProjectName = computed(() => managedProject.value?.name || '项目')
const sourceLanguage = computed(() => managedProject.value?.source_language || '')
const targetLanguage = computed(() => managedProject.value?.target_language || '')
const targetRegion = computed(() => managedProject.value?.target_region || '')
const redrawRules = computed(() => managedProject.value?.redraw_rules || [])
const uploadFailedCount = computed(() => uploadItems.value.filter((item) => item.status === 'failed').length)
const uploadPendingCount = computed(() => uploadItems.value.filter((item) => item.status === 'pending').length)
const uploadActionLabel = computed(() => {
  if (uploadRunning.value) return '正在上传…'
  if (uploadFailedCount.value > 0 && uploadPendingCount.value === 0) return '重试失败视频'
  return `开始上传${uploadItems.value.length ? `（${uploadItems.value.length}）` : ''}`
})

const projectHasActiveTask = computed(() => tasks.value.some((task) => task.status === 'QUEUED' || task.status === 'PROCESSING'))
const sourceSplitStage = computed(() => flowState.value?.stages.find((stage) => stage.stage_key === 'source_split') || null)
const sourceUnderstandingStage = computed(() => flowState.value?.stages.find((stage) => stage.stage_key === 'source_understanding') || null)
const sourceSplitReady = computed(() => sourceSplitStage.value?.consumable === true)
const overallProgress = computed(() => {
  const stages = flowState.value?.stages || []
  if (!stages.length) return 0
  const complete = stages.filter((stage) => stage.consumable).length
  return Math.max(0, Math.min(100, Math.round((complete / stages.length) * 100)))
})

const flowEpisodesById = computed(() => new Map(
  (flowState.value?.episodes || []).map((episode) => [episode.episode_id, episode]),
))

const stageGroups = computed<StageGroupDisplay[]>(() => [
  buildStageGroup(1, '原短剧视频', '上传、排序与镜头检测', ['project_setup', 'source_split'], true),
  buildStageGroup(2, 'AI 拉片', '剧情、对白与镜头理解', ['source_understanding']),
  buildStageGroup(3, '原片确认', '人物 / 场景 / 道具确认', ['source_assets', 'source_snapshot']),
  buildStageGroup(4, '视频重做', '本土化、配音与视频生成', ['target_design', 'target_dialogue', 'remake_timing', 'h3_generation']),
  buildStageGroup(5, '成片输出', '后期检查与最终导出', ['postproduction_output']),
])

function buildStageGroup(
  number: number,
  label: string,
  description: string,
  stageKeys: string[],
  active = false,
): StageGroupDisplay {
  const stages = stageKeys
    .map((key) => flowState.value?.stages.find((stage) => stage.stage_key === key))
    .filter((stage): stage is ProjectFlowStage => Boolean(stage))

  if (!stages.length) {
    return { number, label, description, statusLabel: active ? '当前阶段' : '等待状态', reason: '', state: active ? 'active' : 'waiting', active }
  }

  const allComplete = stages.every((stage) => stage.consumable)
  const processing = stages.some((stage) => stage.execution === 'QUEUED' || stage.execution === 'PROCESSING')
  const review = stages.some((stage) => stage.readiness === 'BLOCKED_REVIEW')
  const blocked = stages.some((stage) => stage.readiness === 'BLOCKED_DEPENDENCY' || stage.readiness === 'WAITING_RUNTIME')
  const ready = stages.some((stage) => stage.readiness === 'READY' && !stage.consumable)
  const firstProblem = stages.find((stage) => !stage.consumable) || stages[stages.length - 1]

  let state: StageVisualState = 'waiting'
  let statusLabel = '待开始'
  if (allComplete) {
    state = active ? 'active' : 'complete'
    statusLabel = '已完成'
  } else if (processing) {
    state = active ? 'active' : 'processing'
    statusLabel = '处理中'
  } else if (review) {
    state = active ? 'active' : 'review'
    statusLabel = '待确认'
  } else if (blocked) {
    state = active ? 'active' : 'blocked'
    statusLabel = '未解锁'
  } else if (ready) {
    state = active ? 'active' : 'ready'
    statusLabel = active ? '进行中' : '可开始'
  } else if (active) {
    state = 'active'
    statusLabel = '进行中'
  }

  return {
    number,
    label,
    description,
    statusLabel,
    reason: firstProblem?.reason || '',
    state,
    active,
  }
}

function formatDuration(durationUs: number | null): string {
  if (!durationUs || durationUs <= 0) return '—'
  const totalSeconds = Math.max(0, Math.round(durationUs / 1_000_000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return hours > 0
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function formatFileSize(bytes: number | null): string {
  if (bytes == null || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  const kb = bytes / 1024
  if (kb < 1024) return `${kb.toFixed(kb >= 100 ? 0 : 1)} KB`
  const mb = kb / 1024
  if (mb < 1024) return `${mb.toFixed(mb >= 100 ? 0 : 1)} MB`
  const gb = mb / 1024
  return `${gb.toFixed(gb >= 10 ? 1 : 2)} GB`
}

function episodeOrder(index: number): string {
  return String(index + 1).padStart(2, '0')
}

function episodeShortLabel(index: number): string {
  return `EP${String(index + 1).padStart(2, '0')}`
}

function episodeFilename(episode: SourceVideoEpisode): string {
  return episode.original_filename || episode.title || '未命名视频'
}

function normalizedTaskType(task: BackgroundTask): string {
  return String(task.task_type || '').trim().toUpperCase()
}

function isShotTask(task: BackgroundTask): boolean {
  const type = normalizedTaskType(task)
  return type === 'EPISODE_SHOTS'
    || type === 'BATCH_SHOTS'
    || type === 'SHOTS'
    || type.includes('SHOT_DETECT')
    || type.includes('SHOTS_DETECT')
    || type.includes('SHOT_ANALY')
}

function isBreakdownTask(task: BackgroundTask): boolean {
  const type = normalizedTaskType(task)
  return type === 'EPISODE_BREAKDOWN_P2'
    || type === 'BATCH_BREAKDOWN_P2'
    || type.includes('BREAKDOWN')
}

function taskTimestamp(task: BackgroundTask): number {
  const raw = task.updated_at || task.created_at
  const value = new Date(raw).getTime()
  return Number.isFinite(value) ? value : 0
}

function latestTaskForEpisode(episodeId: string, matcher: (task: BackgroundTask) => boolean): BackgroundTask | null {
  return tasks.value
    .filter((task) => task.episode_id === episodeId && matcher(task))
    .sort((a, b) => taskTimestamp(b) - taskTimestamp(a))[0] || null
}

function latestBatchTask(matcher: (task: BackgroundTask) => boolean): BackgroundTask | null {
  return tasks.value
    .filter((task) => !task.episode_id && matcher(task))
    .sort((a, b) => taskTimestamp(b) - taskTimestamp(a))[0] || null
}

function activeBatchTask(matcher: (task: BackgroundTask) => boolean): BackgroundTask | null {
  return tasks.value
    .filter((task) => !task.episode_id && matcher(task) && (task.status === 'QUEUED' || task.status === 'PROCESSING'))
    .sort((a, b) => taskTimestamp(b) - taskTimestamp(a))[0] || null
}

function taskProgress(task: BackgroundTask): number | null {
  if (typeof task.progress_percent !== 'number' || !Number.isFinite(task.progress_percent)) return null
  return Math.max(0, Math.min(100, Math.round(task.progress_percent)))
}

function batchLocalProgress(task: BackgroundTask, episodeIndex: number): number | null {
  if (task.status !== 'PROCESSING') return null
  const currentIndex = Math.max(1, Number(task.current_index || 1))
  if (episodeIndex + 1 !== currentIndex) return null
  const total = Math.max(1, Number(task.total_items || episodes.value.length || 1))
  const overall = typeof task.progress_percent === 'number' ? task.progress_percent : null
  if (overall == null) return null
  const localFraction = (overall / 100) * total - (currentIndex - 1)
  return Math.max(0, Math.min(100, Math.round(localFraction * 100)))
}

function batchResultForEpisode(task: BackgroundTask | null, episodeId: string): { status?: unknown; error?: unknown } | null {
  if (!task?.result || typeof task.result !== 'object') return null
  const result = task.result as { results?: unknown }
  if (!Array.isArray(result.results)) return null
  const item = result.results.find((entry) => (
    entry && typeof entry === 'object' && String((entry as { episode_id?: unknown }).episode_id || '') === episodeId
  ))
  return item && typeof item === 'object' ? item as { status?: unknown; error?: unknown } : null
}

function shotStatusForEpisode(episode: SourceVideoEpisode): ProcessStatusDisplay {
  const index = episodes.value.findIndex((item) => item.id === episode.id)
  const flowEpisode = flowEpisodesById.value.get(episode.id)
  const authoritativeShotCount = Math.max(0, Number(flowEpisode?.shot_count ?? episode.shot_count ?? 0))
  const hasCurrentRevision = Boolean(flowEpisode?.current_shot_revision_id)
  const individual = latestTaskForEpisode(episode.id, isShotTask)
  const batchActive = activeBatchTask(isShotTask)

  if (individual?.status === 'QUEUED') return { state: 'queued', label: '排队中', detail: '' }
  if (individual?.status === 'PROCESSING') {
    const progress = taskProgress(individual)
    return { state: 'processing', label: '检测中', detail: progress == null ? '' : `${progress}%` }
  }

  if (batchActive && index >= 0) {
    if (batchActive.status === 'QUEUED') return { state: 'queued', label: '排队中', detail: '批量任务' }
    const currentIndex = Math.max(1, Number(batchActive.current_index || 1))
    const rowIndex = index + 1
    if (rowIndex === currentIndex) {
      const progress = batchLocalProgress(batchActive, index)
      return { state: 'processing', label: '检测中', detail: progress == null ? '批量任务' : `${progress}%` }
    }
    if (rowIndex > currentIndex) return { state: 'queued', label: '排队中', detail: '按剧集顺序等待' }
    if (authoritativeShotCount > 0 && hasCurrentRevision) {
      return { state: 'completed', label: '已完成', detail: `${authoritativeShotCount} 个镜头` }
    }
    return { state: 'failed', label: '失败', detail: '批量任务已跳过该集' }
  }

  if (optimisticQueuedEpisodeIds.value.has(episode.id)) return { state: 'queued', label: '排队中', detail: '' }

  if (authoritativeShotCount > 0 && hasCurrentRevision) {
    const failedRecently = individual?.status === 'FAILED'
    return {
      state: 'completed',
      label: '已完成',
      detail: failedRecently ? `${authoritativeShotCount} 个镜头 · 最近重检失败` : `${authoritativeShotCount} 个镜头`,
    }
  }

  if (authoritativeShotCount > 0 && !hasCurrentRevision) {
    return { state: 'failed', label: '需重新检测', detail: '旧镜头结果缺少当前版本' }
  }

  if (individual?.status === 'FAILED') {
    return { state: 'failed', label: '失败', detail: individual.error_message || '镜头检测失败' }
  }

  const latestBatch = latestBatchTask(isShotTask)
  const batchResult = batchResultForEpisode(latestBatch, episode.id)
  if (String(batchResult?.status || '').toUpperCase() === 'FAILED') {
    return { state: 'failed', label: '失败', detail: String(batchResult?.error || '镜头检测失败') }
  }

  return { state: 'not_started', label: '未检测', detail: '' }
}

function breakdownStatusForEpisode(episode: SourceVideoEpisode): ProcessStatusDisplay {
  const index = episodes.value.findIndex((item) => item.id === episode.id)
  const flowEpisode = flowEpisodesById.value.get(episode.id)
  const hasShots = Number(flowEpisode?.shot_count ?? episode.shot_count ?? 0) > 0 && Boolean(flowEpisode?.current_shot_revision_id)
  if (!hasShots) return { state: 'blocked', label: '等待镜头检测', detail: '' }

  const individual = latestTaskForEpisode(episode.id, isBreakdownTask)
  const batchActive = activeBatchTask(isBreakdownTask)
  if (individual?.status === 'QUEUED') return { state: 'queued', label: '排队中', detail: '' }
  if (individual?.status === 'PROCESSING') {
    const progress = taskProgress(individual)
    return { state: 'processing', label: '拉片中', detail: progress == null ? (individual.stage_label || '') : `${progress}%` }
  }

  if (batchActive && index >= 0) {
    if (batchActive.status === 'QUEUED') return { state: 'queued', label: '排队中', detail: '批量 AI 拉片' }
    const currentIndex = Math.max(1, Number(batchActive.current_index || 1))
    const rowIndex = index + 1
    if (rowIndex === currentIndex) {
      const progress = batchLocalProgress(batchActive, index)
      return { state: 'processing', label: '拉片中', detail: progress == null ? (batchActive.stage_label || '') : `${progress}%` }
    }
    if (rowIndex > currentIndex) return { state: 'queued', label: '排队中', detail: '按剧集顺序等待' }
  }

  if (flowEpisode?.current_breakdown_run_id) {
    if (sourceUnderstandingStage.value?.readiness === 'BLOCKED_REVIEW') {
      return { state: 'review', label: '待确认', detail: '拉片结果已生成' }
    }
    return { state: 'completed', label: '已完成', detail: '结构化拉片已就绪' }
  }

  if (individual?.status === 'FAILED') {
    return { state: 'failed', label: '失败', detail: individual.error_message || 'AI 拉片失败' }
  }

  const latestBatch = latestBatchTask(isBreakdownTask)
  const batchResult = batchResultForEpisode(latestBatch, episode.id)
  if (String(batchResult?.status || '').toUpperCase() === 'FAILED') {
    return { state: 'failed', label: '失败', detail: String(batchResult?.error || 'AI 拉片失败') }
  }

  return { state: 'not_started', label: '未开始', detail: '' }
}

function shotActionLabel(episode: SourceVideoEpisode): string {
  const state = shotStatusForEpisode(episode).state
  if (state === 'completed') return '重新检测'
  if (state === 'failed') return '重试检测'
  return '镜头检测'
}

function isShotActionDisabled(episode: SourceVideoEpisode): boolean {
  const state = shotStatusForEpisode(episode).state
  return detectingEpisodeId.value === episode.id
    || batchDetecting.value
    || projectHasActiveTask.value
    || state === 'queued'
    || state === 'processing'
}

function isSourceMutationDisabled(): boolean {
  return projectHasActiveTask.value || reorderSaving.value || uploadRunning.value || replaceRunning.value || deleting.value
}

async function refreshData(quiet = false): Promise<void> {
  if (!projectId.value || refreshInFlight) return
  refreshInFlight = true
  if (!quiet) {
    loading.value = true
    pageError.value = ''
  }
  try {
    const [sourceVideos, managed, projectTasks, workflow] = await Promise.all([
      listProjectSourceVideos(projectId.value),
      projectManagementApi.getProject(projectId.value),
      api.listProjectTasks(projectId.value).catch(() => [] as BackgroundTask[]),
      getProjectFlowState(projectId.value),
    ])
    videos.value = sourceVideos
    managedProject.value = managed
    tasks.value = projectTasks
    flowState.value = workflow

    if (projectTasks.some((task) => isShotTask(task))) {
      optimisticQueuedEpisodeIds.value = new Set()
    }
  } catch (error) {
    if (!quiet) pageError.value = error instanceof Error ? error.message : '项目视频读取失败'
  } finally {
    refreshInFlight = false
    if (!quiet) loading.value = false
  }
}

function clearPolling(): void {
  if (pollingTimer) clearTimeout(pollingTimer)
  pollingTimer = null
}

function schedulePolling(delayMs = 1200): void {
  clearPolling()
  if (disposed) return
  pollingTimer = setTimeout(async () => {
    await refreshData(true)
    if (disposed) return
    if (projectHasActiveTask.value) schedulePolling(1800)
    else {
      optimisticQueuedEpisodeIds.value = new Set()
      await refreshData(true)
    }
  }, delayMs)
}

function goBack(): void {
  void router.push('/')
}

function openUpload(): void {
  if (projectHasActiveTask.value) {
    actionError.value = '当前项目有后台任务正在执行，任务结束后才能修改原视频'
    return
  }
  actionError.value = ''
  uploadItems.value = []
  uploadOpen.value = true
}

function closeUpload(): void {
  if (uploadRunning.value) return
  uploadOpen.value = false
  uploadItems.value = []
  uploadDragging.value = false
}

function selectFiles(): void {
  fileInput.value?.click()
}

function isSupportedVideo(file: File): boolean {
  return ['mp4', 'mov', 'mkv'].includes(file.name.split('.').pop()?.toLowerCase() || '')
}

function addUploadFiles(files: FileList | File[]): void {
  const next = [...uploadItems.value]
  const existing = new Set(next.map((item) => `${item.file.name}:${item.file.size}:${item.file.lastModified}`))
  Array.from(files).forEach((file) => {
    const key = `${file.name}:${file.size}:${file.lastModified}`
    if (existing.has(key)) return
    existing.add(key)
    const supported = isSupportedVideo(file)
    next.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      progress: 0,
      status: supported ? 'pending' : 'failed',
      error: supported ? '' : '仅支持 mp4 / mov / mkv',
    })
  })
  uploadItems.value = next
}

function handleFileInput(event: Event): void {
  const input = event.target as HTMLInputElement
  if (input.files?.length) addUploadFiles(input.files)
  input.value = ''
}

function handleDrop(event: DragEvent): void {
  event.preventDefault()
  uploadDragging.value = false
  if (event.dataTransfer?.files?.length) addUploadFiles(event.dataTransfer.files)
}

function removeUploadItem(itemId: string): void {
  if (!uploadRunning.value) uploadItems.value = uploadItems.value.filter((item) => item.id !== itemId)
}

async function startUpload(): Promise<void> {
  if (uploadRunning.value || !projectId.value) return
  if (projectHasActiveTask.value) {
    actionError.value = '当前项目有后台任务正在执行，暂时不能上传新视频'
    return
  }
  const candidates = uploadItems.value.filter((item) => (item.status === 'pending' || item.status === 'failed') && isSupportedVideo(item.file))
  if (!candidates.length) {
    actionError.value = '请选择 mp4、mov 或 mkv 视频文件'
    return
  }

  uploadRunning.value = true
  actionError.value = ''
  for (const item of candidates) {
    if (disposed) break
    item.status = 'uploading'
    item.progress = 0
    item.error = ''
    try {
      await uploadEpisodeWithProgress(projectId.value, item.file, (progress) => { item.progress = progress.percent })
      uploadItems.value = uploadItems.value.filter((candidate) => candidate.id !== item.id)
      await refreshData(true)
    } catch (error) {
      item.status = 'failed'
      item.error = error instanceof Error ? error.message : '视频上传失败'
    }
  }
  uploadRunning.value = false
  if (!uploadItems.value.length) uploadOpen.value = false
  await refreshData(true)
}

async function startShotDetection(episode: SourceVideoEpisode): Promise<void> {
  if (isShotActionDisabled(episode)) return
  detectingEpisodeId.value = episode.id
  actionError.value = ''
  try {
    await api.analyzeEpisodeShots(episode.id)
    optimisticQueuedEpisodeIds.value = new Set([...optimisticQueuedEpisodeIds.value, episode.id])
    await refreshData(true)
    schedulePolling(700)
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '镜头检测启动失败'
  } finally {
    detectingEpisodeId.value = null
  }
}

async function startBatchShotDetection(): Promise<void> {
  if (batchDetecting.value || !episodes.value.length || projectHasActiveTask.value) return
  batchDetecting.value = true
  actionError.value = ''
  try {
    await api.analyzeBatchShots(projectId.value)
    optimisticQueuedEpisodeIds.value = new Set(episodes.value.map((item) => item.id))
    await refreshData(true)
    schedulePolling(700)
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '批量镜头检测启动失败'
  } finally {
    batchDetecting.value = false
  }
}

function openReplace(episode: SourceVideoEpisode): void {
  if (isSourceMutationDisabled()) {
    actionError.value = '当前项目有后台任务正在执行，任务结束后才能替换原视频'
    return
  }
  replaceTarget.value = episode
  replaceFile.value = null
  replaceProgress.value = 0
  replaceError.value = ''
}

function closeReplace(): void {
  if (replaceRunning.value) return
  replaceTarget.value = null
  replaceFile.value = null
  replaceProgress.value = 0
  replaceError.value = ''
}

function chooseReplacementFile(): void {
  replaceFileInput.value?.click()
}

function handleReplacementFile(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] || null
  input.value = ''
  replaceError.value = ''
  if (!file) return
  if (!isSupportedVideo(file)) {
    replaceFile.value = null
    replaceError.value = '仅支持 mp4 / mov / mkv 视频文件'
    return
  }
  replaceFile.value = file
}

async function confirmReplace(): Promise<void> {
  if (!replaceTarget.value || !replaceFile.value || replaceRunning.value) return
  replaceRunning.value = true
  replaceProgress.value = 0
  replaceError.value = ''
  try {
    await replaceEpisodeWithProgress(replaceTarget.value.id, replaceFile.value, (progress) => {
      replaceProgress.value = progress.percent
    })
    replaceTarget.value = null
    replaceFile.value = null
    replaceProgress.value = 0
    await refreshData(true)
  } catch (error) {
    replaceError.value = error instanceof Error ? error.message : '视频替换失败'
  } finally {
    replaceRunning.value = false
  }
}

function askDelete(episode: SourceVideoEpisode): void {
  if (isSourceMutationDisabled()) {
    actionError.value = '当前项目有后台任务正在执行，任务结束后才能删除视频'
    return
  }
  deleteTarget.value = episode
}

function closeDelete(): void {
  if (!deleting.value) deleteTarget.value = null
}

async function confirmDelete(): Promise<void> {
  if (!deleteTarget.value || deleting.value) return
  deleting.value = true
  actionError.value = ''
  try {
    await api.deleteEpisode(deleteTarget.value.id)
    deleteTarget.value = null
    await refreshData(true)
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '视频删除失败'
  } finally {
    deleting.value = false
  }
}

function onDragStart(episode: SourceVideoEpisode, event: DragEvent): void {
  if (isSourceMutationDisabled()) {
    event.preventDefault()
    actionError.value = '当前项目有后台任务正在执行，任务结束后才能调整视频顺序'
    return
  }
  draggingEpisodeId.value = episode.id
  event.dataTransfer?.setData('text/plain', episode.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onDragOver(episode: SourceVideoEpisode, event: DragEvent): void {
  if (!draggingEpisodeId.value || draggingEpisodeId.value === episode.id) return
  event.preventDefault()
  dragOverEpisodeId.value = episode.id
}

async function onDrop(target: SourceVideoEpisode, event: DragEvent): Promise<void> {
  event.preventDefault()
  const sourceId = draggingEpisodeId.value || event.dataTransfer?.getData('text/plain') || ''
  draggingEpisodeId.value = null
  dragOverEpisodeId.value = null
  if (!sourceId || sourceId === target.id || isSourceMutationDisabled()) return

  const reordered = [...episodes.value]
  const sourceIndex = reordered.findIndex((item) => item.id === sourceId)
  const targetIndex = reordered.findIndex((item) => item.id === target.id)
  if (sourceIndex < 0 || targetIndex < 0) return
  const [moved] = reordered.splice(sourceIndex, 1)
  if (!moved) return
  reordered.splice(targetIndex, 0, moved)

  videos.value = reordered.map((item, index) => ({ ...item, sort_order: index + 1 }))
  reorderSaving.value = true
  actionError.value = ''
  try {
    await api.reorderEpisodes(projectId.value, reordered.map((item) => item.id))
    await refreshData(true)
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '视频顺序保存失败'
    await refreshData(true)
  } finally {
    reorderSaving.value = false
  }
}

function onDragEnd(): void {
  draggingEpisodeId.value = null
  dragOverEpisodeId.value = null
}

onMounted(async () => {
  await refreshData()
  if (projectHasActiveTask.value) schedulePolling()
})

onBeforeUnmount(() => {
  disposed = true
  clearPolling()
})
</script>

<template>
  <div class="source-video-page" @keydown.esc="uploadOpen ? closeUpload() : replaceTarget ? closeReplace() : closeDelete()">
    <header class="topbar">
      <div class="brand-row">
        <button class="brand" type="button" @click="goBack"><span class="brand-mark">◆</span>AI Drama Studio</button>
        <span class="top-divider"></span>
        <nav class="breadcrumbs">
          <button type="button" @click="goBack">项目管理</button><span>›</span><span>{{ currentProjectName }}</span><span>›</span><strong>原短剧视频</strong>
        </nav>
      </div>
      <button class="help-button" type="button" title="操作说明弹窗将在后续接入"><span>?</span>操作说明</button>
    </header>

    <main class="page-layout">
      <aside class="stage-sidebar">
        <section class="progress-card">
          <h2>项目进度</h2>
          <div class="progress-copy"><span>整体进度</span><strong>{{ overallProgress }}%</strong></div>
          <div class="progress-track"><span :style="{ width: `${overallProgress}%` }"></span></div>
          <small v-if="flowState">依据当前工作流状态实时计算</small>
        </section>

        <nav class="stage-list" aria-label="项目阶段">
          <div
            v-for="stage in stageGroups"
            :key="stage.number"
            :class="['stage-item', `stage-${stage.state}`, { active: stage.active }]"
            :title="stage.reason"
          >
            <b>{{ stage.state === 'complete' ? '✓' : stage.number }}</b>
            <div>
              <strong>{{ stage.label }}</strong>
              <span>{{ stage.description }}</span>
              <small>{{ stage.statusLabel }}</small>
            </div>
          </div>
        </nav>
        <button class="back-button" type="button" @click="goBack">← 返回项目列表</button>
      </aside>

      <section class="main-content">
        <section class="project-card">
          <div>
            <p class="eyebrow">SOURCE DRAMA</p>
            <h1>原短剧视频</h1>
            <p class="subtitle">上传原剧集并整理正式剧集顺序，然后逐集或批量执行镜头检测。</p>
          </div>
          <div class="project-meta">
            <div><i>中</i><strong>原项目语言</strong><span>{{ projectLanguageLabel(sourceLanguage) }}</span></div>
            <em></em>
            <div><i>EN</i><strong>目标语言</strong><span>{{ projectLanguageLabel(targetLanguage) }}</span></div>
            <em></em>
            <div><i>◎</i><strong>目标地区</strong><span>{{ projectRegionLabel(targetRegion) }}</span></div>
            <em></em>
            <div class="rules"><strong>视频重绘规则</strong><span v-for="rule in redrawRules" :key="rule">{{ redrawRuleLabels[rule] }}</span><small v-if="!redrawRules.length">—</small></div>
          </div>
        </section>

        <section class="video-card">
          <header class="video-head">
            <div class="summary">
              <div><h2>视频列表</h2><p>拖拽排序会立即保存为正式剧集顺序</p></div>
              <span>共 {{ episodes.length }} 个视频</span><em></em><span>总时长 {{ formatDuration(totalDurationUs) }}</span>
            </div>
            <div class="toolbar">
              <button class="primary" type="button" :disabled="projectHasActiveTask" @click="openUpload">⇧ 上传视频</button>
              <button class="outline" type="button" :disabled="batchDetecting || projectHasActiveTask || !episodes.length" @click="startBatchShotDetection">▱ {{ batchDetecting ? '正在启动…' : '批量镜头检测' }}</button>
            </div>
          </header>

          <div v-if="projectHasActiveTask" class="task-notice">
            <span class="pulse"></span>
            <div><strong>项目任务正在执行</strong><span>处理期间暂时锁定上传、替换、删除和排序，避免旧任务回写到新的原片。</span></div>
          </div>

          <div v-if="actionError" class="action-error"><span>{{ actionError }}</span><button type="button" @click="actionError = ''">×</button></div>
          <div v-if="pageError" class="state-card"><strong>项目视频加载失败</strong><span>{{ pageError }}</span><button class="outline" type="button" @click="refreshData()">重新加载</button></div>
          <div v-else-if="loading" class="state-card"><span class="spinner"></span>正在读取项目视频与工作流状态…</div>
          <div v-else-if="!episodes.length" class="state-card">
            <div class="empty-icon">▶</div><h3>还没有上传视频</h3>
            <p>上传原短剧视频后可拖拽整理剧集顺序，再执行镜头检测。上传完成本身不再显示冗余“已上传”状态。</p>
            <button class="primary" type="button" :disabled="projectHasActiveTask" @click="openUpload">上传视频</button>
          </div>

          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th class="sort-col">排序</th>
                  <th>视频信息</th>
                  <th class="duration-col">时长</th>
                  <th class="size-col">大小</th>
                  <th class="status-col">镜头检测</th>
                  <th class="status-col">拉片分析</th>
                  <th class="detect-col">检测操作</th>
                  <th class="action-col">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(episode, index) in episodes"
                  :key="episode.id"
                  :class="{ dragging: draggingEpisodeId === episode.id, 'drag-over': dragOverEpisodeId === episode.id }"
                  @dragover="onDragOver(episode, $event)"
                  @drop="onDrop(episode, $event)"
                >
                  <td>
                    <div class="sort-cell">
                      <button class="drag-handle" type="button" draggable="true" :disabled="isSourceMutationDisabled()" title="拖拽调整剧集顺序" @dragstart="onDragStart(episode, $event)" @dragend="onDragEnd">⠿</button>
                      <span class="order">{{ episodeOrder(index) }}</span>
                    </div>
                  </td>
                  <td>
                    <div class="video-info">
                      <div class="thumb"><span>{{ episodeShortLabel(index) }}</span><small>{{ formatDuration(episode.duration_us) }}</small></div>
                      <div class="video-copy"><strong :title="episodeFilename(episode)">{{ episodeFilename(episode) }}</strong><span>{{ episode.title }}</span></div>
                    </div>
                  </td>
                  <td>{{ formatDuration(episode.duration_us) }}</td>
                  <td>{{ formatFileSize(episode.file_size_bytes) }}</td>
                  <td>
                    <div class="process-status">
                      <span :class="['status-pill', `status-${shotStatusForEpisode(episode).state}`]"><i></i>{{ shotStatusForEpisode(episode).label }}</span>
                      <small v-if="shotStatusForEpisode(episode).detail" :title="shotStatusForEpisode(episode).detail">{{ shotStatusForEpisode(episode).detail }}</small>
                    </div>
                  </td>
                  <td>
                    <div class="process-status">
                      <span :class="['status-pill', `status-${breakdownStatusForEpisode(episode).state}`]"><i></i>{{ breakdownStatusForEpisode(episode).label }}</span>
                      <small v-if="breakdownStatusForEpisode(episode).detail" :title="breakdownStatusForEpisode(episode).detail">{{ breakdownStatusForEpisode(episode).detail }}</small>
                    </div>
                  </td>
                  <td><button class="link detect" type="button" :disabled="isShotActionDisabled(episode)" @click="startShotDetection(episode)">{{ detectingEpisodeId === episode.id ? '正在启动…' : shotActionLabel(episode) }}</button></td>
                  <td>
                    <div class="row-actions">
                      <button class="link replace" type="button" :disabled="isSourceMutationDisabled()" @click="openReplace(episode)">替换</button>
                      <button class="link delete" type="button" :disabled="isSourceMutationDisabled()" @click="askDelete(episode)">删除</button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <footer v-if="episodes.length" class="video-foot">
            <div><span class="info">i</span><span>拖拽左侧手柄调整顺序会自动保存；替换原片会让该集旧镜头检测和拉片结果失效。</span></div>
            <strong v-if="reorderSaving">正在保存顺序…</strong>
          </footer>
        </section>

        <section class="next-stage-card">
          <div class="next-icon">2</div>
          <div class="next-copy">
            <small>下一阶段</small><strong>AI 拉片</strong>
            <span v-if="sourceSplitReady">全部剧集已经形成当前镜头结果，AI 拉片阶段已满足前置条件。</span>
            <span v-else>{{ sourceSplitStage?.reason || '上传视频并完成全部镜头检测后进入 AI 拉片。' }}</span>
          </div>
          <div :class="['next-state', { ready: sourceSplitReady }]">{{ sourceSplitReady ? '可进入' : '未解锁' }}</div>
        </section>
      </section>
    </main>

    <div v-if="uploadOpen" class="backdrop" @click.self="closeUpload">
      <section class="modal upload-modal">
        <header class="modal-head"><div><p>视频管理</p><h2>上传视频</h2></div><button type="button" :disabled="uploadRunning" @click="closeUpload">×</button></header>
        <div
          :class="['drop-zone', { active: uploadDragging }]"
          role="button"
          tabindex="0"
          @dragenter.prevent="uploadDragging = true"
          @dragover.prevent="uploadDragging = true"
          @dragleave.prevent="uploadDragging = false"
          @drop="handleDrop"
          @click="selectFiles"
          @keydown.enter.prevent="selectFiles"
          @keydown.space.prevent="selectFiles"
        >
          <input ref="fileInput" type="file" accept=".mp4,.mov,.mkv,video/mp4,video/quicktime,video/x-matroska" multiple @change="handleFileInput" />
          <div class="cloud">⇧</div><strong>拖拽视频到这里，或点击选择</strong><span>支持 mp4 / mov / mkv，可一次选择多个视频</span>
        </div>
        <div v-if="uploadItems.length" class="upload-list">
          <div v-for="item in uploadItems" :key="item.id" class="upload-row">
            <div class="file-copy"><strong>{{ item.file.name }}</strong><span>{{ formatFileSize(item.file.size) }}</span></div>
            <div class="upload-progress">
              <div><span :class="{ failed: item.status === 'failed' }">{{ item.status === 'uploading' ? `上传中 ${item.progress}%` : item.status === 'failed' ? (item.error || '上传失败') : '等待上传' }}</span><button v-if="item.status !== 'uploading'" type="button" :disabled="uploadRunning" @click="removeUploadItem(item.id)">×</button></div>
              <div v-if="item.status === 'uploading'" class="upload-track"><span :style="{ width: `${item.progress}%` }"></span></div>
            </div>
          </div>
        </div>
        <footer class="modal-actions"><button class="secondary" type="button" :disabled="uploadRunning" @click="closeUpload">取消</button><button class="primary" type="button" :disabled="uploadRunning || !uploadItems.length" @click="startUpload">{{ uploadActionLabel }}</button></footer>
      </section>
    </div>

    <div v-if="replaceTarget" class="backdrop" @click.self="closeReplace">
      <section class="modal replace-modal">
        <header class="modal-head"><div><p>视频管理</p><h2>替换原视频</h2></div><button type="button" :disabled="replaceRunning" @click="closeReplace">×</button></header>
        <div class="replace-warning"><strong>替换 {{ episodeFilename(replaceTarget) }}</strong><span>Episode ID 与剧集顺序保持不变；该集旧的镜头检测、AI 拉片和下游资产状态会自动失效，之后需要重新检测。</span></div>
        <input ref="replaceFileInput" class="hidden-input" type="file" accept=".mp4,.mov,.mkv,video/mp4,video/quicktime,video/x-matroska" @change="handleReplacementFile" />
        <button class="replacement-picker" type="button" :disabled="replaceRunning" @click="chooseReplacementFile">
          <span>▣</span>
          <div v-if="replaceFile"><strong>{{ replaceFile.name }}</strong><small>{{ formatFileSize(replaceFile.size) }}</small></div>
          <div v-else><strong>选择新的原视频</strong><small>支持 mp4 / mov / mkv</small></div>
        </button>
        <div v-if="replaceRunning" class="replace-progress"><div><span>正在替换…</span><strong>{{ replaceProgress }}%</strong></div><div class="upload-track"><span :style="{ width: `${replaceProgress}%` }"></span></div></div>
        <p v-if="replaceError" class="modal-error">{{ replaceError }}</p>
        <footer class="modal-actions"><button class="secondary" type="button" :disabled="replaceRunning" @click="closeReplace">取消</button><button class="primary" type="button" :disabled="replaceRunning || !replaceFile" @click="confirmReplace">{{ replaceRunning ? '正在替换…' : '确认替换' }}</button></footer>
      </section>
    </div>

    <div v-if="deleteTarget" class="backdrop" @click.self="closeDelete">
      <section class="modal delete-modal">
        <div class="danger-icon">!</div><h2>删除视频</h2><p>确定删除 <strong>“{{ episodeFilename(deleteTarget) }}”</strong> 吗？</p>
        <p class="note">删除会移除该剧集当前业务数据并重新编号剩余剧集。正在执行后台任务时系统不会允许此操作。</p>
        <footer class="modal-actions"><button class="secondary" type="button" :disabled="deleting" @click="closeDelete">取消</button><button class="danger" type="button" :disabled="deleting" @click="confirmDelete">{{ deleting ? '正在删除…' : '确认删除' }}</button></footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
:global(html), :global(body) { margin: 0; background: #f6f8fc; color: #14213a; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif; }
button, input { font: inherit; } button { cursor: pointer; } button:disabled { cursor: not-allowed; opacity: .5; }
.source-video-page { min-height: 100vh; padding: 0 28px 42px; box-sizing: border-box; }
.topbar { max-width: 1700px; min-height: 78px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 24px; }
.brand-row, .brand, .breadcrumbs, .help-button { display: flex; align-items: center; }
.brand { gap: 10px; padding: 0; border: 0; background: none; color: #1463ff; font-size: 19px; font-weight: 800; white-space: nowrap; }
.brand-mark { font-size: 20px; transform: rotate(45deg); }
.top-divider { width: 1px; height: 25px; margin: 0 20px; background: #dfe4ec; }
.breadcrumbs { gap: 12px; min-width: 0; color: #748095; font-size: 14px; }
.breadcrumbs button { padding: 0; border: 0; background: none; color: #526078; }
.breadcrumbs span:nth-of-type(2) { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.breadcrumbs strong { color: #1f2b42; }
.help-button { gap: 8px; min-height: 40px; padding: 0 15px; border: 1px solid #dce2ec; border-radius: 9px; background: #fff; color: #303d55; font-size: 13px; font-weight: 700; }
.help-button span, .info { width: 18px; height: 18px; display: inline-grid; place-items: center; box-sizing: border-box; border: 1.5px solid currentColor; border-radius: 50%; font-size: 11px; font-weight: 800; }
.page-layout { max-width: 1700px; margin: 0 auto; display: grid; grid-template-columns: 238px minmax(0, 1fr); gap: 18px; }
.stage-sidebar, .project-card, .video-card, .next-stage-card { border: 1px solid #e3e8f0; border-radius: 12px; background: #fff; box-shadow: 0 6px 20px rgba(23,43,77,.035); }
.stage-sidebar { min-height: calc(100vh - 118px); display: flex; flex-direction: column; overflow: hidden; }
.progress-card { padding: 25px 22px 21px; border-bottom: 1px solid #edf0f4; }
.progress-card h2 { margin: 0 0 18px; font-size: 15px; }
.progress-copy { display: flex; align-items: center; justify-content: space-between; gap: 9px; margin-bottom: 10px; color: #65728a; font-size: 13px; }
.progress-copy strong { color: #1463ff; font-size: 15px; }
.progress-track { height: 7px; overflow: hidden; border-radius: 999px; background: #e8edf7; }
.progress-track span { display: block; height: 100%; border-radius: inherit; background: #1463ff; transition: width .25s ease; }
.progress-card small { display: block; margin-top: 10px; color: #98a2b3; font-size: 10px; line-height: 1.45; }
.stage-list { flex: 1; padding: 8px 0; }
.stage-item { position: relative; min-height: 92px; padding: 19px 14px 14px 61px; box-sizing: border-box; color: #7b879b; }
.stage-item:not(:last-child)::after { content: ''; position: absolute; left: 35px; top: 46px; bottom: -27px; width: 1px; background: #e1e6ef; }
.stage-item b { position: absolute; left: 22px; top: 19px; z-index: 1; width: 27px; height: 27px; display: grid; place-items: center; border-radius: 50%; background: #e8ecf2; color: #65728a; font-size: 12px; }
.stage-item > div { display: grid; gap: 4px; }
.stage-item strong { color: #26334a; font-size: 14px; }
.stage-item span { font-size: 11px; line-height: 1.35; }
.stage-item small { margin-top: 2px; color: #98a2b3; font-size: 10px; font-weight: 700; }
.stage-item.active { border-left: 3px solid #1463ff; background: #f2f6ff; }
.stage-item.active b, .stage-complete b { background: #1463ff; color: #fff; }
.stage-item.active strong { color: #1760e7; }
.stage-complete small { color: #079455; }
.stage-processing b { background: #eaf2ff; color: #1760e7; }
.stage-processing small { color: #1760e7; }
.stage-review b { background: #fff4e5; color: #b54708; }
.stage-review small { color: #b54708; }
.stage-ready b { background: #ecfdf3; color: #067647; }
.stage-ready small { color: #067647; }
.stage-blocked { opacity: .72; }
.back-button { min-height: 43px; margin: 18px; border: 1px solid #d8e0eb; border-radius: 8px; background: #fff; color: #35435b; font-size: 13px; font-weight: 700; }
.main-content { min-width: 0; display: grid; align-content: start; gap: 16px; }
.project-card { padding: 24px 30px 22px; display: grid; gap: 20px; }
.eyebrow { margin: 0 0 6px; color: #1463ff; font-size: 10px; font-weight: 800; letter-spacing: .12em; }
.project-card h1 { margin: 0; font-size: 28px; letter-spacing: -.025em; }
.subtitle { margin: 7px 0 0; color: #718096; font-size: 13px; }
.project-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 16px; color: #44516a; font-size: 12px; }
.project-meta > div { display: flex; align-items: center; gap: 7px; white-space: nowrap; }
.project-meta i { min-width: 25px; height: 25px; padding: 0 4px; display: inline-grid; place-items: center; box-sizing: border-box; border: 1px solid #6a9cff; border-radius: 5px; color: #1463ff; font-size: 9px; font-style: normal; font-weight: 800; }
.project-meta em { width: 1px; height: 25px; background: #e4e8ef; }
.project-meta strong { color: #303d54; }
.rules span { padding: 4px 9px; border-radius: 7px; background: #edf4ff; color: #1760e7; font-size: 11px; font-weight: 700; }
.rules small { color: #9aa4b5; }
.video-card { overflow: hidden; }
.video-head { min-height: 86px; padding: 18px 25px; box-sizing: border-box; display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.summary, .toolbar { display: flex; align-items: center; }
.summary { gap: 14px; color: #5d6a82; font-size: 12px; }
.summary > div { margin-right: 8px; }
.summary h2 { margin: 0; color: #18233a; font-size: 20px; }
.summary p { margin: 4px 0 0; color: #98a2b3; font-size: 10px; }
.summary em { width: 1px; height: 17px; background: #dce1e9; }
.toolbar { gap: 10px; }
.primary, .outline, .secondary, .danger { min-height: 42px; padding: 0 17px; box-sizing: border-box; border: 1px solid transparent; border-radius: 8px; font-size: 13px; font-weight: 750; }
.primary { background: #1463ff; color: #fff; box-shadow: 0 5px 13px rgba(20,99,255,.18); }
.outline, .secondary { border-color: #d6deea; background: #fff; color: #285fbb; }
.secondary { color: #3e4b63; }
.danger { background: #d92d20; color: #fff; }
.task-notice { margin: 0 25px 14px; padding: 11px 13px; display: flex; align-items: center; gap: 10px; border: 1px solid #cfe0ff; border-radius: 8px; background: #f4f8ff; }
.task-notice .pulse { width: 8px; height: 8px; flex: 0 0 8px; border-radius: 50%; background: #1463ff; box-shadow: 0 0 0 5px rgba(20,99,255,.1); }
.task-notice div { display: flex; align-items: center; gap: 9px; min-width: 0; }
.task-notice strong { color: #1d4f9e; font-size: 12px; }
.task-notice span { color: #63728a; font-size: 11px; }
.action-error { margin: 0 25px 14px; padding: 10px 12px; display: flex; align-items: center; justify-content: space-between; gap: 12px; border: 1px solid #f2c7c2; border-radius: 8px; background: #fff4f2; color: #b42318; font-size: 12px; }
.action-error button { border: 0; background: none; color: inherit; font-size: 18px; }
.state-card { min-height: 330px; margin: 0 25px 25px; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 10px; border: 1px solid #e4e9f1; border-radius: 10px; color: #758197; font-size: 13px; text-align: center; }
.state-card h3, .state-card strong { margin: 0; color: #253149; }
.state-card p { max-width: 510px; margin: 0; line-height: 1.65; }
.empty-icon { width: 54px; height: 54px; display: grid; place-items: center; border-radius: 14px; background: #edf4ff; color: #1463ff; font-size: 21px; }
.spinner { width: 21px; height: 21px; border: 2px solid #dce4f0; border-top-color: #1463ff; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.table-wrap { margin: 0 25px; overflow-x: auto; border: 1px solid #dfe5ed; border-radius: 9px; }
table { width: 100%; min-width: 1260px; border-collapse: collapse; table-layout: fixed; }
th, td { padding: 14px 14px; border-bottom: 1px solid #e8ecf2; text-align: left; vertical-align: middle; font-size: 12px; }
th { height: 44px; padding-top: 0; padding-bottom: 0; background: #fafbfc; color: #68758a; font-size: 11px; white-space: nowrap; }
tbody tr { height: 90px; transition: .15s ease; }
tbody tr:last-child td { border-bottom: 0; }
tr.dragging { opacity: .48; }
tr.drag-over { background: #f2f6ff; box-shadow: inset 0 2px #5f91ef; }
.sort-col { width: 92px; }
.duration-col { width: 72px; }
.size-col { width: 78px; }
.status-col { width: 144px; }
.detect-col { width: 102px; }
.action-col { width: 105px; }
.sort-cell { display: flex; align-items: center; gap: 10px; }
.drag-handle { width: 22px; height: 34px; padding: 0; border: 0; background: none; color: #18233a; font-size: 21px; cursor: grab; }
.order { min-width: 39px; height: 31px; padding: 0 7px; display: inline-grid; place-items: center; box-sizing: border-box; border-radius: 8px; background: #eef4ff; color: #1463ff; font-size: 12px; font-weight: 800; }
.video-info { min-width: 0; display: flex; align-items: center; gap: 13px; }
.thumb { position: relative; width: 96px; height: 55px; flex: 0 0 96px; overflow: hidden; display: grid; place-items: center; border-radius: 7px; background: radial-gradient(circle at 68% 32%, rgba(226,177,119,.4), transparent 28%), linear-gradient(135deg,#2b2b34,#15191f 52%,#4a3429); color: rgba(255,255,255,.8); font-size: 9px; }
.thumb::before { content: '▶'; position: absolute; color: rgba(255,255,255,.3); font-size: 18px; }
.thumb > span { position: relative; z-index: 1; align-self: start; justify-self: start; margin: 6px; padding: 2px 5px; border-radius: 4px; background: rgba(0,0,0,.34); }
.thumb small { position: absolute; right: 5px; bottom: 4px; padding: 1px 4px; border-radius: 3px; background: rgba(0,0,0,.66); color: #fff; font-size: 9px; }
.video-copy { min-width: 0; display: grid; gap: 5px; }
.video-copy strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #172238; font-size: 12px; }
.video-copy span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #98a2b3; font-size: 10px; }
.process-status { display: grid; justify-items: start; gap: 5px; }
.process-status small { max-width: 138px; overflow: hidden; color: #8792a7; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.status-pill { min-width: 76px; min-height: 27px; padding: 0 9px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; box-sizing: border-box; border-radius: 999px; font-size: 10px; font-weight: 750; white-space: nowrap; }
.status-pill i { width: 7px; height: 7px; border: 1.5px solid currentColor; border-radius: 50%; box-sizing: border-box; }
.status-not_started, .status-blocked { background: #f1f3f6; color: #677389; }
.status-queued { background: #eaf2ff; color: #2c6dcc; }
.status-processing { background: #edf4ff; color: #1463ff; }
.status-processing i { border-style: dotted; animation: spin 1s linear infinite; }
.status-completed { background: #eaf8ef; color: #14804a; }
.status-completed i { background: currentColor; border-color: currentColor; }
.status-failed { background: #fff0ee; color: #c43226; }
.status-review { background: #fff5e8; color: #b65b0a; }
.link { padding: 4px 3px; border: 0; background: none; font-size: 11px; font-weight: 750; }
.link.detect { color: #1760e7; }
.link.replace { color: #344054; }
.link.delete { color: #d12f26; }
.row-actions { display: flex; align-items: center; gap: 9px; }
.video-foot { min-height: 58px; margin-top: 18px; padding: 0 25px; display: flex; align-items: center; justify-content: space-between; gap: 16px; border-top: 1px solid #edf0f4; color: #6d798e; font-size: 11px; }
.video-foot > div { display: flex; align-items: center; gap: 8px; }
.video-foot strong { color: #1760e7; font-size: 10px; white-space: nowrap; }
.next-stage-card { min-height: 88px; padding: 17px 20px; box-sizing: border-box; display: flex; align-items: center; gap: 14px; }
.next-icon { width: 38px; height: 38px; flex: 0 0 38px; display: grid; place-items: center; border-radius: 11px; background: #eef4ff; color: #1463ff; font-weight: 800; }
.next-copy { min-width: 0; display: grid; gap: 3px; flex: 1; }
.next-copy small { color: #98a2b3; font-size: 9px; font-weight: 800; letter-spacing: .08em; }
.next-copy strong { color: #1d2939; font-size: 14px; }
.next-copy span { color: #667085; font-size: 11px; line-height: 1.4; }
.next-state { padding: 7px 11px; border-radius: 999px; background: #f2f4f7; color: #667085; font-size: 10px; font-weight: 800; }
.next-state.ready { background: #ecfdf3; color: #067647; }
.backdrop { position: fixed; inset: 0; z-index: 50; display: grid; place-items: center; padding: 24px; box-sizing: border-box; background: rgba(15,23,42,.42); backdrop-filter: blur(2px); }
.modal { width: min(620px, 100%); max-height: calc(100vh - 48px); overflow: auto; border: 1px solid #e2e7ef; border-radius: 14px; background: #fff; box-shadow: 0 24px 70px rgba(15,23,42,.2); }
.modal-head { padding: 21px 24px 15px; display: flex; align-items: flex-start; justify-content: space-between; border-bottom: 1px solid #edf0f4; }
.modal-head p { margin: 0 0 5px; color: #1463ff; font-size: 10px; font-weight: 800; }
.modal-head h2 { margin: 0; font-size: 21px; }
.modal-head > button { border: 0; background: none; color: #8994a8; font-size: 24px; line-height: 1; }
.drop-zone { min-height: 195px; margin: 20px 24px 15px; display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 9px; border: 1.5px dashed #b9c8df; border-radius: 11px; background: #f9fbff; color: #68758a; text-align: center; transition: .15s ease; }
.drop-zone.active { border-color: #1463ff; background: #f0f5ff; }
.drop-zone input { display: none; }
.drop-zone strong { color: #27344b; font-size: 14px; }
.drop-zone span { font-size: 11px; }
.cloud { width: 45px; height: 45px; display: grid; place-items: center; border-radius: 12px; background: #e9f1ff; color: #1463ff; font-size: 23px; }
.upload-list { margin: 0 24px; display: grid; gap: 9px; }
.upload-row { padding: 11px 12px; display: grid; grid-template-columns: minmax(0, 1fr) 210px; gap: 16px; align-items: center; border: 1px solid #e4e9f1; border-radius: 9px; }
.file-copy { min-width: 0; display: grid; gap: 4px; }
.file-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.file-copy span { color: #8b96a9; font-size: 10px; }
.upload-progress > div:first-child { display: flex; align-items: center; justify-content: space-between; gap: 8px; color: #607089; font-size: 10px; }
.upload-progress .failed { color: #c43226; }
.upload-progress button { border: 0; background: none; color: #8d97a8; }
.upload-track { height: 5px; margin-top: 6px; overflow: hidden; border-radius: 999px; background: #e7ecf3; }
.upload-track span { display: block; height: 100%; border-radius: inherit; background: #1463ff; transition: width .15s linear; }
.modal-actions { padding: 18px 24px 22px; display: flex; justify-content: flex-end; gap: 10px; }
.replace-warning { margin: 20px 24px 14px; padding: 12px 14px; display: grid; gap: 5px; border: 1px solid #f0d29c; border-radius: 9px; background: #fff9ee; }
.replace-warning strong { color: #7a4d08; font-size: 12px; }
.replace-warning span { color: #8a6a36; font-size: 10px; line-height: 1.55; }
.hidden-input { display: none; }
.replacement-picker { width: calc(100% - 48px); min-height: 76px; margin: 0 24px; padding: 12px 14px; display: flex; align-items: center; gap: 12px; border: 1px dashed #b8c6dc; border-radius: 9px; background: #fafcff; text-align: left; }
.replacement-picker > span { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 9px; background: #edf4ff; color: #1463ff; }
.replacement-picker div { min-width: 0; display: grid; gap: 4px; }
.replacement-picker strong { overflow: hidden; color: #27344b; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.replacement-picker small { color: #8b96a9; font-size: 10px; }
.replace-progress { margin: 15px 24px 0; }
.replace-progress > div:first-child { display: flex; justify-content: space-between; color: #58677e; font-size: 10px; }
.modal-error { margin: 13px 24px 0; color: #b42318; font-size: 11px; }
.delete-modal { width: min(480px, 100%); padding: 28px; box-sizing: border-box; text-align: center; }
.danger-icon { width: 46px; height: 46px; margin: 0 auto 13px; display: grid; place-items: center; border-radius: 50%; background: #fff0ee; color: #d92d20; font-size: 22px; font-weight: 850; }
.delete-modal h2 { margin: 0 0 10px; font-size: 20px; }
.delete-modal p { margin: 7px 0; color: #667085; font-size: 12px; line-height: 1.6; }
.delete-modal .note { padding: 10px; border-radius: 8px; background: #f8f9fb; color: #8993a5; font-size: 10px; }
.delete-modal .modal-actions { padding: 18px 0 0; justify-content: center; }
@media (max-width: 1080px) {
  .page-layout { grid-template-columns: 1fr; }
  .stage-sidebar { min-height: auto; }
  .stage-list { display: grid; grid-template-columns: repeat(5, minmax(140px, 1fr)); overflow-x: auto; }
  .stage-item { min-height: 88px; padding-left: 54px; }
  .stage-item:not(:last-child)::after { display: none; }
  .back-button { align-self: start; }
}
@media (max-width: 760px) {
  .source-video-page { padding: 0 14px 28px; }
  .topbar { min-height: 68px; }
  .top-divider, .breadcrumbs span, .breadcrumbs strong, .help-button { display: none; }
  .project-card, .video-head { padding-left: 18px; padding-right: 18px; }
  .video-head { align-items: flex-start; flex-direction: column; }
  .summary { flex-wrap: wrap; }
  .toolbar { width: 100%; }
  .toolbar button { flex: 1; }
  .table-wrap { margin-left: 14px; margin-right: 14px; }
  .video-foot { padding-left: 16px; padding-right: 16px; }
  .upload-row { grid-template-columns: 1fr; }
  .project-meta em { display: none; }
}
</style>
