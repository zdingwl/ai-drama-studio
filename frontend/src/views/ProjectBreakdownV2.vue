<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import ShotFramePreviewV4 from '../components/ShotFramePreviewV4.vue'
import { breakdownApi } from '../api/breakdown'
import { startQuietPolling } from '../utils/quietPolling'
import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { sceneTimelineApi, type SceneTimelineManualShotEdit } from '../api/scene-timeline'
import { evaluateBreakdownShotQuality, hasUnconfirmedSourcePeople } from '../breakdown-quality'
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
type ManualEditMode = 'summary' | 'performance' | 'camera' | 'scene' | 'dialogue'

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

interface ManualEditField {
  key: string
  label: string
  value: string
  multiline?: boolean
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
const framePreview = ref<{ src: string; title: string } | null>(null)
function openFramePreview(src: string, title: string): void { framePreview.value = { src, title } }
const manualEditOpen = ref(false)
const manualEditMode = ref<ManualEditMode>('summary')
const manualEditTitle = ref('')
const manualEditFields = ref<ManualEditField[]>([])
const manualEditDialogueIndex = ref<number | null>(null)
const manualEditSaving = ref(false)
const manualEditError = ref('')

let episodeRequestSerial = 0
let loadedEpisodeId = ''
let refreshing = false
let stopPolling: (() => void) | null = null
let disposed = false
let resultsRefreshPending = false
const handledFinishedTasks = new Set<string>()
const pollingError = ref('')

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

function shotTaskOrdinal(task: BackgroundTask): number | null {
  if (task.task_type !== 'SHOT_BREAKDOWN_P2') return null
  const match = task.title.match(/Shot\s+(\d+)/i)
  if (!match) return null
  const ordinal = Number(match[1])
  return Number.isInteger(ordinal) && ordinal > 0 ? ordinal : null
}

const activeBreakdownTask = computed(() => tasks.value
  .filter((task) => (
    isBreakdownTask(task)
    && (task.episode_id === selectedEpisodeId.value || task.episode_id === null)
    && (task.status === 'QUEUED' || task.status === 'PROCESSING')
  ))
  .sort((a, b) => taskTimestamp(b) - taskTimestamp(a))[0] || null)

const latestShotBreakdownTaskByOrdinal = computed(() => {
  const result = new Map<number, BackgroundTask>()
  const relevant = tasks.value
    .filter((task) => task.episode_id === selectedEpisodeId.value && task.task_type === 'SHOT_BREAKDOWN_P2')
    .sort((a, b) => taskTimestamp(b) - taskTimestamp(a))
  for (const task of relevant) {
    const ordinal = shotTaskOrdinal(task)
    if (ordinal !== null && !result.has(ordinal)) result.set(ordinal, task)
  }
  return result
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
const nextShot = computed(() => selectedShotIndex.value >= 0 ? shots.value[selectedShotIndex.value + 1] || null : null)
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
  if (!values.length) return { state: 'waiting', statusLabel: '状态未读取' }
  if (values.every((stage) => stage.consumable)) return { state: active ? 'active' : 'complete', statusLabel: '已完成' }
  if (values.some((stage) => stage.execution === 'QUEUED' || stage.execution === 'PROCESSING')) return { state: active ? 'active' : 'processing', statusLabel: '处理中' }
  if (values.some((stage) => stage.readiness === 'BLOCKED_REVIEW')) return { state: active ? 'active' : 'review', statusLabel: '待确认' }
  if (values.some((stage) => stage.validity === 'STALE')) return { state: 'waiting', statusLabel: '结果已过期' }
  if (values.some((stage) => stage.readiness === 'WAITING_RUNTIME')) return { state: 'waiting', statusLabel: '等待运行环境' }
  if (values.some((stage) => stage.execution === 'FAILED')) return { state: 'waiting', statusLabel: '执行失败' }
  if (values.some((stage) => stage.readiness === 'BLOCKED_DEPENDENCY')) return { state: 'waiting', statusLabel: '等待上游' }
  return { state: 'waiting', statusLabel: '尚未就绪' }
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
  return hasUnconfirmedSourcePeople(context.shot, context.scene.people)
}

function statusForShot(shot: Shot): ShotStatusDisplay {
  const latestTask = latestShotBreakdownTaskByOrdinal.value.get(shot.ordinal)
  if (latestTask?.status === 'FAILED') {
    return {
      state: 'failed',
      label: '失败',
      detail: latestTask.error_message || latestTask.message || '单分镜拉片失败',
    }
  }
  if (latestTask?.status === 'QUEUED') return { state: 'unprocessed', label: '排队中' }
  if (latestTask?.status === 'PROCESSING') {
    return { state: 'unprocessed', label: '拉片中', detail: latestTask.stage_label || undefined }
  }

  const context = timelineShotMap.value.get(shot.ordinal)
  if (!context) return { state: 'unprocessed', label: '待拉片' }
  if (!timeline.value?.is_current) return { state: 'unprocessed', label: '结果已过期', detail: '请重新整集拉片' }
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
const actionSummary = computed(() => performanceTexts.value.join('；') || '暂无动作描述')
const expressionSummary = computed(() => selectedTimelineShot.value?.performance_details?.expression || '暂无独立表情描述')
const postureSummary = computed(() => selectedTimelineShot.value?.performance_details?.posture || '暂无独立姿态描述')
const gazeSummary = computed(() => selectedTimelineShot.value?.performance_details?.gaze || '暂无独立视线描述')
const interactionSummary = computed(() => selectedTimelineShot.value?.performance_details?.interaction || '暂无独立人物交互描述')
const cameraAngle = computed(() => selectedTimelineShot.value?.cinematography.camera_angle || '未独立识别')
const lighting = computed(() => selectedTimelineShot.value?.cinematography.lighting || '暂无独立光线描述')
const contentOverview = computed(() => (selectedTimelineShot.value?.summary ?? selectedTimelineShot.value?.visual_description ?? selectedTimelineShot.value?.narrative_function)?.trim() || '暂无当前镜头内容概要')
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
  if (status?.state === 'failed' && status.detail) items.push({ key: 'failed', label: status.detail, tone: 'red' })
  return items
})

const sourceResultCurrent = computed(() => Boolean(timeline.value?.is_current) && !timelineError.value)
const editingBlocked = computed(() => !sourceResultCurrent.value || episodeLoading.value || actionBusy.value || adjustingBoundary.value || Boolean(activeBreakdownTask.value))
const h3Sections = computed(() => [
  { label: '人物', value: peopleNames.value.length ? peopleNames.value.join('、') : '无明确人物' },
  { label: '场景', value: sceneName.value },
  { label: '关键道具', value: propSummary.value },
  { label: '动作', value: actionSummary.value },
  { label: '表情', value: expressionSummary.value },
  { label: '视线', value: gazeSummary.value },
  { label: '景别', value: cameraShotType.value },
  { label: '机位', value: cameraAngle.value },
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

function selectShot(shot: Shot, openPendingConfirm = false): void {
  selectedShotId.value = shot.id
  const index = filteredShots.value.findIndex((item) => item.id === shot.id)
  if (index >= 0) currentPage.value = Math.floor(index / PAGE_SIZE) + 1
  detailTab.value = 'shot'
  actionError.value = ''
  actionMessage.value = ''
  syncBoundaryInputs()
  if (openPendingConfirm && selectedPendingItems.value.some((item) => item.key === 'person' || item.key === 'dialogue')) {
    goSourceConfirm()
    return
  }
  void router.replace({ query: { ...route.query, episode: selectedEpisodeId.value, shot: String(shot.ordinal) } })
}

function selectStage(item: StageDisplay): void {
  if (item.number === 1) void router.push({ name: 'studio', params: { projectId: projectId.value } })
  if (item.number === 3) void router.push({ name: 'source-confirm', params: { projectId: projectId.value } })
  if (item.number === 4) void router.push({ name: 'remake', params: { projectId: projectId.value } })
  if (item.number === 5) void router.push({ name: 'output', params: { projectId: projectId.value } })
}

function goSourceConfirm(): void {
  const query: Record<string, string> = {}
  if (selectedEpisodeId.value) query.episode = selectedEpisodeId.value
  if (selectedShot.value) query.shot = String(selectedShot.value.ordinal)
  void router.push({ name: 'source-confirm', params: { projectId: projectId.value }, query })
}

function manualFieldValue(key: string): string {
  return manualEditFields.value.find((field) => field.key === key)?.value || ''
}

function openManualEditor(mode: ManualEditMode, dialogueIndex: number | null = null): void {
  const shot = selectedTimelineShot.value
  const scene = selectedScene.value
  if (!shot || !scene || !selectedShot.value || editingBlocked.value) return

  manualEditMode.value = mode
  manualEditDialogueIndex.value = dialogueIndex
  manualEditError.value = ''

  if (mode === 'summary') {
    manualEditTitle.value = '内容概要'
    manualEditFields.value = [
      { key: 'summary', label: '内容概要', value: shot.summary ?? shot.visual_description ?? shot.narrative_function ?? '', multiline: true },
      { key: 'visual_description', label: '画面描述', value: shot.visual_description || '', multiline: true },
      { key: 'narrative_function', label: '剧情作用', value: shot.narrative_function || '', multiline: true },
    ]
  } else if (mode === 'performance') {
    manualEditTitle.value = '动作与表演'
    manualEditFields.value = [
      { key: 'performance_text', label: '动作', value: performanceTexts.value.join('；'), multiline: true },
      { key: 'expression', label: '表情', value: shot.performance_details?.expression || '', multiline: true },
      { key: 'posture', label: '姿态', value: shot.performance_details?.posture || '', multiline: true },
      { key: 'gaze', label: '视线', value: shot.performance_details?.gaze || '', multiline: true },
      { key: 'interaction', label: '人物交互', value: shot.performance_details?.interaction || '', multiline: true },
    ]
  } else if (mode === 'camera') {
    manualEditTitle.value = '镜头语言'
    manualEditFields.value = [
      { key: 'shot_type', label: '景别', value: cameraShotType.value === '—' ? '' : cameraShotType.value },
      { key: 'camera_angle', label: '机位', value: shot.cinematography.camera_angle || '' },
      { key: 'composition', label: '构图', value: cameraComposition.value === '—' ? '' : cameraComposition.value, multiline: true },
      { key: 'camera_motion', label: '运镜', value: cameraMotion.value === '—' ? '' : cameraMotion.value },
    ]
  } else if (mode === 'scene') {
    manualEditTitle.value = '画面信息'
    manualEditFields.value = [
      { key: 'time_of_day', label: '时间', value: timeOfDay.value === '—' ? '' : timeOfDay.value },
      { key: 'interior_exterior', label: '空间', value: interiorExterior.value === '—' ? '' : interiorExterior.value },
      { key: 'lighting', label: '光线', value: shot.cinematography.lighting || '', multiline: true },
      { key: 'environment', label: '氛围（同场景共享）', value: sceneEnvironment.value === '暂无环境描述' ? '' : sceneEnvironment.value, multiline: true },
    ]
  } else {
    const dialogue = dialogueIndex === null ? null : selectedDialogue.value[dialogueIndex]
    if (!dialogue || dialogueIndex === null) return
    manualEditTitle.value = `对白 ${String(dialogueIndex + 1).padStart(2, '0')}`
    manualEditFields.value = [{ key: 'dialogue_text', label: '最终源对白', value: dialogue.text, multiline: true }]
  }

  manualEditOpen.value = true
}

function closeManualEditor(): void {
  if (manualEditSaving.value) return
  manualEditOpen.value = false
  manualEditError.value = ''
  manualEditFields.value = []
  manualEditDialogueIndex.value = null
}

async function saveManualEdit(): Promise<void> {
  const shot = selectedShot.value
  if (!shot || !selectedEpisodeId.value || manualEditSaving.value) return

  const payload: SceneTimelineManualShotEdit = {}
  if (manualEditMode.value === 'summary') {
    payload.summary = manualFieldValue('summary')
    payload.visual_description = manualFieldValue('visual_description')
    payload.narrative_function = manualFieldValue('narrative_function')
  } else if (manualEditMode.value === 'performance') {
    payload.performance_text = manualFieldValue('performance_text')
    payload.expression = manualFieldValue('expression')
    payload.posture = manualFieldValue('posture')
    payload.gaze = manualFieldValue('gaze')
    payload.interaction = manualFieldValue('interaction')
  } else if (manualEditMode.value === 'camera') {
    payload.shot_type = manualFieldValue('shot_type')
    payload.camera_angle = manualFieldValue('camera_angle')
    payload.composition = manualFieldValue('composition')
    payload.camera_motion = manualFieldValue('camera_motion')
  } else if (manualEditMode.value === 'scene') {
    payload.lighting = manualFieldValue('lighting')
    payload.scene = {
      time_of_day: manualFieldValue('time_of_day'),
      interior_exterior: manualFieldValue('interior_exterior'),
      environment: manualFieldValue('environment'),
    }
  } else {
    const dialogueIndex = manualEditDialogueIndex.value
    const dialogueText = manualFieldValue('dialogue_text').trim()
    if (dialogueIndex === null) return
    if (!dialogueText) {
      manualEditError.value = '对白不能为空。'
      return
    }
    payload.dialogues = [{ index: dialogueIndex, text: dialogueText }]
  }

  manualEditSaving.value = true
  manualEditError.value = ''
  try {
    await sceneTimelineApi.editShot(selectedEpisodeId.value, shot.ordinal, payload)
    await loadEpisodeData()
    await loadProjectContext()
    actionError.value = ''
    actionMessage.value = `${manualEditTitle.value}已保存；人工修改只覆盖当前显示事实，不改写 AI 原始证据。`
    manualEditOpen.value = false
    manualEditFields.value = []
    manualEditDialogueIndex.value = null
  } catch (err) {
    manualEditError.value = err instanceof Error ? err.message : '保存失败，请稍后重试。'
  } finally {
    manualEditSaving.value = false
  }
}

function handlePendingItem(item: PendingItem): void {
  if (item.key === 'person' || item.key === 'dialogue') {
    goSourceConfirm()
    return
  }
  if (item.key === 'failed') {
    void startEpisodeBreakdown(true)
    return
  }
  if (item.label.includes('动作')) openManualEditor('performance')
  else if (item.label.includes('景别') || item.label.includes('构图')) openManualEditor('camera')
  else if (item.label.includes('对白')) detailTab.value = 'dialogue'
  else openManualEditor('summary')
}

async function loadProjectContext(): Promise<void> {
  if (!projectId.value) return
  const [projectResponse, flowResponse, taskResponse] = await Promise.allSettled([
    api.getProject(projectId.value),
    getProjectFlowState(projectId.value),
    api.listProjectTasks(projectId.value, 60),
  ])
  if (projectResponse.status === 'rejected') throw projectResponse.reason
  const projectResult = projectResponse.value
  project.value = projectResult
  if (flowResponse.status === 'fulfilled') flowState.value = flowResponse.value
  else pageError.value = '工作流状态刷新失败，保留最近一次状态。'
  if (taskResponse.status === 'fulfilled') tasks.value = taskResponse.value
  else pageError.value = '任务状态读取失败，请刷新后再启动任务。'

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

  const changedEpisode = loadedEpisodeId !== episodeId
  if (changedEpisode) {
    shots.value = []
    timeline.value = null
    runs.value = []
    loadedEpisodeId = episodeId
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
      timelineError.value = timelineResult.reason instanceof Error ? timelineResult.reason.message : '拉片结果当前不可用'
    }
    if (runsResult.status === 'fulfilled') runs.value = runsResult.value

    const requestedOrdinal = Number(route.query.shot || 0)
    const requestedShot = shots.value.find((item) => item.ordinal === requestedOrdinal)
    const currentExists = shots.value.some((item) => item.id === selectedShotId.value)
    if (!currentExists) selectedShotId.value = requestedShot?.id || shots.value[0]?.id || ''
    if (changedEpisode || !boundaryChanged.value) syncBoundaryInputs()
    if (changedEpisode) {
      const index = shots.value.findIndex((item) => item.id === selectedShotId.value)
      currentPage.value = Math.max(1, Math.floor(index / PAGE_SIZE) + 1)
    }
  } finally {
    if (serial === episodeRequestSerial) episodeLoading.value = false
  }
}

async function refreshAll(showLoading = false): Promise<void> {
  if (refreshing || manualEditOpen.value || adjustingBoundary.value) return
  refreshing = true
  if (showLoading) loading.value = true
  pageError.value = ''
  try {
    await loadProjectContext()
    await loadEpisodeData()
  } catch (err) {
    pageError.value = err instanceof Error ? err.message : 'AI 拉片页面读取失败'
  } finally {
    loading.value = false
    refreshing = false
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
  try { await loadEpisodeData() } catch (err) {
    pageError.value = err instanceof Error ? err.message : '剧集读取失败'
  }
}

async function startEpisodeBreakdown(fromShot = false): Promise<void> {
  const episode = currentEpisode.value
  if (!episode || pageError.value || actionBusy.value || activeBreakdownTask.value || episodeLoading.value || adjustingBoundary.value) return
  if (episode.shot_count <= 0) {
    actionError.value = '本集还没有可用分镜，请先回到“原短剧视频”完成镜头检测。'
    return
  }

  const shot = selectedShot.value
  if (fromShot) {
    if (!shot) return
    if (!sourceResultCurrent.value) {
      actionError.value = '当前分镜拉片需要完整整集基线，请先完成本集整集拉片。'
      return
    }
  } else if (timeline.value) {
    const proceed = window.confirm('重新整集拉片会生成新的拉片 Run，当前结果会保留为历史。是否继续？')
    if (!proceed) return
  }

  actionBusy.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const task = fromShot && shot
      ? await breakdownApi.startShot(episode.id, shot.ordinal)
      : await breakdownApi.startEpisode(episode.id)
    tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)]
    actionMessage.value = fromShot && shot
      ? `Shot ${String(shot.ordinal).padStart(2, '0')} 单镜拉片任务已启动；整集其他分镜不会重跑。`
      : '整集 AI 拉片任务已进入后台执行。刷新页面只读取状态，不会重复启动任务。'
    await loadProjectContext()
  } catch (err) {
    actionError.value = err instanceof Error ? err.message : (fromShot ? '当前分镜拉片任务启动失败' : 'AI 拉片任务启动失败')
  } finally {
    actionBusy.value = false
  }
}

async function adjustShotRange(): Promise<void> {
  const shot = selectedShot.value
  if (!shot || adjustingBoundary.value || actionBusy.value || activeBreakdownTask.value || episodeLoading.value || !boundaryChanged.value) return
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
  markTaskFinished(task)
}

function markTaskFinished(task: BackgroundTask): void {
  tasks.value = tasks.value.map((item) => item.id === task.id ? task : item)
  if (handledFinishedTasks.has(task.id)) return
  handledFinishedTasks.add(task.id)
  resultsRefreshPending = true
}

async function pollProgress(signal: AbortSignal): Promise<void> {
  if (refreshing || disposed) return
  const task = activeBreakdownTask.value
  const expectedProject = projectId.value
  if (task) {
    try {
      const updated = await api.getTask(task.id, signal)
      if (disposed || signal.aborted || projectId.value !== expectedProject) return
      // 完成事件可能先于较旧的在途进度响应到达，不能倒退为处理中。
      if (!handledFinishedTasks.has(updated.id)) {
        tasks.value = tasks.value.map((item) => item.id === updated.id ? updated : item)
        if (updated.status !== 'QUEUED' && updated.status !== 'PROCESSING') markTaskFinished(updated)
      }
      pollingError.value = ''
    } catch (err) {
      if (!disposed && !signal.aborted) pollingError.value = '任务进度暂时无法更新，已降低重试频率；当前结果保持不变。'
      throw err
    }
  }
  if (resultsRefreshPending && !manualEditOpen.value && !adjustingBoundary.value && !episodeLoading.value && !boundaryChanged.value) {
    resultsRefreshPending = false
    await refreshAll(false)
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') framePreview.value = null
  if (event.key === 'Escape' && manualEditOpen.value && !manualEditSaving.value) closeManualEditor()
}

watch(searchText, () => { currentPage.value = 1 })
watch(selectedShotId, () => { syncBoundaryInputs(); framePreview.value = null })
watch(totalPages, (value) => { if (currentPage.value > value) currentPage.value = value })

onMounted(async () => {
  window.addEventListener('studio-task-created', onTaskCreated)
  window.addEventListener('studio-task-finished', onTaskFinished)
  window.addEventListener('keydown', onKeydown)
  await refreshAll(true)
  if (!disposed) stopPolling = startQuietPolling(pollProgress, () => document.visibilityState === 'visible')
})

onBeforeUnmount(() => {
  disposed = true
  episodeRequestSerial += 1
  window.removeEventListener('studio-task-created', onTaskCreated)
  window.removeEventListener('studio-task-finished', onTaskFinished)
  window.removeEventListener('keydown', onKeydown)
  stopPolling?.()
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
              <select :value="selectedEpisodeId" :disabled="loading || episodeLoading || actionBusy || adjustingBoundary || !episodes.length" @change="changeEpisode">
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
            <button class="button secondary current-shot-action" type="button" :disabled="!selectedShot || editingBlocked || Boolean(pageError)" @click="startEpisodeBreakdown(true)">▷ 当前分镜拉片</button>
            <button class="button primary" type="button" :disabled="!currentEpisode || Boolean(pageError) || episodeLoading || adjustingBoundary || actionBusy || Boolean(activeBreakdownTask)" @click="startEpisodeBreakdown(false)">▶ {{ activeBreakdownTask ? '拉片中' : '整集拉片' }} </button>
          </div>
        </section>

        <div v-if="pageError || actionError || actionMessage || timelineError || pollingError" class="message-stack">
          <div v-if="pollingError" class="message warning">{{ pollingError }}</div>
          <div v-if="pageError" class="message danger">{{ pageError }}</div>
          <div v-if="actionError" class="message danger">{{ actionError }}</div>
          <div v-if="actionMessage" class="message success">{{ actionMessage }}</div>
          <div v-if="timelineError && shots.length" class="message warning">状态刷新失败，保留最近一次结果并暂停编辑：{{ timelineError }}</div>
        </div>

        <div class="message warning" v-if="timeline && !timeline.is_current">当前展示历史拉片结果，不计入完成数量。请明确点击整集拉片更新结果。</div>
        <section class="workflow-notice" v-if="flowState" aria-label="当前流程提示">
          <div><strong>{{ flowState.next_action.reason }}</strong><p>待确认数量表示受影响镜头，不代表独立审核任务数。</p></div>
          <button class="button secondary" type="button" @click="goSourceConfirm">进入原片确认</button>
        </section>
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
                @click="selectShot(shot, true)"
              >
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
                <button class="button outline-blue" type="button" :disabled="editingBlocked" @click="startEpisodeBreakdown(true)">↻ 重新拉片</button>
              </header>

              <div class="video-stage">
                <span class="video-label">Reference Video</span>
                <video v-if="shotReference(selectedShot)" :key="shotReference(selectedShot) || ''" :src="shotReference(selectedShot) || ''" controls loop playsinline preload="metadata"></video>
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
                  <label><span>开始时间</span><input v-model="startInput" :disabled="!canEditStart || adjustingBoundary || episodeLoading || Boolean(activeBreakdownTask)" type="text" inputmode="decimal" /></label>
                  <label><span>结束时间</span><input v-model="endInput" :disabled="!canEditEnd || adjustingBoundary || episodeLoading || Boolean(activeBreakdownTask)" type="text" inputmode="decimal" /></label>
                  <div class="duration-readout"><span>时长</span><b>{{ formatSecondsUs(selectedShot.duration_us) }}</b></div>
                  <button class="button outline-blue" type="button" :disabled="!boundaryChanged || adjustingBoundary || episodeLoading || Boolean(activeBreakdownTask)" @click="adjustShotRange">{{ adjustingBoundary ? '保存中…' : '保存分镜范围' }}</button>
                </div>
                <div class="range-labels"><span>{{ formatTimeUs(timelineWindow.start) }}</span><span>{{ formatTimeUs(timelineWindow.end) }}</span></div>
                <div class="range-preview"><span class="range-selection" :style="{ left: `${timelineWindow.left}%`, width: `${timelineWindow.width}%` }"><i></i><i></i></span></div>
              </section>
              <section class="boundary-frames" aria-label="当前分镜首尾帧">
                <header><h3>首尾帧</h3><span>当前分镜与下一分镜 · 点击图片放大</span></header>
                <div v-if="shotReference(selectedShot)" class="boundary-frames-grid">
                  <ShotFramePreviewV4 :key="`${selectedShot.id}-${shotReference(selectedShot)}-${selectedShot.start_us}-start`" :src="shotReference(selectedShot)!" :at-us="0" label="首帧" @open="openFramePreview" />
                  <ShotFramePreviewV4 :key="`${selectedShot.id}-${shotReference(selectedShot)}-${selectedShot.end_us}-end`" :src="shotReference(selectedShot)!" :at-us="Math.max(0, selectedShot.duration_us - 1000)" label="尾帧" @open="openFramePreview" />
                  <ShotFramePreviewV4 v-if="nextShot && shotReference(nextShot)" :key="`${nextShot.id}-${shotReference(nextShot)}-${nextShot.start_us}-next`" :src="shotReference(nextShot)!" :at-us="0" label="下一分镜首帧" @open="openFramePreview" />
                  <div v-else class="boundary-next-empty">{{ nextShot ? '下一分镜缺少参考视频' : '已到本集末尾' }}</div>
                </div>
                <p v-else class="boundary-frames-empty">当前分镜缺少参考视频，暂时无法展示首尾帧。</p>
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
                    <div class="info-card-title"><h3>内容概要</h3><button type="button" :disabled="editingBlocked" @click="openManualEditor('summary')">✎ 编辑</button></div>
                    <p class="summary-paragraph">{{ contentOverview }}</p>
                    <dl class="field-list"><div><dt>画面描述</dt><dd>{{ selectedTimelineShot.visual_description || '暂无画面描述' }}</dd></div><div><dt>剧情作用</dt><dd>{{ selectedTimelineShot.narrative_function || '暂无剧情作用' }}</dd></div></dl>
                  </section>

                  <section class="info-card editable-card">
                    <div class="info-card-title"><h3>动作与表演</h3><button type="button" :disabled="editingBlocked" @click="openManualEditor('performance')">✎ 编辑</button></div>
                    <dl class="field-list"><div><dt>动作</dt><dd>{{ actionSummary }}</dd></div><div><dt>表情</dt><dd>{{ expressionSummary }}</dd></div><div><dt>姿态</dt><dd>{{ postureSummary }}</dd></div><div><dt>视线</dt><dd>{{ gazeSummary }}</dd></div><div><dt>人物交互</dt><dd>{{ interactionSummary }}</dd></div></dl>
                  </section>

                  <section class="info-card editable-card">
                    <div class="info-card-title"><h3>镜头语言</h3><button type="button" :disabled="editingBlocked" @click="openManualEditor('camera')">✎ 编辑</button></div>
                    <dl class="field-list"><div><dt>景别</dt><dd>{{ cameraShotType }}</dd></div><div><dt>机位</dt><dd>{{ cameraAngle }}</dd></div><div><dt>构图</dt><dd>{{ cameraComposition }}</dd></div><div><dt>运镜</dt><dd>{{ cameraMotion }}</dd></div></dl>
                  </section>

                  <section class="info-card editable-card">
                    <div class="info-card-title"><h3>画面</h3><button type="button" :disabled="editingBlocked" @click="openManualEditor('scene')">✎ 编辑</button></div>
                    <dl class="field-list"><div><dt>时间</dt><dd>{{ timeOfDay }}</dd></div><div><dt>空间</dt><dd>{{ interiorExterior }}</dd></div><div><dt>光线</dt><dd>{{ lighting }}</dd></div><div><dt>氛围</dt><dd>{{ sceneEnvironment }}</dd></div></dl>
                  </section>

                  <section v-if="selectedTimelineShot.on_screen_text.length" class="info-card">
                    <h3>画面文字</h3>
                    <p v-for="(text, index) in selectedTimelineShot.on_screen_text" :key="index">{{ formatTimeUs(text.start_us) }} → {{ formatTimeUs(text.end_us) }} · {{ text.text }}</p>
                  </section>
                  <section class="pending-card">
                    <div class="pending-title"><strong>待处理事项（本分镜）</strong><span>{{ selectedPendingItems.length ? `${selectedPendingItems.length} 项` : '未发现提示' }}</span></div>
                    <div v-if="selectedPendingItems.length" class="pending-grid">
                      <button v-for="item in selectedPendingItems" :key="item.key" type="button" :class="['pending-item', item.tone]" @click="handlePendingItem(item)"><i>!</i><span>{{ item.label }}</span><b>1</b></button>
                    </div>
                    <div v-else class="pending-clear">当前分镜未发现局部提示；正式就绪状态以工作流校验为准</div>
                    <p v-if="selectedPendingItems.length">本分镜涉及 <b>{{ selectedPendingItems.length }}</b> 类问题；人物与说话人请进入原片确认统一处理。</p>
                  </section>
                </template>

                <template v-else-if="detailTab === 'people'">
                  <section class="tab-heading-row"><div><strong>当前分镜人物</strong><span>{{ selectedPeople.length }} 人</span></div><button type="button" @click="goSourceConfirm">管理本集人物</button></section>
                  <section v-if="selectedPeople.length" class="person-list">
                    <article v-for="person in selectedPeople" :key="person.ref" class="person-card">
                      <span class="person-avatar"><img v-if="person.final_character?.cover_url" :src="person.final_character.cover_url" alt="" /><b v-else>{{ personDisplayName(person).slice(0, 1) }}</b></span>
                      <div class="person-copy"><div><strong>{{ personDisplayName(person) }}</strong><em :class="{ pending: !person.final_character }">{{ person.final_character ? '✓ 已绑定正式人物' : '! 待确认人物' }}</em></div><p>{{ person.appearance || '暂无人物外观补充描述' }}</p><button type="button" @click="goSourceConfirm">修改人物</button></div>
                    </article>
                  </section>
                  <div v-else class="tab-empty">当前分镜没有识别到人物</div>
                </template>

                <template v-else-if="detailTab === 'assets'">
                  <section class="info-card editable-card"><div class="info-card-title"><h3>场景</h3><button type="button" @click="goSourceConfirm">去原片确认</button></div><dl class="field-list"><div><dt>名称</dt><dd>{{ sceneName }}</dd></div><div><dt>环境</dt><dd>{{ sceneEnvironment }}</dd></div><div><dt>时间</dt><dd>{{ timeOfDay }}</dd></div></dl></section>
                  <section class="info-card editable-card"><div class="info-card-title"><h3>道具</h3><button type="button" @click="goSourceConfirm">管理道具</button></div><div v-if="selectedProps.length" class="prop-list"><div v-for="prop in selectedProps" :key="`${prop.name}-${prop.interaction}`"><span>{{ prop.name.slice(0, 1) }}</span><p><b>{{ prop.name }}</b><small>{{ prop.interaction }}</small></p></div></div><div v-else class="tab-empty compact">当前分镜没有关键道具</div></section>
                </template>

                <template v-else-if="detailTab === 'dialogue'">
                  <section v-if="selectedDialogue.length" class="dialogue-list">
                    <article v-for="(dialogue, index) in selectedDialogue" :key="`${dialogue.start_us}-${dialogue.end_us}-${index}`">
                      <header><span>对白 {{ String(index + 1).padStart(2, '0') }}</span><button type="button" :disabled="editingBlocked" @click="openManualEditor('dialogue', index)">✎ 编辑文本</button></header>
                      <div class="dialogue-speaker"><span>说话人</span><strong>{{ dialogueSpeaker(dialogue) }}</strong></div>
                      <p>{{ dialogue.text }}</p>
                      <footer><span>{{ formatTimeUs(dialogue.start_us) }} → {{ formatTimeUs(dialogue.end_us) }}</span><em>{{ dialogue.speakers.length ? '已绑定说话人' : '需要确认说话人' }}</em><button v-if="!dialogue.speakers.length" type="button" @click="goSourceConfirm">确认说话人</button></footer>
                    </article>
                  </section>
                  <div v-else class="tab-empty">本镜头无对白</div>
                </template>

                <template v-else>
                  <section class="remake-status"><strong>原片重拍参考</strong><span>以下为原片观察信息；正式重拍还需当前原片快照、目标人物、目标配音及生成时间轴。</span></section>
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

    <div v-if="framePreview" class="frame-preview-backdrop" @click.self="framePreview = null">
      <section class="frame-preview-dialog" role="dialog" aria-modal="true" :aria-label="framePreview.title">
        <header><strong>{{ framePreview.title }}</strong><button type="button" autofocus @click="framePreview = null" aria-label="关闭首尾帧预览">关闭 ×</button></header>
        <img :src="framePreview.src" :alt="framePreview.title" />
      </section>
    </div>
    <div v-if="helpOpen" class="modal-backdrop" @click.self="helpOpen = false">
      <section class="help-dialog"><header><strong>AI 拉片操作说明</strong><button type="button" @click="helpOpen = false">×</button></header><div><p>1. 选择剧集后，可查看每个分镜的 Reference Clip、时间范围和拉片结果。</p><p>2. 内容概要、动作与表演、镜头语言、画面信息和对白文本可在本页直接人工修正；人物、场景、道具和说话人进入“原片确认”统一修改。</p><p>3. “当前分镜拉片 / 重新拉片”只重跑当前 Shot：ASR / OCR 只处理当前分镜，VLM 最多读取前后相邻镜头作为上下文；不会重跑整集。</p></div></section>
    </div>

    <div v-if="manualEditOpen" class="breakdown-manual-editor-backdrop" @click.self="closeManualEditor">
      <section class="breakdown-manual-editor-dialog" role="dialog" aria-modal="true" :aria-label="`编辑${manualEditTitle}`">
        <header>
          <div><strong>编辑{{ manualEditTitle }}</strong><span>Shot {{ selectedShot ? String(selectedShot.ordinal).padStart(2, '0') : '—' }} · 人工修改会覆盖当前显示事实，但不会改写 AI 原始证据</span></div>
          <button type="button" :disabled="manualEditSaving" aria-label="关闭" @click="closeManualEditor">×</button>
        </header>
        <form @submit.prevent="saveManualEdit">
          <div class="breakdown-manual-editor-fields">
            <label v-for="field in manualEditFields" :key="field.key" class="breakdown-manual-editor-field">
              <span>{{ field.label }}</span>
              <textarea v-if="field.multiline" v-model="field.value" rows="5"></textarea>
              <input v-else v-model="field.value" type="text" />
            </label>
          </div>
          <p v-if="manualEditError" class="breakdown-manual-editor-error">{{ manualEditError }}</p>
          <footer>
            <button type="button" class="editor-cancel" :disabled="manualEditSaving" @click="closeManualEditor">取消</button>
            <button type="submit" class="editor-save" :disabled="manualEditSaving">{{ manualEditSaving ? '保存中…' : '保存修改' }}</button>
          </footer>
        </form>
      </section>
    </div>
  </div>
</template>

<style scoped src="../project-breakdown-v2.css"></style>
