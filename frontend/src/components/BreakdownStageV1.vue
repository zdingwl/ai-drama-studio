<script setup lang="ts">
import { ref } from 'vue'
import type { Episode } from '../types/studio'
import BreakdownDraftV1 from './BreakdownDraftV1.vue'
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
</script>

<template>
  <section class="breakdown-stage-v1">
    <div class="breakdown-stage-switcher">
      <div>
        <span>02 拉片工作区</span>
        <strong>{{ mode === 'shots' ? '镜头边界' : 'Structured Draft' }}</strong>
      </div>
      <div class="breakdown-stage-tabs" role="tablist" aria-label="拉片子工作区">
        <button :class="{ active: mode === 'shots' }" type="button" @click="mode = 'shots'">
          <b>镜头边界</b>
          <small>切镜 / Revision / Reference Clip</small>
        </button>
        <button :class="{ active: mode === 'draft' }" type="button" @click="mode = 'draft'">
          <b>Structured Draft</b>
          <small>Scene / 人物A-B / 对白 / 动作</small>
        </button>
      </div>
      <div class="breakdown-stage-boundary">AI Draft 只读 · 不等同 Final Asset</div>
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

    <BreakdownDraftV1 v-else :episodes="episodes" />
  </section>
</template>

<style scoped>
.breakdown-stage-v1 { display: grid; gap: 12px; min-height: 0; }
.breakdown-stage-switcher { display: grid; grid-template-columns: 170px minmax(0, 1fr) auto; gap: 12px; align-items: center; border: 1px solid #dce3ec; border-radius: 12px; padding: 9px 11px; background: #fff; box-shadow: 0 4px 18px rgba(38, 51, 76, .035); }
.breakdown-stage-switcher > div:first-child { display: grid; gap: 2px; }
.breakdown-stage-switcher > div:first-child span { color: #8b96a6; font-size: 9px; font-weight: 850; letter-spacing: .05em; text-transform: uppercase; }
.breakdown-stage-switcher > div:first-child strong { color: #38465d; font-size: 12px; }
.breakdown-stage-tabs { display: flex; gap: 5px; justify-content: center; }
.breakdown-stage-tabs button { min-width: 190px; display: grid; gap: 2px; border: 1px solid #e0e5ed; border-radius: 8px; padding: 6px 10px; background: #f8fafc; color: #68758a; cursor: pointer; text-align: left; }
.breakdown-stage-tabs button.active { border-color: #86a2e3; background: #eef4ff; box-shadow: inset 3px 0 0 #547ad0; color: #405b92; }
.breakdown-stage-tabs b { font-size: 10px; }
.breakdown-stage-tabs small { color: #8d97a7; font-size: 8px; }
.breakdown-stage-boundary { border-radius: 999px; padding: 5px 8px; background: #f2f4f7; color: #778294; font-size: 8px; white-space: nowrap; }
@media (max-width: 1050px) {
  .breakdown-stage-switcher { grid-template-columns: 1fr; }
  .breakdown-stage-tabs { justify-content: flex-start; }
  .breakdown-stage-boundary { justify-self: start; }
}
@media (max-width: 620px) {
  .breakdown-stage-tabs { display: grid; grid-template-columns: 1fr 1fr; }
  .breakdown-stage-tabs button { min-width: 0; }
}
</style>
