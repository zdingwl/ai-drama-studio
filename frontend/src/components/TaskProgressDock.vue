<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import type { BackgroundTask } from '../types/studio'

const route = useRoute()
const tasks = ref<BackgroundTask[]>([])
const expanded = ref(false)
const error = ref('')
let timer: number | null = null
let refreshing = false
let disposed = false

const projectId = computed(() => String(route.params.projectId || ''))
const activeTasks = computed(() => tasks.value.filter((item) => item.status === 'QUEUED' || item.status === 'PROCESSING'))
const currentTask = computed(() => activeTasks.value[0] ?? null)
const recentTasks = computed(() => tasks.value.slice(0, 8))

const STALL_WARNING_MS = 120_000
const ACTIVE_POLL_MS = 1_000
const IDLE_POLL_MS = 10_000
const HIDDEN_POLL_MS = 30_000

function isFinished(task: BackgroundTask) {
  return ['READY', 'READY_WITH_WARNINGS', 'FAILED', 'CANCELLED'].includes(task.status)
}

function statusLabel(task: BackgroundTask) {
  const labels: Record<string, string> = {
    QUEUED: '等待中', PROCESSING: '处理中', READY: '已完成', READY_WITH_WARNINGS: '完成但有失败项', FAILED: '失败', CANCELLED: '已取消',
  }
  return labels[task.status] || task.status
}

function percentLabel(task: BackgroundTask) {
  if (task.progress_mode === 'indeterminate' || task.progress_percent === null) return '处理中'
  return `${Math.round(task.progress_percent)}%`
}

/**
 * 职责：识别“数据库仍写 PROCESSING，但后台长时间没有任何心跳”的任务。
 * 输入：BackgroundTask.updated_at；输出：是否需要警告。
 * 为什么：长模型任务不能无限显示“处理中”而不给用户判断它是否卡住的依据。
 */
function isStalled(task: BackgroundTask): boolean {
  if (task.status !== 'PROCESSING') return false
  const updated = Date.parse(task.updated_at)
  return Number.isFinite(updated) && Date.now() - updated >= STALL_WARNING_MS
}

function stallLabel(task: BackgroundTask): string {
  const updated = Date.parse(task.updated_at)
  if (!Number.isFinite(updated)) return '长时间无进度更新'
  const minutes = Math.max(2, Math.floor((Date.now() - updated) / 60_000))
  return `${minutes} 分钟无进度更新，可能卡住`
}

function itemProgressLabel(task: BackgroundTask): string {
  if (task.current_index !== null && task.total_items !== null && task.total_items > 0) {
    return `${task.current_index} / ${task.total_items}`
  }
  return ''
}

/**
 * 职责：读取当前 Project 的后台任务，并检测任务是否刚刚结束。
 * 输入：当前 projectId；输出：更新 tasks / error，并在任务结束时派发 studio-task-finished。
 * 为什么：业务页面需要在后台任务完成后刷新 Shot / Asset 等正式结果。
 */
async function refresh() {
  if (!projectId.value) {
    tasks.value = []
    return
  }
  try {
    const before = new Map(tasks.value.map((item) => [item.id, item.status]))
    tasks.value = await api.listProjectTasks(projectId.value, 30)
    error.value = ''
    for (const task of tasks.value) {
      const oldStatus = before.get(task.id)
      if (oldStatus && oldStatus !== task.status && isFinished(task)) {
        window.dispatchEvent(new CustomEvent('studio-task-finished', { detail: task }))
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '任务状态读取失败'
  }
}

/**
 * 职责：根据当前状态决定下一次任务查询时间。
 * 输入：页面可见性 + 是否存在 QUEUED/PROCESSING Task；输出：下一次轮询延迟。
 * 为什么：运行中的任务需要 1 秒级进度，无任务时没必要持续刷 SQLite 和后端日志。
 */
function nextPollDelay(): number {
  if (document.hidden) return HIDDEN_POLL_MS
  return activeTasks.value.length > 0 ? ACTIVE_POLL_MS : IDLE_POLL_MS
}

function clearTimer(): void {
  if (timer !== null) {
    window.clearTimeout(timer)
    timer = null
  }
}

/**
 * 职责：安排一次“请求完成后再计时”的自适应轮询。
 * 输入：可选立即执行标记；输出：无。
 * 为什么：setInterval 可能在接口变慢时产生重叠请求；setTimeout 串行调度不会堆积 Fetch。
 */
function schedulePoll(immediate = false): void {
  clearTimer()
  if (disposed || !projectId.value) return
  timer = window.setTimeout(() => void pollOnce(), immediate ? 0 : nextPollDelay())
}

async function pollOnce(): Promise<void> {
  if (disposed || !projectId.value || refreshing) return
  refreshing = true
  try {
    await refresh()
  } finally {
    refreshing = false
    schedulePoll(false)
  }
}

/**
 * 职责：Project 切换时停止旧 Project 轮询并立即读取新 Project 状态。
 * 输入：route.params.projectId；输出：重置 Task 并重新调度。
 */
function restartPolling(): void {
  clearTimer()
  tasks.value = []
  if (!projectId.value) return
  schedulePoll(true)
}

/**
 * 职责：业务工作区创建 BackgroundTask 后立即把它放进 Dock。
 * 输入：studio-task-created 的 BackgroundTask；输出：立即显示任务，并切换到活动任务 1 秒轮询。
 * 为什么：无任务时 Dock 只做 10 秒低频查询；如果创建任务后仍等下一次轮询，用户会误以为按钮没有反应。
 */
function onTaskCreated(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)]
  error.value = ''
  // 当前 task 已经进入本地列表，因此 nextPollDelay() 会自动使用 1 秒活动频率。
  schedulePoll(false)
}

/**
 * 职责：标签页重新可见时立即刷新；退到后台后自动进入 30 秒低频轮询。
 * 为什么：用户切回来时应马上看到真实进度，同时后台标签不需要每秒发请求。
 */
function onVisibilityChange(): void {
  schedulePoll(!document.hidden)
}

watch(projectId, restartPolling)
onMounted(() => {
  disposed = false
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('studio-task-created', onTaskCreated)
  restartPolling()
})
onUnmounted(() => {
  disposed = true
  clearTimer()
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('studio-task-created', onTaskCreated)
})
</script>

<template>
  <div v-if="projectId && currentTask" class="task-dock" :class="{ expanded, stalled: isStalled(currentTask) }">
    <button class="task-dock-summary" @click="expanded = !expanded">
      <span :class="['task-state-dot', currentTask.status.toLowerCase()]" />
      <span class="task-dock-copy">
        <strong>{{ currentTask.title }}</strong>
        <small v-if="isStalled(currentTask)" class="task-stall-copy">⚠ {{ stallLabel(currentTask) }}</small>
        <small v-else>
          {{ currentTask.stage_label || statusLabel(currentTask) }}
          <template v-if="currentTask.current_item"> · {{ currentTask.current_item }}</template>
          <template v-if="itemProgressLabel(currentTask)"> · {{ itemProgressLabel(currentTask) }}</template>
        </small>
      </span>
      <span class="task-dock-percent">{{ percentLabel(currentTask) }}</span>
      <span class="task-dock-count">进行中 {{ activeTasks.length }}</span>
    </button>

    <div class="task-progress-track" :class="{ indeterminate: currentTask.progress_mode === 'indeterminate' || currentTask.progress_percent === null }">
      <span v-if="currentTask.progress_mode === 'determinate' && currentTask.progress_percent !== null" :style="{ width: `${currentTask.progress_percent}%` }" />
      <span v-else />
    </div>

    <div v-if="expanded" class="task-dock-panel">
      <div class="task-panel-head"><strong>后台任务</strong><span>页面切换或刷新不会丢失</span></div>
      <p v-if="error" class="task-panel-error">{{ error }}</p>
      <div class="task-panel-list">
        <article v-for="task in recentTasks" :key="task.id" class="task-panel-item" :class="{ 'task-item-stalled': isStalled(task) }">
          <div class="task-item-head">
            <span :class="['task-state-dot', task.status.toLowerCase()]" />
            <div><strong>{{ task.title }}</strong><small>{{ task.stage_label || statusLabel(task) }}<template v-if="task.current_item"> · {{ task.current_item }}</template></small></div>
            <b>{{ percentLabel(task) }}</b>
          </div>
          <div v-if="task.progress_mode === 'determinate' && task.progress_percent !== null" class="task-mini-track"><span :style="{ width: `${task.progress_percent}%` }" /></div>
          <div v-else-if="task.status === 'PROCESSING' || task.status === 'QUEUED'" class="task-mini-track indeterminate"><span /></div>
          <p>{{ task.message || statusLabel(task) }}</p>
          <small v-if="itemProgressLabel(task)">{{ itemProgressLabel(task) }} 项</small>
          <small v-if="isStalled(task)" class="task-stall-detail">⚠ {{ stallLabel(task) }}。如果后端进程仍在运行，请查看控制台；重启后该旧任务会被标记为中断，可重新执行。</small>
          <small v-if="task.error_message" class="task-error-detail">{{ task.error_message }}</small>
        </article>
      </div>
    </div>
  </div>
</template>

<style scoped>
.task-dock.stalled .task-progress-track,
.task-item-stalled .task-mini-track { opacity: .65; }
.task-stall-copy { color: #a35c00 !important; font-weight: 700; }
.task-stall-detail { display: block; margin-top: 5px; color: #9a6400; line-height: 1.45; }
.task-item-stalled { background: #fffaf0; }
</style>
