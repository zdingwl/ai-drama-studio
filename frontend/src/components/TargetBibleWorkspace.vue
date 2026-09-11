<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getProject, listProjectTasks } from '@/features/projects/api'
import {
  getReplicaTargetBible,
  startReplicaTargetBible,
  type ReplicaTargetBibleRead,
} from '@/features/projects/targetBible'
import type { ProjectRead, TaskRead } from '@/features/projects/types'

const route = useRoute()
const project = ref<ProjectRead | null>(null)
const result = ref<ReplicaTargetBibleRead | null>(null)
const activeTask = ref<TaskRead | null>(null)
const loading = ref(false)
const starting = ref(false)
const errorMessage = ref('')
let pollTimer: number | null = null

const projectId = computed(() => String(route.params.id || ''))
const visible = computed(() => project.value?.project_type === 'REPLICA')
const statusText = computed(() => {
  if (activeTask.value && ['queued', 'running', 'interrupted'].includes(activeTask.value.status)) {
    return `正在生成目标设定 ${activeTask.value.progress_percent}%`
  }
  if (!result.value || result.value.status === 'NOT_BUILT') return '尚未生成目标设定'
  if (result.value.status === 'STALE') return '原片或目标配置已有更新，需要重新生成目标设定'
  return '目标设定已就绪'
})
const actionLabel = computed(() => result.value?.status === 'STALE' ? '重新生成目标设定' : '生成目标设定')
const showAction = computed(() => {
  if (starting.value) return false
  if (activeTask.value && ['queued', 'running'].includes(activeTask.value.status)) return false
  return !result.value || result.value.status !== 'CURRENT'
})
const plan = computed(() => result.value?.adaptation_plan.content ?? null)
const bible = computed(() => result.value?.target_bible.content ?? null)

function clearPoll() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshResult() {
  if (!projectId.value || !visible.value) return
  result.value = await getReplicaTargetBible(projectId.value)
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
    errorMessage.value = current.last_error || '目标设定生成失败，请重试。'
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
  result.value = null
  activeTask.value = null
  errorMessage.value = ''
  if (!projectId.value) return
  loading.value = true
  try {
    project.value = await getProject(projectId.value)
    if (project.value.project_type === 'REPLICA') {
      await refreshResult()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标设定加载失败。'
  } finally {
    loading.value = false
  }
}

async function start() {
  if (!projectId.value || !visible.value) return
  starting.value = true
  errorMessage.value = ''
  try {
    const key = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `target-bible-${Date.now()}`
    activeTask.value = await startReplicaTargetBible(projectId.value, key)
    if (activeTask.value.status === 'succeeded') {
      await refreshResult()
    } else if (activeTask.value.status === 'failed') {
      errorMessage.value = activeTask.value.last_error || '目标设定生成失败，请重试。'
    } else {
      beginPoll()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标设定生成失败。'
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
  <section v-if="visible" class="target-bible-workspace">
    <div class="target-header">
      <div>
        <p class="eyebrow">目标版本</p>
        <h2>目标设定</h2>
        <p class="target-subtitle">保留原片故事与节奏，把人物、场景、道具和文化语境转换成 {{ project?.target_region }} / {{ project?.target_language }} 版本。</p>
      </div>
      <div class="target-actions">
        <span class="status-pill" :class="result?.status?.toLowerCase()">{{ statusText }}</span>
        <button v-if="showAction" type="button" class="primary-action" :disabled="loading || starting" @click="start">
          {{ starting ? '正在启动…' : actionLabel }}
        </button>
      </div>
    </div>

    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <p v-if="loading" class="empty-state">正在读取目标设定…</p>

    <template v-else-if="bible && plan">
      <div class="summary-card">
        <h3>本土化方向</h3>
        <p>{{ bible.adaptation_summary }}</p>
        <div class="meta-grid">
          <div><strong>目标地区</strong><span>{{ bible.target_region }}</span></div>
          <div><strong>目标语言</strong><span>{{ bible.target_language }}</span></div>
          <div><strong>视觉方向</strong><span>{{ bible.visual_style }}</span></div>
          <div><strong>场景策略</strong><span>{{ plan.scene_strategy }}</span></div>
        </div>
      </div>

      <div class="summary-card">
        <h3>必须保留</h3>
        <p class="section-note">这些内容来自已确认的原片故事与节奏，本土化不会重写它们。</p>
        <div class="lock-grid">
          <article v-for="item in plan.preservation_locks" :key="item.lock_id" class="lock-card">
            <strong>{{ item.category.replaceAll('_', ' ') }}</strong>
            <p>{{ item.source_summary }}</p>
            <small>{{ item.constraint }}</small>
          </article>
        </div>
      </div>

      <div class="summary-card">
        <h3>目标世界</h3>
        <p>{{ bible.target_world.setting_summary }}</p>
        <p><strong>文化语境：</strong>{{ bible.target_world.cultural_context }}</p>
        <p><strong>社会语境：</strong>{{ bible.target_world.social_context }}</p>
        <ul>
          <li v-for="item in bible.target_world.localization_principles" :key="item">{{ item }}</li>
        </ul>
      </div>

      <div class="entity-section">
        <h3>人物</h3>
        <div class="entity-grid">
          <article v-for="item in bible.characters" :key="item.target_character_id" class="entity-card">
            <p class="source-label">原片：{{ item.source_display_name }}</p>
            <h4>{{ item.display_name }}</h4>
            <p>{{ item.localized_identity }}</p>
            <p><strong>外形方向：</strong>{{ item.appearance_direction }}</p>
            <ul v-if="item.personality_constraints.length">
              <li v-for="rule in item.personality_constraints" :key="rule">{{ rule }}</li>
            </ul>
          </article>
        </div>
      </div>

      <div class="entity-section">
        <h3>场景</h3>
        <div class="entity-grid">
          <article v-for="item in bible.scenes" :key="item.target_scene_id" class="entity-card">
            <p class="source-label">原片：{{ item.source_display_name }}</p>
            <h4>{{ item.display_name }}</h4>
            <p>{{ item.localized_setting }}</p>
            <p><strong>视觉方向：</strong>{{ item.visual_direction }}</p>
          </article>
        </div>
      </div>

      <div class="entity-section">
        <h3>关键道具</h3>
        <div class="entity-grid">
          <article v-for="item in bible.props" :key="item.target_prop_id" class="entity-card">
            <p class="source-label">原片：{{ item.source_display_name }}</p>
            <h4>{{ item.display_name }}</h4>
            <p>{{ item.localized_form }}</p>
          </article>
        </div>
      </div>

      <div class="summary-card" v-if="bible.continuity_rules.length || bible.dialogue_style_rules.length">
        <h3>连续性与表达规则</h3>
        <div class="rules-columns">
          <div>
            <h4>连续性</h4>
            <ul><li v-for="item in bible.continuity_rules" :key="item">{{ item }}</li></ul>
          </div>
          <div>
            <h4>后续对白风格</h4>
            <ul><li v-for="item in bible.dialogue_style_rules" :key="item">{{ item }}</li></ul>
          </div>
        </div>
      </div>
    </template>

    <div v-else-if="!loading" class="empty-state">
      <p>原片解析完成后，可以基于已确认的故事和节奏生成目标地区的人物、场景、道具与文化设定。</p>
    </div>
  </section>
</template>

<style scoped>
.target-bible-workspace {
  margin: 28px auto 0;
  max-width: 1240px;
  padding: 24px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 18px;
  background: var(--surface-color, #fff);
}
.target-header { display: flex; gap: 24px; justify-content: space-between; align-items: flex-start; }
.eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; opacity: .55; }
h2, h3, h4, p { margin-top: 0; }
.target-subtitle { max-width: 760px; opacity: .7; }
.target-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
.status-pill { padding: 6px 10px; border-radius: 999px; background: #f3f4f6; font-size: 13px; white-space: nowrap; }
.status-pill.current { background: #ecfdf5; }
.status-pill.stale { background: #fff7ed; }
.primary-action { border: 0; border-radius: 10px; padding: 10px 16px; font-weight: 700; cursor: pointer; background: #111827; color: #fff; }
.primary-action:disabled { cursor: default; opacity: .55; }
.error-message { margin-top: 16px; padding: 10px 12px; border-radius: 10px; background: #fef2f2; }
.empty-state { margin: 18px 0 0; padding: 22px; border-radius: 12px; background: #f9fafb; opacity: .72; }
.summary-card, .entity-section { margin-top: 22px; padding-top: 20px; border-top: 1px solid #eef0f3; }
.meta-grid, .entity-grid, .lock-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
.meta-grid > div, .entity-card, .lock-card { padding: 14px; border-radius: 12px; background: #f8fafc; }
.meta-grid strong, .meta-grid span { display: block; }
.meta-grid span { margin-top: 5px; }
.lock-card p, .entity-card p { margin-bottom: 8px; }
.lock-card small { opacity: .65; }
.section-note, .source-label { opacity: .6; }
.entity-card h4 { margin-bottom: 8px; font-size: 18px; }
ul { margin: 8px 0 0; padding-left: 20px; }
.rules-columns { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 18px; }
@media (max-width: 720px) {
  .target-bible-workspace { padding: 18px; }
  .target-header { flex-direction: column; }
  .target-actions { align-items: stretch; width: 100%; }
}
</style>
