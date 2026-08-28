<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { breakdownApi } from '../api/breakdown'
import type { Episode } from '../types/studio'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

const selectedEpisodeId = ref('')
const starting = ref(false)
const error = ref('')
const notice = ref('')

const selectedEpisode = computed(() => props.episodes.find((item) => item.id === selectedEpisodeId.value) ?? null)

watch(
  () => props.episodes.map((item) => item.id).join('|'),
  () => {
    if (props.episodes.some((item) => item.id === selectedEpisodeId.value)) return
    selectedEpisodeId.value = props.episodes.find((item) => item.shot_count > 0)?.id ?? props.episodes[0]?.id ?? ''
  },
  { immediate: true },
)

async function startEpisode(): Promise<void> {
  if (!selectedEpisodeId.value || starting.value) return
  starting.value = true
  error.value = ''
  notice.value = ''
  try {
    const task = await breakdownApi.startEpisode(selectedEpisodeId.value)
    notice.value = `已进入后台任务：${task.title}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'AI 拉片任务创建失败'
  } finally {
    starting.value = false
  }
}

async function startBatch(): Promise<void> {
  if (!props.projectId || !props.episodes.length || starting.value) return
  starting.value = true
  error.value = ''
  notice.value = ''
  try {
    const task = await breakdownApi.startBatch(props.projectId)
    notice.value = `已进入后台任务：${task.title}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '批量 AI 拉片任务创建失败'
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <section class="breakdown-task-bar">
    <div class="task-bar-copy">
      <span>P2 PRODUCTION</span>
      <strong>运行 AI 内容拉片</strong>
      <small>ASR → OCR → Qwen3-VL → Fusion；批量任务严格按剧集顺序串行执行。</small>
    </div>

    <label class="task-episode-select">
      <span>单集</span>
      <select v-model="selectedEpisodeId" :disabled="starting || !episodes.length">
        <option v-for="episode in episodes" :key="episode.id" :value="episode.id">
          EP{{ String(episode.sort_order).padStart(2, '0') }} · {{ episode.title }} · {{ episode.shot_count }} Shots
        </option>
      </select>
    </label>

    <div class="task-bar-actions">
      <button
        type="button"
        class="primary"
        :disabled="starting || !selectedEpisode || selectedEpisode.shot_count === 0"
        @click="startEpisode"
      >{{ starting ? '正在创建任务…' : '运行所选剧集' }}</button>
      <button type="button" :disabled="starting || !episodes.length" @click="startBatch">按顺序批量拉片</button>
    </div>

    <div class="task-bar-state">
      <span v-if="error" class="error">{{ error }}</span>
      <span v-else-if="notice" class="notice">{{ notice }} · 进度见全局后台任务栏</span>
      <span v-else>本地重任务 concurrency = 1；重复点击同一任务由后端幂等处理。</span>
    </div>
  </section>
</template>

<style scoped>
.breakdown-task-bar { display: grid; grid-template-columns: minmax(210px, .8fr) minmax(280px, 1fr) auto; gap: 10px 14px; align-items: end; border: 1px solid #d9e3f2; border-radius: 12px; padding: 10px 12px; background: linear-gradient(180deg, #fbfdff 0%, #f5f8fd 100%); }
.task-bar-copy { display: grid; gap: 2px; }
.task-bar-copy > span { color: #6680b4; font-size: 8px; font-weight: 900; letter-spacing: .07em; }
.task-bar-copy strong { color: #35455f; font-size: 11px; }
.task-bar-copy small { color: #7d899c; font-size: 8px; line-height: 1.45; }
.task-episode-select { display: grid; gap: 3px; }
.task-episode-select span { color: #7a8799; font-size: 8px; font-weight: 800; }
.task-episode-select select { width: 100%; min-width: 0; border: 1px solid #d9e0ea; border-radius: 7px; padding: 6px 8px; background: #fff; color: #4b596e; font-size: 9px; outline: none; }
.task-bar-actions { display: flex; gap: 6px; }
.task-bar-actions button { border: 1px solid #d5dde9; border-radius: 7px; padding: 7px 9px; background: #fff; color: #59677b; cursor: pointer; font-size: 9px; font-weight: 800; white-space: nowrap; }
.task-bar-actions button.primary { border-color: #5e82d2; background: #5e82d2; color: #fff; }
.task-bar-actions button:disabled { opacity: .45; cursor: not-allowed; }
.task-bar-state { grid-column: 1 / -1; border-top: 1px solid #e8edf4; padding-top: 6px; color: #8a95a5; font-size: 8px; }
.task-bar-state .notice { color: #5672a7; }
.task-bar-state .error { color: #a34646; }
@media (max-width: 980px) {
  .breakdown-task-bar { grid-template-columns: 1fr; align-items: stretch; }
  .task-bar-state { grid-column: auto; }
  .task-bar-actions { justify-content: flex-start; }
}
</style>
