<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { breakdownApi } from '../api/breakdown'
import type {
  BreakdownDraftPayload,
  BreakdownEvidenceLink,
  BreakdownRunSummary,
  BreakdownSceneSegment,
  BreakdownShotDraft,
  BreakdownTimelineEvent,
} from '../types/breakdown'
import type { Episode } from '../types/studio'
import { runStatusLabel } from '../utils/breakdownUiText'
import BreakdownInspectorV1 from './BreakdownInspectorV1.vue'
import BreakdownNavigatorV1 from './BreakdownNavigatorV1.vue'
import BreakdownShotWorkspaceV1 from './BreakdownShotWorkspaceV1.vue'

const props = defineProps<{
  episodes: Episode[]
  selectedEpisodeId: string
}>()

const emit = defineEmits<{
  (event: 'run-context', run: BreakdownRunSummary | null): void
}>()

const runs = ref<BreakdownRunSummary[]>([])
const draft = ref<BreakdownDraftPayload | null>(null)
const selectedRunId = ref('')
const selectedSceneId = ref('')
const selectedShotId = ref('')
const selectedEventId = ref('')
const loading = ref(false)
const error = ref('')
const showWarnings = ref(false)
const seekUs = ref<number | null>(0)
const seekToken = ref(0)
let requestSerial = 0

const currentEpisode = computed(() => props.episodes.find((item) => item.id === props.selectedEpisodeId) ?? null)
const allShots = computed(() => draft.value?.scene_segments.flatMap((segment) => segment.shots) ?? [])
const selectedSegment = computed(() => {
  const payload = draft.value
  if (!payload) return null
  return payload.scene_segments.find((segment) => segment.id === selectedSceneId.value)
    ?? payload.scene_segments.find((segment) => segment.shots.some((shot) => shot.id === selectedShotId.value))
    ?? null
})
const selectedShot = computed(() => allShots.value.find((shot) => shot.id === selectedShotId.value) ?? null)
const selectedEvent = computed(() => selectedShot.value?.events.find((event) => event.id === selectedEventId.value) ?? null)
const stats = computed(() => {
  const payload = draft.value
  if (!payload) return { segments: 0, shots: 0, subjects: 0, events: 0, props: 0 }
  return {
    segments: payload.scene_segments.length,
    shots: payload.scene_segments.reduce((sum, segment) => sum + segment.shots.length, 0),
    subjects: payload.scene_segments.reduce((sum, segment) => sum + segment.subjects.length, 0),
    events: payload.scene_segments.reduce(
      (sum, segment) => sum + segment.shots.reduce((shotSum, shot) => shotSum + shot.events.length, 0),
      0,
    ),
    props: payload.scene_segments.reduce((sum, segment) => sum + segment.prop_hints.length, 0),
  }
})
const warningLines = computed(() => flattenWarnings(draft.value?.run.warnings))
const unassignedCount = computed(() => {
  const value = draft.value?.unassigned
  if (!value) return 0
  return value.shots.length
    + value.subjects.length
    + value.subject_presences.length
    + value.events.length
    + value.event_participants.length
    + value.prop_hints.length
    + value.prop_occurrences.length
})
const selectedEvidenceLinks = computed<BreakdownEvidenceLink[]>(() => {
  const payload = draft.value
  const shot = selectedShot.value
  if (!payload || !shot) return []

  const ownerIds = new Set<string>()
  const event = selectedEvent.value
  if (event) {
    ownerIds.add(event.id)
    event.participants.forEach((participant) => ownerIds.add(participant.id))
  } else {
    ownerIds.add(shot.id)
    shot.subjects.forEach((item) => ownerIds.add(item.id))
    shot.events.forEach((item) => {
      ownerIds.add(item.id)
      item.participants.forEach((participant) => ownerIds.add(participant.id))
    })
    shot.prop_occurrences.forEach((item) => ownerIds.add(item.id))
  }
  return payload.evidence_links.filter((item) => ownerIds.has(item.owner_id))
})

function flattenWarnings(value: unknown, prefix = ''): string[] {
  if (value === null || value === undefined || value === '') return []
  if (Array.isArray(value)) return value.flatMap((item) => flattenWarnings(item, prefix))
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => {
      const nextPrefix = prefix ? `${prefix}.${key}` : key
      return flattenWarnings(item, nextPrefix)
    })
  }
  return [prefix ? `${prefix}: ${String(value)}` : String(value)]
}

function runStatusClass(status: string): string {
  if (status === 'READY') return 'ready'
  if (status === 'READY_WITH_WARNINGS') return 'warning'
  if (status === 'FAILED') return 'danger'
  if (status === 'STALE') return 'stale'
  if (status === 'PROCESSING') return 'processing'
  return 'neutral'
}

function revisionLabel(run: BreakdownRunSummary | null | undefined): string {
  return run?.source_shot_revision ? `R${run.source_shot_revision.revision}` : 'R?'
}

function selectInitialContext(payload: BreakdownDraftPayload | null, preferredShotId = ''): void {
  if (!payload) {
    selectedSceneId.value = ''
    selectedShotId.value = ''
    selectedEventId.value = ''
    seekUs.value = 0
    return
  }

  const shots = payload.scene_segments.flatMap((segment) => segment.shots)
  const shot = shots.find((item) => item.id === preferredShotId) ?? shots[0] ?? null
  const segment = shot
    ? payload.scene_segments.find((item) => item.id === shot.scene_segment_id) ?? null
    : payload.scene_segments[0] ?? null

  selectedSceneId.value = segment?.id ?? ''
  selectedShotId.value = shot?.id ?? segment?.shots[0]?.id ?? ''
  selectedEventId.value = ''
  seekUs.value = 0
  seekToken.value += 1
}

function applyDraft(payload: BreakdownDraftPayload | null): void {
  const previousShotId = selectedShotId.value
  draft.value = payload
  selectedRunId.value = payload?.run.id ?? ''
  emit('run-context', payload?.run ?? null)
  showWarnings.value = false
  selectInitialContext(payload, previousShotId)
}

async function loadEpisode(episodeId: string): Promise<void> {
  if (!episodeId) {
    runs.value = []
    applyDraft(null)
    return
  }

  const serial = ++requestSerial
  loading.value = true
  error.value = ''
  try {
    const [history, current] = await Promise.all([
      breakdownApi.listRuns(episodeId),
      breakdownApi.getCurrent(episodeId),
    ])
    if (serial !== requestSerial) return
    runs.value = history
    if (current) {
      applyDraft(current)
      return
    }
    if (history.length) {
      const latest = await breakdownApi.getRun(history[0].id)
      if (serial !== requestSerial) return
      applyDraft(latest)
      return
    }
    applyDraft(null)
  } catch (err) {
    if (serial !== requestSerial) return
    error.value = err instanceof Error ? err.message : '结构化草稿读取失败'
    runs.value = []
    applyDraft(null)
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

async function chooseRun(runId: string): Promise<void> {
  if (!runId || runId === selectedRunId.value) return
  const serial = ++requestSerial
  loading.value = true
  error.value = ''
  try {
    const payload = await breakdownApi.getRun(runId)
    if (serial !== requestSerial) return
    applyDraft(payload)
  } catch (err) {
    if (serial !== requestSerial) return
    error.value = err instanceof Error ? err.message : '拉片运行记录读取失败'
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

function selectScene(segment: BreakdownSceneSegment): void {
  selectedSceneId.value = segment.id
  const shot = segment.shots.find((item) => item.id === selectedShotId.value) ?? segment.shots[0] ?? null
  selectedShotId.value = shot?.id ?? ''
  selectedEventId.value = ''
  seekUs.value = 0
  seekToken.value += 1
}

function selectShot(shot: BreakdownShotDraft): void {
  selectedSceneId.value = shot.scene_segment_id
  selectedShotId.value = shot.id
  selectedEventId.value = ''
  seekUs.value = 0
  seekToken.value += 1
}

function selectEvent(event: BreakdownTimelineEvent): void {
  const shot = selectedShot.value
  if (!shot) return
  const localUs = typeof event.shot_relative_start_us === 'number'
    ? event.shot_relative_start_us
    : Math.max(0, event.source_start_us - shot.source_start_us)
  selectedEventId.value = event.id
  seekUs.value = localUs
  seekToken.value += 1
}

watch(
  () => props.selectedEpisodeId,
  async (episodeId) => {
    runs.value = []
    applyDraft(null)
    await loadEpisode(episodeId)
  },
  { immediate: true },
)
</script>

<template>
  <section class="breakdown-draft-v2">
    <div v-if="error" class="draft-v2-alert danger">{{ error }}</div>
    <div v-if="loading" class="draft-v2-loading"><span></span>正在读取结构化草稿…</div>

    <template v-if="draft">
      <div class="draft-summary-bar">
        <div class="draft-summary-context">
          <strong>{{ currentEpisode ? `E${String(currentEpisode.sort_order).padStart(2, '0')} · ${currentEpisode.title}` : '结构化草稿' }}</strong>
          <span :class="['run-state', runStatusClass(draft.run.status)]">{{ revisionLabel(draft.run) }} · {{ runStatusLabel(draft.run.status) }}</span>
          <span>{{ draft.run.source_shot_revision?.is_current ? '当前镜头版本' : '历史镜头版本' }}</span>
          <span>{{ draft.run.is_current ? '当前剧集草稿' : '只读历史草稿' }}</span>
        </div>

        <div class="draft-summary-stats">
          <span>场景 <b>{{ stats.segments }}</b></span>
          <span>镜头 <b>{{ stats.shots }}</b></span>
          <span>匿名人物 <b>{{ stats.subjects }}</b></span>
          <span>事件 <b>{{ stats.events }}</b></span>
          <span>道具提示 <b>{{ stats.props }}</b></span>
          <button v-if="warningLines.length" type="button" @click="showWarnings = !showWarnings">⚠ {{ warningLines.length }} 条提示</button>
          <span v-if="unassignedCount" class="unassigned-pill">未归属 {{ unassignedCount }}</span>
        </div>
      </div>

      <div v-if="showWarnings && warningLines.length" class="draft-warning-panel">
        <strong>运行提示</strong>
        <span v-for="line in warningLines.slice(0, 8)" :key="line">{{ line }}</span>
        <span v-if="warningLines.length > 8">还有 {{ warningLines.length - 8 }} 条提示</span>
      </div>

      <div v-if="draft.run.error_message" class="draft-v2-alert danger">
        <strong>运行错误</strong>
        <span>{{ draft.run.error_message }}</span>
      </div>
    </template>

    <div v-if="!draft && !loading" class="draft-v2-empty">
      <strong>暂无可读取的结构化草稿</strong>
      <p>选择的剧集还没有拉片运行记录。P3 不会伪造结果，也不会在读取时自动运行模型。</p>
    </div>

    <div v-else-if="draft" class="draft-v2-grid">
      <BreakdownNavigatorV1
        :segments="draft.scene_segments"
        :runs="runs"
        :selected-run-id="selectedRunId"
        :selected-scene-id="selectedSceneId"
        :selected-shot-id="selectedShotId"
        @select-run="chooseRun"
        @select-scene="selectScene"
        @select-shot="selectShot"
      />

      <BreakdownShotWorkspaceV1
        :segment="selectedSegment"
        :shot="selectedShot"
        :selected-event-id="selectedEventId"
        @select-event="selectEvent"
      />

      <BreakdownInspectorV1
        :run="draft.run"
        :segment="selectedSegment"
        :shot="selectedShot"
        :event="selectedEvent"
        :evidence-links="selectedEvidenceLinks"
        :unassigned="draft.unassigned"
        :seek-us="seekUs"
        :seek-token="seekToken"
      />
    </div>
  </section>
</template>

<style scoped>
.breakdown-draft-v2 { min-height: 0; display: grid; gap: 10px; color: #263650; }
.draft-summary-bar { min-width: 0; display: flex; justify-content: space-between; gap: 14px; align-items: center; border: 1px solid #dfe5ef; border-radius: 12px; padding: 9px 12px; background: #fff; box-shadow: 0 5px 18px rgba(42, 59, 90, .035); }
.draft-summary-context { min-width: 0; display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
.draft-summary-context > strong { max-width: 320px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #31435f; font-size: 12px; }
.draft-summary-context > span { border-radius: 999px; padding: 4px 7px; background: #f2f5f9; color: #728097; font-size: 10px; white-space: nowrap; }
.draft-summary-context .run-state { font-weight: 850; }
.run-state.ready { background: #e8f7ef; color: #14804e; }
.run-state.warning { background: #fff4da; color: #91620e; }
.run-state.danger { background: #ffe8e8; color: #b54242; }
.run-state.stale { background: #f0edf7; color: #756396; }
.run-state.processing { background: #eaf2ff; color: #3569bf; }
.draft-summary-stats { flex: none; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; align-items: center; }
.draft-summary-stats > span, .draft-summary-stats > button { border: 1px solid #e4e8ef; border-radius: 999px; padding: 5px 8px; background: #fff; color: #78869b; font-size: 10px; white-space: nowrap; }
.draft-summary-stats b { color: #344966; font-size: 11px; }
.draft-summary-stats button { cursor: pointer; color: #97620e; }
.draft-summary-stats .unassigned-pill { border-color: #efd8a5; background: #fff8e9; color: #8e6518; }
.draft-warning-panel { display: grid; gap: 4px; border: 1px solid #efd6a0; border-radius: 11px; padding: 10px 12px; background: #fff9ec; color: #77591e; font-size: 11px; line-height: 1.5; }
.draft-warning-panel strong { font-size: 12px; }
.draft-v2-alert { display: grid; gap: 3px; border-radius: 10px; padding: 10px 12px; font-size: 12px; line-height: 1.5; }
.draft-v2-alert.danger { border: 1px solid #efb8b8; background: #fff3f3; color: #a14343; }
.draft-v2-loading { display: flex; align-items: center; gap: 8px; border: 1px solid #dfe7f6; border-radius: 10px; padding: 9px 12px; background: #f6f9ff; color: #60739a; font-size: 12px; }
.draft-v2-loading span { width: 12px; height: 12px; border: 2px solid #a9bce4; border-top-color: transparent; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.draft-v2-empty { min-height: 520px; display: grid; place-content: center; justify-items: center; gap: 8px; border: 1px dashed #d9e1ed; border-radius: 14px; background: #fbfcfe; text-align: center; padding: 30px; }
.draft-v2-empty strong { color: #42516a; font-size: 17px; }
.draft-v2-empty p { max-width: 560px; margin: 0; color: #8290a4; font-size: 13px; line-height: 1.6; }
.draft-v2-grid { display: grid; grid-template-columns: 260px minmax(620px, 1fr) 350px; gap: 12px; height: max(690px, calc(100vh - 245px)); min-height: 690px; overflow: hidden; align-items: stretch; }
@media (max-width: 1450px) {
  .draft-v2-grid { grid-template-columns: 235px minmax(560px, 1fr) 315px; }
  .draft-summary-bar { align-items: flex-start; }
}
@media (max-width: 1180px) {
  .draft-summary-bar { display: grid; }
  .draft-summary-stats { justify-content: flex-start; }
  .draft-v2-grid { grid-template-columns: 235px minmax(0, 1fr); height: auto; overflow: visible; }
  .draft-v2-grid :deep(.breakdown-inspector-v1) { grid-column: 1 / -1; max-height: none; grid-template-columns: minmax(320px, .8fr) minmax(360px, 1.2fr); align-items: start; }
}
@media (max-width: 860px) {
  .draft-v2-grid { grid-template-columns: 1fr; }
  .draft-v2-grid :deep(.draft-navigator-v1), .draft-v2-grid :deep(.shot-workspace-v1), .draft-v2-grid :deep(.breakdown-inspector-v1) { height: auto; overflow: visible; }
  .draft-v2-grid :deep(.breakdown-inspector-v1) { grid-column: auto; grid-template-columns: 1fr; }
}
</style>