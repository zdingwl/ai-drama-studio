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
  type PlanStepStatus,
  type ProjectExecutionPlan,
  type ProjectRead,
  type ShotBoundaryResultStatus,
  type TaskRead,
  type TaskStatus,
} from '@/features/projects/types'
import { apiRequest } from '@/lib/api'

const route = useRoute()
const projectId = computed(() => String(route.params.id))
const project = ref<ProjectRead | null>(null)
const plan = ref<ProjectExecutionPlan | null>(null)
const tasks = ref<TaskRead[]>([])
const episodes = ref<EpisodeRead[]>([])
const selectedEpisodeId = ref('')
const shotBoundary = ref<EpisodeShotBoundaryRead | null>(null)
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

const statusText: Record<PlanStepStatus, string> = {
  COMPLETED: '已完成',
  READY: '可开始',
  BLOCKED_DEPENDENCY: '等待上一步',
  WAITING_CAPABILITY: '等待能力接入',
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
  NOT_BUILT: '尚未处理',
  CURRENT: '当前有效',
  STALE: '原片已变化，需要重新处理',
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
    return
  }
  loadingShots.value = true
  shotErrorMessage.value = ''
  try {
    shotBoundary.value = await getEpisodeShotBoundary(projectId.value, selectedEpisodeId.value)
  } catch (error) {
    shotErrorMessage.value = error instanceof Error ? error.message : '镜头结果读取失败'
  } finally {
    loadingShots.value = false
  }
}

async function changeEpisode(): Promise<void> {
  shotBoundary.value = null
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
    shotErrorMessage.value = error instanceof Error ? error.message : '镜头处理启动失败'
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

onMounted(loadWorkspace)
onBeforeUnmount(stopTaskPolling)
</script>

<template>
  <section class="workspace">
    <RouterLink to="/" class="back-link">← 返回项目</RouterLink>

    <p v-if="loading" class="muted">正在加载项目…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>

    <template v-else-if="project">
      <header class="workspace-header">
        <div>
          <span class="project-type">{{ projectTypeLabel(project.project_type) }}</span>
          <h1>{{ project.name }}</h1>
          <p>{{ project.target_language }} · {{ project.target_region }}</p>
        </div>
        <div v-if="plan" class="skill-card">
          <small>当前根技能</small>
          <strong>{{ plan.skill_title }}</strong>
          <span>{{ plan.skill_id }}</span>
        </div>
        <div v-else class="skill-card">
          <small>执行计划</small>
          <strong>尚未生成</strong>
          <span>可以先上传并处理原片</span>
        </div>
      </header>

      <section v-if="isVideoProject" class="shot-section">
        <div class="section-heading">
          <div>
            <p class="eyebrow">视频技术预处理</p>
            <h2>镜头边界</h2>
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
        <p class="section-note">先上传真实 Episode，再选择某一集显式开始处理。这里只识别切镜时间，并生成缩略图和可播放参考片段；不做人物、剧情或对白理解。</p>
        <p v-if="shotErrorMessage" class="error-message">{{ shotErrorMessage }}</p>
        <p v-if="loadingEpisodes && !episodes.length" class="muted">正在读取已上传原片…</p>

        <div v-if="episodes.length" class="episode-controls">
          <label>
            <span>选择剧集</span>
            <select v-model="selectedEpisodeId" @change="changeEpisode">
              <option v-for="episode in episodes" :key="episode.id" :value="episode.id">
                第 {{ episode.episode_order }} 集 · {{ episode.source_asset.original_filename }}
              </option>
            </select>
          </label>
          <button class="primary-button" type="button" :disabled="startingShots || !selectedEpisodeId" @click="startShotBoundary">
            {{ startingShots ? '正在提交…' : shotBoundary?.status === 'CURRENT' ? '重新处理这一集' : '开始处理这一集' }}
          </button>
        </div>
        <div v-else-if="!loadingEpisodes" class="shot-empty">
          <strong>还没有原片</strong>
          <span>先点击“上传原片”选择一集或多集短剧视频。上传完成后剧集列表会自动出现，不需要再点“读取”。</span>
        </div>

        <p v-if="loadingShots" class="muted">正在读取镜头结果…</p>
        <template v-else-if="shotBoundary">
          <div class="shot-result-heading">
            <div>
              <strong>第 {{ shotBoundary.episode_order }} 集 · {{ shotBoundary.source_filename }}</strong>
              <span class="result-status" :class="shotBoundary.status.toLowerCase()">
                {{ shotStatusText[shotBoundary.status] }}
              </span>
            </div>
            <span>{{ shotBoundary.shot_count }} 个镜头</span>
          </div>
          <p v-if="shotBoundary.status === 'STALE'" class="stale-note">
            原片已经变化，下面保留的是旧结果供核对；请重新处理这一集后再作为正式结果使用。
          </p>
          <div v-if="shotBoundary.shots.length" class="shot-grid">
            <article v-for="shot in shotBoundary.shots" :key="shot.id" class="shot-card">
              <img :src="shot.thumbnail_url" :alt="`镜头 ${shot.shot_number} 缩略图`" loading="lazy" />
              <div class="shot-card-body">
                <div class="shot-title-row">
                  <strong>镜头 {{ String(shot.shot_number).padStart(3, '0') }}</strong>
                  <span>{{ (shot.duration_us / 1_000_000).toFixed(3) }}s</span>
                </div>
                <p>{{ formatTime(shot.start_us) }} → {{ formatTime(shot.end_us) }}</p>
                <video :src="shot.reference_clip_url" controls preload="metadata"></video>
              </div>
            </article>
          </div>
          <div v-else class="shot-empty">
            <strong>还没有镜头结果</strong>
            <span>点击“开始处理这一集”后，任务会进入下方任务队列。</span>
          </div>
        </template>
      </section>

      <section class="task-section">
        <div class="section-heading">
          <div>
            <p class="eyebrow">任务状态</p>
            <h2>当前执行任务</h2>
          </div>
          <button class="secondary-button" type="button" :disabled="refreshingTasks" @click="refreshTasks">
            {{ refreshingTasks ? '刷新中…' : '刷新任务' }}
          </button>
        </div>

        <p v-if="taskErrorMessage" class="error-message">{{ taskErrorMessage }}</p>
        <div v-if="tasks.length" class="task-list">
          <article v-for="task in tasks" :key="task.id" class="task-card">
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
      </section>

      <section class="acceptance-section">
        <div class="section-heading">
          <div>
            <p class="eyebrow">开发验收工具</p>
            <h2>P4 任务执行机制</h2>
          </div>
        </div>
        <p class="acceptance-note">这里只运行本地模拟任务，不调用真实模型、不产生费用。用于人工检查排队、进度、失败重试、中断继续、取消和重复提交保护。</p>
        <div class="acceptance-actions">
          <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('success')">{{ p4Starting === 'success' ? '启动中…' : '测试正常完成' }}</button>
          <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('retry')">{{ p4Starting === 'retry' ? '启动中…' : '测试失败 → 重试' }}</button>
          <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('resume')">{{ p4Starting === 'resume' ? '启动中…' : '测试中断 → 继续' }}</button>
          <button type="button" :disabled="Boolean(p4Starting)" @click="verifyDuplicateProtection">{{ p4Starting === 'dedupe' ? '测试中…' : '测试防重复提交' }}</button>
        </div>
        <p v-if="p4AcceptanceMessage" class="success-message">{{ p4AcceptanceMessage }}</p>
      </section>

      <section v-if="plan" class="plan-section">
        <div class="section-heading">
          <div>
            <p class="eyebrow">执行计划</p>
            <h2>系统根据 Skill 和现有资产生成的正式计划</h2>
          </div>
          <span class="revision">版本 {{ plan.workflow_revision }}</span>
        </div>
        <div class="plan-list">
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
              <p v-if="step.status === 'BLOCKED_DEPENDENCY'" class="dependency-note">完成上游正式结果后会自动解锁，不会通过页面刷新偷偷启动任务。</p>
            </div>
          </article>
        </div>
      </section>
      <section v-else class="plan-section">
        <div class="plan-empty">
          <strong>当前还没有可显示的执行计划</strong>
          <span>{{ planErrorMessage || '原片上传、镜头处理和任务区仍然可以独立使用。' }}</span>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.workspace { display: grid; gap: 24px; }
.back-link { color: #5b4ee8; text-decoration: none; font-weight: 700; }
.workspace-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 24px; border: 1px solid #e7e7ef; border-radius: 20px; background: #fff; }
.workspace-header h1 { margin: 10px 0 6px; font-size: 32px; }
.workspace-header p { margin: 0; color: #667085; }
.project-type { display: inline-flex; padding: 5px 9px; border-radius: 999px; background: #f1f0ff; color: #5b4ee8; font-size: 12px; font-weight: 800; }
.skill-card { min-width: 230px; display: grid; gap: 5px; padding: 16px; border-radius: 14px; background: #f8f8fb; }
.skill-card small, .skill-card span, .muted { color: #667085; }
.shot-section { display: grid; gap: 16px; padding: 22px; border: 1px solid #d9e5ff; border-radius: 18px; background: #fbfdff; }
.section-note, .acceptance-note { margin: 0; color: #667085; line-height: 1.7; }
.source-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.upload-button { display: inline-flex; align-items: center; border: 0; border-radius: 10px; padding: 10px 14px; background: #5b4ee8; color: #fff; font-weight: 800; cursor: pointer; }
.upload-button:has(input:disabled) { cursor: wait; opacity: .55; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
.episode-controls { display: flex; align-items: end; gap: 12px; flex-wrap: wrap; }
.episode-controls label { display: grid; gap: 7px; min-width: 340px; font-weight: 700; }
.episode-controls select { min-height: 42px; padding: 0 12px; border: 1px solid #d0d5dd; border-radius: 10px; background: #fff; }
.primary-button, .secondary-button, .task-actions button, .acceptance-actions button { border-radius: 10px; padding: 10px 14px; font-weight: 800; cursor: pointer; }
.primary-button { border: 0; background: #5b4ee8; color: #fff; }
.secondary-button, .task-actions button, .acceptance-actions button { border: 1px solid #d0d5dd; background: #fff; }
button:disabled { cursor: wait; opacity: .55; }
.shot-result-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding-top: 4px; }
.shot-result-heading > div { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.result-status { padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 800; }
.result-status.current { color: #027a48; background: #ecfdf3; }
.result-status.stale { color: #b54708; background: #fffaeb; }
.result-status.not_built { color: #475467; background: #f2f4f7; }
.stale-note { margin: 0; padding: 11px 13px; border-radius: 10px; color: #b54708; background: #fffaeb; }
.shot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.shot-card { overflow: hidden; border: 1px solid #e4e7ec; border-radius: 14px; background: #fff; }
.shot-card img { display: block; width: 100%; aspect-ratio: 16 / 9; object-fit: cover; background: #101828; }
.shot-card-body { display: grid; gap: 9px; padding: 12px; }
.shot-title-row { display: flex; justify-content: space-between; gap: 12px; }
.shot-card-body p { margin: 0; color: #667085; font-variant-numeric: tabular-nums; }
.shot-card video { width: 100%; border-radius: 9px; background: #000; }
.shot-empty, .plan-empty { display: grid; gap: 4px; padding: 18px; border-radius: 12px; background: #f8fafc; color: #667085; }
.shot-empty strong, .plan-empty strong { color: #344054; }
.acceptance-section { display: grid; gap: 14px; padding: 20px; border: 1px solid #ddd9ff; border-radius: 16px; background: #faf9ff; }
.acceptance-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.success-message { margin: 0; color: #027a48; font-weight: 700; }
.task-section, .plan-section { display: grid; gap: 16px; }
.section-heading { display: flex; justify-content: space-between; align-items: end; gap: 16px; }
.section-heading h2 { margin: 3px 0 0; font-size: 22px; }
.eyebrow { margin: 0; color: #6d5dfc; font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.task-list { display: grid; gap: 12px; }
.task-card { display: grid; gap: 10px; padding: 16px; border: 1px solid #e4e7ec; border-radius: 14px; background: #fff; }
.task-heading, .step-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.task-heading h3, .step-heading h3 { margin: 0 0 5px; }
.task-status, .status { display: inline-flex; padding: 4px 8px; border-radius: 999px; background: #f2f4f7; color: #475467; font-size: 12px; font-weight: 800; }
.task-running, .ready { color: #175cd3; background: #eff8ff; }
.task-succeeded, .completed { color: #027a48; background: #ecfdf3; }
.task-failed { color: #b42318; background: #fef3f2; }
.task-cancelled, .task-interrupted, .waiting_capability, .blocked_dependency { color: #b54708; background: #fffaeb; }
.progress-track { height: 8px; overflow: hidden; border-radius: 999px; background: #eaecf0; }
.progress-value { height: 100%; background: #6d5dfc; transition: width .2s ease; }
.task-error, .error-message { margin: 0; color: #b42318; }
.task-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.task-empty { margin: 0; }
.plan-list { display: grid; gap: 12px; }
.plan-step { display: grid; grid-template-columns: 44px 1fr; gap: 14px; padding: 16px; border: 1px solid #e4e7ec; border-radius: 14px; background: #fff; }
.step-number { display: grid; place-items: center; width: 40px; height: 40px; border-radius: 12px; background: #f2f4f7; font-weight: 800; }
.step-content p { margin: 8px 0 0; color: #667085; }
.phase { color: #7f56d9; font-size: 12px; font-weight: 800; }
.revision { color: #667085; font-weight: 700; }
.dependency-note { font-size: 13px; }
@media (max-width: 760px) {
  .workspace-header, .section-heading, .shot-result-heading { align-items: stretch; flex-direction: column; }
  .skill-card, .episode-controls label { min-width: 0; width: 100%; }
  .source-actions, .episode-controls { align-items: stretch; }
  .source-actions > *, .upload-button { width: 100%; justify-content: center; }
  .shot-grid { grid-template-columns: 1fr; }
}
</style>
