<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { breakdownApi } from '../api/breakdown'
import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { sceneTimelineApi } from '../api/scene-timeline'
import type { BreakdownRunSummary } from '../types/breakdown'
import type { ProjectFlowStage, ProjectFlowState } from '../types/project-flow-state'
import type {
  SceneTimelineDialogue,
  SceneTimelinePayload,
  SceneTimelinePerson,
  SceneTimelineScene,
  SceneTimelineShot,
} from '../types/scene-timeline'
import type { BackgroundTask, Episode, Project, Shot } from '../types/studio'

type ShotFilter = 'all' | 'unprocessed' | 'review' | 'failed'
type ShotUiStatus = 'completed' | 'unprocessed' | 'review' | 'failed'
type DetailTab = 'breakdown' | 'people' | 'assets' | 'dialogue'
type StageVisualState = 'complete' | 'active' | 'processing' | 'review' | 'waiting'

interface TimelineShotContext {
  scene: SceneTimelineScene
  shot: SceneTimelineShot
}

interface StageDisplay {
  number: number
  label: string
  description: string
  details: string[]
  statusLabel: string
  state: StageVisualState
  active: boolean
  clickable: boolean
}

interface ShotStatusDisplay {
  state: ShotUiStatus
  label: string
  detail?: string
}

const PAGE_SIZE = 8
const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))

const project = ref<Project | null>(null)
const flowState = ref<ProjectFlowState | null>(null)
const tasks = ref<BackgroundTask[]>([])
const timeline = ref<SceneTimelinePayload | null>(null)
const runs = ref<BreakdownRunSummary[]>([])
const shots = ref<Shot[]>([])

const loading = ref(true)
const episodeLoading = ref(false)
const pageError = ref('')
const actionError = ref('')
const actionMessage = ref('')
const timelineError = ref('')
const actionBusy = ref(false)
const adjustingBoundary = ref(false)
const selectedEpisodeId = ref('')
const selectedShotId = ref('')
const shotFilter = ref<ShotFilter>('all')
const detailTab = ref<DetailTab>('breakdown')
const searchText = ref('')
const currentPage = ref(1)
const startInput = ref('')
const endInput = ref('')
const helpOpen = ref(false)
const moreOpen = ref(false)
const h3Open = ref(false)

let episodeRequestSerial = 0
let pollTimer: ReturnType<typeof setInterval> | null = null

const episodes = computed(() => [...(project.value?.episodes || [])].sort((a, b) => a.sort_order - b.sort_order))
const currentEpisode = computed(() => episodes.value.find((item) => item.id === selectedEpisodeId.value) || null)
const currentRun = computed(() => runs.value.find((item) => item.is_current) || runs.value[0] || null)
const sourceUnderstandingStage = computed(() => flowState.value?.stages.find((stage) => stage.stage_key === 'source_understanding') || null)

function taskTimestamp(task: BackgroundTask): number {
  const value = new Date(task.updated_at || task.created_at).getTime()
  return Number.isFinite(value) ? value : 0
}

function isBreakdownTask(task: BackgroundTask): boolean {
  return String(task.task_type || '').toUpperCase().includes('BREAKDOWN')
}

const latestEpisodeBreakdownTask = computed(() => tasks.value
  .filter((task) => isBreakdownTask(task) && (task.episode_id === selectedEpisodeId.value || task.episode_id === null))
  .sort((a, b) => taskTimestamp(b) - taskTimestamp(a))[0] || null)

const activeBreakdownTask = computed(() => {
  const task = latestEpisodeBreakdownTask.value
  return task && (task.status === 'QUEUED' || task.status === 'PROCESSING') ? task : null
})

const timelineShotMap = computed(() => {
  const result = new Map<number, TimelineShotContext>()
  for (const scene of timeline.value?.scenes || []) {
    for (const shot of scene.shots) result.set(shot.ordinal, { scene, shot })
  }
  return result
})

const selectedShot = computed(() => shots.value.find((item) => item.id === selectedShotId.value) || shots.value[0] || null)
const selectedShotIndex = computed(() => selectedShot.value ? shots.value.findIndex((item) => item.id === selectedShot.value?.id) : -1)
const selectedTimelineContext = computed(() => selectedShot.value ? timelineShotMap.value.get(selectedShot.value.ordinal) || null : null)
const selectedTimelineShot = computed(() => selectedTimelineContext.value?.shot || null)
const selectedScene = computed(() => selectedTimelineContext.value?.scene || null)

const selectedPeople = computed<SceneTimelinePerson[]>(() => {
  const scene = selectedScene.value
  const shot = selectedTimelineShot.value
  if (!scene || !shot) return []
  return shot.people
    .map((ref) => scene.people.find((person) => person.ref === ref) || null)
    .filter((person): person is SceneTimelinePerson => Boolean(person))
})

const selectedDialogue = computed(() => selectedTimelineShot.value?.dialogue || [])
const selectedProps = computed(() => {
  const shot = selectedTimelineShot.value
  if (!shot) return []
  const finalProps = shot.final_props || []
  if (finalProps.length) return finalProps.map((item) => ({ name: item.name, coverUrl: item.cover_url, interaction: '已确认道具' }))
  return shot.props.map((item) => ({ name: item.label, coverUrl: null, interaction: item.interaction || '画面出现' }))
})

const overallProgress = computed(() => {
  const stages = flowState.value?.stages || []
  if (!stages.length) return 0
  const finished = stages.filter((stage) => stage.consumable).length
  return Math.max(0, Math.min(100, Math.round((finished / stages.length) * 100)))
})

function stageStateFor(keys: string[], active: boolean): { state: StageVisualState; statusLabel: string } {
  const values = keys
    .map((key) => flowState.value?.stages.find((stage) => stage.stage_key === key))
    .filter((stage): stage is ProjectFlowStage => Boolean(stage))
  if (!values.length) return { state: active ? 'active' : 'waiting', statusLabel: active ? '进行中' : '未开始' }
  if (values.every((stage) => stage.consumable)) return { state: active ? 'active' : 'complete', statusLabel: '已完成' }
  if (values.some((stage) => stage.execution === 'QUEUED' || stage.execution === 'PROCESSING')) {
    return { state: active ? 'active' : 'processing', statusLabel: '处理中' }
  }
  if (values.some((stage) => stage.readiness === 'BLOCKED_REVIEW')) {
    return { state: active ? 'active' : 'review', statusLabel: '待确认' }
  }
  return { state: active ? 'active' : 'waiting', statusLabel: active ? '进行中' : '未开始' }
}

const stageItems = computed<StageDisplay[]>(() => {
  const definitions = [
    { number: 1, label: '原短剧视频', description: '上传视频与排序', details: [] as string[], keys: ['project_setup', 'source_split'], active: false, clickable: true },
    { number: 2, label: 'AI 拉片', description: '镜头内容分析', details: ['人物归并', '场景道具', '对白校正'], keys: ['source_understanding'], active: true, clickable: true },
    { number: 3, label: '原片确认', description: '人物 / 场景确认', details: [] as string[], keys: ['source_assets', 'source_snapshot'], active: false, clickable: false },
    { number: 4, label: '重拍设计', description: '本土化人物与场景设计', details: [] as string[], keys: ['target_design'], active: false, clickable: false },
    { number: 5, label: '视频生成', description: 'AI 重拍与合成', details: [] as string[], keys: ['target_dialogue', 'remake_timing', 'h3_generation'], active: false, clickable: false },
    { number: 6, label: '成片输出', description: '成片预览与导出', details: [] as string[], keys: ['postproduction_output'], active: false, clickable: false },
  ]
  return definitions.map((item) => ({ ...item, ...stageStateFor(item.keys, item.active) }))
})

function hasCharacterReviewForShot(context: TimelineShotContext): boolean {
  const openCharacterCases = Number(flowState.value?.review_summary.by_type.CHARACTER_IDENTITY || 0)
  if (openCharacterCases <= 0) return false
  return context.shot.people.some((ref) => {
    const person = context.scene.people.find((item) => item.ref === ref)
    return person?.final_character === null
  })
}

function statusForShot(shot: Shot): ShotStatusDisplay {
  const context = timelineShotMap.value.get(shot.ordinal)
  if (context) {
    if (hasCharacterReviewForShot(context)) return { state: 'review', label: '待确认', detail: '人物待归并' }
    return { state: 'completed', label: '已完成' }
  }
  return { state: 'unprocessed', label: '未拉片' }
}

const statusCounts = computed(() => {
  const counts: Record<ShotUiStatus, number> = { completed: 0, unprocessed: 0, review: 0, failed: 0 }
  for (const shot of shots.value) counts[statusForShot(shot).state] += 1
  return counts
})

function shotSearchText(shot: Shot): string {
  const context = timelineShotMap.value.get(shot.ordinal)
  const pieces = [
    `shot ${shot.ordinal}`,
    shot.short_description || '',
    context?.scene.title || '',
    context?.shot.visual_description || '',
    ...(context?.shot.performance || []).map((item) => item.text),
    ...(context?.shot.dialogue || []).map((item) => item.text),
    ...(context?.shot.props || []).map((item) => item.label),
  ]
  return pieces.join(' ').toLowerCase()
}

const filteredShots = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  return shots.value.filter((shot) => {
    const status = statusForShot(shot).state
    const matchesFilter = shotFilter.value === 'all'
      || (shotFilter.value === 'unprocessed' && status === 'unprocessed')
      || (shotFilter.value === 'review' && status === 'review')
      || (shotFilter.value === 'failed' && status === 'failed')
    if (!matchesFilter) return false
    return !keyword || shotSearchText(shot).includes(keyword)
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(filteredShots.value.length / PAGE_SIZE)))
const pagedShots = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return filteredShots.value.slice(start, start + PAGE_SIZE)
})

const filmstripShots = computed(() => {
  const index = selectedShotIndex.value
  if (index < 0) return []
  let start = Math.max(0, index - 4)
  let end = Math.min(shots.value.length, start + 9)
  start = Math.max(0, end - 9)
  return shots.value.slice(start, end)
})

const canEditStart = computed(() => selectedShotIndex.value > 0)
const canEditEnd = computed(() => selectedShotIndex.value >= 0 && selectedShotIndex.value < shots.value.length - 1)
const boundaryChanged = computed(() => {
  const shot = selectedShot.value
  if (!shot) return false
  const start = parseTimeInput(startInput.value)
  const end = parseTimeInput(endInput.value)
  return (start !== null && start !== shot.start_us) || (end !== null && end !== shot.end_us)
})

const sceneName = computed(() => selectedScene.value?.final_scene?.name || selectedScene.value?.title || selectedScene.value?.scene_info.location || '未识别场景')
const sceneEnvironment = computed(() => selectedScene.value?.scene_info.environment || '暂无环境补充描述')
const peopleNames = computed(() => selectedPeople.value.map((person) => person.final_character?.name || person.display_name || '人物'))
const actionSummary = computed(() => {
  const performance = selectedTimelineShot.value?.performance.map((item) => item.text).filter(Boolean) || []
  if (performance.length) return performance.join('；')
  return selectedTimelineShot.value?.visual_description || '暂无动作描述'
})
const interactionSummary = computed(() => {
  const shot = selectedTimelineShot.value
  if (!shot || shot.people.length < 2) return shot?.people.length ? '当前镜头以单人行为为主' : '未识别明确人物互动'
  return `${peopleNames.value.join('、')} 同镜出现，具体互动以动作描述为准`
})
const cameraItems = computed(() => {
  const camera = selectedTimelineShot.value?.cinematography
  if (!camera) return []
  return [camera.shot_type, camera.composition, camera.camera_motion].filter((item): item is string => Boolean(item?.trim()))
})
const lightLabel = computed(() => selectedScene.value?.scene_info.time_of_day || '未标注')
const qualityLabel = computed(() => {
  const episode = currentEpisode.value
  if (!episode?.height) return '未知'
  return episode.height >= 1080 ? '清晰' : episode.height >= 720 ? '标准' : '较低'
})

const h3Sections = computed(() => [
  { label: '主体', value: peopleNames.value.length ? peopleNames.value.join('、') : '当前镜头未识别明确主体' },
  { label: '动作', value: actionSummary.value },
  { label: '场景', value: sceneName.value },
  { label: '镜头', value: cameraItems.value.length ? cameraItems.value.join('、') : '暂无镜头参数' },
  { label: '更多元素', value: selectedProps.value.length ? selectedProps.value.map((item) => item.name).join('、') : sceneEnvironment.value },
])
const fullH3Description = computed(() => h3Sections.value.map((item) => `${item.label}：${item.value}`).join('\n'))

const selectedStatus = computed(() => selectedShot.value ? statusForShot(selectedShot.value) : null)
const breakdownProgressLabel = computed(() => {
  const task = activeBreakdownTask.value
  if (!task) return ''
  if (task.progress_percent === null) return task.stage_label || 'AI 拉片处理中'
  return `${task.stage_label || 'AI 拉片处理中'} ${Math.round(task.progress_percent)}%`
})

function episodeLabel(episode: Episode): string {
  const order = String(Math.max(1, episode.sort_order)).padStart(2, '0')
  return `EP${order} ${episode.title || `第${episode.sort_order}集`}`
}

function formatTimeUs(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const totalMs = Math.max(0, Math.round(value / 1000))
  const minutes = Math.floor(totalMs / 60_000)
  const seconds = Math.floor((totalMs % 60_000) / 1000)
  const ms = totalMs % 1000
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function formatDurationUs(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return formatTimeUs(Math.max(0, value))
}

function parseTimeInput(value: string): number | null {
  const text = value.trim()
  if (!text) return null
  if (/^\d+(?:\.\d+)?$/.test(text)) return Math.round(Number(text) * 1_000_000)
  const parts = text.split(':')
  if (parts.length < 2 || parts.length > 3) return null
  const seconds = Number(parts.pop())
  const minutes = Number(parts.pop())
  const hours = parts.length ? Number(parts.pop()) : 0
  if (![seconds, minutes, hours].every(Number.isFinite) || seconds < 0 || minutes < 0 || hours < 0 || seconds >= 60 || minutes >= 60) return null
  return Math.round((hours * 3600 + minutes * 60 + seconds) * 1_000_000)
}

function syncBoundaryInputs(): void {
  const shot = selectedShot.value
  startInput.value = shot ? formatTimeUs(shot.start_us) : ''
  endInput.value = shot ? formatTimeUs(shot.end_us) : ''
}

function personDisplayName(person: SceneTimelinePerson): string {
  return person.final_character?.name || person.display_name || '人物'
}

function dialogueSpeaker(dialogue: SceneTimelineDialogue): string {
  const scene = selectedScene.value
  if (!scene || !dialogue.speakers.length) return '对白'
  const names = dialogue.speakers.map((ref) => {
    const person = scene.people.find((item) => item.ref === ref)
    return person ? personDisplayName(person) : '人物'
  })
  return Array.from(new Set(names)).join('、') || '对白'
}

function shotThumbnail(shot: Shot): string | null {
  return shot.thumbnail_url || timelineShotMap.value.get(shot.ordinal)?.shot.thumbnail_url || null
}

function shotReference(shot: Shot | null): string | null {
  if (!shot) return null
  return shot.reference_url || timelineShotMap.value.get(shot.ordinal)?.shot.reference_url || null
}

function selectShot(shot: Shot): void {
  selectedShotId.value = shot.id
  detailTab.value = 'breakdown'
  moreOpen.value = false
  actionError.value = ''
  actionMessage.value = ''
  syncBoundaryInputs()
  void router.replace({
    query: { ...route.query, episode: selectedEpisodeId.value, shot: String(shot.ordinal) },
  })
}

function selectStage(item: StageDisplay): void {
  if (!item.clickable) return
  if (item.number === 1) {
    void router.push(`/projects/${encodeURIComponent(projectId.value)}`)
  }
}

async function loadProjectContext(): Promise<void> {
  if (!projectId.value) return
  const [projectResult, flowResult, taskResult] = await Promise.all([
    api.getProject(projectId.value),
    getProjectFlowState(projectId.value),
    api.listProjectTasks(projectId.value, 60),
  ])
  project.value = projectResult
  flowState.value = flowResult
  tasks.value = taskResult

  const requestedEpisode = String(route.query.episode || '')
  const exists = projectResult.episodes.some((item) => item.id === selectedEpisodeId.value)
  const requestedExists = projectResult.episodes.some((item) => item.id === requestedEpisode)
  if (!exists) selectedEpisodeId.value = requestedExists ? requestedEpisode : [...projectResult.episodes].sort((a, b) => a.sort_order - b.sort_order)[0]?.id || ''
}

async function loadEpisodeData(): Promise<void> {
  const episodeId = selectedEpisodeId.value
  if (!episodeId) {
    shots.value = []
    timeline.value = null
    runs.value = []
    selectedShotId.value = ''
    return
  }

  const serial = ++episodeRequestSerial
  episodeLoading.value = true
  timelineError.value = ''
  try {
    const [shotsResult, timelineResult, runsResult] = await Promise.allSettled([
      api.listShots(episodeId),
      sceneTimelineApi.getEpisode(episodeId),
      breakdownApi.listRuns(episodeId),
    ])
    if (serial !== episodeRequestSerial) return

    if (shotsResult.status === 'rejected') throw shotsResult.reason
    shots.value = [...shotsResult.value].sort((a, b) => a.ordinal - b.ordinal)

    if (timelineResult.status === 'fulfilled') timeline.value = timelineResult.value
    else {
      timeline.value = null
      timelineError.value = timelineResult.reason instanceof Error ? timelineResult.reason.message : '拉片结果当前不可用'
    }

    runs.value = runsResult.status === 'fulfilled' ? runsResult.value : []

    const requestedOrdinal = Number(route.query.shot || 0)
    const requestedShot = shots.value.find((item) => item.ordinal === requestedOrdinal)
    const currentExists = shots.value.some((item) => item.id === selectedShotId.value)
    if (!currentExists) selectedShotId.value = requestedShot?.id || shots.value[0]?.id || ''
    syncBoundaryInputs()
    currentPage.value = 1
  } finally {
    if (serial === episodeRequestSerial) episodeLoading.value = false
  }
}

async function refreshAll(showLoading = false): Promise<void> {
  if (showLoading) loading.value = true
  pageError.value = ''
  try {
    await loadProjectContext()
    await loadEpisodeData()
  } catch (err) {
    pageError.value = err instanceof Error ? err.message : 'AI 拉片页面读取失败'
  } finally {
    loading.value = false
  }
}

async function refreshStatus(): Promise<void> {
  actionError.value = ''
  actionMessage.value = ''
  try {
    await refreshAll(false)
  } catch {
    // refreshAll already owns the page error text.
  }
}

async function changeEpisode(event: Event): Promise<void> {
  const element = event.target as HTMLSelectElement
  selectedEpisodeId.value = element.value
  selectedShotId.value = ''
  shotFilter.value = 'all'
  searchText.value = ''
  currentPage.value = 1
  await router.replace({ query: { ...route.query, episode: selectedEpisodeId.value, shot: undefined } })
  await loadEpisodeData()
}

async function startEpisodeBreakdown(fromShot = false): Promise<void> {
  const episode = currentEpisode.value
  if (!episode || actionBusy.value || activeBreakdownTask.value) return
  if (episode.shot_count <= 0) {
    actionError.value = '本集还没有可用分镜，请先回到“原短剧视频”完成镜头检测。'
    return
  }
  if (fromShot) {
    const proceed = window.confirm('当前生产管线仍按整集执行拉片。点击“确定”会重新拉片本集全部分镜，不会只重跑当前 Shot。')
    if (!proceed) return
  } else if (timeline.value) {
    const proceed = window.confirm('重新整集拉片会生成新的拉片 Run，当前结果会保留为历史。是否继续？')
    if (!proceed) return
  }

  actionBusy.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const task = await breakdownApi.startEpisode(episode.id)
    tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)]
    actionMessage.value = 'AI 拉片任务已进入后台执行。页面只会读取进度，不会因为刷新重复启动任务。'
    await loadProjectContext()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : 'AI 拉片任务启动失败'
  } finally {
    actionBusy.value = false
  }
}

async function adjustShotRange(): Promise<void> {
  const shot = selectedShot.value
  if (!shot || adjustingBoundary.value || !boundaryChanged.value) return
  const nextStart = parseTimeInput(startInput.value)
  const nextEnd = parseTimeInput(endInput.value)
  if (nextStart === null || nextEnd === null) {
    actionError.value = '时间格式不正确，请使用 00:21.400 这类“分:秒.毫秒”格式。'
    return
  }
  if (nextStart >= nextEnd) {
    actionError.value = '开始时间必须早于结束时间。'
    return
  }

  const startChanged = nextStart !== shot.start_us
  const endChanged = nextEnd !== shot.end_us
  if (startChanged && endChanged) {
    actionError.value = '当前后端一次只支持安全移动一个公共边界。请先调整开始时间并保存，再调整结束时间，避免第二次保存失败造成部分更新。'
    return
  }
  if (startChanged && !canEditStart.value) {
    actionError.value = '第一个分镜的开始时间固定为视频起点。'
    return
  }
  if (endChanged && !canEditEnd.value) {
    actionError.value = '最后一个分镜的结束时间固定为视频终点。'
    return
  }

  adjustingBoundary.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const result = await api.adjustShotBoundary(shot.id, startChanged ? 'start' : 'end', startChanged ? nextStart : nextEnd)
    shots.value = [...result].sort((a, b) => a.ordinal - b.ordinal)
    selectedShotId.value = shot.id
    syncBoundaryInputs()
    actionMessage.value = '分镜边界已保存。受影响的拉片结果需要用户明确点击“整集拉片”后才会重新计算。'
    await Promise.all([loadProjectContext(), loadEpisodeData()])
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : '分镜范围调整失败'
    syncBoundaryInputs()
  } finally {
    adjustingBoundary.value = false
  }
}

function changeFilter(value: ShotFilter): void {
  shotFilter.value = value
  currentPage.value = 1
}

function pageTo(value: number): void {
  currentPage.value = Math.max(1, Math.min(totalPages.value, value))
}

async function copyH3Description(): Promise<void> {
  try {
    await navigator.clipboard.writeText(fullH3Description.value)
    actionMessage.value = 'H3 重拍描述已复制。'
    moreOpen.value = false
  } catch {
    actionError.value = '浏览器未允许复制，请打开“查看完整描述”后手动复制。'
  }
}

function onTaskCreated(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value || !isBreakdownTask(task)) return
  tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)]
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value || !isBreakdownTask(task)) return
  void refreshAll(false)
}

watch(searchText, () => { currentPage.value = 1 })
watch(selectedShotId, syncBoundaryInputs)
watch(totalPages, (value) => { if (currentPage.value > value) currentPage.value = value })

onMounted(async () => {
  window.addEventListener('studio-task-created', onTaskCreated)
  window.addEventListener('studio-task-finished', onTaskFinished)
  await refreshAll(true)
  pollTimer = setInterval(() => {
    if (activeBreakdownTask.value) void refreshAll(false)
  }, 2500)
})

onBeforeUnmount(() => {
  window.removeEventListener('studio-task-created', onTaskCreated)
  window.removeEventListener('studio-task-finished', onTaskFinished)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="breakdown-page-v1">
    <header class="global-topbar">
      <button class="brand" type="button" @click="router.push('/')">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i></span>
        <strong>AI Drama Studio</strong>
      </button>
      <span class="top-divider"></span>
      <nav class="breadcrumbs" aria-label="面包屑">
        <button type="button" @click="router.push('/')">项目管理</button>
        <span>›</span>
        <strong>AI 拉片</strong>
        <span>›</span>
        <strong>{{ currentEpisode ? `EP${String(currentEpisode.sort_order).padStart(2, '0')}` : '—' }}</strong>
      </nav>
      <button class="help-button" type="button" @click="helpOpen = true"><span>?</span> 操作说明</button>
    </header>

    <div class="page-shell">
      <aside class="project-progress-card">
        <div class="progress-heading">
          <strong>项目进度</strong>
          <div class="progress-copy"><span>整体进度</span><b>{{ overallProgress }}%</b></div>
          <div class="progress-track"><span :style="{ width: `${overallProgress}%` }"></span></div>
        </div>

        <div class="stage-list">
          <button
            v-for="item in stageItems"
            :key="item.number"
            type="button"
            :class="['stage-item', `state-${item.state}`, { active: item.active, clickable: item.clickable }]"
            :disabled="!item.clickable"
            @click="selectStage(item)"
          >
            <span class="stage-number">{{ item.number }}</span>
            <span class="stage-copy">
              <strong>{{ item.label }}</strong>
              <small>{{ item.description }}</small>
              <small v-for="detail in item.details" :key="detail">{{ detail }}</small>
              <em>{{ item.statusLabel }}</em>
            </span>
          </button>
        </div>

        <button class="back-projects" type="button" @click="router.push('/')">← 返回项目列表</button>
      </aside>

      <main class="breakdown-main">
        <section class="page-heading-card">
          <div class="page-heading-title">
            <div class="title-line">
              <h1>AI 拉片</h1>
              <span>镜头内容分析</span><i>·</i><span>人物归并</span><i>·</i><span>场景道具</span><i>·</i><span>对白校正</span>
            </div>
            <div class="episode-summary-row">
              <label>剧集选择</label>
              <select :value="selectedEpisodeId" :disabled="loading || !episodes.length" @change="changeEpisode">
                <option v-for="episode in episodes" :key="episode.id" :value="episode.id">{{ episodeLabel(episode) }}</option>
              </select>
              <span class="summary-stat">分镜总数：<b>{{ shots.length }}</b></span>
              <span class="summary-stat">已完成：<b>{{ statusCounts.completed }}</b></span>
              <span class="summary-stat">待确认：<b>{{ statusCounts.review }}</b></span>
              <span class="summary-stat danger">失败：<b>{{ statusCounts.failed }}</b></span>
              <span v-if="activeBreakdownTask" class="running-pill">{{ breakdownProgressLabel }}</span>
            </div>
          </div>
          <div class="heading-actions">
            <button class="button secondary" type="button" :disabled="loading || episodeLoading" @click="refreshStatus">↻&nbsp; 刷新状态</button>
            <button class="button primary" type="button" :disabled="!currentEpisode || actionBusy || Boolean(activeBreakdownTask)" @click="startEpisodeBreakdown(false)">
              <span>▶</span>{{ activeBreakdownTask ? '拉片中' : '整集拉片' }}<b>⌄</b>
            </button>
          </div>
        </section>

        <div v-if="pageError || actionError || actionMessage || timelineError" class="message-stack">
          <div v-if="pageError" class="message danger">{{ pageError }}</div>
          <div v-if="actionError" class="message danger">{{ actionError }}</div>
          <div v-if="actionMessage" class="message success">{{ actionMessage }}</div>
          <div v-if="timelineError && shots.length" class="message warning">当前分镜仍可查看，但拉片阅读结果不可用：{{ timelineError }}</div>
        </div>

        <section class="workspace-grid">
          <aside class="shot-list-card panel-card">
            <header class="panel-header shot-list-header">
              <div><strong>分镜列表</strong><span>({{ shots.length }})</span></div>
            </header>
            <div class="shot-search"><span>⌕</span><input v-model="searchText" type="search" placeholder="搜索分镜号 / 内容 / 对白" /></div>
            <div class="shot-filters">
              <button :class="{ active: shotFilter === 'all' }" type="button" @click="changeFilter('all')">全部 <b>{{ shots.length }}</b></button>
              <button :class="{ active: shotFilter === 'unprocessed' }" type="button" @click="changeFilter('unprocessed')">未拉片 <b>{{ statusCounts.unprocessed }}</b></button>
              <button :class="{ active: shotFilter === 'review' }" type="button" @click="changeFilter('review')">待确认 <b>{{ statusCounts.review }}</b></button>
              <button :class="{ active: shotFilter === 'failed' }" type="button" @click="changeFilter('failed')">失败 <b>{{ statusCounts.failed }}</b></button>
            </div>

            <div v-if="episodeLoading" class="shot-list-loading"><span></span>正在读取分镜…</div>
            <div v-else-if="!pagedShots.length" class="shot-list-empty">当前筛选条件下没有分镜</div>
            <div v-else class="shot-list-scroll">
              <button
                v-for="shot in pagedShots"
                :key="shot.id"
                type="button"
                :class="['shot-row', { selected: selectedShot?.id === shot.id }]"
                @click="selectShot(shot)"
              >
                <span class="drag-dots">⋮</span>
                <span class="shot-thumb">
                  <img v-if="shotThumbnail(shot)" :src="shotThumbnail(shot) || ''" alt="" loading="lazy" />
                  <i v-else>SHOT</i>
                </span>
                <span class="shot-row-copy">
                  <strong>Shot {{ String(shot.ordinal).padStart(2, '0') }}</strong>
                  <small>{{ formatTimeUs(shot.start_us) }} - {{ formatTimeUs(shot.end_us) }}</small>
                  <em :class="`status-${statusForShot(shot).state}`"><i></i>{{ statusForShot(shot).label }}<span v-if="statusForShot(shot).detail"> · {{ statusForShot(shot).detail }}</span></em>
                </span>
              </button>
            </div>

            <footer class="shot-pagination">
              <button type="button" :disabled="currentPage <= 1" @click="pageTo(currentPage - 1)">‹</button>
              <button v-for="page in totalPages" v-show="page <= 3 || page === totalPages || Math.abs(page - currentPage) <= 1" :key="page" type="button" :class="{ active: currentPage === page }" @click="pageTo(page)">{{ page }}</button>
              <span v-if="totalPages > 5">…</span>
              <button type="button" :disabled="currentPage >= totalPages" @click="pageTo(currentPage + 1)">›</button>
            </footer>
          </aside>

          <section class="shot-workbench-card panel-card">
            <template v-if="selectedShot">
              <header class="shot-workbench-header">
                <div>
                  <div class="shot-title-row">
                    <h2>Shot {{ String(selectedShot.ordinal).padStart(2, '0') }}</h2>
                    <span v-if="selectedStatus" :class="['shot-status-pill', `status-${selectedStatus.state}`]"><i></i>{{ selectedStatus.label }}</span>
                  </div>
                  <p>时间范围：{{ formatTimeUs(selectedShot.start_us) }} - {{ formatTimeUs(selectedShot.end_us) }} <span>时长：{{ formatDurationUs(selectedShot.duration_us) }}</span></p>
                </div>
                <div class="shot-action-group">
                  <button class="button outline-blue" type="button" :disabled="actionBusy || Boolean(activeBreakdownTask)" @click="startEpisodeBreakdown(true)">↻&nbsp; 重新拉片</button>
                  <div class="more-menu-wrap">
                    <button class="button secondary" type="button" @click="moreOpen = !moreOpen">更多操作⌄</button>
                    <div v-if="moreOpen" class="more-menu">
                      <button type="button" @click="copyH3Description">复制 H3 描述</button>
                      <button type="button" @click="router.push(`/projects/${encodeURIComponent(projectId)}`)">返回原片视频</button>
                    </div>
                  </div>
                </div>
              </header>

              <div class="video-stage">
                <video v-if="shotReference(selectedShot)" :key="shotReference(selectedShot) || ''" :src="shotReference(selectedShot) || ''" controls playsinline preload="metadata"></video>
                <div v-else class="video-empty"><strong>当前分镜没有可播放 Reference Clip</strong><span>请先确认镜头检测结果和媒体文件。</span></div>
              </div>

              <div class="filmstrip-wrap">
                <div class="filmstrip-time-labels"><span>{{ formatTimeUs(Math.max(0, selectedShot.start_us - 3_000_000)) }}</span><b>{{ formatTimeUs(selectedShot.start_us) }}</b><b>{{ formatTimeUs(selectedShot.end_us) }}</b><span>{{ formatTimeUs(selectedShot.end_us + 3_000_000) }}</span></div>
                <div class="filmstrip-row">
                  <button type="button" :disabled="selectedShotIndex <= 0" @click="shots[selectedShotIndex - 1] && selectShot(shots[selectedShotIndex - 1])">‹</button>
                  <div class="filmstrip-track">
                    <button v-for="shot in filmstripShots" :key="shot.id" type="button" :class="['film-frame', { active: shot.id === selectedShot.id }]" @click="selectShot(shot)">
                      <img v-if="shotThumbnail(shot)" :src="shotThumbnail(shot) || ''" alt="" />
                      <span v-else>{{ shot.ordinal }}</span>
                    </button>
                  </div>
                  <button type="button" :disabled="selectedShotIndex >= shots.length - 1" @click="shots[selectedShotIndex + 1] && selectShot(shots[selectedShotIndex + 1])">›</button>
                </div>
              </div>

              <div class="boundary-editor">
                <label><span>开始时间</span><input v-model="startInput" :disabled="!canEditStart || adjustingBoundary" type="text" inputmode="decimal" /></label>
                <div class="duration-readout"><span>时长：</span><b>{{ formatDurationUs(selectedShot.duration_us) }}</b></div>
                <label><span>结束时间</span><input v-model="endInput" :disabled="!canEditEnd || adjustingBoundary" type="text" inputmode="decimal" /></label>
                <button class="button outline-blue" type="button" :disabled="!boundaryChanged || adjustingBoundary" @click="adjustShotRange">↻&nbsp; {{ adjustingBoundary ? '保存中…' : '调整分镜范围' }}</button>
              </div>

              <section class="quick-overview">
                <h3>快速信息概览</h3>
                <div class="overview-grid">
                  <div><span>场景</span><b>{{ sceneName }}</b></div>
                  <div><span>景别</span><b>{{ selectedTimelineShot?.cinematography.shot_type || selectedShot.shot_type || '—' }}</b></div>
                  <div><span>机位</span><b>{{ selectedTimelineShot?.cinematography.composition || '—' }}</b></div>
                  <div><span>运镜</span><b>{{ selectedTimelineShot?.cinematography.camera_motion || selectedShot.camera_motion || '—' }}</b></div>
                  <div><span>光线</span><b>{{ lightLabel }}</b></div>
                  <div><span>构图</span><b>{{ selectedTimelineShot?.cinematography.composition || '—' }}</b></div>
                  <div class="people-overview"><span>主要人物</span><b><i v-for="person in selectedPeople.slice(0, 4)" :key="person.ref">{{ personDisplayName(person).slice(0, 1) }}</i>{{ selectedPeople.length }} 人</b></div>
                  <div><span>对话行数</span><b>{{ selectedDialogue.length }} 行</b></div>
                  <div class="wide"><span>关键道具</span><b>{{ selectedProps.length ? selectedProps.map((item) => item.name).join('、') : '—' }}</b></div>
                </div>
              </section>
            </template>
            <div v-else class="workbench-empty">请选择一个分镜查看详情</div>
          </section>

          <aside class="detail-panel panel-card">
            <div class="detail-tabs">
              <button :class="{ active: detailTab === 'breakdown' }" type="button" @click="detailTab = 'breakdown'">拉片信息</button>
              <button :class="{ active: detailTab === 'people' }" type="button" @click="detailTab = 'people'">人物 ({{ selectedPeople.length }})</button>
              <button :class="{ active: detailTab === 'assets' }" type="button" @click="detailTab = 'assets'">场景 / 道具</button>
              <button :class="{ active: detailTab === 'dialogue' }" type="button" @click="detailTab = 'dialogue'">对白 ({{ selectedDialogue.length }})</button>
            </div>

            <div class="detail-scroll">
              <template v-if="selectedShot && selectedTimelineShot && selectedScene">
                <template v-if="detailTab === 'breakdown'">
                  <section class="info-card">
                    <h3><span>♟</span>动作与表情</h3>
                    <div class="info-block"><b>动作描述</b><p>{{ actionSummary }}</p></div>
                    <div class="info-block"><b>人物交互</b><p>{{ interactionSummary }}</p></div>
                  </section>

                  <section class="info-card environment-card">
                    <h3><span>✿</span>环境与氛围</h3>
                    <div class="mini-grid"><div><span>环境描述</span><b>{{ sceneEnvironment }}</b></div><div><span>时间 / 氛围</span><b>{{ selectedScene.scene_info.time_of_day || '—' }}</b></div></div>
                  </section>

                  <section class="info-card">
                    <h3><span>⚑</span>剧情作用</h3>
                    <div class="mini-grid one"><div><span>剧情摘要</span><b>{{ selectedScene.story_summary || selectedTimelineShot.visual_description || '暂无剧情摘要' }}</b></div></div>
                  </section>

                  <section class="info-card technical-card">
                    <h3><span>⚙</span>技术信息</h3>
                    <div class="technical-grid">
                      <div><span>分辨率</span><b>{{ currentEpisode?.width && currentEpisode?.height ? `${currentEpisode.width} × ${currentEpisode.height}` : '—' }}</b></div>
                      <div><span>帧率</span><b>{{ currentEpisode?.fps ? `${Number(currentEpisode.fps).toFixed(0)} FPS` : '—' }}</b></div>
                      <div><span>画面质量</span><b class="quality-badge">{{ qualityLabel }}</b></div>
                    </div>
                  </section>

                  <section class="info-card h3-card">
                    <div class="info-card-title"><h3>H3 重拍描述（结构化）</h3><button type="button" @click="h3Open = true">查看完整描述</button></div>
                    <div class="h3-lines"><div v-for="item in h3Sections" :key="item.label"><span>{{ item.label }}</span><p>{{ item.value }}</p></div></div>
                  </section>
                </template>

                <template v-else-if="detailTab === 'people'">
                  <section v-if="selectedPeople.length" class="tab-list-card">
                    <article v-for="person in selectedPeople" :key="person.ref" class="person-card">
                      <span class="person-avatar">
                        <img v-if="person.final_character?.cover_url" :src="person.final_character.cover_url" alt="" />
                        <b v-else>{{ personDisplayName(person).slice(0, 1) }}</b>
                      </span>
                      <div><strong>{{ personDisplayName(person) }}</strong><small>{{ person.final_character ? '已归并为正式人物' : '匿名人物 / 待确认' }}</small><p v-if="person.appearance">{{ person.appearance }}</p></div>
                    </article>
                  </section>
                  <div v-else class="tab-empty">当前分镜没有识别到主要人物</div>
                </template>

                <template v-else-if="detailTab === 'assets'">
                  <section class="info-card">
                    <h3>场景</h3>
                    <div class="asset-scene-row"><strong>{{ sceneName }}</strong><span>{{ [selectedScene.scene_info.interior_exterior, selectedScene.scene_info.time_of_day].filter(Boolean).join(' · ') || '暂无场景标签' }}</span><p>{{ sceneEnvironment }}</p></div>
                  </section>
                  <section class="info-card">
                    <h3>道具</h3>
                    <div v-if="selectedProps.length" class="prop-list"><div v-for="prop in selectedProps" :key="`${prop.name}-${prop.interaction}`"><span>{{ prop.name.slice(0, 1) }}</span><p><b>{{ prop.name }}</b><small>{{ prop.interaction }}</small></p></div></div>
                    <div v-else class="tab-empty compact">当前分镜没有关键道具</div>
                  </section>
                </template>

                <template v-else>
                  <section v-if="selectedDialogue.length" class="dialogue-list">
                    <article v-for="(dialogue, index) in selectedDialogue" :key="`${dialogue.start_us}-${dialogue.end_us}-${index}`">
                      <header><strong>{{ dialogueSpeaker(dialogue) }}</strong><span>{{ formatTimeUs(dialogue.start_us) }} - {{ formatTimeUs(dialogue.end_us) }}</span></header>
                      <p>{{ dialogue.text }}</p>
                    </article>
                  </section>
                  <div v-else class="tab-empty">当前分镜没有对白</div>
                </template>
              </template>
              <div v-else class="tab-empty large">当前分镜还没有可展示的拉片结果。<br />可以查看 Reference Clip，并在确认分镜边界后执行整集拉片。</div>
            </div>
            <footer class="data-updated">数据更新时间：{{ currentRun?.completed_at ? new Date(currentRun.completed_at).toLocaleString('zh-CN', { hour12: false }) : '—' }}</footer>
          </aside>
        </section>

        <div class="bottom-tip"><span>ⓘ</span>提示：调整分镜范围或重新拉片后，相关分析结果可能需要按当前最新分镜重新生成，请确认后操作。</div>
      </main>
    </div>

    <div v-if="helpOpen" class="modal-backdrop" @click.self="helpOpen = false">
      <section class="help-dialog">
        <header><div><strong>AI 拉片操作说明</strong><span>只在用户明确操作时启动重任务</span></div><button type="button" @click="helpOpen = false">×</button></header>
        <div class="help-grid">
          <article><b>1</b><div><strong>先看分镜</strong><p>左侧选择分镜，中间播放原片 Reference Clip，并确认开始 / 结束边界。</p></div></article>
          <article><b>2</b><div><strong>再看拉片事实</strong><p>右侧直接查看人物、场景、动作、对白和镜头信息，不展示 ASR / OCR / VLM 技术证据。</p></div></article>
          <article><b>3</b><div><strong>有问题再重跑</strong><p>整集拉片会创建新的后台任务；刷新页面只读状态，不会自动重复执行模型。</p></div></article>
          <article><b>4</b><div><strong>边界修改后主动重算</strong><p>修改分镜边界会形成新的 Shot Revision。系统不会在保存后偷偷启动 GPU 重任务。</p></div></article>
        </div>
      </section>
    </div>

    <div v-if="h3Open" class="modal-backdrop" @click.self="h3Open = false">
      <section class="h3-dialog">
        <header><div><strong>H3 重拍描述</strong><span>当前分镜的结构化阅读结果</span></div><button type="button" @click="h3Open = false">×</button></header>
        <div class="h3-full-lines"><div v-for="item in h3Sections" :key="item.label"><b>{{ item.label }}</b><p>{{ item.value }}</p></div></div>
        <footer><button class="button secondary" type="button" @click="h3Open = false">关闭</button><button class="button primary" type="button" @click="copyH3Description">复制描述</button></footer>
      </section>
    </div>
  </div>
</template>

<style scoped src="../project-breakdown-v1.css"></style>
