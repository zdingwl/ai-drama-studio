<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import {
  cancelProjectTask,
  getEpisodeShotBoundary,
  getProject,
  getProjectPlan,
  listProjectEpisodes,
  listProjectTasks,
  resumeProjectTask,
  retryProjectTask,
  startEpisodeShotBoundary,
  startP4AcceptanceTask,
  type P4AcceptanceScenario,
} from '@/features/projects/api'
import {
  VIDEO_PROJECT_TYPES,
  projectTypeLabel,
  type EpisodeRead,
  type EpisodeShotBoundaryRead,
  type ExecutionPlanStep,
  type PlanStepStatus,
  type ProjectExecutionPlan,
  type ProjectRead,
  type ShotAnchorRead,
  type ShotBoundaryResultStatus,
  type TaskRead,
  type TaskStatus,
} from '@/features/projects/types'
import { apiRequest } from '@/lib/api'

interface ProductStage {
  id: string
  phase: string
  title: string
  description: string
  status: PlanStepStatus
  completedSteps: number
  totalSteps: number
  steps: ExecutionPlanStep[]
}

const route = useRoute()
const projectId = computed(() => String(route.params.id))
const project = ref<ProjectRead | null>(null)
const plan = ref<ProjectExecutionPlan | null>(null)
const tasks = ref<TaskRead[]>([])
const episodes = ref<EpisodeRead[]>([])
const selectedEpisodeId = ref('')
const shotBoundary = ref<EpisodeShotBoundaryRead | null>(null)
const previewShot = ref<ShotAnchorRead | null>(null)
const loading = ref(true)
const refreshingTasks = ref(false)
const loadingEpisodes = ref(false)
const uploadingVideos = ref(false)
const loadingShots = ref(false)
const startingShots = ref(false)
const taskActionId = ref('')
const p4Starting = ref('')
const errorMessage = ref('')
const planErrorMessage = ref('')
const taskErrorMessage = ref('')
const shotErrorMessage = ref('')
const p4AcceptanceMessage = ref('')
let taskPollTimer: number | null = null

const isVideoProject = computed(() => project.value ? VIDEO_PROJECT_TYPES.has(project.value.project_type) : false)
const selectedEpisode = computed(() => episodes.value.find((episode) => episode.id === selectedEpisodeId.value) ?? null)
const selectedEpisodeIsPortrait = computed(() => {
  const episode = selectedEpisode.value
  return Boolean(episode && episode.height > episode.width)
})
const sortedTasks = computed(() => [...tasks.value].sort((left, right) => (
  new Date(right.created_at).getTime() - new Date(left.created_at).getTime()
)))
const primaryTasks = computed(() => {
  const active = sortedTasks.value.filter((task) => task.status === 'queued' || task.status === 'running')
  return active.length ? active : sortedTasks.value.slice(0, 1)
})
const historyTasks = computed(() => {
  const primaryIds = new Set(primaryTasks.value.map((task) => task.id))
  return sortedTasks.value.filter((task) => !primaryIds.has(task.id))
})

const statusText: Record<PlanStepStatus, string> = {
  COMPLETED: '已完成',
  READY: '可开始',
  BLOCKED_DEPENDENCY: '等待上游结果',
  WAITING_CAPABILITY: '能力待接入',
}

const taskStatusText: Record<TaskStatus, string> = {
  queued: '排队中',
  running: '处理中',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

const shotStatusText: Record<ShotBoundaryResultStatus, string> = {
  NOT_BUILT: '技术锚点未生成',
  CURRENT: '技术锚点当前有效',
  STALE: '原片已变化，需要更新锚点',
}

const videoStageMeta: Record<string, { title: string; description: string }> = {
  输入: {
    title: '原片',
    description: '登记并保留完整 Episode，完整原片始终是 Source Truth。',
  },
  理解: {
    title: '原片理解',
    description: '系统内部组合镜头技术锚点、连续对白与画面文字证据、整集多模态理解和逐镜精细拉片；用户不需要逐项运行技术步骤。',
  },
  目标版本: {
    title: '目标版本设计',
    description: '基于正式原片理解结果设计目标地区的人物、场景、道具、对白与世界。',
  },
  分镜: {
    title: '分镜与时长',
    description: '把目标资产、真实语音时长和导演镜头组织成可生成计划。',
  },
  生成: {
    title: '视频生成',
    description: '执行视频生成、质量检查和正式结果选择。',
  },
  成片: {
    title: '后期与成片',
    description: '完成音频、字幕、口型、剪辑和最终输出。',
  },
}

function aggregateStageStatus(steps: ExecutionPlanStep[]): PlanStepStatus {
  if (steps.every((step) => step.status === 'COMPLETED')) return 'COMPLETED'
  // 产品阶段表示“整个阶段是否可完整执行”。只要内部还有能力未接入，就不能把阶段冒充成 READY。
  if (steps.some((step) => step.status === 'WAITING_CAPABILITY')) return 'WAITING_CAPABILITY'
  if (steps.some((step) => step.status === 'READY')) return 'READY'
  return 'BLOCKED_DEPENDENCY'
}

const productStages = computed<ProductStage[]>(() => {
  if (!plan.value) return []
  if (!isVideoProject.value) {
    return plan.value.steps.map((step) => ({
      id: step.id,
      phase: step.phase,
      title: step.title,
      description: step.description,
      status: step.status,
      completedSteps: step.status === 'COMPLETED' ? 1 : 0,
      totalSteps: 1,
      steps: [step],
    }))
  }

  const phases: string[] = []
  const grouped = new Map<string, ExecutionPlanStep[]>()
  for (const step of plan.value.steps) {
    if (!grouped.has(step.phase)) {
      phases.push(step.phase)
      grouped.set(step.phase, [])
    }
    grouped.get(step.phase)?.push(step)
  }

  return phases.map((phase) => {
    const steps = grouped.get(phase) ?? []
    const meta = videoStageMeta[phase]
    return {
      id: `phase-${phase}`,
      phase,
      title: meta?.title ?? phase,
      description: meta?.description ?? steps.map((step) => step.description).join(' '),
      status: aggregateStageStatus(steps),
      completedSteps: steps.filter((step) => step.status === 'COMPLETED').length,
      totalSteps: steps.length,
      steps,
    }
  })
})

const currentProductStage = computed(() => {
  if (!productStages.value.length) return null
  return productStages.value.find((stage) => stage.status !== 'COMPLETED') ?? productStages.value.at(-1) ?? null
})

const sourceUnderstandingStage = computed(() => productStages.value.find((stage) => stage.phase === '理解') ?? null)
const shotBoundaryPlanStep = computed(() => plan.value?.steps.find((step) => step.capabilities.includes('SHOT_BOUNDARY')) ?? null)
const sourceEvidencePlanStep = computed(() => plan.value?.steps.find((step) => step.capabilities.includes('SOURCE_DIALOGUE_EVIDENCE')) ?? null)
const episodeUnderstandingPlanStep = computed(() => plan.value?.steps.find((step) => step.capabilities.includes('EPISODE_UNDERSTANDING')) ?? null)
const shotBreakdownPlanStep = computed(() => plan.value?.steps.find((step) => step.capabilities.includes('SHOT_BREAKDOWN')) ?? null)

function planStepStatus(step: ExecutionPlanStep | null): string {
  return step ? statusText[step.status] : '当前项目不需要'
}

async function loadWorkspace(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  planErrorMessage.value = ''
  try {
    const [projectResult, taskResult, planResult] = await Promise.all([
      getProject(projectId.value),
      listProjectTasks(projectId.value),
      getProjectPlan(projectId.value).catch((error: unknown) => {
        planErrorMessage.value = error instanceof Error ? error.message : '执行计划暂不可用'
        return null
      }),
    ])
    project.value = projectResult
    tasks.value = taskResult
    plan.value = planResult

    if (VIDEO_PROJECT_TYPES.has(projectResult.project_type)) {
      await loadEpisodes()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '项目加载失败'
  } finally {
    loading.value = false
  }
}

async function refreshTasks(): Promise<void> {
  refreshingTasks.value = true
  taskErrorMessage.value = ''
  try {
    tasks.value = await listProjectTasks(projectId.value)
  } catch (error) {
    taskErrorMessage.value = error instanceof Error ? error.message : '任务状态刷新失败'
  } finally {
    refreshingTasks.value = false
  }
}

async function loadEpisodes(): Promise<void> {
  loadingEpisodes.value = true
  shotErrorMessage.value = ''
  try {
    episodes.value = await listProjectEpisodes(projectId.value)
    if (!episodes.value.length) {
      selectedEpisodeId.value = ''
      shotBoundary.value = null
      previewShot.value = null
      return
    }
    if (!episodes.value.some((episode) => episode.id === selectedEpisodeId.value)) {
      selectedEpisodeId.value = episodes.value[0]?.id ?? ''
    }
    await refreshShotBoundary()
  } catch (error) {
    shotErrorMessage.value = error instanceof Error ? error.message : '剧集读取失败'
  } finally {
    loadingEpisodes.value = false
  }
}

async function uploadVideos(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  if (!input.files?.length) return
  uploadingVideos.value = true
  shotErrorMessage.value = ''
  try {
    const data = new FormData()
    Array.from(input.files).forEach((file) => data.append('files', file))
    await apiRequest<EpisodeRead[]>(`/projects/${projectId.value}/sources/videos`, {
      method: 'POST',
      body: data,
    })
    plan.value = null
    planErrorMessage.value = '原片已更新，请根据当前素材重新生成执行计划。'
    await loadEpisodes()
  } catch (error) {
    shotErrorMessage.value = error instanceof Error ? error.message : '原片上传失败'
  } finally {
    uploadingVideos.value = false
    input.value = ''
  }
}

async function refreshShotBoundary(): Promise<void> {
  if (!selectedEpisodeId.value) {
    shotBoundary.value = null
    previewShot.value = null
    return
  }
  loadingShots.value = true
  shotErrorMessage.value = ''
  previewShot.value = null
  try {
    shotBoundary.value = await getEpisodeShotBoundary(projectId.value, selectedEpisodeId.value)
  } catch (error) {
    shotErrorMessage.value = error instanceof Error ? error.message : '镜头技术锚点读取失败'
  } finally {
    loadingShots.value = false
  }
}

async function changeEpisode(): Promise<void> {
  shotBoundary.value = null
  previewShot.value = null
  await refreshShotBoundary()
}

function stopTaskPolling(): void {
  if (taskPollTimer !== null) {
    window.clearInterval(taskPollTimer)
    taskPollTimer = null
  }
}

function startTaskPolling(): void {
  if (taskPollTimer !== null) return
  taskPollTimer = window.setInterval(async () => {
    await refreshTasks()
    const hasActiveTask = tasks.value.some((task) => task.status === 'queued' || task.status === 'running')
    if (!hasActiveTask) {
      if (selectedEpisodeId.value) await refreshShotBoundary()
      stopTaskPolling()
    }
  }, 800)
}

function replaceTask(updated: TaskRead): void {
  const index = tasks.value.findIndex((item) => item.id === updated.id)
  if (index >= 0) {
    tasks.value[index] = updated
  } else {
    tasks.value.unshift(updated)
  }
}

function newCommandKey(prefix: string): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
  return `${prefix}-${suffix}`.slice(0, 128)
}

async function startShotBoundary(): Promise<void> {
  if (!selectedEpisodeId.value) return
  startingShots.value = true
  shotErrorMessage.value = ''
  try {
    const task = await startEpisodeShotBoundary(
      projectId.value,
      selectedEpisodeId.value,
      newCommandKey(`p5-shot-${selectedEpisodeId.value}`),
    )
    replaceTask(task)
    startTaskPolling()
  } catch (error) {
    shotErrorMessage.value = error instanceof Error ? error.message : '镜头技术锚点任务启动失败'
  } finally {
    startingShots.value = false
  }
}

async function startAcceptanceScenario(scenario: P4AcceptanceScenario): Promise<void> {
  p4Starting.value = scenario
  p4AcceptanceMessage.value = ''
  taskErrorMessage.value = ''
  try {
    const task = await startP4AcceptanceTask(projectId.value, scenario, newCommandKey(`p4-${scenario}`))
    replaceTask(task)
    startTaskPolling()
  } catch (error) {
    taskErrorMessage.value = error instanceof Error ? error.message : 'P4 验收任务启动失败'
  } finally {
    p4Starting.value = ''
  }
}

async function verifyDuplicateProtection(): Promise<void> {
  p4Starting.value = 'dedupe'
  p4AcceptanceMessage.value = ''
  taskErrorMessage.value = ''
  const key = newCommandKey('p4-dedupe')
  try {
    const beforeTasks = await listProjectTasks(projectId.value)
    const beforeTaskIds = new Set(beforeTasks.map((task) => task.id))
    const [first, second] = await Promise.all([
      startP4AcceptanceTask(projectId.value, 'dedupe', key),
      startP4AcceptanceTask(projectId.value, 'dedupe', key),
    ])
    const afterTasks = await listProjectTasks(projectId.value)
    tasks.value = afterTasks
    const newlyCreatedTasks = afterTasks.filter((task) => !beforeTaskIds.has(task.id))
    const passed = first.id === second.id
      && newlyCreatedTasks.length === 1
      && newlyCreatedTasks[0]?.id === first.id

    if (passed) {
      p4AcceptanceMessage.value = '重复提交保护：通过。本次两次相同提交只新增了 1 个“防重复提交”任务。'
    } else {
      taskErrorMessage.value = `重复提交保护：未通过。本次测试新增了 ${newlyCreatedTasks.length} 个任务。`
    }

    if (afterTasks.some((task) => task.status === 'queued' || task.status === 'running')) {
      startTaskPolling()
    }
  } catch (error) {
    taskErrorMessage.value = error instanceof Error ? error.message : '重复提交保护测试失败'
  } finally {
    p4Starting.value = ''
  }
}

async function runTaskAction(task: TaskRead, action: 'retry' | 'cancel' | 'resume'): Promise<void> {
  taskActionId.value = task.id
  taskErrorMessage.value = ''
  try {
    const updated = action === 'retry'
      ? await retryProjectTask(projectId.value, task.id)
      : action === 'cancel'
        ? await cancelProjectTask(projectId.value, task.id)
        : await resumeProjectTask(projectId.value, task.id)
    replaceTask(updated)
    if (updated.status === 'queued' || updated.status === 'running') startTaskPolling()
  } catch (error) {
    taskErrorMessage.value = error instanceof Error ? error.message : '任务操作失败'
  } finally {
    taskActionId.value = ''
  }
}

function formatTime(us: number): string {
  const totalMs = Math.max(0, Math.round(us / 1000))
  const milliseconds = totalMs % 1000
  const totalSeconds = Math.floor(totalMs / 1000)
  const seconds = totalSeconds % 60
  const totalMinutes = Math.floor(totalSeconds / 60)
  const minutes = totalMinutes % 60
  const hours = Math.floor(totalMinutes / 60)
  const core = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`
  return hours > 0 ? `${String(hours).padStart(2, '0')}:${core}` : core
}

function formatDuration(us: number): string {
  const seconds = us / 1_000_000
  return seconds >= 10 ? `${seconds.toFixed(2)}s` : `${seconds.toFixed(3)}s`
}

function openShotPreview(shot: ShotAnchorRead): void {
  previewShot.value = shot
}

function closeShotPreview(): void {
  previewShot.value = null
}

onMounted(loadWorkspace)
onBeforeUnmount(stopTaskPolling)
</script>

<template>
  <section class="workspace">
    <div class="workspace-nav">
      <RouterLink to="/" class="back-link">← 返回项目</RouterLink>
    </div>

    <p v-if="loading" class="muted loading-state">正在加载项目…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>

    <template v-else-if="project">
      <header class="project-summary">
        <div class="project-identity">
          <div class="project-title-row">
            <h1>{{ project.name }}</h1>
            <span class="project-type">{{ projectTypeLabel(project.project_type) }}</span>
          </div>
          <div class="project-meta">
            <span>{{ project.target_language }} · {{ project.target_region }}</span>
            <span v-if="plan">执行计划 v{{ plan.workflow_revision }}</span>
            <span v-else>执行计划尚未生成</span>
          </div>
        </div>
        <div class="project-stage">
          <span class="stage-dot" :class="{ ready: Boolean(plan) }"></span>
          <div>
            <small>当前阶段</small>
            <strong>{{ currentProductStage?.title ?? (isVideoProject ? (episodes.length ? '原片理解' : '上传原片') : '准备项目') }}</strong>
          </div>
        </div>
      </header>

      <section v-if="isVideoProject" class="understanding-section">
        <div class="workbench-header understanding-header">
          <div class="workbench-title">
            <p class="eyebrow">Source Understanding</p>
            <div class="workbench-title-row">
              <h2>原片理解</h2>
              <span v-if="sourceUnderstandingStage" class="status" :class="sourceUnderstandingStage.status.toLowerCase()">
                {{ statusText[sourceUnderstandingStage.status] }}
              </span>
            </div>
            <p class="section-note">
              系统直接读取完整 Episode 做原片理解。镜头技术锚点、连续对白与画面文字证据会作为内部证据协同使用，不会先把视频切碎再拼剧情。
            </p>
          </div>
          <div class="source-actions">
            <label class="upload-button">
              <span>{{ uploadingVideos ? '正在上传…' : episodes.length ? '继续上传原片' : '上传原片' }}</span>
              <input
                class="visually-hidden"
                type="file"
                multiple
                accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm,.avi,.m4v"
                :disabled="uploadingVideos"
                @change="uploadVideos"
              />
            </label>
            <button v-if="episodes.length" class="secondary-button" type="button" :disabled="loadingEpisodes" @click="loadEpisodes">
              {{ loadingEpisodes ? '刷新中…' : '刷新剧集' }}
            </button>
          </div>
        </div>

        <p v-if="shotErrorMessage" class="error-message workbench-message">{{ shotErrorMessage }}</p>
        <p v-if="loadingEpisodes && !episodes.length" class="muted workbench-message">正在读取已上传原片…</p>

        <template v-if="episodes.length">
          <div class="episode-toolbar source-toolbar">
            <label class="episode-picker">
              <span>当前原片</span>
              <select v-model="selectedEpisodeId" @change="changeEpisode">
                <option v-for="episode in episodes" :key="episode.id" :value="episode.id">
                  第 {{ episode.episode_order }} 集 · {{ episode.source_asset.original_filename }}
                </option>
              </select>
            </label>
            <div v-if="selectedEpisode" class="episode-facts">
              <span>{{ selectedEpisode.width }} × {{ selectedEpisode.height }}</span>
              <span>{{ formatTime(selectedEpisode.duration_us) }}</span>
              <span>{{ selectedEpisode.has_audio ? '含音轨' : '无音轨' }}</span>
            </div>
          </div>

          <div class="analysis-principle">
            <div class="principle-icon">◎</div>
            <div>
              <strong>完整 Episode 始终是原片事实源</strong>
              <span>内部生成的 Reference Clip 只是人工核对和逐镜精看用的派生资产，不会替代完整视频进入 ASR 或整集多模态理解。</span>
            </div>
          </div>

          <div class="evidence-grid">
            <article class="evidence-card complete">
              <span class="evidence-index">01</span>
              <div>
                <strong>完整原片</strong>
                <small>Source Truth</small>
              </div>
              <b>已就绪</b>
            </article>
            <article class="evidence-card" :class="shotBoundary?.status === 'CURRENT' ? 'complete' : ''">
              <span class="evidence-index">02</span>
              <div>
                <strong>镜头技术锚点</strong>
                <small>{{ shotBoundary ? shotStatusText[shotBoundary.status] : planStepStatus(shotBoundaryPlanStep) }}</small>
              </div>
              <b>{{ shotBoundary?.status === 'CURRENT' ? `${shotBoundary.shot_count} 镜头` : planStepStatus(shotBoundaryPlanStep) }}</b>
            </article>
            <article class="evidence-card">
              <span class="evidence-index">03</span>
              <div>
                <strong>对白与画面文字证据</strong>
                <small>从完整时间轴连续提取，不按 Shot 切断对白</small>
              </div>
              <b>{{ planStepStatus(sourceEvidencePlanStep) }}</b>
            </article>
            <article v-if="episodeUnderstandingPlanStep" class="evidence-card">
              <span class="evidence-index">04</span>
              <div>
                <strong>整集多模态理解</strong>
                <small>先理解整集剧情、人物、场景、事件和关系</small>
              </div>
              <b>{{ planStepStatus(episodeUnderstandingPlanStep) }}</b>
            </article>
            <article v-if="shotBreakdownPlanStep" class="evidence-card">
              <span class="evidence-index">05</span>
              <div>
                <strong>逐镜精细拉片</strong>
                <small>整集知识建立后，再回到镜头层做精细事实提取</small>
              </div>
              <b>{{ planStepStatus(shotBreakdownPlanStep) }}</b>
            </article>
          </div>

          <details class="technical-details">
            <summary>
              <div>
                <strong>技术分析详情</strong>
                <span>镜头时间锚点、缩略图与 Reference Clip</span>
              </div>
              <small>{{ shotBoundary?.status === 'CURRENT' ? `${shotBoundary.shot_count} 个镜头` : '按需展开' }}</small>
            </summary>
            <div class="technical-body">
              <div class="technical-toolbar">
                <div>
                  <p class="eyebrow">内部技术能力</p>
                  <h3>镜头技术锚点</h3>
                  <p>这里只识别切镜时间，生成缩略图和可播放参考片段；不做人物、剧情或对白理解。</p>
                </div>
                <button class="primary-button" type="button" :disabled="startingShots || !selectedEpisodeId" @click="startShotBoundary">
                  {{ startingShots ? '正在提交…' : shotBoundary?.status === 'CURRENT' ? '重新生成技术锚点' : '生成技术锚点' }}
                </button>
              </div>

              <p v-if="loadingShots" class="muted workbench-message technical-message">正在读取镜头技术锚点…</p>

              <template v-else-if="shotBoundary">
                <div class="shot-result-heading">
                  <div class="shot-result-file">
                    <strong>第 {{ shotBoundary.episode_order }} 集 · {{ shotBoundary.source_filename }}</strong>
                    <span v-if="shotBoundary.status === 'CURRENT'">内部技术锚点可供后续理解和人工核对使用</span>
                    <span v-else-if="shotBoundary.status === 'NOT_BUILT'">按需生成镜头时间锚点；这不是“原片理解”的完成标志</span>
                  </div>
                  <div class="shot-count">
                    <strong>{{ shotBoundary.shot_count }}</strong>
                    <span>镜头</span>
                  </div>
                </div>

                <p v-if="shotBoundary.status === 'STALE'" class="stale-note">
                  原片已经变化，下面保留的是旧技术结果供核对；重新生成后才能作为当前内部锚点使用。
                </p>

                <div
                  v-if="shotBoundary.shots.length"
                  class="shot-grid"
                  :class="{ 'is-portrait': selectedEpisodeIsPortrait }"
                >
                  <article v-for="shot in shotBoundary.shots" :key="shot.id" class="shot-card">
                    <button
                      class="shot-thumb-button"
                      type="button"
                      :aria-label="`播放镜头 ${shot.shot_number} 参考片段`"
                      @click="openShotPreview(shot)"
                    >
                      <img :src="shot.thumbnail_url" :alt="`镜头 ${shot.shot_number} 缩略图`" loading="lazy" />
                      <span class="play-badge">▶</span>
                    </button>
                    <div class="shot-card-body">
                      <div class="shot-title-row">
                        <strong>#{{ String(shot.shot_number).padStart(3, '0') }}</strong>
                        <span>{{ formatDuration(shot.duration_us) }}</span>
                      </div>
                      <div class="shot-time">
                        <span>{{ formatTime(shot.start_us) }}</span>
                        <i>→</i>
                        <span>{{ formatTime(shot.end_us) }}</span>
                      </div>
                      <button class="preview-button" type="button" @click="openShotPreview(shot)">播放参考片段</button>
                    </div>
                  </article>
                </div>

                <div v-else class="empty-state result-empty">
                  <div class="empty-icon">◫</div>
                  <div>
                    <strong>还没有镜头技术锚点</strong>
                    <span>如需核对 Shot Boundary，可在这里显式生成；页面打开不会自动启动任务。</span>
                  </div>
                </div>
              </template>
            </div>
          </details>
        </template>

        <div v-else-if="!loadingEpisodes" class="empty-state source-empty">
          <div class="empty-icon">＋</div>
          <div>
            <strong>还没有原片</strong>
            <span>先上传一集或多集完整短剧视频。上传完成后剧集列表会自动出现，原片不会被预先切碎。</span>
          </div>
        </div>
      </section>

      <section class="task-section">
        <div class="section-heading compact-heading">
          <div>
            <p class="eyebrow">任务状态</p>
            <h2>{{ primaryTasks.some((task) => task.status === 'queued' || task.status === 'running') ? '正在执行' : '最近任务' }}</h2>
          </div>
          <button class="secondary-button" type="button" :disabled="refreshingTasks" @click="refreshTasks">
            {{ refreshingTasks ? '刷新中…' : '刷新任务' }}
          </button>
        </div>

        <p v-if="taskErrorMessage" class="error-message">{{ taskErrorMessage }}</p>
        <div v-if="primaryTasks.length" class="task-list">
          <article v-for="task in primaryTasks" :key="task.id" class="task-card">
            <div class="task-heading">
              <div>
                <h3>{{ task.task_name }}</h3>
                <span class="task-status" :class="`task-${task.status}`">{{ taskStatusText[task.status] }}</span>
              </div>
              <strong>{{ task.progress_percent }}%</strong>
            </div>
            <div class="progress-track" aria-hidden="true">
              <div class="progress-value" :style="{ width: `${task.progress_percent}%` }"></div>
            </div>
            <p v-if="task.last_error" class="task-error">{{ task.last_error }}</p>
            <div v-if="task.can_retry || task.can_cancel || task.can_resume" class="task-actions">
              <button v-if="task.can_retry" type="button" :disabled="taskActionId === task.id" @click="runTaskAction(task, 'retry')">重试</button>
              <button v-if="task.can_resume" type="button" :disabled="taskActionId === task.id" @click="runTaskAction(task, 'resume')">继续</button>
              <button v-if="task.can_cancel" type="button" :disabled="taskActionId === task.id" @click="runTaskAction(task, 'cancel')">取消</button>
            </div>
          </article>
        </div>
        <p v-else class="muted task-empty">当前没有执行任务。</p>

        <details v-if="historyTasks.length" class="history-details">
          <summary>
            <span>历史任务</span>
            <small>{{ historyTasks.length }} 条</small>
          </summary>
          <div class="history-task-list">
            <article v-for="task in historyTasks" :key="task.id" class="task-card history-task-card">
              <div class="task-heading">
                <div>
                  <h3>{{ task.task_name }}</h3>
                  <span class="task-status" :class="`task-${task.status}`">{{ taskStatusText[task.status] }}</span>
                </div>
                <strong>{{ task.progress_percent }}%</strong>
              </div>
              <p v-if="task.last_error" class="task-error">{{ task.last_error }}</p>
              <div v-if="task.can_retry || task.can_cancel || task.can_resume" class="task-actions">
                <button v-if="task.can_retry" type="button" :disabled="taskActionId === task.id" @click="runTaskAction(task, 'retry')">重试</button>
                <button v-if="task.can_resume" type="button" :disabled="taskActionId === task.id" @click="runTaskAction(task, 'resume')">继续</button>
                <button v-if="task.can_cancel" type="button" :disabled="taskActionId === task.id" @click="runTaskAction(task, 'cancel')">取消</button>
              </div>
            </article>
          </div>
        </details>
      </section>

      <details class="secondary-panel acceptance-section">
        <summary>
          <div>
            <strong>开发验收工具</strong>
            <span>P4 任务执行机制</span>
          </div>
          <small>仅开发调试</small>
        </summary>
        <div class="details-body">
          <p class="acceptance-note">这里只运行本地模拟任务，不调用真实模型、不产生费用。用于人工检查排队、进度、失败重试、中断继续、取消和重复提交保护。</p>
          <div class="acceptance-actions">
            <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('success')">{{ p4Starting === 'success' ? '启动中…' : '测试正常完成' }}</button>
            <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('retry')">{{ p4Starting === 'retry' ? '启动中…' : '测试失败 → 重试' }}</button>
            <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('resume')">{{ p4Starting === 'resume' ? '启动中…' : '测试中断 → 继续' }}</button>
            <button type="button" :disabled="Boolean(p4Starting)" @click="verifyDuplicateProtection">{{ p4Starting === 'dedupe' ? '测试中…' : '测试防重复提交' }}</button>
          </div>
          <p v-if="p4AcceptanceMessage" class="success-message">{{ p4AcceptanceMessage }}</p>
        </div>
      </details>

      <details v-if="plan" class="secondary-panel plan-section">
        <summary>
          <div>
            <strong>产品执行计划</strong>
            <span>{{ plan.skill_title }}</span>
          </div>
          <small>版本 {{ plan.workflow_revision }}</small>
        </summary>
        <div class="details-body">
          <div class="plan-list product-plan-list">
            <article v-for="(stage, index) in productStages" :key="stage.id" class="plan-step product-stage-step">
              <div class="step-number">{{ String(index + 1).padStart(2, '0') }}</div>
              <div class="step-content">
                <div class="step-heading">
                  <div>
                    <span class="phase">{{ stage.phase }}</span>
                    <h3>{{ stage.title }}</h3>
                  </div>
                  <span class="status" :class="stage.status.toLowerCase()">{{ statusText[stage.status] }}</span>
                </div>
                <p>{{ stage.description }}</p>
                <p v-if="stage.totalSteps > 1" class="stage-progress-note">内部 {{ stage.completedSteps }}/{{ stage.totalSteps }} 个执行步骤已完成；技术子步骤不会作为用户主流程逐项展开。</p>
              </div>
            </article>
          </div>

          <details class="internal-plan-details">
            <summary>查看内部执行步骤（开发/排障）</summary>
            <div class="plan-list internal-plan-list">
              <article v-for="(step, index) in plan.steps" :key="step.id" class="plan-step">
                <div class="step-number">{{ String(index + 1).padStart(2, '0') }}</div>
                <div class="step-content">
                  <div class="step-heading">
                    <div>
                      <span class="phase">{{ step.phase }}</span>
                      <h3>{{ step.title }}</h3>
                    </div>
                    <span class="status" :class="step.status.toLowerCase()">{{ statusText[step.status] }}</span>
                  </div>
                  <p>{{ step.description }}</p>
                </div>
              </article>
            </div>
          </details>
        </div>
      </details>

      <section v-else class="secondary-panel plan-empty">
        <strong>当前还没有可显示的执行计划</strong>
        <span>{{ planErrorMessage || '原片上传和已有技术分析结果仍可读取；不会因为页面刷新自动启动处理。' }}</span>
      </section>
    </template>

    <div v-if="previewShot" class="preview-overlay" role="presentation" @click.self="closeShotPreview">
      <section class="preview-dialog" role="dialog" aria-modal="true" :aria-label="`镜头 ${previewShot.shot_number} 参考片段`">
        <header class="preview-header">
          <div>
            <strong>镜头 {{ String(previewShot.shot_number).padStart(3, '0') }}</strong>
            <span>{{ formatTime(previewShot.start_us) }} → {{ formatTime(previewShot.end_us) }} · {{ formatDuration(previewShot.duration_us) }}</span>
          </div>
          <button type="button" aria-label="关闭参考片段" @click="closeShotPreview">关闭</button>
        </header>
        <div class="preview-media" :class="{ portrait: selectedEpisodeIsPortrait }">
          <video :src="previewShot.reference_clip_url" controls autoplay preload="metadata"></video>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.workspace {
  display: grid;
  gap: 18px;
  max-width: 1360px;
  margin: 0 auto;
}

.workspace-nav { min-height: 22px; }
.back-link { color: #5146d9; text-decoration: none; font-size: 14px; font-weight: 700; }
.back-link:hover { text-decoration: underline; }
.loading-state { padding: 36px 0; }

.project-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px;
  border: 1px solid #e4e4df;
  border-radius: 16px;
  background: #fff;
}
.project-identity { min-width: 0; }
.project-title-row { display: flex; align-items: center; gap: 10px; min-width: 0; }
.project-title-row h1 { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 26px; line-height: 1.2; letter-spacing: -0.02em; }
.project-type { flex: 0 0 auto; padding: 4px 8px; border-radius: 999px; background: #f0efff; color: #5548df; font-size: 12px; font-weight: 800; }
.project-meta { display: flex; gap: 14px; margin-top: 7px; color: #74746f; font-size: 13px; }
.project-stage { flex: 0 0 auto; display: flex; align-items: center; gap: 10px; min-width: 180px; padding-left: 20px; border-left: 1px solid #ecece8; }
.stage-dot { width: 9px; height: 9px; border-radius: 50%; background: #b9b9b3; box-shadow: 0 0 0 4px #f0f0ec; }
.stage-dot.ready { background: #5b4ee8; box-shadow: 0 0 0 4px #efedff; }
.project-stage div { display: grid; gap: 2px; }
.project-stage small { color: #8a8a84; font-size: 11px; }
.project-stage strong { font-size: 13px; }

.understanding-section {
  overflow: hidden;
  border: 1px solid #deded8;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(32, 32, 29, .04);
}
.workbench-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 22px; }
.understanding-header { padding-bottom: 18px; }
.workbench-title { min-width: 0; }
.workbench-title-row { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
.workbench-title h2 { margin: 0; font-size: 27px; letter-spacing: -.025em; }
.eyebrow { margin: 0; color: #6b5ce7; font-size: 11px; font-weight: 800; letter-spacing: .11em; text-transform: uppercase; }
.section-note, .acceptance-note { margin: 8px 0 0; color: #73736d; font-size: 13px; line-height: 1.65; }
.source-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.upload-button, .primary-button, .secondary-button, .preview-button, .task-actions button, .acceptance-actions button { min-height: 36px; border-radius: 9px; font-weight: 750; cursor: pointer; }
.upload-button { display: inline-flex; align-items: center; padding: 0 13px; border: 1px solid #5146d9; background: #5b4ee8; color: #fff; font-size: 13px; }
.upload-button:has(input:disabled) { cursor: wait; opacity: .55; }
.primary-button { padding: 0 16px; border: 1px solid #20201d; background: #20201d; color: #fff; font-size: 13px; }
.secondary-button, .task-actions button, .acceptance-actions button { padding: 0 12px; border: 1px solid #d6d6d0; background: #fff; font-size: 13px; }
.secondary-button:hover, .task-actions button:hover, .acceptance-actions button:hover { background: #f7f7f4; }
button:disabled { cursor: wait; opacity: .55; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.workbench-message { margin: 0 22px 14px; }

.episode-toolbar { display: grid; grid-template-columns: minmax(360px, 1fr) auto; align-items: end; gap: 12px; margin: 0 22px 16px; padding: 12px; border: 1px solid #e7e7e1; border-radius: 12px; background: #f8f8f5; }
.episode-picker { display: grid; gap: 6px; min-width: 0; }
.episode-picker > span { color: #686863; font-size: 11px; font-weight: 800; }
.episode-picker select { width: 100%; min-height: 38px; padding: 0 34px 0 10px; border: 1px solid #d5d5cf; border-radius: 8px; background: #fff; font-size: 13px; }
.episode-facts { display: flex; align-items: center; gap: 6px; min-height: 38px; }
.episode-facts span { padding: 5px 8px; border-radius: 7px; background: #ecece8; color: #686863; font-size: 11px; font-variant-numeric: tabular-nums; }

.analysis-principle { display: flex; align-items: center; gap: 12px; margin: 0 22px 14px; padding: 13px 14px; border: 1px solid #dfdef5; border-radius: 12px; background: #f7f6ff; }
.principle-icon { flex: 0 0 auto; display: grid; place-items: center; width: 34px; height: 34px; border-radius: 10px; background: #eae8ff; color: #5a4ee0; font-weight: 900; }
.analysis-principle > div:last-child { display: grid; gap: 3px; }
.analysis-principle strong { font-size: 13px; }
.analysis-principle span { color: #6e6d78; font-size: 12px; line-height: 1.55; }

.evidence-grid { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 8px; padding: 0 22px 18px; }
.evidence-card { min-width: 0; display: grid; grid-template-columns: 28px minmax(0, 1fr); gap: 9px; align-items: center; padding: 12px; border: 1px solid #e5e5df; border-radius: 12px; background: #fafaf8; }
.evidence-card.complete { border-color: #d7e9db; background: #f6fbf7; }
.evidence-index { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 8px; background: #ecece8; color: #7b7b75; font-size: 10px; font-weight: 900; }
.evidence-card.complete .evidence-index { background: #e0f0e3; color: #2e6a3b; }
.evidence-card > div { min-width: 0; display: grid; gap: 3px; }
.evidence-card strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.evidence-card small { overflow: hidden; color: #7e7e78; font-size: 10px; line-height: 1.4; text-overflow: ellipsis; }
.evidence-card b { grid-column: 2; color: #595954; font-size: 10px; font-weight: 800; }
.evidence-card.complete b { color: #2e6a3b; }

.technical-details { border-top: 1px solid #ecece7; }
.technical-details > summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 22px; list-style: none; cursor: pointer; background: #fbfbf9; }
.technical-details > summary::-webkit-details-marker { display: none; }
.technical-details > summary:hover { background: #f7f7f4; }
.technical-details > summary > div { min-width: 0; display: flex; align-items: baseline; gap: 10px; }
.technical-details > summary strong { font-size: 13px; }
.technical-details > summary span, .technical-details > summary small { color: #81817b; font-size: 11px; }
.technical-body { border-top: 1px solid #ecece7; }
.technical-toolbar { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; padding: 18px 22px; }
.technical-toolbar h3 { margin: 3px 0 0; font-size: 18px; }
.technical-toolbar p:last-child { margin: 6px 0 0; color: #777771; font-size: 12px; }
.technical-message { margin-top: -6px; }

.status, .task-status { display: inline-flex; padding: 3px 7px; border-radius: 999px; background: #eeeeea; color: #62625d; font-size: 10px; font-weight: 800; }
.ready, .task-running { color: #365b91; background: #e8eef8; }
.completed, .task-succeeded { color: #316335; background: #e8f3e8; }
.waiting_capability, .blocked_dependency, .task-cancelled, .task-interrupted { color: #765f32; background: #f4eee2; }
.task-failed { color: #9a342d; background: #f9e9e7; }

.shot-result-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 14px 22px; border-top: 1px solid #ecece7; border-bottom: 1px solid #ecece7; background: #fafaf8; }
.shot-result-file { min-width: 0; display: grid; gap: 3px; }
.shot-result-file strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
.shot-result-file span { color: #85857f; font-size: 12px; }
.shot-count { flex: 0 0 auto; display: flex; align-items: baseline; gap: 5px; }
.shot-count strong { font-size: 22px; letter-spacing: -.03em; }
.shot-count span { color: #777771; font-size: 12px; }
.stale-note { margin: 14px 22px 0; padding: 10px 12px; border: 1px solid #f1dfb7; border-radius: 9px; background: #fff9ea; color: #8b5d14; font-size: 13px; }
.shot-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; padding: 14px 22px 22px; }
.shot-card { min-width: 0; display: grid; grid-template-columns: 124px minmax(0, 1fr); min-height: 106px; overflow: hidden; border: 1px solid #e3e3de; border-radius: 11px; background: #fff; transition: border-color .15s ease, box-shadow .15s ease; }
.shot-card:hover { border-color: #d0d0ca; box-shadow: 0 3px 12px rgba(32, 32, 29, .06); }
.shot-grid.is-portrait .shot-card { grid-template-columns: 84px minmax(0, 1fr); min-height: 124px; }
.shot-thumb-button { position: relative; width: 100%; min-height: 100%; overflow: hidden; padding: 0; border: 0; border-right: 1px solid #e3e3de; background: #151515; cursor: pointer; }
.shot-thumb-button img { display: block; width: 100%; height: 100%; min-height: 106px; object-fit: contain; background: #151515; }
.shot-grid.is-portrait .shot-thumb-button img { min-height: 124px; }
.play-badge { position: absolute; left: 8px; bottom: 8px; display: grid; place-items: center; width: 25px; height: 25px; padding-left: 2px; border-radius: 50%; background: rgba(255,255,255,.92); color: #1f1f1c; font-size: 9px; box-shadow: 0 1px 5px rgba(0,0,0,.2); }
.shot-card-body { min-width: 0; display: grid; align-content: center; gap: 8px; padding: 11px 12px; }
.shot-title-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.shot-title-row strong { font-size: 14px; }
.shot-title-row span { color: #7a7a74; font-size: 11px; font-variant-numeric: tabular-nums; }
.shot-time { display: flex; align-items: center; gap: 5px; min-width: 0; color: #666660; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.shot-time i { color: #a0a09a; font-family: inherit; font-style: normal; }
.preview-button { justify-self: start; min-height: 28px; padding: 0 9px; border: 1px solid #d9d9d3; background: #fafaf8; color: #41413d; font-size: 11px; }
.preview-button:hover { border-color: #bcbcb5; background: #f3f3ef; }

.empty-state { display: flex; align-items: center; gap: 12px; margin: 0 22px 22px; padding: 18px; border: 1px dashed #d7d7d1; border-radius: 12px; background: #fafaf8; }
.source-empty { margin-top: 0; }
.result-empty { margin-top: 16px; }
.empty-icon { flex: 0 0 auto; display: grid; place-items: center; width: 38px; height: 38px; border-radius: 10px; background: #eeeeea; color: #777771; font-size: 18px; }
.empty-state > div:last-child { display: grid; gap: 4px; }
.empty-state strong { font-size: 14px; }
.empty-state span { color: #777771; font-size: 12px; line-height: 1.5; }

.task-section { display: grid; gap: 12px; padding: 18px 20px; border: 1px solid #e0e0da; border-radius: 16px; background: #fff; }
.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.compact-heading h2 { margin: 3px 0 0; font-size: 19px; }
.task-list { display: grid; gap: 10px; }
.task-card { display: grid; gap: 9px; padding: 13px 14px; border: 1px solid #e4e4de; border-radius: 11px; background: #fafaf8; }
.task-heading, .step-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.task-heading > div { min-width: 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.task-heading h3, .step-heading h3 { margin: 0; font-size: 14px; }
.task-heading > strong { flex: 0 0 auto; font-size: 13px; font-variant-numeric: tabular-nums; }
.progress-track { height: 5px; overflow: hidden; border-radius: 999px; background: #e7e7e2; }
.progress-value { height: 100%; border-radius: inherit; background: #6558e8; transition: width .2s ease; }
.task-error, .error-message { margin: 0; color: #a33b32; font-size: 12px; line-height: 1.5; }
.task-actions { display: flex; gap: 7px; flex-wrap: wrap; }
.task-actions button { min-height: 30px; padding: 0 10px; font-size: 11px; }
.task-empty { margin: 0; }
.history-details { border-top: 1px solid #ecece7; }
.history-details > summary, .secondary-panel > summary { list-style: none; cursor: pointer; }
.history-details > summary::-webkit-details-marker, .secondary-panel > summary::-webkit-details-marker { display: none; }
.history-details > summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-top: 12px; color: #5f5f5a; font-size: 12px; font-weight: 750; }
.history-details > summary small { color: #92928c; font-weight: 600; }
.history-task-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; padding-top: 10px; }
.history-task-card { background: #fff; }

.secondary-panel { overflow: hidden; border: 1px solid #e0e0da; border-radius: 14px; background: #fff; }
.secondary-panel > summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; }
.secondary-panel > summary:hover { background: #fafaf8; }
.secondary-panel > summary > div { min-width: 0; display: flex; align-items: baseline; gap: 10px; }
.secondary-panel > summary strong { font-size: 13px; }
.secondary-panel > summary span, .secondary-panel > summary small { overflow: hidden; color: #81817b; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.details-body { padding: 0 16px 16px; border-top: 1px solid #eeeeea; }
.acceptance-note { margin-top: 14px; }
.acceptance-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.acceptance-actions button { min-height: 32px; font-size: 11px; }
.success-message { margin: 10px 0 0; color: #316335; font-size: 12px; font-weight: 700; }
.plan-list { display: grid; gap: 8px; padding-top: 12px; }
.plan-step { display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 10px; padding: 12px; border: 1px solid #e6e6e1; border-radius: 10px; background: #fafaf8; }
.product-stage-step { background: #fff; }
.step-number { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 8px; background: #ecece8; color: #767670; font-size: 11px; font-weight: 800; }
.step-heading h3 { margin-top: 2px; }
.step-content p { margin: 6px 0 0; color: #74746f; font-size: 12px; line-height: 1.5; }
.phase { color: #7567df; font-size: 10px; font-weight: 800; }
.stage-progress-note { font-size: 11px !important; }
.internal-plan-details { margin-top: 12px; padding-top: 12px; border-top: 1px solid #ecece7; }
.internal-plan-details > summary { cursor: pointer; color: #686863; font-size: 11px; font-weight: 750; }
.internal-plan-list { padding-top: 10px; }
.plan-empty { display: grid; gap: 4px; padding: 14px 16px; color: #777771; font-size: 12px; }
.plan-empty strong { color: #454541; font-size: 13px; }

.preview-overlay { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 24px; background: rgba(18,18,18,.68); backdrop-filter: blur(3px); }
.preview-dialog { width: min(760px, 100%); overflow: hidden; border-radius: 16px; background: #111; box-shadow: 0 24px 80px rgba(0,0,0,.32); }
.preview-header { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 13px 14px 13px 16px; background: #fff; }
.preview-header > div { min-width: 0; display: grid; gap: 3px; }
.preview-header strong { font-size: 14px; }
.preview-header span { color: #777771; font-size: 11px; font-variant-numeric: tabular-nums; }
.preview-header button { min-height: 30px; padding: 0 10px; border: 1px solid #d7d7d1; border-radius: 8px; background: #fff; font-size: 11px; font-weight: 700; cursor: pointer; }
.preview-media { display: grid; place-items: center; min-height: 260px; padding: 18px; background: #0b0b0b; }
.preview-media video { display: block; width: 100%; max-height: 72vh; background: #000; }
.preview-media.portrait video { width: auto; max-width: 100%; min-height: min(62vh, 620px); }
.muted { color: #777771; }

@media (max-width: 1180px) {
  .evidence-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@media (max-width: 980px) {
  .shot-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .episode-toolbar { grid-template-columns: minmax(0, 1fr); }
  .episode-facts { flex-wrap: wrap; }
  .evidence-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .workspace { gap: 14px; }
  .project-summary, .workbench-header, .section-heading, .technical-toolbar { align-items: stretch; flex-direction: column; }
  .project-stage { min-width: 0; padding: 10px 0 0; border-top: 1px solid #ecece8; border-left: 0; }
  .project-title-row { align-items: flex-start; flex-direction: column; }
  .project-title-row h1 { white-space: normal; font-size: 23px; }
  .source-actions, .source-actions > *, .upload-button { width: 100%; justify-content: center; }
  .episode-toolbar { grid-template-columns: 1fr; align-items: stretch; }
  .evidence-grid, .shot-grid, .history-task-list { grid-template-columns: 1fr; }
  .technical-details > summary > div { display: grid; gap: 3px; }
  .preview-overlay { padding: 10px; }
  .preview-media { min-height: 220px; padding: 8px; }
  .preview-media.portrait video { min-height: 0; max-height: 76vh; }
}
</style>
