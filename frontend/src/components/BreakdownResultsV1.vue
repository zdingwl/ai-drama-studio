<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { breakdownApi } from '../api/breakdown'
import type {
  BreakdownDraftPayload,
  BreakdownPropOccurrence,
  BreakdownRunSummary,
  BreakdownSceneSegment,
  BreakdownShotDraft,
  BreakdownShotSubject,
  BreakdownTimelineEvent,
} from '../types/breakdown'
import type { Episode } from '../types/studio'
import {
  cameraMotionLabel,
  propImportanceLabel,
  sceneSpaceLabel,
  screenPositionLabel,
  shotTypeLabel,
  speakingStateLabel,
  timeOfDayLabel,
} from '../utils/breakdownUiText'

const props = defineProps<{
  episodes: Episode[]
  selectedEpisodeId: string
}>()

const emit = defineEmits<{
  (event: 'run-context', run: BreakdownRunSummary | null): void
}>()

const runs = ref<BreakdownRunSummary[]>([])
const draft = ref<BreakdownDraftPayload | null>(null)
const currentRunId = ref('')
const selectedRunId = ref('')
const selectedSceneId = ref('')
const selectedShotId = ref('')
const loading = ref(false)
const error = ref('')
const videoRef = ref<HTMLVideoElement | null>(null)
const pendingSeekUs = ref<number | null>(0)
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
const selectedShotIndex = computed(() => allShots.value.findIndex((shot) => shot.id === selectedShotId.value))
const hasPreviousShot = computed(() => selectedShotIndex.value > 0)
const hasNextShot = computed(() => selectedShotIndex.value >= 0 && selectedShotIndex.value < allShots.value.length - 1)
const referenceUrl = computed(() => selectedShot.value?.source_shot_revision_item?.reference_url ?? '')
const dialogueEvents = computed(() => selectedShot.value?.events.filter((event) => event.event_type === 'DIALOGUE') ?? [])
const actionEvents = computed(() => selectedShot.value?.events.filter((event) => event.event_type === 'ACTION') ?? [])
const ocrEvents = computed(() => selectedShot.value?.events.filter((event) => event.event_type === 'OCR') ?? [])
const audioEvents = computed(() => selectedShot.value?.events.filter((event) => event.event_type === 'AUDIO_EVENT') ?? [])
const importantProps = computed(() => {
  const items = [...(selectedShot.value?.prop_occurrences ?? [])]
  const rank = (item: BreakdownPropOccurrence): number => {
    const importance = String(item.prop_hint.importance ?? '').toUpperCase()
    if (importance === 'KEY') return 0
    if (importance === 'SUPPORTING') return 1
    return 2
  }
  items.sort((a, b) => rank(a) - rank(b))
  const preferred = items.filter((item) => rank(item) <= 1)
  const source = preferred.length ? preferred : items
  const seen = new Set<string>()
  return source.filter((item) => {
    const label = (item.prop_hint.label_hint || item.prop_hint.normalized_hint || '').trim()
    if (!label || seen.has(label)) return false
    seen.add(label)
    return true
  }).slice(0, 8)
})

function timecode(us: number | null | undefined): string {
  if (us === null || us === undefined) return '—'
  const totalMs = Math.max(0, Math.round(us / 1000))
  const minutes = Math.floor(totalMs / 60_000)
  const seconds = Math.floor((totalMs % 60_000) / 1000)
  const ms = totalMs % 1000
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function durationText(startUs: number, endUs: number): string {
  return `${Math.max(0, (endUs - startUs) / 1_000_000).toFixed(2)} 秒`
}

function sceneTitle(segment: BreakdownSceneSegment | null): string {
  if (!segment) return '场景信息待补充'
  return [
    segment.location_hint,
    sceneSpaceLabel(segment.interior_exterior),
    timeOfDayLabel(segment.time_of_day),
  ].filter(Boolean).join(' · ') || '场景信息待补充'
}

function eventSpeakers(event: BreakdownTimelineEvent): string {
  const speakers = event.participants
    .filter((item) => item.role === 'SPEAKER')
    .map((item) => item.subject.display_label)
    .filter((item): item is string => Boolean(item))
  return Array.from(new Set(speakers)).join('、')
}

function eventContent(event: BreakdownTimelineEvent): string {
  return event.content_text?.trim() || '未提供内容'
}

function personMeta(item: BreakdownShotSubject): string {
  const parts: string[] = []
  if (item.speaking_state && item.speaking_state.toUpperCase() !== 'UNKNOWN') parts.push(speakingStateLabel(item.speaking_state))
  if (item.screen_position && item.screen_position.toUpperCase() !== 'UNKNOWN') parts.push(screenPositionLabel(item.screen_position))
  return parts.join(' · ')
}

function propLabel(item: BreakdownPropOccurrence): string {
  return item.prop_hint.label_hint || item.prop_hint.normalized_hint || '未命名道具'
}

function propMeta(item: BreakdownPropOccurrence): string {
  const importance = String(item.prop_hint.importance ?? '').toUpperCase()
  if (importance === 'KEY' || importance === 'SUPPORTING') return propImportanceLabel(item.prop_hint.importance)
  return ''
}

function formatRunTime(run: BreakdownRunSummary): string {
  const value = run.completed_at || run.started_at
  if (!value) return '时间未知'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间未知'
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function runSimpleStatus(run: BreakdownRunSummary): string {
  if (run.id === currentRunId.value) return '当前结果'
  if (run.status === 'FAILED') return '失败记录'
  if (run.status === 'PROCESSING') return '处理中'
  return '历史结果'
}

function selectInitialContext(payload: BreakdownDraftPayload | null, preferredShotId = ''): void {
  if (!payload) {
    selectedSceneId.value = ''
    selectedShotId.value = ''
    pendingSeekUs.value = 0
    return
  }
  const shots = payload.scene_segments.flatMap((segment) => segment.shots)
  const shot = shots.find((item) => item.id === preferredShotId) ?? shots[0] ?? null
  const segment = shot
    ? payload.scene_segments.find((item) => item.id === shot.scene_segment_id) ?? null
    : payload.scene_segments[0] ?? null
  selectedSceneId.value = segment?.id ?? ''
  selectedShotId.value = shot?.id ?? segment?.shots[0]?.id ?? ''
  pendingSeekUs.value = 0
}

function applyDraft(payload: BreakdownDraftPayload | null): void {
  const previousShotId = selectedShotId.value
  draft.value = payload
  selectedRunId.value = payload?.run.id ?? ''
  emit('run-context', payload?.run ?? null)
  selectInitialContext(payload, previousShotId)
}

async function loadEpisode(episodeId: string): Promise<void> {
  if (!episodeId) {
    runs.value = []
    currentRunId.value = ''
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
    currentRunId.value = current?.run.id ?? ''
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
    error.value = err instanceof Error ? err.message : '拉片结果读取失败'
    runs.value = []
    currentRunId.value = ''
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
    error.value = err instanceof Error ? err.message : '历史拉片结果读取失败'
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

function selectScene(segment: BreakdownSceneSegment): void {
  selectedSceneId.value = segment.id
  const shot = segment.shots.find((item) => item.id === selectedShotId.value) ?? segment.shots[0] ?? null
  if (shot) void selectShot(shot)
}

async function selectShot(shot: BreakdownShotDraft): Promise<void> {
  selectedSceneId.value = shot.scene_segment_id
  selectedShotId.value = shot.id
  pendingSeekUs.value = 0
  await nextTick()
  applyPendingSeek()
}

function selectAdjacentShot(offset: number): void {
  const index = selectedShotIndex.value
  if (index < 0) return
  const next = allShots.value[index + offset]
  if (next) void selectShot(next)
}

async function jumpToEvent(event: BreakdownTimelineEvent): Promise<void> {
  const shot = selectedShot.value
  if (!shot) return
  pendingSeekUs.value = typeof event.shot_relative_start_us === 'number'
    ? event.shot_relative_start_us
    : Math.max(0, event.source_start_us - shot.source_start_us)
  await nextTick()
  applyPendingSeek()
}

function applyPendingSeek(): void {
  const video = videoRef.value
  const shot = selectedShot.value
  if (!video || !shot || pendingSeekUs.value === null) return
  const durationUs = shot.source_shot_revision_item?.duration_us
    ?? Math.max(0, shot.source_end_us - shot.source_start_us)
  const targetUs = Math.max(0, Math.min(pendingSeekUs.value, Math.max(0, durationUs - 1_000)))
  video.currentTime = targetUs / 1_000_000
  pendingSeekUs.value = null
}

watch(
  () => props.selectedEpisodeId,
  async (episodeId) => {
    runs.value = []
    currentRunId.value = ''
    applyDraft(null)
    await loadEpisode(episodeId)
  },
  { immediate: true },
)
</script>

<template>
  <section class="breakdown-results-v1">
    <div v-if="error" class="result-alert danger">{{ error }}</div>
    <div v-if="loading" class="result-loading"><span></span>正在读取拉片结果…</div>

    <div v-if="draft" class="result-topbar">
      <div>
        <strong>{{ currentEpisode ? `E${String(currentEpisode.sort_order).padStart(2, '0')} · ${currentEpisode.title}` : '拉片结果' }}</strong>
        <span>{{ draft.scene_segments.length }} 个场景 · {{ allShots.length }} 个镜头</span>
      </div>
      <div class="topbar-actions">
        <span v-if="draft.run.status === 'READY_WITH_WARNINGS'" class="check-pill">部分内容建议人工检查</span>
        <button
          v-if="currentRunId && selectedRunId !== currentRunId"
          type="button"
          @click="chooseRun(currentRunId)"
        >返回当前结果</button>
      </div>
    </div>

    <div v-if="!draft && !loading" class="result-empty">
      <strong>还没有拉片结果</strong>
      <p>先完成镜头切分，再点击上方“重新拉片本集”或“按顺序批量拉片”。</p>
    </div>

    <div v-else-if="draft && draft.scene_segments.length" class="result-layout">
      <aside class="result-navigator">
        <header>
          <strong>镜头目录</strong>
          <span>{{ draft.scene_segments.length }} 场景 · {{ allShots.length }} 镜头</span>
        </header>

        <div class="scene-list">
          <section v-for="segment in draft.scene_segments" :key="segment.id" class="scene-item">
            <button
              type="button"
              :class="['scene-button', { active: segment.id === selectedSceneId }]"
              @click="selectScene(segment)"
            >
              <span>场景 {{ String(segment.ordinal).padStart(2, '0') }}</span>
              <b>{{ sceneTitle(segment) }}</b>
              <i>{{ segment.shots.length }}</i>
            </button>
            <div class="shot-list">
              <button
                v-for="shot in segment.shots"
                :key="shot.id"
                type="button"
                :class="['shot-button', { active: shot.id === selectedShotId }]"
                @click="selectShot(shot)"
              >
                <b>镜头 {{ String(shot.shot_ordinal_snapshot).padStart(4, '0') }}</b>
                <span>{{ timecode(shot.source_start_us) }}</span>
                <i>{{ durationText(shot.source_start_us, shot.source_end_us) }}</i>
              </button>
            </div>
          </section>
        </div>

        <details v-if="runs.length > 1" class="history-results">
          <summary>历史结果 <span>{{ runs.length }}</span></summary>
          <div>
            <button
              v-for="run in runs"
              :key="run.id"
              type="button"
              :class="{ active: run.id === selectedRunId }"
              @click="chooseRun(run.id)"
            >
              <b>{{ runSimpleStatus(run) }}</b>
              <span>{{ formatRunTime(run) }}</span>
            </button>
          </div>
        </details>
      </aside>

      <main v-if="selectedSegment && selectedShot" class="result-content">
        <section class="scene-strip">
          <span>场景 {{ String(selectedSegment.ordinal).padStart(2, '0') }}</span>
          <strong>{{ sceneTitle(selectedSegment) }}</strong>
          <p v-if="selectedSegment.summary || selectedSegment.environment_description">
            {{ selectedSegment.summary || selectedSegment.environment_description }}
          </p>
        </section>

        <section class="shot-result-card">
          <header class="shot-result-head">
            <div>
              <strong>镜头 {{ String(selectedShot.shot_ordinal_snapshot).padStart(4, '0') }}</strong>
              <span>{{ timecode(selectedShot.source_start_us) }} → {{ timecode(selectedShot.source_end_us) }} · {{ durationText(selectedShot.source_start_us, selectedShot.source_end_us) }}</span>
            </div>
            <div class="shot-language-pills">
              <span v-if="selectedShot.shot_type_hint">{{ shotTypeLabel(selectedShot.shot_type_hint) }}</span>
              <span v-if="selectedShot.camera_motion_hint">{{ cameraMotionLabel(selectedShot.camera_motion_hint) }}</span>
            </div>
          </header>

          <div class="visual-summary">
            <img
              v-if="selectedShot.source_shot_revision_item?.thumbnail_url"
              :src="selectedShot.source_shot_revision_item.thumbnail_url"
              alt="镜头缩略图"
            />
            <div v-else class="thumbnail-empty">镜头 {{ String(selectedShot.shot_ordinal_snapshot).padStart(4, '0') }}</div>
            <div>
              <span class="result-label">画面</span>
              <strong>{{ selectedShot.summary || '暂无镜头摘要' }}</strong>
              <p v-if="selectedShot.visual_description && selectedShot.visual_description !== selectedShot.summary">{{ selectedShot.visual_description }}</p>
            </div>
          </div>

          <div class="direct-results">
            <section class="result-row">
              <div class="result-row-label">场景</div>
              <div class="result-row-body">
                <strong>{{ sceneTitle(selectedSegment) }}</strong>
                <p v-if="selectedSegment.environment_description">{{ selectedSegment.environment_description }}</p>
              </div>
            </section>

            <section class="result-row">
              <div class="result-row-label">人物</div>
              <div class="result-row-body">
                <div v-if="selectedShot.subjects.length" class="people-list">
                  <div v-for="person in selectedShot.subjects" :key="person.id" class="person-item">
                    <b>{{ person.subject.display_label || '人物' }}</b>
                    <span>{{ person.activity_summary || '出现在镜头中' }}</span>
                    <small v-if="personMeta(person)">{{ personMeta(person) }}</small>
                  </div>
                </div>
                <span v-else class="empty-value">无人</span>
              </div>
            </section>

            <section class="result-row">
              <div class="result-row-label">对白</div>
              <div class="result-row-body">
                <div v-if="dialogueEvents.length" class="event-result-list">
                  <button v-for="event in dialogueEvents" :key="event.id" type="button" @click="jumpToEvent(event)">
                    <span class="event-time">{{ timecode(event.source_start_us) }}</span>
                    <strong v-if="eventSpeakers(event)">{{ eventSpeakers(event) }}</strong>
                    <p>{{ eventContent(event) }}</p>
                    <i>▶</i>
                  </button>
                </div>
                <span v-else class="empty-value">无对白</span>
              </div>
            </section>

            <section class="result-row">
              <div class="result-row-label">动作</div>
              <div class="result-row-body">
                <div v-if="actionEvents.length" class="event-result-list compact">
                  <button v-for="event in actionEvents" :key="event.id" type="button" @click="jumpToEvent(event)">
                    <span class="event-time">{{ timecode(event.source_start_us) }}</span>
                    <p>{{ eventContent(event) }}</p>
                    <i>▶</i>
                  </button>
                </div>
                <span v-else class="empty-value">无明显动作</span>
              </div>
            </section>

            <section class="result-row">
              <div class="result-row-label">关键道具</div>
              <div class="result-row-body">
                <div v-if="importantProps.length" class="prop-list">
                  <span v-for="item in importantProps" :key="item.id">
                    <b>{{ propLabel(item) }}</b>
                    <small v-if="propMeta(item)">{{ propMeta(item) }}</small>
                  </span>
                </div>
                <span v-else class="empty-value">无关键道具</span>
              </div>
            </section>

            <section v-if="ocrEvents.length" class="result-row optional-row">
              <div class="result-row-label">画面文字</div>
              <div class="result-row-body event-result-list compact">
                <button v-for="event in ocrEvents" :key="event.id" type="button" @click="jumpToEvent(event)">
                  <span class="event-time">{{ timecode(event.source_start_us) }}</span>
                  <p>{{ eventContent(event) }}</p>
                  <i>▶</i>
                </button>
              </div>
            </section>

            <section v-if="audioEvents.length" class="result-row optional-row">
              <div class="result-row-label">声音</div>
              <div class="result-row-body event-result-list compact">
                <button v-for="event in audioEvents" :key="event.id" type="button" @click="jumpToEvent(event)">
                  <span class="event-time">{{ timecode(event.source_start_us) }}</span>
                  <p>{{ eventContent(event) }}</p>
                  <i>▶</i>
                </button>
              </div>
            </section>

            <section v-if="selectedShot.narrative_function_hint" class="result-row optional-row">
              <div class="result-row-label">镜头作用</div>
              <div class="result-row-body">
                <strong>{{ selectedShot.narrative_function_hint }}</strong>
              </div>
            </section>
          </div>
        </section>
      </main>

      <aside v-if="selectedShot" class="reference-panel">
        <section class="reference-card">
          <header>
            <div>
              <span>原镜头</span>
              <strong>镜头 {{ String(selectedShot.shot_ordinal_snapshot).padStart(4, '0') }}</strong>
            </div>
          </header>
          <div class="reference-video">
            <video
              v-if="referenceUrl"
              ref="videoRef"
              :key="selectedShot.source_shot_revision_item_id"
              :src="referenceUrl"
              controls
              preload="metadata"
              @loadedmetadata="applyPendingSeek"
            ></video>
            <div v-else class="reference-missing">没有可用的参考片段</div>
          </div>
          <div class="reference-time">
            <span>{{ timecode(selectedShot.source_start_us) }} → {{ timecode(selectedShot.source_end_us) }}</span>
            <b>{{ durationText(selectedShot.source_start_us, selectedShot.source_end_us) }}</b>
          </div>
          <div class="reference-actions">
            <button type="button" :disabled="!hasPreviousShot" @click="selectAdjacentShot(-1)">← 上一镜</button>
            <button type="button" class="primary" :disabled="!hasNextShot" @click="selectAdjacentShot(1)">下一镜 →</button>
          </div>
        </section>
        <p class="identity-note">人物名称暂为拉片阶段的临时标记，后续资产识别会自动回填正式人物。</p>
      </aside>
    </div>

    <div v-else-if="draft && !loading" class="result-empty">
      <strong>这次拉片没有生成可展示的镜头结果</strong>
      <p>可以重新运行本集；历史记录仍保留在后台。</p>
      <details v-if="draft.run.error_message" class="error-details">
        <summary>查看错误详情</summary>
        <p>{{ draft.run.error_message }}</p>
      </details>
    </div>
  </section>
</template>

<style scoped>
.breakdown-results-v1 { min-height: 0; display: grid; gap: 10px; color: #2a3b56; }
.result-alert { border-radius: 10px; padding: 10px 12px; font-size: 12px; }
.result-alert.danger { border: 1px solid #efd0d0; background: #fff4f4; color: #a34747; }
.result-loading { display: flex; gap: 8px; align-items: center; border-radius: 10px; padding: 10px 12px; background: #f5f8fd; color: #667894; font-size: 12px; }
.result-loading > span { width: 9px; height: 9px; border: 2px solid #b8c7de; border-top-color: #4e7ee0; border-radius: 50%; animation: spin .8s linear infinite; }
.result-topbar { display: flex; justify-content: space-between; gap: 14px; align-items: center; border: 1px solid #dfe5ee; border-radius: 12px; padding: 9px 12px; background: #fff; }
.result-topbar > div:first-child { min-width: 0; display: flex; gap: 9px; align-items: center; }
.result-topbar strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #2e425f; font-size: 13px; }
.result-topbar span { color: #7d8ba0; font-size: 11px; white-space: nowrap; }
.topbar-actions { display: flex; gap: 7px; align-items: center; }
.topbar-actions button { min-height: 32px; border: 1px solid #cfd9e8; border-radius: 8px; padding: 0 10px; background: #fff; color: #50637f; cursor: pointer; font-size: 11px; font-weight: 800; }
.check-pill { border-radius: 999px; padding: 5px 8px; background: #fff4dc; color: #96620b !important; }
.result-empty { min-height: 430px; display: grid; place-content: center; justify-items: center; gap: 6px; border: 1px dashed #d8e0eb; border-radius: 14px; background: #fbfcfe; padding: 28px; text-align: center; }
.result-empty strong { font-size: 17px; color: #41526d; }
.result-empty p { margin: 0; color: #8491a3; font-size: 12px; line-height: 1.6; }
.result-layout { min-height: 690px; display: grid; grid-template-columns: 230px minmax(520px, 1fr) 300px; gap: 10px; align-items: start; }
.result-navigator { min-height: 690px; max-height: calc(100vh - 205px); position: sticky; top: 10px; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; border: 1px solid #dfe5ee; border-radius: 13px; background: #fff; overflow: hidden; }
.result-navigator > header { display: grid; gap: 2px; padding: 12px 12px 10px; border-bottom: 1px solid #edf0f5; }
.result-navigator > header strong { font-size: 13px; }
.result-navigator > header span { color: #8a96a8; font-size: 11px; }
.scene-list { min-height: 0; overflow: auto; padding: 7px; }
.scene-item + .scene-item { margin-top: 5px; }
.scene-button { width: 100%; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 6px; align-items: center; border: 1px solid transparent; border-radius: 8px; padding: 8px; background: #f8fafc; color: #53627a; cursor: pointer; text-align: left; }
.scene-button.active { border-color: #c8d8f8; background: #f1f6ff; }
.scene-button > span { font-size: 10px; font-weight: 850; color: #63748e; }
.scene-button b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.scene-button i { min-width: 20px; border-radius: 999px; padding: 2px 5px; background: #e9eef5; font-size: 10px; font-style: normal; text-align: center; }
.shot-list { display: grid; gap: 2px; margin: 3px 0 5px 16px; padding-left: 8px; border-left: 1px solid #dce4ef; }
.shot-button { width: 100%; display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 6px; align-items: center; border: 1px solid transparent; border-radius: 7px; padding: 7px; background: transparent; color: #607087; cursor: pointer; text-align: left; }
.shot-button:hover { background: #f8faff; }
.shot-button.active { border-color: #c5d8ff; background: #eaf2ff; color: #315da9; }
.shot-button b { font-size: 10px; white-space: nowrap; }
.shot-button span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #8996a8; font-size: 10px; }
.shot-button i { font-size: 10px; font-style: normal; white-space: nowrap; }
.history-results { border-top: 1px solid #edf0f5; background: #fbfcfe; }
.history-results summary { display: flex; justify-content: space-between; gap: 8px; padding: 10px 12px; color: #6d7c92; cursor: pointer; font-size: 11px; font-weight: 800; }
.history-results summary span { border-radius: 999px; padding: 1px 5px; background: #edf1f6; }
.history-results > div { display: grid; gap: 4px; padding: 0 8px 8px; }
.history-results button { display: flex; justify-content: space-between; gap: 8px; border: 1px solid #e4e9f0; border-radius: 7px; padding: 7px 8px; background: #fff; color: #66758a; cursor: pointer; text-align: left; }
.history-results button.active { border-color: #b9cdf7; background: #f1f6ff; }
.history-results button b { font-size: 10px; }
.history-results button span { font-size: 9px; }
.result-content { min-width: 0; display: grid; gap: 10px; }
.scene-strip { display: grid; grid-template-columns: auto auto minmax(0, 1fr); gap: 7px 9px; align-items: center; border: 1px solid #dfe5ee; border-radius: 12px; padding: 10px 12px; background: #fff; }
.scene-strip > span { border-radius: 6px; padding: 4px 7px; background: #2d4366; color: #fff; font-size: 10px; font-weight: 850; }
.scene-strip strong { font-size: 12px; }
.scene-strip p { margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #718097; font-size: 11px; }
.shot-result-card { border: 1px solid #dfe5ee; border-radius: 13px; background: #fff; overflow: hidden; }
.shot-result-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 11px 13px; border-bottom: 1px solid #edf0f5; }
.shot-result-head > div:first-child { display: grid; gap: 2px; }
.shot-result-head strong { color: #293e5e; font-size: 15px; }
.shot-result-head span { color: #8491a4; font-size: 11px; }
.shot-language-pills { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; }
.shot-language-pills span { border-radius: 999px; padding: 4px 7px; background: #eef3fa; color: #5d7090; font-size: 10px; }
.visual-summary { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 14px; padding: 13px; border-bottom: 1px solid #edf0f5; }
.visual-summary img, .thumbnail-empty { width: 150px; aspect-ratio: 4 / 3; border-radius: 9px; object-fit: cover; background: #eef2f7; }
.thumbnail-empty { display: grid; place-items: center; color: #8b97a8; font-size: 11px; }
.visual-summary > div:last-child { min-width: 0; display: grid; align-content: start; gap: 5px; }
.result-label { color: #7d8ba0; font-size: 10px; font-weight: 850; }
.visual-summary strong { color: #2d405c; font-size: 14px; line-height: 1.55; }
.visual-summary p { margin: 0; color: #63738b; font-size: 12px; line-height: 1.65; }
.direct-results { display: grid; }
.result-row { display: grid; grid-template-columns: 86px minmax(0, 1fr); border-bottom: 1px solid #edf0f5; }
.result-row:last-child { border-bottom: 0; }
.result-row-label { padding: 12px 10px 12px 13px; color: #667791; font-size: 11px; font-weight: 900; }
.result-row-body { min-width: 0; padding: 10px 13px 10px 4px; color: #334761; font-size: 12px; }
.result-row-body > strong { font-size: 12px; }
.result-row-body > p { margin: 4px 0 0; color: #687990; line-height: 1.55; }
.empty-value { color: #9aa5b5; font-size: 12px; }
.people-list { display: grid; gap: 6px; }
.person-item { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 7px; align-items: center; }
.person-item b { color: #344967; font-size: 12px; }
.person-item span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #53657f; }
.person-item small { color: #8491a4; font-size: 10px; white-space: nowrap; }
.event-result-list { display: grid; gap: 5px; }
.event-result-list button { width: 100%; display: grid; grid-template-columns: 64px auto minmax(0, 1fr) 16px; gap: 7px; align-items: center; border: 1px solid #e6eaf1; border-radius: 8px; padding: 7px 8px; background: #fbfcfe; color: #3c4f6a; cursor: pointer; text-align: left; }
.event-result-list.compact button { grid-template-columns: 64px minmax(0, 1fr) 16px; }
.event-result-list button:hover { border-color: #c9d8f4; background: #f4f8ff; }
.event-time { color: #7f8ea3; font-size: 10px; font-variant-numeric: tabular-nums; }
.event-result-list strong { font-size: 11px; white-space: nowrap; }
.event-result-list p { margin: 0; color: #3f536f; font-size: 12px; line-height: 1.45; }
.event-result-list i { color: #6f8cc5; font-size: 9px; font-style: normal; }
.prop-list { display: flex; flex-wrap: wrap; gap: 6px; }
.prop-list > span { display: inline-flex; gap: 5px; align-items: center; border: 1px solid #ead8ad; border-radius: 999px; padding: 5px 8px; background: #fff8e8; color: #74591d; }
.prop-list b { font-size: 11px; }
.prop-list small { color: #9a7622; font-size: 9px; }
.optional-row { background: #fcfdff; }
.reference-panel { position: sticky; top: 10px; display: grid; gap: 8px; }
.reference-card { border: 1px solid #dfe5ee; border-radius: 13px; background: #fff; overflow: hidden; }
.reference-card header { padding: 11px 12px 9px; }
.reference-card header > div { display: grid; gap: 2px; }
.reference-card header span { color: #8290a4; font-size: 10px; }
.reference-card header strong { color: #2d405e; font-size: 13px; }
.reference-video { margin: 0 10px; border-radius: 9px; overflow: hidden; background: #10151d; }
.reference-video video { width: 100%; aspect-ratio: 16 / 9; display: block; object-fit: contain; background: #10151d; }
.reference-missing { min-height: 150px; display: grid; place-items: center; color: #bbc3cf; font-size: 11px; }
.reference-time { display: flex; justify-content: space-between; gap: 8px; padding: 8px 11px; color: #6f7f95; font-size: 10px; }
.reference-time b { color: #304665; }
.reference-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; padding: 0 10px 10px; }
.reference-actions button { min-height: 34px; border: 1px solid #d4deec; border-radius: 8px; background: #fff; color: #53657f; cursor: pointer; font-size: 11px; font-weight: 800; }
.reference-actions button.primary { border-color: #4f7ee0; background: #4f7ee0; color: #fff; }
.reference-actions button:disabled { opacity: .4; cursor: not-allowed; }
.identity-note { margin: 0; border-radius: 9px; padding: 8px 10px; background: #f5f7fa; color: #8793a5; font-size: 10px; line-height: 1.5; }
.error-details { margin-top: 8px; color: #6e7d92; font-size: 11px; }
.error-details summary { cursor: pointer; font-weight: 800; }
.error-details p { max-width: 700px; margin: 6px 0 0; color: #a04b4b; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (max-width: 1300px) {
  .result-layout { grid-template-columns: 210px minmax(460px, 1fr) 270px; }
}
@media (max-width: 1040px) {
  .result-layout { grid-template-columns: 210px minmax(0, 1fr); }
  .reference-panel { position: static; grid-column: 1 / -1; }
  .reference-card { display: grid; grid-template-columns: minmax(180px, 280px) minmax(0, 1fr); align-items: center; }
  .reference-card header { grid-column: 1 / -1; }
  .reference-video { margin-bottom: 10px; }
  .reference-actions { align-self: end; }
  .identity-note { grid-column: 1 / -1; }
}
@media (max-width: 760px) {
  .result-topbar { align-items: flex-start; display: grid; }
  .result-topbar > div:first-child { display: grid; }
  .result-layout { display: grid; grid-template-columns: 1fr; min-height: 0; }
  .result-navigator { min-height: 0; max-height: 380px; position: static; }
  .scene-strip { grid-template-columns: auto minmax(0, 1fr); }
  .scene-strip p { grid-column: 1 / -1; white-space: normal; }
  .visual-summary { grid-template-columns: 110px minmax(0, 1fr); }
  .visual-summary img, .thumbnail-empty { width: 110px; }
  .result-row { grid-template-columns: 72px minmax(0, 1fr); }
  .person-item { grid-template-columns: auto minmax(0, 1fr); }
  .person-item small { grid-column: 2; }
  .reference-card { display: block; }
}
</style>
