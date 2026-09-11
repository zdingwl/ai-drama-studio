<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getProject, listProjectTasks } from '@/features/projects/api'
import { getReplicaTargetBible, type ReplicaTargetBibleRead } from '@/features/projects/targetBible'
import {
  getReplicaTargetScript,
  startReplicaTargetScript,
  type ReplicaTargetScriptRead,
} from '@/features/projects/targetScript'
import type { ProjectRead, TaskRead } from '@/features/projects/types'

const route = useRoute()
const project = ref<ProjectRead | null>(null)
const targetBible = ref<ReplicaTargetBibleRead | null>(null)
const result = ref<ReplicaTargetScriptRead | null>(null)
const activeTask = ref<TaskRead | null>(null)
const loading = ref(false)
const starting = ref(false)
const errorMessage = ref('')
let pollTimer: number | null = null

const projectId = computed(() => String(route.params.id || ''))
const visible = computed(() => project.value?.project_type === 'REPLICA')
const p11Ready = computed(() => targetBible.value?.status === 'CURRENT')
const statusText = computed(() => {
  if (activeTask.value && ['queued', 'running', 'interrupted'].includes(activeTask.value.status)) {
    return `正在生成目标剧本 ${activeTask.value.progress_percent}%`
  }
  if (!p11Ready.value) return '等待当前有效的目标设定'
  if (!result.value || result.value.status === 'NOT_BUILT') return '可以生成目标剧本'
  if (result.value.status === 'STALE') return '目标设定已有更新，需要重新生成目标剧本'
  return '目标剧本已就绪'
})
const actionLabel = computed(() => result.value?.status === 'STALE' ? '重新生成目标剧本' : '生成目标剧本')
const showAction = computed(() => {
  if (!p11Ready.value || starting.value) return false
  if (activeTask.value && ['queued', 'running'].includes(activeTask.value.status)) return false
  return !result.value || result.value.status !== 'CURRENT'
})
const script = computed(() => result.value?.content ?? null)

function clearPoll() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshResult() {
  if (!projectId.value || !visible.value) return
  result.value = await getReplicaTargetScript(projectId.value)
}

async function pollTask() {
  if (!activeTask.value || !projectId.value) return
  const tasks = await listProjectTasks(projectId.value)
  const current = tasks.find((item) => item.id === activeTask.value?.id)
  if (!current) return
  activeTask.value = current
  if (current.status === 'succeeded') {
    clearPoll()
    await refreshResult()
  } else if (current.status === 'failed' || current.status === 'cancelled') {
    clearPoll()
    errorMessage.value = current.last_error || '目标剧本生成失败，请重试。'
    await refreshResult()
  }
}

function beginPoll() {
  clearPoll()
  pollTimer = window.setInterval(() => {
    void pollTask()
  }, 1500)
}

async function load() {
  clearPoll()
  targetBible.value = null
  result.value = null
  activeTask.value = null
  errorMessage.value = ''
  if (!projectId.value) return
  loading.value = true
  try {
    project.value = await getProject(projectId.value)
    if (project.value.project_type === 'REPLICA') {
      const [bible, targetScript] = await Promise.all([
        getReplicaTargetBible(projectId.value),
        getReplicaTargetScript(projectId.value),
      ])
      targetBible.value = bible
      result.value = targetScript
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标剧本加载失败。'
  } finally {
    loading.value = false
  }
}

async function start() {
  if (!projectId.value || !visible.value || !p11Ready.value) return
  starting.value = true
  errorMessage.value = ''
  try {
    const key = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `target-script-${Date.now()}`
    activeTask.value = await startReplicaTargetScript(projectId.value, key)
    if (activeTask.value.status === 'succeeded') {
      await refreshResult()
    } else if (activeTask.value.status === 'failed') {
      errorMessage.value = activeTask.value.last_error || '目标剧本生成失败，请重试。'
    } else {
      beginPoll()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标剧本生成失败。'
  } finally {
    starting.value = false
  }
}

watch(projectId, () => {
  void load()
}, { immediate: true })

onBeforeUnmount(clearPoll)
</script>

<template>
  <section v-if="visible" class="target-script-workspace">
    <div class="target-script-header">
      <div>
        <p class="eyebrow">目标版本</p>
        <h2>目标剧本</h2>
        <p class="target-script-subtitle">以已确认的目标设定和原片对白为基础，逐句形成直译、本土化表达和最终目标对白。</p>
      </div>
      <div class="target-script-actions">
        <span class="status-pill" :class="result?.status?.toLowerCase()">{{ statusText }}</span>
        <button v-if="showAction" type="button" class="primary-action" :disabled="loading || starting" @click="start">
          {{ starting ? '正在启动…' : actionLabel }}
        </button>
      </div>
    </div>

    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <p v-if="loading" class="empty-state">正在读取目标剧本…</p>

    <template v-else-if="script && result?.status === 'CURRENT'">
      <section v-for="episode in script.episodes" :key="episode.episode_id" class="episode-section">
        <h3>第 {{ episode.episode_order }} 集</h3>
        <article v-for="line in episode.dialogue" :key="line.utterance_id" class="dialogue-card">
          <div class="line-heading">
            <strong>对白 {{ line.utterance_number }}</strong>
            <span>{{ (line.source_start_us / 1000000).toFixed(2) }}s – {{ (line.source_end_us / 1000000).toFixed(2) }}s</span>
          </div>
          <div class="dialogue-grid">
            <div><small>原对白</small><p>{{ line.source_text }}</p></div>
            <div><small>直译</small><p>{{ line.translation_text }}</p></div>
            <div><small>本土化</small><p>{{ line.localization_text }}</p></div>
            <div><small>最终对白</small><p>{{ line.final_target_dialogue }}</p></div>
          </div>
          <ul v-if="line.localization_notes.length" class="notes">
            <li v-for="note in line.localization_notes" :key="note">{{ note }}</li>
          </ul>
        </article>
      </section>
    </template>

    <div v-else-if="!loading" class="empty-state">
      <p v-if="p11Ready">目标设定已就绪。需要时可以显式生成目标剧本；页面刷新不会自动启动生成。</p>
      <p v-else>请先完成并保持当前有效的目标设定，再生成目标剧本。</p>
    </div>
  </section>
</template>

<style scoped>
.target-script-workspace { margin: 28px auto 0; max-width: 1240px; padding: 24px; border: 1px solid var(--border-color, #e5e7eb); border-radius: 18px; background: var(--surface-color, #fff); }
.target-script-header { display: flex; gap: 24px; justify-content: space-between; align-items: flex-start; }
.eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; opacity: .55; }
h2, h3, p { margin-top: 0; }
.target-script-subtitle { max-width: 760px; opacity: .7; }
.target-script-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
.status-pill { padding: 6px 10px; border-radius: 999px; background: #f3f4f6; font-size: 13px; white-space: nowrap; }
.status-pill.current { background: #ecfdf5; }
.status-pill.stale { background: #fff7ed; }
.primary-action { border: 0; border-radius: 10px; padding: 10px 16px; font-weight: 700; cursor: pointer; background: #111827; color: #fff; }
.primary-action:disabled { cursor: default; opacity: .55; }
.error-message { margin-top: 16px; padding: 10px 12px; border-radius: 10px; background: #fef2f2; }
.empty-state { margin: 18px 0 0; padding: 22px; border-radius: 12px; background: #f9fafb; opacity: .72; }
.episode-section { margin-top: 22px; padding-top: 20px; border-top: 1px solid #eef0f3; }
.dialogue-card { margin-top: 12px; padding: 16px; border-radius: 12px; background: #f8fafc; }
.line-heading { display: flex; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.line-heading span, small { opacity: .6; }
.dialogue-grid { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.dialogue-grid > div { padding: 12px; border-radius: 10px; background: #fff; }
.dialogue-grid p { margin: 6px 0 0; }
.notes { margin: 10px 0 0; padding-left: 20px; }
@media (max-width: 720px) {
  .target-script-workspace { padding: 18px; }
  .target-script-header { flex-direction: column; }
  .target-script-actions { align-items: stretch; width: 100%; }
  .dialogue-grid { grid-template-columns: 1fr; }
}
</style>
