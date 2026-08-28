<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { BreakdownRunSummary } from '../types/breakdown'
import type { BackgroundTask, Episode } from '../types/studio'
import BreakdownResultsV1 from './BreakdownResultsV1.vue'
import BreakdownTaskBarV1 from './BreakdownTaskBarV1.vue'
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

const mode = ref<'shots' | 'draft'>(props.episodes.some((episode) => episode.shot_count > 0) ? 'draft' : 'shots')
const draftRefreshToken = ref(0)
const selectedEpisodeId = ref('')
const currentDraftRun = ref<BreakdownRunSummary | null>(null)

watch(
  () => props.episodes.map((item) => `${item.id}:${item.shot_count}`).join('|'),
  () => {
    if (props.episodes.some((item) => item.id === selectedEpisodeId.value)) return
    selectedEpisodeId.value = props.episodes.find((item) => item.shot_count > 0)?.id ?? props.episodes[0]?.id ?? ''
    currentDraftRun.value = null
  },
  { immediate: true },
)

watch(selectedEpisodeId, () => {
  currentDraftRun.value = null
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
          <small>检查切镜 / 拆分 / 合并 / 参考片段</small>
        </button>
        <button :class="{ active: mode === 'draft' }" type="button" @click="mode = 'draft'">
          <b>拉片结果</b>
          <small>场景 / 人物 / 对白 / 动作 / 道具</small>
        </button>
      </div>
    </div>

    <template v-if="mode === 'shots'">
      <ShotCacheManagerV51 :project-id="projectId" :episodes="episodes" />
      <ShotWorkbenchV4
        :key="refreshToken"
        :project-id="projectId"
        :episodes="episodes"
        @refresh-project="emit('refresh-project')"
      />
    </template>

    <div v-else class="draft-mode-stack">
      <BreakdownTaskBarV1
        v-model:selected-episode-id="selectedEpisodeId"
        :project-id="projectId"
        :episodes="episodes"
        :run="currentDraftRun"
      />
      <BreakdownResultsV1
        :key="draftRefreshToken"
        :episodes="episodes"
        :selected-episode-id="selectedEpisodeId"
        @run-context="currentDraftRun = $event"
      />
    </div>
  </section>
</template>

<style scoped>
.breakdown-stage-v1, .draft-mode-stack { display: grid; gap: 10px; min-height: 0; }
.breakdown-stage-switcher { display: grid; grid-template-columns: 160px minmax(0, 1fr); gap: 14px; align-items: center; border: 1px solid #dce3ec; border-radius: 13px; padding: 10px 12px; background: #fff; box-shadow: 0 5px 20px rgba(38, 51, 76, .04); }
.stage-switcher-title { display: grid; gap: 3px; }
.stage-switcher-title span { color: #7e8ca1; font-size: 10px; font-weight: 850; letter-spacing: .04em; text-transform: uppercase; }
.stage-switcher-title strong { color: #31435f; font-size: 15px; }
.breakdown-stage-tabs { display: flex; gap: 7px; justify-content: flex-end; }
.breakdown-stage-tabs button { min-width: 240px; min-height: 46px; display: grid; gap: 2px; border: 1px solid #e0e5ed; border-radius: 9px; padding: 7px 11px; background: #f8fafc; color: #68758a; cursor: pointer; text-align: left; }
.breakdown-stage-tabs button.active { border-color: #86a2e3; background: #eef4ff; box-shadow: inset 3px 0 0 #547ad0; color: #405b92; }
.breakdown-stage-tabs b { font-size: 13px; }
.breakdown-stage-tabs small { color: #8895a8; font-size: 10px; }
@media (max-width: 900px) {
  .breakdown-stage-switcher { grid-template-columns: 1fr; }
  .breakdown-stage-tabs { justify-content: flex-start; }
}
@media (max-width: 620px) {
  .breakdown-stage-tabs { display: grid; grid-template-columns: 1fr 1fr; }
  .breakdown-stage-tabs button { min-width: 0; }
}
</style>
