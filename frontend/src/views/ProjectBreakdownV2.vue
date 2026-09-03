<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { breakdownApi } from '../api/breakdown'
import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { sceneTimelineApi } from '../api/scene-timeline'
import { evaluateBreakdownShotQuality } from '../breakdown-quality'
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
type DetailTab = 'shot' | 'people' | 'assets' | 'dialogue' | 'remake'
type StageVisualState = 'complete' | 'active' | 'processing' | 'review' | 'waiting'

interface TimelineShotContext {
  scene: SceneTimelineScene
  shot: SceneTimelineShot
}

interface StageDisplay {
  number: number
  label: string
  description: string
  statusLabel: string
  state: StageVisualState
  active: boolean
}

interface ShotStatusDisplay {
  state: ShotUiStatus
  label: string
  detail?: string
}

interface PendingItem {
  key: string
  label: string
  tone: 'orange' | 'blue' | 'red'
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
const detailTab = ref<DetailTab>('shot')
const searchText = ref('')
const currentPage = ref(1)
const startInput = ref('')
const endInput = ref('')
const helpOpen = ref(false)

let episodeRequestSerial = 0
let pollTimer: ReturnType<typeof setInterval> | null = null

const episodes = computed(() => [...(project.value?.episodes || [])].sort((a, b) => a.sort_order - b.sort_order))
const currentEpisode = computed(() => episodes.value.find((item) => item.id === selectedEpisodeId.value) || null)
const currentRun = computed(() => runs.value.find((item) => item.is_current) || runs.value[0] || null)

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
  if (values.some((stage) => stage.execution === 'QUEUED' || stage.execution === 'PROCESSING')) return { state: active ? 'active' : 'processing', statusLabel: '处理中' }
  if (values.some((stage) => stage.readiness === 'BLOCKED_REVIEW')) return { state: active ? 'active' : 'review', statusLabel: '待确认' }
  return { state: active ? 'active' : 'waiting', statusLabel: active ? '进行中' : '未开始' }
}

const stageItems = computed<StageDisplay[]>(() => {
  const definitions = [
    { number: 1, label: '原短剧视频', description: '上传、排序与镜头检测', keys: ['project_setup', 'source_split'], active: false },
    { number: 2, label: 'AI 拉片', description: '镜头内容分析 · 人物归并 · 对白校正', keys: ['source_understanding'], active: true },
    { number: 3, label: '原片确认', description: '人物 / 场景 / 道具确认', keys: ['source_assets', 'source_snapshot'], active: false },
    { number: 4, label: '视频重做', description: '本土化、配音与视频生成', keys: ['target_design', 'target_dialogue', 'remake_timing', 'h3_generation'], active: false },
    { number: 5, label: '成片输出', description: '后期检查与最终导出', keys: ['postproduction_output'], active: false },
  ]
  return definitions.map((item) => ({ ...item, ...stageStateFor(item.keys, item.active) }))
})

function hasCharacterReviewForShot(context: TimelineShotContext): boolean {
  return context.shot.people.some((ref) => {
    const person = context.scene.people.find((item) => item.ref === ref)
    return person?.final_character === null
  })
}

function statusForShot(shot: Shot): ShotStatusDisplay {
  const context = timelineShotMap.value.get(shot.ordinal)
  if (!context) return { state: 'unprocessed', label: '待拉片' }
  if (hasCharacterReviewForShot(context)) return { state: 'review', label: '待确认', detail: '人物身份待确认' }
  const quality = evaluateBreakdownShotQuality(context.shot)
  if (!quality.ready) return { state: 'review', label: '待确认', detail: quality.reason }
  return { state: 'completed', label: '已完成' }
}

const statusCounts = computed(() => {
  const counts: Record<ShotUiStatus, number> = { completed: 0, unprocessed: 0, review: 0, failed: 0 }
  for (const shot of shots.value) counts[statusForShot(shot).state] += 1
  return counts
})

function personDisplayName(person: SceneTimelinePerson): string {
  return person.final_character?.name || person.display_name || '人物'
}

function dialogueSpeaker(dialogue: SceneTimelineDialogue): string {
  const scene = selectedScene.value
  if (!scene || !dialogue.speakers.length) return '待确认说话人'
  const names = dialogue.speakers.map((ref) => {
    const person = scene.people.find((item) => item.ref === ref)
    return person ? personDisplayName(person) : '人物'
  })
  return Array.from(new Set(names)).join('、') || '待确认说话人'
}

function contextForShot(shot: Shot): TimelineShotContext | null {
  return timelineShotMap.value.get(shot.ordinal) || null
}

function shotSummary(shot: Shot): string {
  const context = contextForShot(shot)
  if (!context) return shot.short_description || '等待拉片'
  const names = context.shot.people
    .map((ref) => context.scene.people.find((item) => item.ref === ref))
    .filter((item): item is SceneTimelinePerson => Boolean(item))
    .map(personDisplayName)
  const personText = names.length ? names.slice(0, 2).join('、') : '无人物'
  const sceneText = context.scene.final_scene?.name || context.scene.title || context.scene.scene_info.location || '未识别场景'
  const dialogueText = context.shot.dialogue.length ? `${context.shot.dialogue.length}句对白` : '无对白'
  return `${personText} · ${sceneText} · ${dialogueText}`
}

function shotSearchText(shot: Shot): string {
  const context = contextForShot(shot)
  const pieces = [
    `shot ${shot.ordinal}`,
    shot.short_description || '',
    shotSummary(shot),
    context?.shot.summary || '',
    context?.shot.narrative_function || '',
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
const sceneEnvironment = computed(() => selectedScene.value?.scene_info.environment || '暂无环境描述')
const peopleNames = computed(() => selectedPeople.value.map(personDisplayName))
const performanceTexts = computed(() => selectedTimelineShot.value?.performance.map((item) => item.text.trim()).filter(Boolean) || [])
const actionSummary = computed(() => performanceTexts.value.join('；') || selectedTimelineShot.value?.visual_description || '暂无动作描述')
const interactionSummary = computed(() => {
  const shot = selectedTimelineShot.value
  if (!shot || !shot.people.length) return '未识别明确人物互动'
  if (shot.people.length === 1) return '当前镜头以单人行为为主'
  return `${peopleNames.value.join('、')} 同镜出现，具体互动以动作描述为准`
})

function performanceByKeywords(keywords: string[], fallback: string): string {
  const text = performanceTexts.value.find((item) => keywords.some((keyword) => item.includes(keyword)))
  return text || fallback
}

const expressionSummary = computed(() => performanceByKeywords(['表情', '笑', '惊', '哭', '怒', '愤', '紧张', '平静', '悲', '喜'], '暂无独立表情描述'))
const postureSummary = computed(() => performanceByKeywords(['站', '坐', '躺', '蹲', '姿态', '身体', '头部', '转身'], '暂无独立姿态描述'))
const gazeSummary = computed(() => performanceByKeywords(['视线', '看向', '注视', '望向', '眼神'], '暂无独立视线描述'))
const contentOverview = computed(() => selectedTimelineShot.value?.summary?.trim() || selectedTimelineShot.value?.visual_description?.trim() || selectedTimelineShot.value?.narrative_function?.trim() || '暂无当前镜头内容概要')
const shotNarrativeSummary = computed(() => selectedTimelineShot.value?.narrative_function?.trim() || '暂无当前镜头剧情作用')
const cameraShotType = computed(() => selectedTimelineShot.value?.cinematography.shot_type || selectedShot.value?.shot_type || '—')
const cameraComposition = computed(() => selectedTimelineShot.value?.cinematography.composition || '—')
const cameraMotion = computed(() => selectedTimelineShot.value?.cinematography.camera_motion || selectedShot.value?.camera_motion || '—')
const timeOfDay = computed(() => selectedScene.value?.scene_info.time_of_day || '—')
const interiorExterior = computed(() => selectedScene.value?.scene_info.interior_exterior || '—')
const dialogueSummary = computed(() => selectedDialogue.value.length
  ? selectedDialogue.value.map((item) => `${dialogueSpeaker(item)}：${item.text}`).join('；')
  : '无对白')
const propSummary = computed(() => selectedProps.value.length ? selectedProps.value.map((item) => item.name).join('、') : '无关键道具')

const selectedPendingItems = computed<PendingItem[]>(() => {
  if (!selectedTimelineShot.value) return []
  const items: PendingItem[] = []
  if (selectedPeople.value.some((person) => !person.final_character)) items.push({ key: 'person', label: '人物身份待确认', tone: 'orange' })
  if (selectedDialogue.value.some((dialogue) => !dialogue.speakers.length)) items.push({ key: 'dialogue', label: '对白说话人待确认', tone: 'blue' })
  const status = selectedStatus.value
  if (status?.state === 'review' && status.detail && !items.some((item) => status.detail?.includes(item.key === 'person' ? '人物' : '对白'))) {
    items.push({ key: 'quality', label: status.detail, tone: 'red' })
  }
  return items
})

const h3Ready = computed(() => Boolean(selectedTimelineShot.value) && selectedPendingItems.value.length === 0)
const h3Sections = computed(() => [
  { label: '人物', value: peopleNames.value.length ? peopleNames.value.join('、') : '无明确人物' },
  { label: '场景', value: sceneName.value },
  { label: '关键道具', value: propSummary.value },
  { label: '动作', value: actionSummary.value },
  { label: '表情', value: expressionSummary.value },
  { label: '视线', value: gazeSummary.value },
  { label: '景别', value: cameraShotType.value },
  { label: '机位', value: '未独立识别' },
  { label: '构图', value: cameraComposition.value },
  { label: '运镜', value: cameraMotion.value },
  { label: '对白', value: dialogueSummary.value },
  { label: '源镜头时长', value: selectedShot.value ? formatSecondsUs(selectedShot.value.duration_us) : '—' },
])

const selectedStatus = computed(() => selectedShot.value ? statusForShot(selectedShot.value) : null)
const breakdownProgressLabel = computed(() => {
  const task = activeBreakdownTask.value
  if (!task) return ''
  if (task.progress_percent === null) return task.stage_label || 'AI 拉片处理中'
  return `${task.stage_label || 'AI 拉片处理中'} ${Math.round(task.progress_percent)}%`
})

const timelineWindow = computed(() => {
  const shot = selectedShot.value
  if (!shot) return { start: 0, end: 1, left: 0, width: 0 }
  const previous = shots.value[selectedShotIndex.value - 1]
  const next = shots.value[selectedShotIndex.value + 1]
  const start = previous ? previous.start_us : Math.max(0, shot.start_us - 3_000_000)
  const end = next ? next.end_us : shot.end_us + 3_000_000
  const span = Math.max(1, end - start)
  return {
    start,
    end,
    left: Math.max(0, Math.min(100, ((shot.start_us - start) / span) * 100)),
    width: Math.max(1, Math.min(100, ((shot.end_us - shot.start_us) / span) * 100)),
  }
})

function episodeLabel(episode: Episode): string {
  const order = String(Math.max(1, episode.sort_order)).padStart(2, '0')
  return `EP${order}  ${episode.title || `第${episode.sort_order}集`}`
}

function formatTimeUs(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  const totalMs = Math.max(0, Math.round(value / 1000))
  const minutes = Math.floor(totalMs / 60_000)
  const seconds = Math.floor((totalMs % 60_000) / 1000)
  const ms = totalMs % 1000
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function formatSecondsUs(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return `${(Math.max(0, value) / 1_000_000).toFixed(2)} 秒`
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

function shotThumbnail(shot: Shot): string | null {
  return shot.thumbnail_url || contextForShot(shot)?.shot.thumbnail_url || null
}

function shotReference(shot: Shot | null): string | null {
  if (!shot) return null
  return shot.reference_url || contextForShot(shot)?.shot.reference_url || null
}

function selectShot(shot: Shot): void {
  selectedShotId.value = shot.id
  detailTab.value = 'shot'
  actionError.value = ''
  actionMessage.value = ''
  syncBoundaryInputs()
  void router.replace({ query: { ...route.query, episode: selectedEpisodeId.value, shot: String(shot.ordinal) } })
}

function selectStage(item: StageDisplay): void {
  if (item.number === 1) void router.push({ name: 'studio', params: { projectId: projectId.value } })
  if (item.number === 3) void router.push({ name: 'source-confirm', params: { projectId: projectId.value } })
  if (item.number === 4) void router.push({ name: 'remake', params: { projectId: projectId.value } })
  if (item.number === 5) void router.push({ name: 'output', params: { projectId: projectId.value } })
}

function showEditUnavailable(label: string): void {
  actionError.value = ''
  actionMessage.value = `${label}编辑入口已按设计稿预留；当前后端还没有对应的安全写接口，本轮不做前端假保存。`
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
    const proceed = window.confirm('当前后端还没有真正的单分镜拉片接口。继续会重新拉片本集全部分镜；不会伪装成只处理当前 Shot。是否继续？')
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
    actionMessage.value = 'AI 拉片任务已进入后台执行。刷新页面只读取状态，不会重复启动任务。'
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
    actionError.value = '当前后端一次只能安全移动一个公共边界。请先修改一侧并保存，再修改另一侧。'
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
    actionMessage.value = '分镜范围已保存。当前镜头内容发生变化后，需要用户明确重新执行拉片。'
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
  <div class="breakdown-page-v2">
    <header class="global-topbar">
      <button class="brand" type="button" @click="router.push('/')">
        <span class="brand-mark" aria-hidden="true"><i></i><i></i></span>
        <strong>AI Drama Studio</strong>
      </button>
      <span class="top-divider"></span>
      <nav class="breadcrumbs" aria-label="面包屑">
        <button type="button" @click="router.push('/')">项目管理</button>
        <span>›</span><strong>AI 拉片</strong><span>›</span>
        <strong>{{ currentEpisode ? `EP${String(currentEpisode.sort_order).padStart(2, '0')}` : '—' }}</strong>
      </nav>
      <button class="help-button" type="button" @click="helpOpen = true"><span>?</span> 操作说明</button>
    </header>

    <div class="page-shell">
      <aside class="project-progress-card">
        <div class="project-meta">
          <strong>{{ project?.name || '当前项目' }}</strong>
          <span>项目 ID：{{ projectId || '—' }}</span>
        </div>
        <div class="progress-heading">
          <div class="progress-copy"><span>当前进度</span><b>{{ overallProgress }}%</b></div>
          <div class="progress-track"><span :style="{ width: `${overallProgress}%` }"></span></div>
        </div>

        <div class="stage-list">
          <button
            v-for="item in stageItems"
            :key="item.number"
            type="button"
            :class="['stage-item', `state-${item.state}`, { active: item.active }]"
            @click="selectStage(item)"
          >
            <span class="stage-number">{{ item.number }}</span>
            <span class="stage-copy"><strong>{{ item.label }}</strong><small>{{ item.description }}</small><em>{{ item.statusLabel }}</em></span>
          </button>
        </div>
        <button class="back-projects" type="button" @click="router.push('/')">← 返回项目列表</button>
      </aside>

      <main class="breakdown-main">
        <section class="page-heading-card">
          <div class="heading-main">
            <div class="title-line"><h1>AI 拉片</h1><span>分镜内容分析 · 人物归并 · 对白校正 · H3 重拍数据准备</span></div>
            <div class="heading-data-row">
              <select :value="selectedEpisodeId" :disabled="loading || !episodes.length" @change="changeEpisode">
                <option v-for="episode in episodes" :key="episode.id" :value="episode.id">{{ episodeLabel(episode) }}</option>
              </select>
              <div class="stat-card"><span class="stat-icon blue">⌘</span><p><b>{{ shots.length }}</b><small>个分镜</small></p></div>
              <div class="stat-card"><span class="stat-icon green">✓</span><p><b>{{ statusCounts.completed }}</b><small>已完成</small></p></div>
              <div class="stat-card"><span class="stat-icon orange">!</span><p><b>{{ statusCounts.review }}</b><small>待确认</small></p></div>
              <div class="stat-card"><span class="stat-icon red">×</span><p><b>{{ statusCounts.failed }}</b><small>失败</small></p></div>
              <span v-if="activeBreakdownTask" class="running-pill">{{ breakdownProgressLabel }}</span>
            </div>
          </div>
          <div class="heading-actions">
            <button class="button secondary" type="button" :disabled="loading || episodeLoading" @click="refreshAll(false)">↻ 刷新</button>
            <button class="button secondary current-shot-action" type="button" :disabled="!selectedShot || actionBusy || Boolean(activeBreakdownTask)" @click="startEpisodeBreakdown(true)">▷ 当前分镜拉片</button>
            <button class="button primary" type="button" :disabled="!currentEpisode || actionBusy || Boolean(activeBreakdownTask)" @click="startEpisodeBreakdown(false)">▶ {{ activeBreakdownTask ? '拉片中' : '整集拉片' }} <b>⌄</b></button>
          </div>
        </section>

        <div v-if="pageError || actionError || actionMessage || timelineError" class="message-stack">
          <div v-if="pageError" class="message danger">{{ pageError }}</div>
          <div v-if="actionError" class="message danger">{{ actionError }}</div>
          <div v-if="actionMessage" class="message success">{{ actionMessage }}</div>
          <div v-if="timelineError && shots.length" class="message warning">当前分镜仍可查看，但拉片结果读取失败：{{ timelineError }}</div>
        </div>

        <section class="workspace-grid">
          <aside class="shot-list-card panel-card">
            <header class="panel-header"><strong>分镜</strong></header>
            <div class="shot-search"><span>⌕</span><input v-model="searchText" type="search" placeholder="搜索分镜 / 对白 / 人物" /></div>
            <div class="shot-filters">
              <button :class="{ active: shotFilter === 'all' }" type="button" @click="changeFilter('all')">全部 {{ shots.length }}</button>
              <button :class="{ active: shotFilter === 'unprocessed' }" type="button" @click="changeFilter('unprocessed')">待处理 {{ statusCounts.unprocessed }}</button>
              <button :class="{ active: shotFilter === 'review' }" type="button" @click="changeFilter('review')">待确认 {{ statusCounts.review }}</button>
              <button :class="{ active: shotFilter === 'failed' }" type="button" @click="changeFilter('failed')">失败 {{ statusCounts.failed }}</button>
            </div>

            <div v-if="episodeLoading" class="shot-list-loading">正在读取分镜…</div>
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
                <span class="shot-thumb"><img v-if="shotThumbnail(shot)" :src="shotThumbnail(shot) || ''" alt="" loading="lazy" /><i v-else>SHOT</i></span>
                <span class="shot-row-copy">
                  <strong>Shot {{ String(shot.ordinal).padStart(2, '0') }}</strong>
                  <small>{{ formatTimeUs(shot.start_us) }} → {{ formatTimeUs(shot.end_us) }}</small>
                  <span class="shot-summary">{{ shotSummary(shot) }}</span>
                  <em :class="`status-${statusForShot(shot).state}`"><i></i>{{ statusForShot(shot).label }}<template v-if="statusForShot(shot).detail"> · {{ statusForShot(shot).detail }}</template></em>
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
                <div><h2>Shot {{ String(selectedShot.ordinal).padStart(2, '0') }}</h2><p>{{ formatTimeUs(selectedShot.start_us) }} → {{ formatTimeUs(selectedShot.end_us) }} <span>时长 {{ formatSecondsUs(selectedShot.duration_us) }}</span></p></div>
                <button class="button outline-blue" type="button" :disabled="actionBusy || Boolean(activeBreakdownTask)" @click="startEpisodeBreakdown(true)">↻ 重新拉片</button>
              </header>

              <div class="video-stage">
                <span class="video-label">Reference Video</span>
                <video v-if="shotReference(selectedShot)" :key="shotReference(selectedShot) || ''" :src="shotReference(selectedShot) || ''" controls playsinline preload="metadata"></video>
                <div v-else class="video-empty"><strong>当前分镜没有可播放 Reference Clip</strong><span>请先确认镜头检测结果和媒体文件。</span></div>
              </div>

              <div class="filmstrip-wrap">
                <div class="filmstrip-time-labels"><span>{{ formatTimeUs(timelineWindow.start) }}</span><b>{{ formatTimeUs(selectedShot.start_us) }}</b><b>{{ formatTimeUs(selectedShot.end_us) }}</b><span>{{ formatTimeUs(timelineWindow.end) }}</span></div>
                <div class="filmstrip-row">
                  <button type="button" :disabled="selectedShotIndex <= 0" @click="shots[selectedShotIndex - 1] && selectShot(shots[selectedShotIndex - 1])">‹</button>
                  <div class="filmstrip-track">
                    <button v-for="shot in filmstripShots" :key="shot.id" type="button" :class="['film-frame', { active: shot.id === selectedShot.id }]" @click="selectShot(shot)"><img v-if="shotThumbnail(shot)" :src="shotThumbnail(shot) || ''" alt="" /><span v-else>{{ shot.ordinal }}</span></button>
                  </div>
                  <button type="button" :disabled="selectedShotIndex >= shots.length - 1" @click="shots[selectedShotIndex + 1] && selectShot(shots[selectedShotIndex + 1])">›</button>
                </div>
              </div>

              <section class="boundary-editor">
                <h3>分镜范围</h3>
                <div class="boundary-fields">
                  <label><span>开始时间</span><input v-model="startInput" :disabled="!canEditStart || adjustingBoundary" type="text" inputmode="decimal" /></label>
                  <label><span>结束时间</span><input v-model="endInput" :disabled="!canEditEnd || adjustingBoundary" type="text" inputmode="decimal" /></label>
                  <div class="duration-readout"><span>时长</span><b>{{ formatSecondsUs(selectedShot.duration_us) }}</b></div>
                  <button class="button outline-blue" type="button" :disabled="!boundaryChanged || adjustingBoundary" @click="adjustShotRange">{{ adjustingBoundary ? '保存中…' : '保存分镜范围' }}</button>
                </div>
                <div class="range-labels"><span>{{ formatTimeUs(timelineWindow.start) }}</span><span>{{ formatTimeUs(timelineWindow.end) }}</span></div>
                <div class="range-preview"><span class="range-selection" :style="{ left: `${timelineWindow.left}%`, width: `${timelineWindow.width}%` }"><i></i><i></i></span></div>
              </section>
            </template>
            <div v-else class="workbench-empty">请选择一个分镜查看详情</div>
          </section>

          <aside class="detail-panel panel-card">
            <div class="detail-tabs">
              <button :class="{ active: detailTab === 'shot' }" type="button" @click="detailTab = 'shot'">镜头信息</button>
              <button :class="{ active: detailTab === 'people' }" type="button" @click="detailTab = 'people'">人物</button>
              <button :class="{ active: detailTab === 'assets' }" type="button" @click="detailTab = 'assets'">场景道具</button>
              <button :class="{ active: detailTab === 'dialogue' }" type="button" @click="detailTab = 'dialogue'">对白</button>
              <button :class="{ active: detailTab === 'remake' }" type="button" @click="detailTab = 'remake'">重拍信息</button>
            </div>

            <div class="detail-scroll">
              <template v-if="selectedShot && selectedTimelineShot && selectedScene">
                <template v-if="detailTab === 'shot'">
                  <section class="info-card editable-card">
                    <div class="info-card-title"><h3>内容概要</h3><button type="button" @click="showEditUnavailable('内容概要')">✎ 编辑</button></div>
                    <p class="summary-paragraph">{{ contentOverview }}</p>
                  </section>

                  <section class="info-card editable-card">
                    <div class="info-card-title"><h3>动作与表演</h3><button type="button" @click="showEditUnavailable('动作与表演')">✎ 编辑</button></div>
                    <dl class="field-list"><div><dt>动作</dt><dd>{{ actionSummary }}</dd></div><div><dt>表情</dt><dd>{{ expressionSummary }}</dd></div><div><dt>姿态</dt><dd>{{ postureSummary }}</dd></div><div><dt>视线</dt><dd>{{ gazeSummary }}</dd></div><div><dt>人物交互</dt><dd>{{ interactionSummary }}</dd></div></dl>
                  </section>

                  <section class="info-card editable-card">
                    <div class="info-card-title"><h3>镜头语言</h3><button type="button" @click="showEditUnavailable('镜头语言')">✎ 编辑</button></div>
                    <dl class="field-list"><div><dt>景别</dt><dd>{{ cameraShotType }}</dd></div><div><dt>机位</dt><dd>未独立识别</dd></div><div><dt>构图</dt><dd>{{ cameraComposition }}</dd></div><div><dt>运镜</dt><dd>{{ cameraMotion }}</dd></div></dl>
                  </section>

                  <section class="info-card editable-card">
                    <div class="info-card-title"><h3>画面</h3><button type="button" @click="showEditUnavailable('画面信息')">✎ 编辑</button></div>
                    <dl class="field-list"><div><dt>时间</dt><dd>{{ timeOfDay }}</dd></div><div><dt>空间</dt><dd>{{ interiorExterior }}</dd></div><div><dt>光线</dt><dd>暂无独立光线描述</dd></div><div><dt>氛围</dt><dd>{{ sceneEnvironment }}</dd></div></dl>
                  </section>

                  <section class="pending-card">
                    <div class="pending-title"><strong>待处理事项（本分镜）</strong><span>{{ selectedPendingItems.length ? `${selectedPendingItems.length} 项` : '已处理' }}</span></div>
                    <div v-if="selectedPendingItems.length" class="pending-grid"><div v-for="item in selectedPendingItems" :key="item.key" :class="['pending-item', item.tone]"><i>!</i><span>{{ item.label }}</span><b>1</b></div></div>
                    <div v-else class="pending-clear">✓ 当前分镜没有阻塞项</div>
                    <p v-if="selectedPendingItems.length">可进入原片确认前还需处理 <b>{{ selectedPendingItems.length }}</b> 项</p>
                  </section>
                </template>

                <template v-else-if="detailTab === 'people'">
                  <section class="tab-heading-row"><div><strong>当前分镜人物</strong><span>{{ selectedPeople.length }} 人</span></div><button type="button" @click="showEditUnavailable('本集人物管理')">管理本集人物</button></section>
                  <section v-if="selectedPeople.length" class="person-list">
                    <article v-for="person in selectedPeople" :key="person.ref" class="person-card">
                      <span class="person-avatar"><img v-if="person.final_character?.cover_url" :src="person.final_character.cover_url" alt="" /><b v-else>{{ personDisplayName(person).slice(0, 1) }}</b></span>
                      <div class="person-copy"><div><strong>{{ personDisplayName(person) }}</strong><em :class="{ pending: !person.final_character }">{{ person.final_character ? '✓ 已自动绑定' : '! 待确认人物' }}</em></div><p>{{ person.appearance || '暂无人物外观补充描述' }}</p><button type="button" @click="showEditUnavailable('人物绑定')">修改人物</button></div>
                    </article>
                  </section>
                  <div v-else class="tab-empty">当前分镜没有识别到人物</div>
                </template>

                <template v-else-if="detailTab === 'assets'">
                  <section class="info-card editable-card"><div class="info-card-title"><h3>场景</h3><button type="button" @click="showEditUnavailable('场景')">✎ 编辑</button></div><dl class="field-list"><div><dt>名称</dt><dd>{{ sceneName }}</dd></div><div><dt>环境</dt><dd>{{ sceneEnvironment }}</dd></div><div><dt>时间</dt><dd>{{ timeOfDay }}</dd></div></dl></section>
                  <section class="info-card editable-card"><div class="info-card-title"><h3>道具</h3><button type="button" @click="showEditUnavailable('道具')">＋ 添加道具</button></div><div v-if="selectedProps.length" class="prop-list"><div v-for="prop in selectedProps" :key="`${prop.name}-${prop.interaction}`"><span>{{ prop.name.slice(0, 1) }}</span><p><b>{{ prop.name }}</b><small>{{ prop.interaction }}</small></p></div></div><div v-else class="tab-empty compact">当前分镜没有关键道具</div></section>
                </template>

                <template v-else-if="detailTab === 'dialogue'">
                  <section v-if="selectedDialogue.length" class="dialogue-list">
                    <article v-for="(dialogue, index) in selectedDialogue" :key="`${dialogue.start_us}-${dialogue.end_us}-${index}`">
                      <header><span>对白 {{ String(index + 1).padStart(2, '0') }}</span><button type="button" @click="showEditUnavailable('对白')">✎ 编辑</button></header>
                      <div class="dialogue-speaker"><span>说话人</span><strong>{{ dialogueSpeaker(dialogue) }}</strong></div>
                      <p>{{ dialogue.text }}</p>
                      <footer><span>{{ formatTimeUs(dialogue.start_us) }} → {{ formatTimeUs(dialogue.end_us) }}</span><em>{{ dialogue.speakers.length ? '已绑定说话人' : '需要确认说话人' }}</em></footer>
                    </article>
                  </section>
                  <div v-else class="tab-empty">本镜头无对白</div>
                </template>

                <template v-else>
                  <section class="remake-status" :class="{ ready: h3Ready }"><strong>{{ h3Ready ? '✓ H3 重拍信息完整' : '! H3 重拍信息仍有待确认项' }}</strong><span>以下内容直接由当前分镜已确认事实组合，不额外编造。</span></section>
                  <section class="info-card remake-card"><dl class="field-list"><div v-for="item in h3Sections" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div><div><dt>剧情作用</dt><dd>{{ shotNarrativeSummary }}</dd></div></dl></section>
                </template>
              </template>
              <div v-else class="tab-empty large">当前分镜还没有可展示的拉片结果。<br />可以先确认 Reference Clip 和分镜边界，再执行整集拉片。</div>
            </div>
            <footer class="data-updated">数据更新时间：{{ currentRun?.completed_at ? new Date(currentRun.completed_at).toLocaleString('zh-CN', { hour12: false }) : '—' }}</footer>
          </aside>
        </section>
      </main>
    </div>

    <div v-if="helpOpen" class="modal-backdrop" @click.self="helpOpen = false">
      <section class="help-dialog"><header><strong>AI 拉片操作说明</strong><button type="button" @click="helpOpen = false">×</button></header><div><p>1. 选择剧集后，可查看每个分镜的 Reference Clip、时间范围和拉片结果。</p><p>2. 当前页面按设计稿预留镜头、人物、场景道具、对白和重拍信息编辑入口；没有安全写接口的字段不会做前端假保存。</p><p>3. “当前分镜拉片”在后端单分镜任务完成前仍会明确提示整集重跑，不会伪装成单 Shot 成功。</p></div></section>
    </div>
  </div>
</template>

<style scoped src="../project-breakdown-v2.css"></style>
