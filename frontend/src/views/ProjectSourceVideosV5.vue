<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { projectManagementApi } from '../api/project-management'
import { uploadEpisodeWithProgress } from '../api/source-video-management'
import {
  projectLanguageLabel,
  projectRegionLabel,
} from '../constants/projectOptions'
import type { BackgroundTask, Episode, Project } from '../types/studio'
import type { ManagedProject, ProjectRedrawRule } from '../types/project-management'

type ShotDetectionState = 'not_detected' | 'queued' | 'processing' | 'completed' | 'failed'
type UploadItemStatus = 'pending' | 'uploading' | 'failed'

interface UploadItem {
  id: string
  file: File
  progress: number
  status: UploadItemStatus
  error: string
}

interface ShotStatusDisplay {
  state: ShotDetectionState
  label: string
  detail: string
}

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))

const project = ref<Project | null>(null)
const managedProject = ref<ManagedProject | null>(null)
const tasks = ref<BackgroundTask[]>([])
const loading = ref(true)
const pageError = ref('')
const actionError = ref('')

const uploadOpen = ref(false)
const uploadItems = ref<UploadItem[]>([])
const uploadRunning = ref(false)
const uploadDragging = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)

const deleteTarget = ref<Episode | null>(null)
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

const redrawRuleOptions: Array<{ value: ProjectRedrawRule; label: string }> = [
  { value: 'CHARACTER', label: '人物' },
  { value: 'SCENE', label: '场景' },
  { value: 'LANGUAGE', label: '语言' },
]

const episodes = computed(() => {
  return [...(project.value?.episodes || [])].sort((left, right) => {
    if (left.sort_order !== right.sort_order) return left.sort_order - right.sort_order
    return left.created_at.localeCompare(right.created_at)
  })
})

const totalDurationUs = computed(() => {
  return episodes.value.reduce((total, episode) => total + Math.max(0, episode.duration_us || 0), 0)
})

const currentProjectName = computed(() => managedProject.value?.name || project.value?.name || '项目')
const sourceLanguage = computed(() => managedProject.value?.source_language || project.value?.source_language || '')
const targetLanguage = computed(() => managedProject.value?.target_language || project.value?.target_language || '')
const targetRegion = computed(() => managedProject.value?.target_region || project.value?.target_region || '')
const redrawRules = computed(() => managedProject.value?.redraw_rules || [])

const uploadFailedCount = computed(() => uploadItems.value.filter((item) => item.status === 'failed').length)
const uploadPendingCount = computed(() => uploadItems.value.filter((item) => item.status === 'pending').length)
const uploadActionLabel = computed(() => {
  if (uploadRunning.value) return '正在上传…'
  if (uploadFailedCount.value > 0 && uploadPendingCount.value === 0) return '重试失败视频'
  return `开始上传${uploadItems.value.length ? `（${uploadItems.value.length}）` : ''}`
})

const batchEligibleEpisodes = computed(() => {
  return episodes.value.filter((episode) => {
    const state = shotStatusForEpisode(episode).state
    return state === 'not_detected' || state === 'failed'
  })
})

const hasActiveShotTasks = computed(() => {
  if (optimisticQueuedEpisodeIds.value.size > 0) return true
  return tasks.value.some((task) => isShotTask(task) && (task.status === 'QUEUED' || task.status === 'PROCESSING'))
})

function redrawRuleLabel(rule: ProjectRedrawRule): string {
  return redrawRuleOptions.find((item) => item.value === rule)?.label || rule
}

function formatDuration(durationUs: number | null): string {
  if (!durationUs || durationUs <= 0) return '—'
  const totalSeconds = Math.max(0, Math.round(durationUs / 1_000_000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function episodeOrder(index: number): string {
  return String(index + 1).padStart(2, '0')
}

function episodeShortLabel(index: number): string {
  return `EP${String(index + 1).padStart(2, '0')}`
}

function episodeFilename(episode: Episode): string {
  return episode.original_filename || episode.title || `${episodeShortLabel(episodes.value.indexOf(episode))}.mp4`
}

function isShotTask(task: BackgroundTask): boolean {
  const type = String(task.task_type || '').trim().toLowerCase()
  if (!type) return false
  return (
    type === 'shots'
    || type === 'shot'
    || type.includes('shot_detect')
    || type.includes('shots_detect')
    || type.includes('detect_shot')
    || type.includes('shot_analy')
    || type.includes('shots_analy')
    || type.includes('analyze_shot')
  )
}

function latestShotTaskForEpisode(episodeId: string): BackgroundTask | null {
  return tasks.value
    .filter((task) => task.episode_id === episodeId && isShotTask(task))
    .sort((left, right) => {
      const leftAt = new Date(left.created_at).getTime()
      const rightAt = new Date(right.created_at).getTime()
      return rightAt - leftAt
    })[0] || null
}

function persistedShotState(episode: Episode): ShotDetectionState {
  const status = String(episode.shots_status || '').trim().toLowerCase()
  if (['ready', 'completed', 'complete', 'success', 'succeeded', 'done'].includes(status) || episode.shot_count > 0) {
    return 'completed'
  }
  if (['processing', 'running', 'in_progress'].includes(status)) return 'processing'
  if (['queued', 'pending', 'waiting'].includes(status)) return 'queued'
  if (['failed', 'error'].includes(status)) return 'failed'
  return 'not_detected'
}

function shotStatusForEpisode(episode: Episode): ShotStatusDisplay {
  const latestTask = latestShotTaskForEpisode(episode.id)
  if (latestTask) {
    if (latestTask.status === 'QUEUED') return { state: 'queued', label: '排队中', detail: '' }
    if (latestTask.status === 'PROCESSING') {
      const progress = Number.isFinite(latestTask.progress) ? Math.max(0, Math.min(100, Math.round(latestTask.progress))) : 0
      return { state: 'processing', label: '进行中', detail: progress > 0 ? `${progress}%` : '' }
    }
    if (latestTask.status === 'READY' || latestTask.status === 'READY_WITH_WARNINGS') {
      return {
        state: 'completed',
        label: '已完成',
        detail: episode.shot_count > 0 ? `${episode.shot_count} 个镜头` : '',
      }
    }
    if (latestTask.status === 'FAILED') {
      return { state: 'failed', label: '失败', detail: latestTask.error_message || '' }
    }
  }

  if (optimisticQueuedEpisodeIds.value.has(episode.id)) {
    return { state: 'queued', label: '排队中', detail: '' }
  }

  const state = persistedShotState(episode)
  if (state === 'completed') {
    return { state, label: '已完成', detail: episode.shot_count > 0 ? `${episode.shot_count} 个镜头` : '' }
  }
  if (state === 'processing') return { state, label: '进行中', detail: '' }
  if (state === 'queued') return { state, label: '排队中', detail: '' }
  if (state === 'failed') return { state, label: '失败', detail: '' }
  return { state: 'not_detected', label: '未检测', detail: '' }
}

function shotActionLabel(episode: Episode): string {
  return shotStatusForEpisode(episode).state === 'completed' ? '重新镜头检测' : '镜头检测'
}

function isShotActionDisabled(episode: Episode): boolean {
  const state = shotStatusForEpisode(episode).state
  return detectingEpisodeId.value === episode.id || state === 'queued' || state === 'processing'
}

function isDeleteDisabled(episode: Episode): boolean {
  const state = shotStatusForEpisode(episode).state
  return deleting.value || state === 'queued' || state === 'processing'
}

function mergeManagedProjectIntoProject(rawProject: Project, managed: ManagedProject | null): Project {
  if (!managed) return rawProject
  return {
    ...rawProject,
    name: managed.name,
    source_language: managed.source_language,
    target_language: managed.target_language,
    target_region: managed.target_region,
  }
}

async function refreshData(options: { quiet?: boolean } = {}): Promise<void> {
  if (!projectId.value || refreshInFlight) return
  refreshInFlight = true
  if (!options.quiet) {
    loading.value = true
    pageError.value = ''
  }
  try {
    const [rawProject, managed, projectTasks] = await Promise.all([
      api.getProject(projectId.value),
      projectManagementApi.getProject(projectId.value).catch(() => null),
      api.listProjectTasks(projectId.value).catch(() => [] as BackgroundTask[]),
    ])
    project.value = mergeManagedProjectIntoProject(rawProject, managed)
    managedProject.value = managed
    tasks.value = projectTasks

    const taskEpisodeIds = new Set(
      projectTasks
        .filter((task) => isShotTask(task) && task.episode_id)
        .map((task) => String(task.episode_id)),
    )
    if (taskEpisodeIds.size > 0) {
      const next = new Set(optimisticQueuedEpisodeIds.value)
      for (const episodeId of taskEpisodeIds) next.delete(episodeId)
      optimisticQueuedEpisodeIds.value = next
    }
  } catch (error) {
    if (!options.quiet) {
      pageError.value = error instanceof Error ? error.message : '项目视频读取失败'
    }
  } finally {
    refreshInFlight = false
    if (!options.quiet) loading.value = false
  }
}

function clearPolling(): void {
  if (pollingTimer) {
    clearTimeout(pollingTimer)
    pollingTimer = null
  }
}

function schedulePolling(delayMs = 1600): void {
  clearPolling()
  if (disposed) return
  pollingTimer = setTimeout(async () => {
    await refreshData({ quiet: true })
    if (disposed) return
    if (hasActiveShotTasks.value) schedulePolling(1800)
    else {
      optimisticQueuedEpisodeIds.value = new Set()
      await refreshData({ quiet: true })
    }
  }, delayMs)
}

function goBack(): void {
  void router.push('/')
}

function openUpload(): void {
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
  const extension = file.name.split('.').pop()?.toLowerCase() || ''
  return ['mp4', 'mov', 'mkv'].includes(extension)
}

function addUploadFiles(files: FileList | File[]): void {
  const next = [...uploadItems.value]
  const existingKeys = new Set(next.map((item) => `${item.file.name}:${item.file.size}:${item.file.lastModified}`))

  for (const file of Array.from(files)) {
    const key = `${file.name}:${file.size}:${file.lastModified}`
    if (existingKeys.has(key)) continue
    existingKeys.add(key)
    next.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file,
      progress: 0,
      status: isSupportedVideo(file) ? 'pending' : 'failed',
      error: isSupportedVideo(file) ? '' : '仅支持 mp4 / mov / mkv',
    })
  }
  uploadItems.value = next
}

function handleFileInput(event: Event): void {
  const target = event.target as HTMLInputElement
  if (target.files?.length) addUploadFiles(target.files)
  target.value = ''
}

function handleDrop(event: DragEvent): void {
  event.preventDefault()
  uploadDragging.value = false
  if (event.dataTransfer?.files?.length) addUploadFiles(event.dataTransfer.files)
}

function removeUploadItem(itemId: string): void {
  if (uploadRunning.value) return
  uploadItems.value = uploadItems.value.filter((item) => item.id !== itemId)
}

async function startUpload(): Promise<void> {
  if (uploadRunning.value || !projectId.value) return
  const candidates = uploadItems.value.filter((item) => item.status === 'pending' || item.status === 'failed')
  const supportedCandidates = candidates.filter((item) => isSupportedVideo(item.file))
  if (!supportedCandidates.length) {
    actionError.value = '请选择 mp4、mov 或 mkv 视频文件'
    return
  }

  uploadRunning.value = true
  actionError.value = ''

  for (const item of supportedCandidates) {
    if (disposed) break
    item.status = 'uploading'
    item.progress = 0
    item.error = ''
    try {
      await uploadEpisodeWithProgress(projectId.value, item.file, (progress) => {
        item.progress = progress.percent
      })
      uploadItems.value = uploadItems.value.filter((candidate) => candidate.id !== item.id)
      await refreshData({ quiet: true })
    } catch (error) {
      item.status = 'failed'
      item.error = error instanceof Error ? error.message : '视频上传失败'
    }
  }

  uploadRunning.value = false
  if (!uploadItems.value.length) {
    uploadOpen.value = false
  }
  await refreshData({ quiet: true })
}

async function startShotDetection(episode: Episode): Promise<void> {
  if (isShotActionDisabled(episode)) return
  detectingEpisodeId.value = episode.id
  actionError.value = ''
  try {
    await api.analyzeEpisodeShots(episode.id)
    optimisticQueuedEpisodeIds.value = new Set([...optimisticQueuedEpisodeIds.value, episode.id])
    await refreshData({ quiet: true })
    schedulePolling(800)
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '镜头检测启动失败'
  } finally {
    detectingEpisodeId.value = null
  }
}

async function startBatchShotDetection(): Promise<void> {
  if (batchDetecting.value) return
  const eligible = batchEligibleEpisodes.value
  if (!eligible.length) {
    actionError.value = '没有需要镜头检测的视频'
    return
  }

  batchDetecting.value = true
  actionError.value = ''
  try {
    await api.analyzeBatchShots(projectId.value, { episode_ids: eligible.map((episode) => episode.id) })
    optimisticQueuedEpisodeIds.value = new Set([
      ...optimisticQueuedEpisodeIds.value,
      ...eligible.map((episode) => episode.id),
    ])
    await refreshData({ quiet: true })
    schedulePolling(800)
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '批量镜头检测启动失败'
  } finally {
    batchDetecting.value = false
  }
}

function askDelete(episode: Episode): void {
  if (isDeleteDisabled(episode)) return
  actionError.value = ''
  deleteTarget.value = episode
}

function closeDelete(): void {
  if (deleting.value) return
  deleteTarget.value = null
}

async function confirmDelete(): Promise<void> {
  if (!deleteTarget.value || deleting.value) return
  const episodeId = deleteTarget.value.id
  deleting.value = true
  actionError.value = ''
  try {
    await api.deleteEpisode(episodeId)
    deleteTarget.value = null
    await refreshData({ quiet: true })
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '视频删除失败'
  } finally {
    deleting.value = false
  }
}

function onDragStart(episode: Episode, event: DragEvent): void {
  if (reorderSaving.value) {
    event.preventDefault()
    return
  }
  draggingEpisodeId.value = episode.id
  dragOverEpisodeId.value = null
  event.dataTransfer?.setData('text/plain', episode.id)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}

function onDragOver(episode: Episode, event: DragEvent): void {
  if (!draggingEpisodeId.value || draggingEpisodeId.value === episode.id) return
  event.preventDefault()
  dragOverEpisodeId.value = episode.id
  if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
}

async function onDrop(target: Episode, event: DragEvent): Promise<void> {
  event.preventDefault()
  const sourceId = draggingEpisodeId.value || event.dataTransfer?.getData('text/plain') || ''
  draggingEpisodeId.value = null
  dragOverEpisodeId.value = null
  if (!sourceId || sourceId === target.id || reorderSaving.value) return

  const current = episodes.value
  const sourceIndex = current.findIndex((episode) => episode.id === sourceId)
  const targetIndex = current.findIndex((episode) => episode.id === target.id)
  if (sourceIndex < 0 || targetIndex < 0) return

  const reordered = [...current]
  const [moved] = reordered.splice(sourceIndex, 1)
  if (!moved) return
  reordered.splice(targetIndex, 0, moved)

  if (project.value) {
    project.value = {
      ...project.value,
      episodes: reordered.map((episode, index) => ({ ...episode, sort_order: index + 1 })),
    }
  }

  reorderSaving.value = true
  actionError.value = ''
  try {
    const saved = await api.reorderEpisodes(projectId.value, reordered.map((episode) => episode.id))
    if (project.value) project.value = { ...project.value, episodes: saved }
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '视频顺序保存失败'
    await refreshData({ quiet: true })
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
  if (hasActiveShotTasks.value) schedulePolling()
})

onBeforeUnmount(() => {
  disposed = true
  clearPolling()
})
</script>

<template>
  <div class="source-video-page" @keydown.esc="uploadOpen ? closeUpload() : closeDelete()">
    <header class="topbar">
      <div class="brand-row">
        <button class="brand" type="button" @click="goBack">
          <span class="brand-mark" aria-hidden="true">
            <i></i><i></i><i></i>
          </span>
          <span>AI Drama Studio</span>
        </button>
        <span class="top-divider"></span>
        <nav class="breadcrumbs" aria-label="面包屑">
          <button type="button" @click="goBack">项目管理</button>
          <span>›</span>
          <span>{{ currentProjectName }}</span>
          <span>›</span>
          <strong>原短剧视频</strong>
        </nav>
      </div>
      <button class="help-button" type="button" aria-label="操作说明">
        <span class="help-icon">?</span>
        操作说明
      </button>
    </header>

    <main class="page-layout">
      <aside class="stage-sidebar">
        <section class="progress-card">
          <h2>项目进度</h2>
          <div class="progress-copy">
            <span>整体进度</span>
            <strong>25%</strong>
          </div>
          <div class="progress-track"><span style="width: 25%"></span></div>
        </section>

        <nav class="stage-list" aria-label="项目阶段">
          <div class="stage-item active">
            <span class="stage-dot">1</span>
            <div>
              <strong>项目管理</strong>
              <span>上传视频与排序</span>
            </div>
          </div>
          <div class="stage-item">
            <span class="stage-dot">2</span>
            <div>
              <strong>角色/场景/道具分析</strong>
              <span>待开始</span>
            </div>
          </div>
          <div class="stage-item">
            <span class="stage-dot">3</span>
            <div>
              <strong>镜头级分析</strong>
              <span>待开始</span>
            </div>
          </div>
          <div class="stage-item">
            <span class="stage-dot">4</span>
            <div>
              <strong>视频生成</strong>
              <span>待开始</span>
            </div>
          </div>
        </nav>

        <button class="back-button" type="button" @click="goBack">
          <span aria-hidden="true">←</span>
          返回项目列表
        </button>
      </aside>

      <section class="main-content">
        <section class="project-card">
          <div class="project-title-row">
            <h1>原短剧视频</h1>
          </div>
          <div class="project-meta">
            <div class="meta-item">
              <span class="meta-icon">中</span>
              <strong>原项目语言：</strong>
              <span>{{ projectLanguageLabel(sourceLanguage) }}</span>
            </div>
            <span class="meta-divider"></span>
            <div class="meta-item">
              <span class="meta-icon">EN</span>
              <strong>目标语言：</strong>
              <span>{{ projectLanguageLabel(targetLanguage) }}</span>
            </div>
            <span class="meta-divider"></span>
            <div class="meta-item">
              <span class="region-flag" aria-hidden="true">◎</span>
              <strong>目标地区：</strong>
              <span>{{ projectRegionLabel(targetRegion) }}</span>
            </div>
            <span class="meta-divider"></span>
            <div class="meta-item rules-item">
              <strong>视频重绘规则：</strong>
              <span v-for="rule in redrawRules" :key="rule" class="rule-chip">{{ redrawRuleLabel(rule) }}</span>
              <span v-if="!redrawRules.length" class="meta-empty">—</span>
            </div>
          </div>
        </section>

        <section class="video-card">
          <header class="video-card-head">
            <div class="video-summary">
              <h2>视频列表</h2>
              <span>共 {{ episodes.length }} 个视频</span>
              <i></i>
              <span>总时长 {{ formatDuration(totalDurationUs) }}</span>
            </div>
            <div class="toolbar-actions">
              <button class="primary-button" type="button" @click="openUpload">
                <span aria-hidden="true">⇧</span>
                上传视频
              </button>
              <button
                class="outline-button"
                type="button"
                :disabled="batchDetecting || !episodes.length"
                @click="startBatchShotDetection"
              >
                <span aria-hidden="true">▱</span>
                {{ batchDetecting ? '正在启动…' : '批量镜头检测' }}
              </button>
            </div>
          </header>

          <div v-if="actionError" class="action-error" role="alert">
            <span>{{ actionError }}</span>
            <button type="button" aria-label="关闭错误" @click="actionError = ''">×</button>
          </div>

          <div v-if="pageError" class="page-state error-state">
            <strong>项目视频加载失败</strong>
            <span>{{ pageError }}</span>
            <button class="outline-button" type="button" @click="refreshData()">重新加载</button>
          </div>

          <div v-else-if="loading" class="page-state loading-state">
            <span class="spinner"></span>
            正在读取项目视频…
          </div>

          <div v-else-if="!episodes.length" class="page-state empty-state">
            <div class="empty-video-icon">▶</div>
            <h3>还没有上传视频</h3>
            <p>点击“上传视频”添加原短剧剧集，上传完成后即可排序并进行镜头检测。</p>
            <button class="primary-button" type="button" @click="openUpload">上传视频</button>
          </div>

          <div v-else class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th class="sort-column">排序</th>
                  <th>视频信息</th>
                  <th class="duration-column">时长</th>
                  <th class="size-column">大小</th>
                  <th class="status-column">镜头检测状态</th>
                  <th class="detect-column">镜头检测</th>
                  <th class="action-column">操作</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(episode, index) in episodes"
                  :key="episode.id"
                  :class="{
                    'dragging-row': draggingEpisodeId === episode.id,
                    'drag-over-row': dragOverEpisodeId === episode.id,
                  }"
                  @dragover="onDragOver(episode, $event)"
                  @drop="onDrop(episode, $event)"
                >
                  <td class="sort-cell">
                    <button
                      class="drag-handle"
                      type="button"
                      draggable="true"
                      :disabled="reorderSaving"
                      aria-label="拖拽调整顺序"
                      @dragstart="onDragStart(episode, $event)"
                      @dragend="onDragEnd"
                    >
                      <span>⠿</span>
                    </button>
                    <span class="order-badge">{{ episodeOrder(index) }}</span>
                  </td>
                  <td>
                    <div class="video-info">
                      <div class="video-thumb">
                        <span>{{ episodeShortLabel(index) }}</span>
                        <small>{{ formatDuration(episode.duration_us) }}</small>
                      </div>
                      <strong :title="episodeFilename(episode)">{{ episodeFilename(episode) }}</strong>
                    </div>
                  </td>
                  <td>{{ formatDuration(episode.duration_us) }}</td>
                  <td class="muted-cell" title="当前视频接口未返回文件大小">—</td>
                  <td>
                    <div class="shot-status">
                      <span :class="['status-pill', `status-${shotStatusForEpisode(episode).state}`]">
                        <i></i>
                        {{ shotStatusForEpisode(episode).label }}
                      </span>
                      <small
                        v-if="shotStatusForEpisode(episode).detail"
                        :title="shotStatusForEpisode(episode).state === 'failed' ? shotStatusForEpisode(episode).detail : undefined"
                      >
                        {{ shotStatusForEpisode(episode).detail }}
                      </small>
                    </div>
                  </td>
                  <td>
                    <button
                      class="detect-link"
                      type="button"
                      :disabled="isShotActionDisabled(episode)"
                      @click="startShotDetection(episode)"
                    >
                      {{ detectingEpisodeId === episode.id ? '正在启动…' : shotActionLabel(episode) }}
                    </button>
                  </td>
                  <td>
                    <button
                      class="delete-link"
                      type="button"
                      :disabled="isDeleteDisabled(episode)"
                      @click="askDelete(episode)"
                    >删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <footer v-if="episodes.length" class="video-card-foot">
            <span class="info-icon">i</span>
            <span>提示：拖拽左侧手柄可调整视频顺序，顺序变更后自动保存。</span>
            <span v-if="reorderSaving" class="saving-copy">正在保存顺序…</span>
          </footer>
        </section>
      </section>
    </main>

    <div v-if="uploadOpen" class="modal-backdrop" @click.self="closeUpload">
      <section class="modal-card upload-modal" role="dialog" aria-modal="true" aria-label="上传视频">
        <header class="modal-head">
          <div>
            <p>视频管理</p>
            <h2>上传视频</h2>
          </div>
          <button class="modal-close" type="button" :disabled="uploadRunning" aria-label="关闭" @click="closeUpload">×</button>
        </header>

        <div
          :class="['drop-zone', { dragging: uploadDragging }]"
          @dragenter.prevent="uploadDragging = true"
          @dragover.prevent="uploadDragging = true"
          @dragleave.prevent="uploadDragging = false"
          @drop="handleDrop"
          @click="selectFiles"
        >
          <input
            ref="fileInput"
            class="file-input"
            type="file"
            accept=".mp4,.mov,.mkv,video/mp4,video/quicktime,video/x-matroska"
            multiple
            @change="handleFileInput"
          />
          <div class="upload-cloud">⇧</div>
          <strong>拖拽视频到这里，或点击选择</strong>
          <span>支持 mp4 / mov / mkv，可一次选择多个视频</span>
          <button class="primary-button select-button" type="button" tabindex="-1">选择视频</button>
        </div>

        <div v-if="uploadItems.length" class="upload-list">
          <div v-for="item in uploadItems" :key="item.id" class="upload-row">
            <div class="upload-file-copy">
              <strong>{{ item.file.name }}</strong>
              <span>{{ (item.file.size / 1024 / 1024).toFixed(1) }} MB</span>
            </div>
            <div class="upload-progress-block">
              <div class="upload-status-row">
                <span v-if="item.status === 'uploading'">上传中 {{ item.progress }}%</span>
                <span v-else-if="item.status === 'failed'" class="upload-failed">{{ item.error || '上传失败' }}</span>
                <span v-else>等待上传</span>
                <button
                  v-if="item.status !== 'uploading'"
                  type="button"
                  :disabled="uploadRunning"
                  aria-label="移除视频"
                  @click="removeUploadItem(item.id)"
                >×</button>
              </div>
              <div v-if="item.status === 'uploading'" class="upload-progress-track">
                <span :style="{ width: `${item.progress}%` }"></span>
              </div>
            </div>
          </div>
        </div>

        <footer class="modal-actions">
          <button class="secondary-button" type="button" :disabled="uploadRunning" @click="closeUpload">取消</button>
          <button
            class="primary-button"
            type="button"
            :disabled="uploadRunning || !uploadItems.length"
            @click="startUpload"
          >{{ uploadActionLabel }}</button>
        </footer>
      </section>
    </div>

    <div v-if="deleteTarget" class="modal-backdrop" @click.self="closeDelete">
      <section class="modal-card delete-modal" role="dialog" aria-modal="true" aria-label="删除视频">
        <div class="danger-icon">!</div>
        <h2>删除视频</h2>
        <p>确定删除 <strong>“{{ episodeFilename(deleteTarget) }}”</strong> 吗？</p>
        <p class="delete-note">删除会同时移除该剧集关联的处理数据，请确认当前没有正在运行的镜头检测任务。</p>
        <footer class="modal-actions">
          <button class="secondary-button" type="button" :disabled="deleting" @click="closeDelete">取消</button>
          <button class="danger-button" type="button" :disabled="deleting" @click="confirmDelete">
            {{ deleting ? '正在删除…' : '确认删除' }}
          </button>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
:global(html) {
  background: #f6f8fc;
}

:global(body) {
  margin: 0;
  background: #f6f8fc;
  color: #14213a;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
}

button,
input {
  font: inherit;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: .52;
}

.source-video-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 0 28px 40px;
}

.topbar {
  min-height: 78px;
  max-width: 1700px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.brand-row,
.brand,
.breadcrumbs,
.help-button {
  display: flex;
  align-items: center;
}

.brand {
  gap: 10px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #1463ff;
  font-size: 19px;
  font-weight: 800;
  white-space: nowrap;
}

.brand-mark {
  position: relative;
  width: 28px;
  height: 27px;
  display: block;
}

.brand-mark i {
  position: absolute;
  width: 13px;
  height: 9px;
  border-radius: 4px 8px 8px 4px;
  background: #1463ff;
  transform: rotate(30deg);
}

.brand-mark i:nth-child(1) { left: 2px; top: 2px; }
.brand-mark i:nth-child(2) { left: 9px; top: 9px; opacity: .82; }
.brand-mark i:nth-child(3) { left: 2px; top: 16px; opacity: .65; }

.top-divider {
  width: 1px;
  height: 25px;
  margin: 0 20px;
  background: #dfe4ec;
}

.breadcrumbs {
  gap: 12px;
  min-width: 0;
  color: #738096;
  font-size: 14px;
}

.breadcrumbs button {
  padding: 0;
  border: 0;
  background: transparent;
  color: #536079;
}

.breadcrumbs strong,
.breadcrumbs > span:nth-last-child(2) {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.breadcrumbs strong {
  color: #1e2b42;
  font-weight: 700;
}

.help-button {
  min-height: 40px;
  gap: 8px;
  padding: 0 15px;
  border: 1px solid #dce2ec;
  border-radius: 9px;
  background: #fff;
  color: #303d55;
  font-size: 13px;
  font-weight: 700;
  box-shadow: 0 3px 12px rgba(32, 48, 78, .03);
}

.help-icon,
.info-icon {
  width: 18px;
  height: 18px;
  display: inline-grid;
  place-items: center;
  box-sizing: border-box;
  border: 1.5px solid currentColor;
  border-radius: 50%;
  font-size: 11px;
  font-style: normal;
  font-weight: 800;
}

.page-layout {
  max-width: 1700px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 18px;
}

.stage-sidebar,
.project-card,
.video-card {
  border: 1px solid #e3e8f0;
  background: #fff;
  box-shadow: 0 6px 20px rgba(23, 43, 77, .035);
}

.stage-sidebar {
  min-height: calc(100vh - 118px);
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  overflow: hidden;
}

.progress-card {
  padding: 25px 22px 21px;
  border-bottom: 1px solid #edf0f4;
}

.progress-card h2 {
  margin: 0 0 18px;
  color: #243149;
  font-size: 15px;
}

.progress-copy {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 10px;
  color: #65728a;
  font-size: 13px;
}

.progress-copy strong {
  color: #294264;
  font-size: 14px;
}

.progress-track,
.upload-progress-track {
  overflow: hidden;
  border-radius: 999px;
  background: #e8edf7;
}

.progress-track {
  height: 7px;
}

.progress-track span,
.upload-progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #1463ff;
}

.stage-list {
  flex: 1;
  padding: 0 0 8px;
}

.stage-item {
  position: relative;
  min-height: 96px;
  box-sizing: border-box;
  padding: 24px 14px 16px 60px;
  display: flex;
  align-items: flex-start;
  color: #7b879b;
}

.stage-item:not(:last-child)::after {
  content: '';
  position: absolute;
  left: 34px;
  top: 47px;
  bottom: -29px;
  width: 1px;
  background: #e1e6ef;
}

.stage-item.active {
  border-left: 3px solid #1463ff;
  background: #f2f6ff;
  color: #1760e7;
}

.stage-dot {
  position: absolute;
  left: 22px;
  top: 22px;
  z-index: 1;
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #e5e9f0;
  color: #65728a;
  font-size: 12px;
  font-weight: 800;
}

.stage-item.active .stage-dot {
  background: #1463ff;
  color: #fff;
  box-shadow: 0 4px 11px rgba(20, 99, 255, .24);
}

.stage-item div {
  display: grid;
  gap: 8px;
}

.stage-item strong {
  color: #26334a;
  font-size: 14px;
  line-height: 1.35;
}

.stage-item.active strong {
  color: #1760e7;
}

.stage-item div span {
  font-size: 12px;
}

.back-button {
  min-height: 43px;
  margin: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  border: 1px solid #d8e0eb;
  border-radius: 8px;
  background: #fff;
  color: #35435b;
  font-size: 13px;
  font-weight: 700;
}

.main-content {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 16px;
}

.project-card,
.video-card {
  border-radius: 12px;
}

.project-card {
  padding: 25px 30px 21px;
}

.project-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.project-title-row h1 {
  margin: 0;
  color: #111b2f;
  font-size: 28px;
  line-height: 1.2;
  letter-spacing: -.025em;
}

.project-meta {
  margin-top: 20px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  color: #44516a;
  font-size: 13px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
}

.meta-item strong {
  color: #303d54;
  font-weight: 700;
}

.meta-icon {
  min-width: 25px;
  height: 25px;
  padding: 0 4px;
  display: inline-grid;
  place-items: center;
  box-sizing: border-box;
  border: 1px solid #6a9cff;
  border-radius: 5px;
  color: #1463ff;
  font-size: 10px;
  font-weight: 800;
}

.region-flag {
  width: 25px;
  height: 25px;
  display: inline-grid;
  place-items: center;
  border-radius: 50%;
  background: #f0f5ff;
  color: #1463ff;
  font-size: 16px;
  font-weight: 800;
}

.meta-divider {
  width: 1px;
  height: 25px;
  background: #e4e8ef;
}

.rules-item {
  gap: 6px;
}

.rule-chip {
  padding: 4px 9px;
  border-radius: 7px;
  background: #edf4ff;
  color: #1760e7;
  font-size: 12px;
  font-weight: 700;
}

.meta-empty,
.muted-cell {
  color: #9aa4b5;
}

.video-card {
  overflow: hidden;
}

.video-card-head {
  min-height: 80px;
  box-sizing: border-box;
  padding: 18px 25px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.video-summary,
.toolbar-actions {
  display: flex;
  align-items: center;
}

.video-summary {
  gap: 14px;
  color: #5d6a82;
  font-size: 13px;
}

.video-summary h2 {
  margin: 0 8px 0 0;
  color: #18233a;
  font-size: 20px;
}

.video-summary i {
  width: 1px;
  height: 17px;
  background: #dce1e9;
}

.toolbar-actions {
  gap: 10px;
}

.primary-button,
.outline-button,
.secondary-button,
.danger-button {
  min-height: 42px;
  box-sizing: border-box;
  border-radius: 8px;
  padding: 0 17px;
  border: 1px solid transparent;
  font-size: 13px;
  font-weight: 750;
}

.primary-button {
  background: #1463ff;
  color: #fff;
  box-shadow: 0 5px 13px rgba(20, 99, 255, .18);
}

.primary-button:hover:not(:disabled) {
  background: #0957ec;
}

.outline-button,
.secondary-button {
  border-color: #d6deea;
  background: #fff;
  color: #285fbb;
}

.secondary-button {
  color: #3e4b63;
}

.danger-button {
  background: #d92d20;
  color: #fff;
}

.action-error {
  margin: 0 25px 14px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border: 1px solid #f2c7c2;
  border-radius: 8px;
  background: #fff4f2;
  color: #b42318;
  font-size: 12px;
}

.action-error button {
  border: 0;
  background: transparent;
  color: inherit;
  font-size: 18px;
}

.page-state {
  min-height: 330px;
  margin: 0 25px 25px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  border: 1px solid #e4e9f1;
  border-radius: 10px;
  color: #758197;
  font-size: 13px;
  text-align: center;
}

.page-state h3,
.page-state strong {
  margin: 0;
  color: #253149;
}

.page-state p {
  max-width: 460px;
  margin: 0 0 4px;
  line-height: 1.65;
}

.empty-video-icon {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: #edf4ff;
  color: #1463ff;
  font-size: 21px;
}

.spinner {
  width: 21px;
  height: 21px;
  border: 2px solid #dce4f0;
  border-top-color: #1463ff;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}

@keyframes spin { to { transform: rotate(360deg); } }

.table-wrap {
  margin: 0 25px;
  overflow-x: auto;
  border: 1px solid #dfe5ed;
  border-radius: 9px;
}

table {
  width: 100%;
  min-width: 1080px;
  border-collapse: collapse;
  table-layout: fixed;
}

th,
td {
  border-bottom: 1px solid #e8ecf2;
  padding: 14px 16px;
  text-align: left;
  vertical-align: middle;
  font-size: 13px;
}

th {
  height: 44px;
  box-sizing: border-box;
  padding-top: 0;
  padding-bottom: 0;
  background: #fafbfc;
  color: #68758a;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

tbody tr {
  height: 88px;
  transition: background .15s ease, box-shadow .15s ease;
}

tbody tr:last-child td {
  border-bottom: 0;
}

.dragging-row {
  opacity: .48;
}

.drag-over-row {
  background: #f2f6ff;
  box-shadow: inset 0 2px #5f91ef;
}

.sort-column { width: 108px; }
.duration-column { width: 86px; }
.size-column { width: 78px; }
.status-column { width: 150px; }
.detect-column { width: 130px; }
.action-column { width: 70px; }

.sort-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.drag-handle {
  width: 24px;
  height: 34px;
  padding: 0;
  border: 0;
  background: transparent;
  color: #18233a;
  font-size: 21px;
  line-height: 1;
  cursor: grab;
}

.drag-handle:active {
  cursor: grabbing;
}

.order-badge {
  min-width: 39px;
  height: 31px;
  padding: 0 7px;
  display: inline-grid;
  place-items: center;
  box-sizing: border-box;
  border-radius: 8px;
  background: #eef4ff;
  color: #1463ff;
  font-size: 13px;
  font-weight: 800;
}

.video-info {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 16px;
}

.video-thumb {
  position: relative;
  width: 102px;
  height: 58px;
  flex: 0 0 102px;
  overflow: hidden;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background:
    radial-gradient(circle at 68% 32%, rgba(226, 177, 119, .4), transparent 28%),
    linear-gradient(135deg, #2b2b34, #15191f 52%, #4a3429);
  color: rgba(255, 255, 255, .8);
  font-size: 11px;
  letter-spacing: .05em;
}

.video-thumb::before {
  content: '▶';
  position: absolute;
  color: rgba(255, 255, 255, .3);
  font-size: 18px;
}

.video-thumb > span {
  position: relative;
  z-index: 1;
  align-self: start;
  justify-self: start;
  margin: 7px;
  padding: 2px 5px;
  border-radius: 4px;
  background: rgba(0, 0, 0, .34);
}

.video-thumb small {
  position: absolute;
  right: 5px;
  bottom: 4px;
  padding: 1px 4px;
  border-radius: 3px;
  background: rgba(0, 0, 0, .66);
  color: #fff;
  font-size: 10px;
}

.video-info strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #172238;
  font-size: 13px;
  font-weight: 700;
}

.shot-status {
  display: grid;
  justify-items: start;
  gap: 5px;
}

.status-pill {
  min-width: 76px;
  min-height: 28px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  box-sizing: border-box;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 750;
}

.status-pill i {
  width: 7px;
  height: 7px;
  border: 1.5px solid currentColor;
  border-radius: 50%;
  box-sizing: border-box;
}

.status-not_detected {
  background: #f1f3f6;
  color: #677389;
}

.status-queued {
  background: #eaf2ff;
  color: #2c6dcc;
}

.status-processing {
  background: #e9f2ff;
  color: #1463ff;
}

.status-completed {
  background: #e9f8ee;
  color: #17a14b;
}

.status-failed {
  background: #ffeded;
  color: #e02e2e;
}

.shot-status small {
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #7a869b;
  font-size: 11px;
}

.detect-link,
.delete-link {
  padding: 5px 0;
  border: 0;
  background: transparent;
  font-size: 12px;
  font-weight: 750;
}

.detect-link {
  color: #1463ff;
}

.delete-link {
  color: #f04438;
}

.detect-link:hover:not(:disabled),
.delete-link:hover:not(:disabled) {
  text-decoration: underline;
}

.video-card-foot {
  min-height: 62px;
  margin: 0 25px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #65728a;
  font-size: 12px;
}

.saving-copy {
  margin-left: auto;
  color: #1463ff;
  font-weight: 700;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  box-sizing: border-box;
  padding: 24px;
  background: rgba(20, 29, 45, .48);
  backdrop-filter: blur(2px);
}

.modal-card {
  width: min(680px, 100%);
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  box-sizing: border-box;
  border: 1px solid #e1e6ee;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(20, 30, 50, .22);
}

.upload-modal {
  padding: 24px;
}

.modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 20px;
}

.modal-head p {
  margin: 0 0 5px;
  color: #1463ff;
  font-size: 12px;
  font-weight: 750;
}

.modal-head h2,
.delete-modal h2 {
  margin: 0;
  color: #18233a;
  font-size: 22px;
}

.modal-close {
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 8px;
  background: #f3f5f8;
  color: #65728a;
  font-size: 22px;
}

.drop-zone {
  min-height: 235px;
  box-sizing: border-box;
  padding: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  border: 1.5px dashed #79a4f6;
  border-radius: 11px;
  background: #fbfdff;
  color: #6b7890;
  text-align: center;
  cursor: pointer;
  transition: .15s ease;
}

.drop-zone.dragging {
  border-color: #1463ff;
  background: #f1f6ff;
}

.file-input {
  display: none;
}

.upload-cloud {
  width: 52px;
  height: 52px;
  margin-bottom: 12px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #1463ff;
  color: #fff;
  font-size: 28px;
  box-shadow: 0 8px 18px rgba(20, 99, 255, .2);
}

.drop-zone strong {
  color: #26334a;
  font-size: 16px;
}

.drop-zone > span {
  margin-top: 7px;
  font-size: 12px;
}

.select-button {
  margin-top: 18px;
  pointer-events: none;
}

.upload-list {
  margin-top: 16px;
  display: grid;
  gap: 9px;
}

.upload-row {
  padding: 11px 13px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 260px;
  align-items: center;
  gap: 18px;
  border: 1px solid #e4e9f0;
  border-radius: 9px;
}

.upload-file-copy {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.upload-file-copy strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #26334a;
  font-size: 12px;
}

.upload-file-copy span,
.upload-status-row {
  color: #7a869a;
  font-size: 11px;
}

.upload-progress-block {
  display: grid;
  gap: 7px;
}

.upload-status-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.upload-status-row button {
  padding: 0;
  border: 0;
  background: transparent;
  color: #9aa5b6;
  font-size: 18px;
}

.upload-failed {
  max-width: 210px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #d92d20;
}

.upload-progress-track {
  height: 5px;
}

.modal-actions {
  margin-top: 20px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.delete-modal {
  width: min(470px, 100%);
  padding: 28px;
  text-align: center;
}

.danger-icon {
  width: 50px;
  height: 50px;
  margin: 0 auto 14px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #fff0ee;
  color: #d92d20;
  font-size: 22px;
  font-weight: 900;
}

.delete-modal p {
  margin: 12px 0 0;
  color: #5d6a81;
  font-size: 13px;
  line-height: 1.65;
}

.delete-modal .delete-note {
  color: #8a95a6;
  font-size: 11px;
}

@media (max-width: 1080px) {
  .source-video-page {
    padding: 0 16px 32px;
  }

  .page-layout {
    grid-template-columns: 1fr;
  }

  .stage-sidebar {
    min-height: 0;
  }

  .progress-card {
    padding: 18px;
  }

  .stage-list {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
  }

  .stage-item {
    min-height: 86px;
    padding: 20px 12px 12px 48px;
  }

  .stage-item:not(:last-child)::after {
    display: none;
  }

  .stage-dot {
    left: 15px;
    top: 19px;
  }

  .back-button {
    align-self: flex-start;
  }

  .project-meta {
    gap: 11px;
  }
}

@media (max-width: 760px) {
  .topbar,
  .video-card-head {
    align-items: stretch;
    flex-direction: column;
  }

  .topbar {
    padding: 16px 0;
  }

  .top-divider,
  .breadcrumbs {
    display: none;
  }

  .help-button {
    align-self: flex-start;
  }

  .stage-list {
    grid-template-columns: 1fr 1fr;
  }

  .project-card {
    padding: 20px;
  }

  .project-title-row h1 {
    font-size: 24px;
  }

  .meta-divider {
    display: none;
  }

  .video-card-head {
    padding: 18px;
  }

  .video-summary {
    flex-wrap: wrap;
  }

  .toolbar-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .table-wrap,
  .video-card-foot {
    margin-left: 18px;
    margin-right: 18px;
  }

  .upload-row {
    grid-template-columns: 1fr;
  }
}
</style>
