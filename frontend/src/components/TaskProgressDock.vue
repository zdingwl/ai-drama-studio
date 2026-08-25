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
  <div v-if="projectId && currentTask" class="task-dock" :class="{ expanded }">
    <button class="task-dock-summary" @click="expanded = !expanded">
      <span :class="['task-state-dot', currentTask.status.toLowerCase()]" />
      <span class="task-dock-copy">
        <strong>{{ currentTask.title }}</strong>
        <small>{{ currentTask.stage_label || statusLabel(currentTask) }}<template v-if="currentTask.current_item"> · {{ currentTask.current_item }}</template></small>
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
        <article v-for="task in recentTasks" :key="task.id" class="task-panel-item">
          <div class="task-item-head">
            <span :class="['task-state-dot', task.status.toLowerCase()]" />
            <div><strong>{{ task.title }}</strong><small>{{ task.stage_label || statusLabel(task) }}</small></div>
            <b>{{ percentLabel(task) }}</b>
          </div>
          <div v-if="task.progress_mode === 'determinate' && task.progress_percent !== null" class="task-mini-track"><span :style="{ width: `${task.progress_percent}%` }" /></div>
          <div v-else-if="task.status === 'PROCESSING' || task.status === 'QUEUED'" class="task-mini-track indeterminate"><span /></div>
          <p>{{ task.message || statusLabel(task) }}</p>
          <small v-if="task.current_index && task.total_items">{{ task.current_index }} / {{ task.total_items }} 项</small>
          <small v-if="task.error_message" class="task-error-detail">{{ task.error_message }}</small>
        </article>
      </div>
    </div>
  </div>
</template>
