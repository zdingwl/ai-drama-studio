<script setup lang="ts">
import type { BreakdownSceneSegment, BreakdownShotDraft, BreakdownTimelineEvent } from '../types/breakdown'
import BreakdownShotWorkspaceV1 from './BreakdownShotWorkspaceV1.vue'

defineProps<{
  segment: BreakdownSceneSegment | null
  shot: BreakdownShotDraft | null
  selectedEventId: string
  shotPosition: number
  shotTotal: number
  hasPreviousShot: boolean
  hasNextShot: boolean
}>()

const emit = defineEmits<{
  (event: 'select-event', item: BreakdownTimelineEvent): void
  (event: 'previous-shot'): void
  (event: 'next-shot'): void
}>()
</script>

<template>
  <section class="shot-review-shell-v1">
    <header v-if="shot" class="shot-review-nav">
      <div class="shot-review-context">
        <span>连续审核</span>
        <strong>镜头 {{ String(shot.shot_ordinal_snapshot).padStart(4, '0') }}</strong>
        <small>第 {{ shotPosition }} / {{ shotTotal }} 镜</small>
      </div>
      <div class="shot-review-actions" aria-label="连续镜头导航">
        <button type="button" :disabled="!hasPreviousShot" @click="emit('previous-shot')">← 上一镜</button>
        <button type="button" class="primary" :disabled="!hasNextShot" @click="emit('next-shot')">下一镜 →</button>
      </div>
    </header>

    <BreakdownShotWorkspaceV1
      :segment="segment"
      :shot="shot"
      :selected-event-id="selectedEventId"
      @select-event="emit('select-event', $event)"
    />
  </section>
</template>

<style scoped>
.shot-review-shell-v1 { min-width: 0; display: grid; align-content: start; gap: 10px; }
.shot-review-nav { display: flex; justify-content: space-between; gap: 14px; align-items: center; border: 1px solid #dfe5ef; border-radius: 12px; padding: 9px 11px; background: #fff; box-shadow: 0 5px 18px rgba(42, 59, 90, .035); }
.shot-review-context { min-width: 0; display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
.shot-review-context > span { color: #78879d; font-size: 12px; font-weight: 800; }
.shot-review-context strong { color: #2c405f; font-size: 14px; }
.shot-review-context small { border-radius: 999px; padding: 4px 8px; background: #f1f4f8; color: #697990; font-size: 12px; }
.shot-review-actions { flex: none; display: flex; gap: 7px; }
.shot-review-actions button { min-height: 36px; border: 1px solid #d3deed; border-radius: 8px; padding: 0 11px; background: #fff; color: #4f617c; cursor: pointer; font-size: 12px; font-weight: 800; }
.shot-review-actions button.primary { border-color: #4f7ee0; background: #4f7ee0; color: #fff; }
.shot-review-actions button:disabled { opacity: .4; cursor: not-allowed; }
@media (max-width: 720px) {
  .shot-review-nav { align-items: stretch; display: grid; }
  .shot-review-actions { display: grid; grid-template-columns: 1fr 1fr; }
}
</style>
