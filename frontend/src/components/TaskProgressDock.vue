<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import type { BackgroundTask } from '../types/studio'

const props = withDefaults(defineProps<{
  embedded?: boolean
}>(), {
  embedded: false,
})

const route = useRoute()
const tasks = ref<BackgroundTask[]>([])
const expanded = ref(false)
const error = ref('')
const dismissedTaskIds = ref<string[]>([])
let timer: number | null = null
let refreshing = false
let disposed = false

const projectId = computed(() => String(route.params.projectId || ''))
const activeTasks = computed(() => tasks.value.filter((item) => item.status === 'QUEUED' || item.status === 'PROCESSING'))
const currentTask = computed(() => activeTasks.value[0] ?? null)
const attentionTask = computed(() => tasks.value.find((item) => (
  (item.status === 'FAILED' || item.status === 'READY_WITH_WARNINGS')
  && !dismissedTaskIds.value.includes(item.id)
)) ?? null)
const displayTask = computed(() => currentTask.value ?? attentionTask.value)
const recentTasks = computed(() => tasks.value.slice(0, 8))

const STALL_WARNING_MS = 120_000
const ACTIVE_POLL_MS = 1_000
const IDLE_POLL_MS = 10_000
const HIDDEN_POLL_MS = 30_000
const DISMISSED_STORAGE_PREFIX = 'ai-drama-studio:task-dock-dismissed:v1:'
const MAX_DISMISSED_TASK_IDS = 100

function dismissedStorageKey(targetProjectId: string): string {
  return `${DISMISSED_STORAGE_PREFIX}${encodeURIComponent(targetProjectId)}`
}

function loadDismissedTaskIds(targetProjectId: string): string[] {
  if (!targetProjectId) return []
  try {
    const raw = window.localStorage.getItem(dismissedStorageKey(targetProjectId))
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return Array.from(new Set(
      parsed.filter((item): item is string => typeof item === 'string' && item.trim().length > 0),
    )).slice(-MAX_DISMISSED_TASK_IDS)
  } catch {
    return []
  }
}

function persistDismissedTaskIds(targetProjectId: string, taskIds: string[]): void {
  if (!targetProjectId) return
  try {
    const normalized = Array.from(new Set(taskIds)).slice(-MAX_DISMISSED_TASK_IDS)
    const key = dismissedStorageKey(targetProjectId)
    if (normalized.length) window.localStorage.setItem(key, JSON.stringify(normalized))
    else window.localStorage.removeItem(key)
  } catch {
    // localStorage 不可用时只影响“已读提示”持久化，不影响任务本身。
  }
}

function replaceDismissedTaskIds(taskIds: string[]): void {
  dismissedTaskIds.value = Array.from(new Set(taskIds)).slice(-MAX_DISMISSED_TASK_IDS)
  persistDismissedTaskIds(projectId.value, dismissedTaskIds.value)
}

function isFinished(task: BackgroundTask): boolean {
  return ['READY', 'READY_WITH_WARNINGS', 'FAILED', 'CANCELLED'].includes(task.status)
}

function statusLabel(task: BackgroundTask): string {
  const labels: Record<string, string> = {
    QUEUED: '等待开始',
    PROCESSING: '处理中',
    READY: '已完成',
    READY_WITH_WARNINGS: '已完成 · 需要检查',
    FAILED: '没有完成',
    CANCELLED: '已取消',
  }
  return labels[task.status] || task.status
}

function percentLabel(task: BackgroundTask): string {
  if (task.status === 'FAILED') return '未完成'
  if (task.status === 'READY_WITH_WARNINGS') return '需检查'
  if (task.status === 'CANCELLED') return '已取消'
  if (task.status === 'READY') return '100%'
  if (task.progress_mode === 'indeterminate' || task.progress_percent === null) return '处理中'
  return `${Math.round(task.progress_percent)}%`
}

function isStalled(task: BackgroundTask): boolean {
  if (task.status !== 'PROCESSING') return false
  const updated = Date.parse(task.updated_at)
  return Number.isFinite(updated) && Date.now() - updated >= STALL_WARNING_MS
}

function stallLabel(task: BackgroundTask): string {
  const updated = Date.parse(task.updated_at)
  if (!Number.isFinite(updated)) return '长时间没有新的进度'
  const minutes = Math.max(2, Math.floor((Date.now() - updated) / 60_000))
  return `${minutes} 分钟没有新的进度`
}

function itemProgressLabel(task: BackgroundTask): string {
  if (task.current_index !== null && task.total_items !== null && task.total_items > 0) {
    return `${task.current_index} / ${task.total_items}`
  }
  return ''
}

function summaryText(task: BackgroundTask): string {
  if (isStalled(task)) return `${stallLabel(task)}，建议检查本地处理是否仍在运行`
  if (task.status === 'FAILED') return '任务没有完成，展开后可查看处理建议'
  if (task.status === 'READY_WITH_WARNINGS') return '任务已经完成，但有部分内容需要检查'
  if (task.status === 'CANCELLED') return '任务已取消'

  const parts = [task.stage_label || statusLabel(task)]
  if (task.current_item) parts.push(task.current_item)
  if (itemProgressLabel(task)) parts.push(itemProgressLabel(task))
  return parts.join(' · ')
}

function userTaskMessage(task: BackgroundTask): string {
  if (isStalled(task)) return '这个任务长时间没有更新。如果本地处理已经停止，可以回到对应阶段重新执行。'
  if (task.status === 'FAILED') return '这次任务没有完成。先回到对应阶段重新执行；如果重复失败，再展开“技术详情”查看原始错误。'
  if (task.status === 'READY_WITH_WARNINGS') return '主要结果已经生成，但有部分内容需要人工检查。进入对应阶段查看待处理项即可。'
  if (task.status === 'READY') return '任务已完成，正式结果已经可以在对应阶段查看。'
  if (task.status === 'CANCELLED') return '任务已取消，没有继续处理。'
  return task.message || summaryText(task)
}

function dismissAttentionTasks(): void {
  const ids = tasks.value
    .filter((task) => task.status === 'FAILED' || task.status === 'READY_WITH_WARNINGS')
    .map((task) => task.id)
  if (ids.length) replaceDismissedTaskIds([...dismissedTaskIds.value, ...ids])
  expanded.value = false
}

async function refresh(): Promise<void> {
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
        if (task.status === 'FAILED' || task.status === 'READY_WITH_WARNINGS') expanded.value = true
        window.dispatchEvent(new CustomEvent('studio-task-finished', { detail: task }))
      }
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '任务状态读取失败'
  }
}

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

function restartPolling(): void {
  clearTimer()
  tasks.value = []
  dismissedTaskIds.value = loadDismissedTaskIds(projectId.value)
  expanded.value = false
  if (!projectId.value) return
  schedulePoll(true)
}

function onTaskCreated(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  if (dismissedTaskIds.value.includes(task.id)) {
    replaceDismissedTaskIds(dismissedTaskIds.value.filter((id) => id !== task.id))
  }
  tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)]
  error.value = ''
  expanded.value = false
  schedulePoll(false)
}

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
  <div
    v-if="projectId && (displayTask || props.embedded)"
    class="task-dock"
    :class="{
      embedded: props.embedded,
      expanded,
      stalled: displayTask ? isStalled(displayTask) : false,
      failed: displayTask?.status === 'FAILED',
      warning: displayTask?.status === 'READY_WITH_WARNINGS',
    }"
  >
    <div v-if="displayTask" class="task-dock-summary-row">
      <button class="task-dock-summary" type="button" @click="expanded = !expanded">
        <span :class="['task-state-dot', displayTask.status.toLowerCase()]" />
        <span class="task-dock-copy">
          <strong>{{ displayTask.title }}</strong>
          <small :class="{ 'task-stall-copy': isStalled(displayTask), 'task-failed-copy': displayTask.status === 'FAILED' }">
            {{ summaryText(displayTask) }}
          </small>
        </span>
        <span class="task-dock-percent">{{ percentLabel(displayTask) }}</span>
        <span v-if="currentTask" class="task-dock-count">进行中 {{ activeTasks.length }}</span>
        <span v-else class="task-dock-count">查看详情</span>
      </button>
      <button
        v-if="!currentTask && attentionTask"
        class="task-dock-dismiss"
        type="button"
        title="关闭当前已读提示；未来新任务仍会正常显示"
        aria-label="关闭当前任务提示"
        @click="dismissAttentionTasks"
      >×</button>
    </div>

    <div v-else class="task-dock-summary-row">
      <button class="task-dock-summary" type="button" @click="expanded = !expanded">
        <span class="task-state-dot idle" />
        <span class="task-dock-copy">
          <strong>后台任务</strong>
          <small>{{ recentTasks.length ? '当前空闲 · 可查看最近任务' : '当前没有后台任务' }}</small>
        </span>
        <span class="task-dock-percent">—</span>
        <span class="task-dock-count">{{ recentTasks.length ? `最近 ${recentTasks.length}` : '空闲' }}</span>
      </button>
    </div>

    <div
      v-if="displayTask && (displayTask.status === 'PROCESSING' || displayTask.status === 'QUEUED')"
      class="task-progress-track"
      :class="{ indeterminate: displayTask.progress_mode === 'indeterminate' || displayTask.progress_percent === null }"
    >
      <span v-if="displayTask.progress_mode === 'determinate' && displayTask.progress_percent !== null" :style="{ width: `${displayTask.progress_percent}%` }" />
      <span v-else />
    </div>

    <div v-if="expanded" class="task-dock-panel">
      <div class="task-panel-head">
        <div><strong>后台任务</strong><small>{{ activeTasks.length ? `${activeTasks.length} 个正在处理` : '当前空闲' }}</small></div>
        <span>页面切换或刷新不会丢失</span>
      </div>

      <p v-if="error" class="task-panel-error">任务列表暂时无法更新：{{ error }}</p>

      <div v-if="recentTasks.length" class="task-panel-list">
        <article
          v-for="task in recentTasks"
          :key="task.id"
          class="task-panel-item"
          :class="{
            'task-item-stalled': isStalled(task),
            'task-item-failed': task.status === 'FAILED',
            'task-item-warning': task.status === 'READY_WITH_WARNINGS',
          }"
        >
          <div class="task-item-head">
            <span :class="['task-state-dot', task.status.toLowerCase()]" />
            <div>
              <strong>{{ task.title }}</strong>
              <small>{{ statusLabel(task) }}<template v-if="itemProgressLabel(task)"> · {{ itemProgressLabel(task) }}</template></small>
            </div>
            <b>{{ percentLabel(task) }}</b>
          </div>

          <div
            v-if="task.progress_mode === 'determinate' && task.progress_percent !== null && (task.status === 'PROCESSING' || task.status === 'QUEUED')"
            class="task-mini-track"
          ><span :style="{ width: `${task.progress_percent}%` }" /></div>
          <div v-else-if="task.status === 'PROCESSING' || task.status === 'QUEUED'" class="task-mini-track indeterminate"><span /></div>

          <p class="task-user-message">{{ userTaskMessage(task) }}</p>
          <small v-if="task.current_item && (task.status === 'QUEUED' || task.status === 'PROCESSING')" class="task-current-item">当前：{{ task.current_item }}</small>

          <details v-if="task.error_message" class="task-technical-details">
            <summary>技术详情</summary>
            <pre>{{ task.error_message }}</pre>
          </details>
        </article>
      </div>
      <div v-else class="task-panel-empty">还没有后台任务记录。</div>
    </div>
  </div>
</template>

<style scoped>
.task-dock-summary-row { display: flex; align-items: stretch; }
.task-dock-summary-row > .task-dock-summary { flex: 1; min-width: 0; }
.task-dock-dismiss {
  width: 38px;
  border: 0;
  border-left: 1px solid #e4e8ef;
  background: #fff;
  color: #7f8a9a;
  font-size: 20px;
  cursor: pointer;
}
.task-dock-dismiss:hover { background: #f7f9fc; color: #4b5870; }
.task-dock.failed { border-color: #e4aaaa; }
.task-dock.failed .task-dock-summary-row { background: #fff7f7; }
.task-dock.warning .task-dock-summary-row { background: #fffaf0; }
.task-dock.stalled .task-progress-track,
.task-item-stalled .task-mini-track { opacity: .65; }
.task-stall-copy { color: #9a6400 !important; font-weight: 700; }
.task-failed-copy { color: #b33b3b !important; font-weight: 700; }
.task-item-stalled { border-color: #ead59d; background: #fffaf0; }
.task-item-failed { border-color: #efcaca; background: #fff8f8; }
.task-item-warning { border-color: #eadcae; background: #fffdf6; }
.task-state-dot.idle { background: #7fb493; box-shadow: 0 0 0 3px #edf7f1; }
.task-panel-head > div { display: grid; gap: 1px; }
.task-panel-head > div small { color: #8994a4; font-size: 10px; }
.task-user-message { margin: 7px 0 0 !important; color: #59687d !important; line-height: 1.55; }
.task-current-item { display: block; margin-top: 4px; color: #7c899b !important; }
.task-technical-details {
  margin-top: 8px;
  border-top: 1px solid #e8ecf2;
  padding-top: 7px;
}
.task-technical-details > summary {
  width: fit-content;
  color: #7b8798;
  font-size: 10px;
  font-weight: 750;
  cursor: pointer;
}
.task-technical-details pre {
  display: block;
  margin: 7px 0 0;
  max-height: 220px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  border: 1px solid #efcaca;
  border-radius: 7px;
  padding: 8px 10px;
  background: #fff;
  color: #a92828;
  font: 11px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace;
}
.task-panel-error { border-radius: 7px; padding: 7px 9px; background: #fff5f5; }
.task-panel-empty { padding: 18px 8px; color: #8490a2; text-align: center; font-size: 11px; }
</style>
