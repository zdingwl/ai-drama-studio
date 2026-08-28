<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { BreakdownRunSummary, BreakdownSceneSegment, BreakdownShotDraft } from '../types/breakdown'
import { runStatusLabel, sceneSpaceLabel, timeOfDayLabel } from '../utils/breakdownUiText'

const props = defineProps<{
  segments: BreakdownSceneSegment[]
  runs: BreakdownRunSummary[]
  selectedRunId: string
  selectedSceneId: string
  selectedShotId: string
}>()

const emit = defineEmits<{
  (event: 'select-run', runId: string): void
  (event: 'select-scene', segment: BreakdownSceneSegment): void
  (event: 'select-shot', shot: BreakdownShotDraft): void
}>()

const expandedSceneIds = ref<string[]>([])
const showAllHistory = ref(false)
const searchQuery = ref('')

const visibleRuns = computed(() => showAllHistory.value ? props.runs : props.runs.slice(0, 4))
const totalShots = computed(() => props.segments.reduce((sum, segment) => sum + segment.shots.length, 0))
const filteredSegments = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return props.segments
  return props.segments.filter((segment) => {
    const sceneText = [
      `scene ${segment.ordinal}`,
      `场景 ${segment.ordinal}`,
      segment.location_hint,
      segment.interior_exterior,
      sceneSpaceLabel(segment.interior_exterior),
      segment.time_of_day,
      timeOfDayLabel(segment.time_of_day),
      segment.summary,
      segment.environment_description,
    ].filter(Boolean).join(' ').toLowerCase()
    if (sceneText.includes(query)) return true
    return segment.shots.some((shot) => [
      `shot ${shot.shot_ordinal_snapshot}`,
      `镜头 ${shot.shot_ordinal_snapshot}`,
      String(shot.shot_ordinal_snapshot).padStart(4, '0'),
      shot.summary,
      shot.visual_description,
    ].filter(Boolean).join(' ').toLowerCase().includes(query))
  })
})

watch(
  () => [props.selectedSceneId, props.segments.map((item) => item.id).join('|')],
  () => {
    const next = new Set(expandedSceneIds.value)
    if (props.selectedSceneId) next.add(props.selectedSceneId)
    if (!next.size && props.segments[0]) next.add(props.segments[0].id)
    expandedSceneIds.value = Array.from(next).filter((id) => props.segments.some((segment) => segment.id === id))
  },
  { immediate: true },
)

watch(searchQuery, (value) => {
  if (!value.trim()) return
  expandedSceneIds.value = Array.from(new Set([...expandedSceneIds.value, ...filteredSegments.value.map((item) => item.id)]))
})

function toggleScene(segment: BreakdownSceneSegment): void {
  const next = new Set(expandedSceneIds.value)
  if (next.has(segment.id)) next.delete(segment.id)
  else next.add(segment.id)
  expandedSceneIds.value = Array.from(next)
}

function chooseScene(segment: BreakdownSceneSegment): void {
  if (!expandedSceneIds.value.includes(segment.id)) expandedSceneIds.value = [...expandedSceneIds.value, segment.id]
  emit('select-scene', segment)
}

function isExpanded(segmentId: string): boolean {
  return expandedSceneIds.value.includes(segmentId)
}

function sceneLabel(segment: BreakdownSceneSegment): string {
  return segment.location_hint || '场景信息待补充'
}

function sceneMeta(segment: BreakdownSceneSegment): string {
  return [sceneSpaceLabel(segment.interior_exterior), timeOfDayLabel(segment.time_of_day)].filter(Boolean).join(' · ') || '语义待补充'
}

function timecode(us: number): string {
  const totalMs = Math.max(0, Math.round(us / 1000))
  const minutes = Math.floor(totalMs / 60_000)
  const seconds = Math.floor((totalMs % 60_000) / 1000)
  const ms = totalMs % 1000
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function durationText(shot: BreakdownShotDraft): string {
  return `${Math.max(0, (shot.source_end_us - shot.source_start_us) / 1_000_000).toFixed(2)} 秒`
}

function revisionLabel(run: BreakdownRunSummary): string {
  return run.source_shot_revision ? `R${run.source_shot_revision.revision}` : 'R?'
}

function runStatusClass(status: string): string {
  if (status === 'READY') return 'ready'
  if (status === 'READY_WITH_WARNINGS') return 'warning'
  if (status === 'FAILED') return 'danger'
  if (status === 'STALE') return 'stale'
  if (status === 'PROCESSING') return 'processing'
  return 'neutral'
}
</script>

<template>
  <aside class="draft-navigator-v1">
    <section class="nav-card scene-nav-card">
      <header class="nav-card-title">
        <div>
          <strong>场景 / 镜头导航</strong>
          <span>快速定位当前草稿</span>
        </div>
        <small>{{ segments.length }} 个场景 · {{ totalShots }} 个镜头</small>
      </header>

      <label class="scene-search">
        <span>⌕</span>
        <input v-model="searchQuery" type="search" placeholder="搜索场景 / 镜头 / 内容" />
      </label>

      <div v-if="filteredSegments.length" class="scene-tree">
        <div v-for="segment in filteredSegments" :key="segment.id" class="scene-tree-item">
          <button
            type="button"
            :class="['scene-tree-head', { active: segment.id === selectedSceneId }]"
            @click="chooseScene(segment)"
          >
            <span class="scene-toggle" @click.stop="toggleScene(segment)">{{ isExpanded(segment.id) ? '⌄' : '›' }}</span>
            <span class="scene-index">场景 {{ String(segment.ordinal).padStart(2, '0') }}</span>
            <span class="scene-copy">
              <b>{{ sceneLabel(segment) }}</b>
              <small>{{ sceneMeta(segment) }}</small>
            </span>
            <span class="scene-count">{{ segment.shots.length }}</span>
          </button>

          <div v-if="isExpanded(segment.id)" class="shot-tree">
            <button
              v-for="shot in segment.shots"
              :key="shot.id"
              type="button"
              :class="['shot-tree-row', { active: shot.id === selectedShotId }]"
              @click="emit('select-shot', shot)"
            >
              <span class="shot-dot"></span>
              <b>镜头 {{ String(shot.shot_ordinal_snapshot).padStart(4, '0') }}</b>
              <small>{{ timecode(shot.source_start_us) }} → {{ timecode(shot.source_end_us) }}</small>
              <i>{{ durationText(shot) }}</i>
            </button>
            <div v-if="!segment.shots.length" class="nav-empty compact">当前场景没有镜头草稿。</div>
          </div>
        </div>
      </div>
      <div v-else class="nav-empty">{{ segments.length ? '没有匹配的场景 / 镜头。' : '这次运行没有可导航的场景分段。' }}</div>
    </section>

    <section class="nav-card history-card">
      <header class="nav-card-title">
        <div>
          <strong>草稿历史</strong>
          <span>历史运行记录永久可读</span>
        </div>
        <small>{{ runs.length }}</small>
      </header>

      <div v-if="runs.length" class="history-list">
        <button
          v-for="run in visibleRuns"
          :key="run.id"
          type="button"
          :class="['history-row', { active: run.id === selectedRunId }]"
          @click="emit('select-run', run.id)"
        >
          <span :class="['history-dot', runStatusClass(run.status)]"></span>
          <span class="history-main">
            <b>{{ revisionLabel(run) }}</b>
            <small>{{ run.pipeline_profile || run.schema_version }}</small>
          </span>
          <span class="history-state">
            <i :class="runStatusClass(run.status)">{{ runStatusLabel(run.status) }}</i>
            <small>{{ run.source_shot_revision?.is_current ? '当前镜头版本' : '历史镜头版本' }}</small>
          </span>
        </button>
      </div>
      <div v-else class="nav-empty compact">当前剧集还没有拉片运行记录。</div>

      <button
        v-if="runs.length > 4"
        type="button"
        class="history-more"
        @click="showAllHistory = !showAllHistory"
      >{{ showAllHistory ? '收起历史' : `查看全部历史 (${runs.length})` }}</button>
    </section>

    <div class="draft-boundary-card">
      <strong>草稿边界</strong>
      <p>人物A/B、场景草稿、道具提示都不是最终资产。P3 只负责查看、定位、回看与追溯。</p>
    </div>
  </aside>
</template>

<style scoped>
.draft-navigator-v1 { min-width: 0; display: grid; grid-template-rows: minmax(340px, 1fr) auto auto; gap: 12px; height: 100%; min-height: 0; }
.nav-card { min-height: 0; border: 1px solid #dfe5ef; border-radius: 14px; background: #fff; box-shadow: 0 8px 28px rgba(45, 62, 94, .045); overflow: hidden; }
.scene-nav-card { display: grid; grid-template-rows: auto auto 1fr; }
.nav-card-title { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 14px 14px 11px; border-bottom: 1px solid #edf0f5; }
.nav-card-title > div { display: grid; gap: 2px; min-width: 0; }
.nav-card-title strong { color: #263652; font-size: 14px; }
.nav-card-title span { color: #8a96a9; font-size: 12px; }
.nav-card-title > small { flex: none; color: #71809a; font-size: 12px; }
.scene-search { display: grid; grid-template-columns: 20px minmax(0, 1fr); gap: 5px; align-items: center; margin: 9px 9px 2px; border: 1px solid #dfe5ee; border-radius: 9px; padding: 0 9px; background: #f9fbfd; }
.scene-search > span { color: #8a97aa; font-size: 14px; text-align: center; }
.scene-search input { min-width: 0; height: 36px; border: 0; outline: 0; background: transparent; color: #40516a; font-size: 12px; }
.scene-search input::placeholder { color: #9aa5b5; }
.scene-tree { min-height: 0; overflow: auto; padding: 8px; }
.scene-tree-item + .scene-tree-item { margin-top: 3px; }
.scene-tree-head { width: 100%; display: grid; grid-template-columns: 18px auto minmax(0, 1fr) 24px; gap: 7px; align-items: center; border: 1px solid transparent; border-radius: 9px; padding: 9px 8px; background: transparent; color: #40506a; cursor: pointer; text-align: left; }
.scene-tree-head:hover { background: #f7f9fd; }
.scene-tree-head.active { border-color: #c8d9ff; background: #f1f6ff; box-shadow: inset 3px 0 0 #4e7fe5; }
.scene-toggle { color: #7d8ba1; font-size: 16px; line-height: 1; text-align: center; }
.scene-index { color: #354969; font-size: 12px; font-weight: 850; white-space: nowrap; }
.scene-copy { min-width: 0; display: grid; gap: 2px; }
.scene-copy b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.scene-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #8995a8; font-size: 11px; }
.scene-count { justify-self: end; min-width: 22px; border-radius: 999px; padding: 2px 5px; background: #eef2f8; color: #75839a; font-size: 11px; text-align: center; }
.shot-tree { position: relative; display: grid; gap: 3px; margin: 2px 5px 7px 29px; padding-left: 12px; border-left: 1px solid #dce4f0; }
.shot-tree-row { width: 100%; display: grid; grid-template-columns: 8px auto minmax(0, 1fr) auto; gap: 7px; align-items: center; border: 1px solid transparent; border-radius: 8px; padding: 8px 8px; background: transparent; color: #53627a; cursor: pointer; text-align: left; }
.shot-tree-row:hover { background: #f8faff; }
.shot-tree-row.active { border-color: #c5d8ff; background: #eaf2ff; color: #315ca8; }
.shot-dot { width: 6px; height: 6px; border-radius: 50%; background: #aab4c3; }
.shot-tree-row.active .shot-dot { background: #3979ef; box-shadow: 0 0 0 3px rgba(57, 121, 239, .12); }
.shot-tree-row b { font-size: 12px; white-space: nowrap; }
.shot-tree-row small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #8b97aa; font-size: 11px; }
.shot-tree-row i { color: #65748c; font-size: 11px; font-style: normal; white-space: nowrap; }
.history-card { overflow: visible; }
.history-list { display: grid; gap: 6px; padding: 9px; }
.history-row { width: 100%; display: grid; grid-template-columns: 8px minmax(0, .8fr) minmax(0, 1.2fr); gap: 8px; align-items: center; border: 1px solid #e8ecf2; border-radius: 9px; padding: 9px 8px; background: #fbfcfe; color: #44536b; cursor: pointer; text-align: left; }
.history-row.active { border-color: #b8cdfa; background: #f1f6ff; box-shadow: inset 3px 0 0 #4d7fe7; }
.history-dot { width: 7px; height: 7px; border-radius: 50%; background: #a4aebe; }
.history-dot.ready { background: #1fa267; }
.history-dot.warning { background: #d7941d; }
.history-dot.danger { background: #dc5252; }
.history-dot.stale { background: #8d7bb8; }
.history-dot.processing { background: #3979ef; }
.history-main, .history-state { min-width: 0; display: grid; gap: 2px; }
.history-main b { font-size: 13px; }
.history-main small, .history-state small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #8995a7; font-size: 11px; }
.history-state { justify-items: end; }
.history-state i { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; border-radius: 999px; padding: 3px 7px; font-size: 11px; font-style: normal; font-weight: 800; }
i.ready { background: #e8f7ef; color: #14804e; }
i.warning { background: #fff4da; color: #91620e; }
i.danger { background: #ffe8e8; color: #b54242; }
i.stale { background: #f0edf7; color: #756396; }
i.processing { background: #eaf2ff; color: #3569bf; }
i.neutral { background: #eef1f5; color: #6f7a8b; }
.history-more { width: calc(100% - 18px); margin: 0 9px 10px; border: 0; border-radius: 8px; padding: 8px; background: #f5f8fd; color: #4f73b7; cursor: pointer; font-size: 12px; font-weight: 750; }
.draft-boundary-card { border: 1px solid #dbe7fb; border-radius: 12px; padding: 11px 12px; background: #f6f9ff; }
.draft-boundary-card strong { color: #4469aa; font-size: 12px; }
.draft-boundary-card p { margin: 4px 0 0; color: #75839a; font-size: 11px; line-height: 1.55; }
.nav-empty { padding: 24px 14px; color: #919cad; font-size: 12px; line-height: 1.55; text-align: center; }
.nav-empty.compact { padding: 10px; }
@media (max-width: 1180px) {
  .draft-navigator-v1 { grid-template-rows: auto auto auto; }
  .scene-tree { max-height: 480px; }
}
</style>