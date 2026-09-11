<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getProject } from '@/features/projects/api'
import { getReplicaTargetScript, type ReplicaTargetScriptRead } from '@/features/projects/targetScript'
import type { ProjectRead } from '@/features/projects/types'

const route = useRoute()
const project = ref<ProjectRead | null>(null)
const result = ref<ReplicaTargetScriptRead | null>(null)
const loading = ref(false)
const errorMessage = ref('')

const projectId = computed(() => String(route.params.id || ''))
const visible = computed(() => project.value?.project_type === 'REPLICA')
const statusText = computed(() => {
  if (!result.value || result.value.status === 'NOT_BUILT') return '目标剧本尚未开放'
  if (result.value.status === 'STALE') return '目标设定已有更新，现有目标剧本需要更新'
  return '目标剧本已就绪'
})
const script = computed(() => result.value?.content ?? null)

async function load() {
  result.value = null
  errorMessage.value = ''
  if (!projectId.value) return
  loading.value = true
  try {
    project.value = await getProject(projectId.value)
    if (project.value.project_type === 'REPLICA') {
      result.value = await getReplicaTargetScript(projectId.value)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标剧本加载失败。'
  } finally {
    loading.value = false
  }
}

watch(projectId, () => {
  void load()
}, { immediate: true })
</script>

<template>
  <section v-if="visible" class="target-script-workspace">
    <div class="target-script-header">
      <div>
        <p class="eyebrow">目标版本</p>
        <h2>目标剧本</h2>
        <p class="target-script-subtitle">逐句保留原对白来源，并分别呈现直译、本土化表达和最终目标对白。</p>
      </div>
      <span class="status-pill" :class="result?.status?.toLowerCase()">{{ statusText }}</span>
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
      <p>目标剧本将在目标设定通过验收后开放。当前不会自动生成或启动目标对白任务。</p>
    </div>
  </section>
</template>

<style scoped>
.target-script-workspace { margin: 28px auto 0; max-width: 1240px; padding: 24px; border: 1px solid var(--border-color, #e5e7eb); border-radius: 18px; background: var(--surface-color, #fff); }
.target-script-header { display: flex; gap: 24px; justify-content: space-between; align-items: flex-start; }
.eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; opacity: .55; }
h2, h3, p { margin-top: 0; }
.target-script-subtitle { max-width: 760px; opacity: .7; }
.status-pill { padding: 6px 10px; border-radius: 999px; background: #f3f4f6; font-size: 13px; white-space: nowrap; }
.status-pill.current { background: #ecfdf5; }
.status-pill.stale { background: #fff7ed; }
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
  .dialogue-grid { grid-template-columns: 1fr; }
}
</style>
