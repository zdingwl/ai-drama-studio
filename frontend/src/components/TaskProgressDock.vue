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

const projectId = computed(() => String(route.params.projectId || ''))
const activeTasks = computed(() => tasks.value.filter((item) => item.status === 'QUEUED' || item.status === 'PROCESSING'))
const currentTask = computed(() => activeTasks.value[0] ?? null)
const recentTasks = computed(() => tasks.value.slice(0, 8))

const STALL_WARNING_MS = 120_000

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

function restartTimer() {
  if (timer !== null) window.clearInterval(timer)
  if (!projectId.value) return
  void refresh()
  timer = window.setInterval(() => void refresh(), 1000)
}

watch(projectId, restartTimer)
onMounted(restartTimer)
onUnmounted(() => {
  if (timer !== null) window.clearInterval(timer)
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
