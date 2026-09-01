<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { BreakdownRunSummary } from '../types/breakdown'
import type { BackgroundTask, Episode } from '../types/studio'
import BreakdownTaskBarV1 from './BreakdownTaskBarV1.vue'
import SceneTimelineResultsV1 from './SceneTimelineResultsV1.vue'
import ShotCacheManagerV51 from './ShotCacheManagerV51.vue'
import ShotWorkbenchV4 from './ShotWorkbenchV4.vue'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
  refreshToken: number
}>()

const emit = defineEmits<{
  (event: 'refresh-project'): void
}>()

const route = useRoute()
const router = useRouter()
const mode = ref<'shots' | 'draft'>(props.episodes.some((episode) => episode.shot_count > 0) ? 'draft' : 'shots')
const draftRefreshToken = ref(0)
const selectedEpisodeId = ref('')
const currentDraftRun = ref<BreakdownRunSummary | null>(null)

function defaultEpisodeId(): string {
  return props.episodes.find((item) => item.shot_count > 0)?.id ?? props.episodes[0]?.id ?? ''
}

function syncEpisodeFromRoute(): void {
  const requested = String(route.query.episode || '')
  const requestedExists = props.episodes.some((item) => item.id === requested)
  const currentExists = props.episodes.some((item) => item.id === selectedEpisodeId.value)
  const next = requestedExists ? requested : currentExists ? selectedEpisodeId.value : defaultEpisodeId()

  if (selectedEpisodeId.value !== next) selectedEpisodeId.value = next
  if (next && requested !== next) {
    void router.replace({ query: { ...route.query, episode: next } })
  }
}

watch(
  () => props.episodes.map((item) => `${item.id}:${item.shot_count}`).join('|'),
  syncEpisodeFromRoute,
  { immediate: true },
)

watch(
  () => route.query.episode,
  syncEpisodeFromRoute,
)

watch(selectedEpisodeId, (episodeId) => {
  currentDraftRun.value = null
  if (episodeId && String(route.query.episode || '') !== episodeId) {
    void router.replace({ query: { ...route.query, episode: episodeId } })
  }
})

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== props.projectId) return
  if (task.task_type === 'EPISODE_BREAKDOWN_P2' || task.task_type === 'BATCH_BREAKDOWN_P2') {
    currentDraftRun.value = null
    draftRefreshToken.value += 1
  }
}

onMounted(() => window.addEventListener('studio-task-finished', onTaskFinished))
onUnmounted(() => window.removeEventListener('studio-task-finished', onTaskFinished))
</script>

<template>
  <section class="breakdown-stage-v1">
    <div class="breakdown-stage-switcher">
      <div class="stage-switcher-title">
        <span>02 拉片</span>
        <strong>{{ mode === 'shots' ? '镜头管理' : '拉片结果' }}</strong>
      </div>
      <div class="breakdown-stage-tabs" role="tablist" aria-label="拉片子工作区">
        <button :class="{ active: mode === 'shots' }" type="button" @click="mode = 'shots'">
          <b>镜头管理</b>
          <small>检查与修正切点</small>
        </button>
        <button :class="{ active: mode === 'draft' }" type="button" @click="mode = 'draft'">
          <b>拉片结果</b>
          <small>直接查看场景与镜头内容</small>
        </button>
      </div>
    </div>

    <template v-if="mode === 'shots'">
      <ShotWorkbenchV4
        :key="refreshToken"
        :project-id="projectId"
        :episodes="episodes"
        @refresh-project="emit('refresh-project')"
      />
      <details class="shot-stage-advanced">
        <summary>高级设置与缓存</summary>
        <ShotCacheManagerV51 :project-id="projectId" :episodes="episodes" />
      </details>
    </template>

    <div v-else class="draft-mode-stack">
      <BreakdownTaskBarV1
        v-model:selected-episode-id="selectedEpisodeId"
        :project-id="projectId"
        :episodes="episodes"
        :run="currentDraftRun"
      />
      <SceneTimelineResultsV1
        :key="draftRefreshToken"
        :episodes="episodes"
        :selected-episode-id="selectedEpisodeId"
        @run-context="currentDraftRun = $event"
      />
    </div>
  </section>
</template>

<style scoped>
.breakdown-stage-v1,
.draft-mode-stack { display: grid; gap: 10px; min-height: 0; }
.breakdown-stage-switcher {
  min-width: 0;
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  border: 1px solid #dce3ec;
  border-radius: 12px;
  padding: 8px 10px;
  background: #fff;
  box-shadow: 0 5px 18px rgba(38, 51, 76, .035);
}
.stage-switcher-title { flex: none; display: flex; gap: 9px; align-items: baseline; }
.stage-switcher-title span { color: #8591a4; font-size: 10px; font-weight: 850; letter-spacing: .04em; }
.stage-switcher-title strong { color: #31435f; font-size: 14px; }
.breakdown-stage-tabs { display: flex; gap: 6px; justify-content: flex-end; }
.breakdown-stage-tabs button {
  min-width: 150px;
  min-height: 38px;
  display: grid;
  gap: 1px;
  border: 1px solid #e0e5ed;
  border-radius: 8px;
  padding: 5px 10px;
  background: #f8fafc;
  color: #68758a;
  cursor: pointer;
  text-align: left;
}
.breakdown-stage-tabs button.active { border-color: #8da9e6; background: #eef4ff; box-shadow: inset 3px 0 0 #547ad0; color: #405b92; }
.breakdown-stage-tabs b { font-size: 12px; }
.breakdown-stage-tabs small { color: #8b97a9; font-size: 9px; }
.shot-stage-advanced { border: 1px solid #dfe5ef; border-radius: 10px; background: #fff; overflow: hidden; }
.shot-stage-advanced > summary { padding: 9px 12px; color: #7c899d; font-size: 10px; font-weight: 800; cursor: pointer; }
.shot-stage-advanced[open] > summary { border-bottom: 1px solid #edf0f5; background: #fbfcfe; }
.shot-stage-advanced :deep(.shot-cache-v51) { margin: 0; border: 0; border-radius: 0; box-shadow: none; }
@media (max-width: 760px) {
  .breakdown-stage-switcher { align-items: stretch; flex-direction: column; }
  .breakdown-stage-tabs { justify-content: flex-start; }
}
@media (max-width: 520px) {
  .breakdown-stage-tabs { display: grid; grid-template-columns: 1fr 1fr; }
  .breakdown-stage-tabs button { min-width: 0; }
}
</style>
