<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
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

const props = defineProps<{
  episodes: Episode[]
}>()

const selectedEpisodeId = ref('')
const runs = ref<BreakdownRunSummary[]>([])
const draft = ref<BreakdownDraftPayload | null>(null)
const selectedRunId = ref('')
const selectedShotId = ref('')
const selectedEventId = ref('')
const loading = ref(false)
const error = ref('')
const videoRef = ref<HTMLVideoElement | null>(null)
const pendingSeekUs = ref<number | null>(null)
let requestSerial = 0

const allShots = computed(() => draft.value?.scene_segments.flatMap((segment) => segment.shots) ?? [])
const selectedShot = computed(() => allShots.value.find((shot) => shot.id === selectedShotId.value) ?? null)
const selectedSegment = computed(() => {
  const shot = selectedShot.value
  if (!shot) return null
  return draft.value?.scene_segments.find((segment) => segment.id === shot.scene_segment_id) ?? null
})
const selectedEvidenceLinks = computed(() => {
  const payload = draft.value
  const shot = selectedShot.value
  if (!payload || !shot) return []
  const ownerIds = new Set<string>([shot.id])
  shot.subjects.forEach((item) => ownerIds.add(item.id))
  shot.events.forEach((item) => {
    ownerIds.add(item.id)
    item.participants.forEach((participant) => ownerIds.add(participant.id))
  })
  shot.prop_occurrences.forEach((item) => ownerIds.add(item.id))
  return payload.evidence_links.filter((item) => ownerIds.has(item.owner_id))
})
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
const selectedReferenceUrl = computed(() => selectedShot.value?.source_shot_revision_item?.reference_url ?? '')

function flattenWarnings(value: unknown, prefix = ''): string[] {
  if (value === null || value === undefined || value === '') return []
  if (Array.isArray(value)) {
    return value.flatMap((item) => flattenWarnings(item, prefix))
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).flatMap(([key, item]) => {
      const nextPrefix = prefix ? `${prefix}.${key}` : key
      return flattenWarnings(item, nextPrefix)
    })
  }
  return [prefix ? `${prefix}: ${String(value)}` : String(value)]
}

function timecode(us: number | null | undefined): string {
  if (us === null || us === undefined) return '—'
  const totalMs = Math.max(0, Math.round(us / 1000))
  const hours = Math.floor(totalMs / 3_600_000)
  const minutes = Math.floor((totalMs % 3_600_000) / 60_000)
  const seconds = Math.floor((totalMs % 60_000) / 1000)
  const ms = totalMs % 1000
  if (hours > 0) {
    return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function durationText(startUs: number, endUs: number): string {
  return `${Math.max(0, (endUs - startUs) / 1_000_000).toFixed(2)}s`
}

function confidenceText(value: number | null | undefined): string {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—'
}

function runStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    READY: '可用 Draft',
    READY_WITH_WARNINGS: '可用 · 有提示',
    STALE: '历史 · 已过期',
    PROCESSING: '处理中',
    FAILED: '失败历史',
  }
  return labels[status] || status
}

function runStatusClass(status: string): string {
  if (status === 'READY') return 'ready'
  if (status === 'READY_WITH_WARNINGS') return 'warning'
  if (status === 'FAILED') return 'danger'
  if (status === 'STALE') return 'stale'
  return 'neutral'
}

function revisionLabel(run: BreakdownRunSummary | null | undefined): string {
  const revision = run?.source_shot_revision
  return revision ? `R${revision.revision}` : 'Revision ?'
}

function sceneLabel(segment: BreakdownSceneSegment): string {
  const parts = [segment.location_hint, segment.interior_exterior, segment.time_of_day].filter(Boolean)
  return parts.length ? parts.join(' · ') : '场景信息待补充'
}

function eventTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    DIALOGUE: '对白',
    ACTION: '动作',
    OCR: '画面文字',
    VISUAL: '画面',
    AUDIO_EVENT: '声音',
  }
  return labels[type] || type
}

function eventSpeakers(event: BreakdownTimelineEvent): string {
  const speakers = event.participants
    .filter((item) => item.role === 'SPEAKER')
    .map((item) => item.subject.display_label)
    .filter((item): item is string => Boolean(item))
  return Array.from(new Set(speakers)).join('、')
}

function eventContent(event: BreakdownTimelineEvent): string {
  const text = event.content_text?.trim()
  if (text) return text
  if (event.event_type === 'VISUAL') return '视觉事件（无额外文本）'
  return '未提供文本内容'
}

function isSelectedEvent(event: BreakdownTimelineEvent): boolean {
  return selectedEventId.value === event.id
}

function selectFirstShot(payload: BreakdownDraftPayload | null, preferredShotId = ''): void {
  if (!payload) {
    selectedShotId.value = ''
    selectedEventId.value = ''
    return
  }
  const shots = payload.scene_segments.flatMap((segment) => segment.shots)
  const selected = shots.find((shot) => shot.id === preferredShotId) ?? shots[0] ?? null
  selectedShotId.value = selected?.id ?? ''
  selectedEventId.value = ''
  pendingSeekUs.value = null
}

function applyDraft(payload: BreakdownDraftPayload | null): void {
  const previousShotId = selectedShotId.value
  draft.value = payload
  selectedRunId.value = payload?.run.id ?? ''
  selectFirstShot(payload, previousShotId)
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
    error.value = err instanceof Error ? err.message : 'Structured Draft 读取失败'
    runs.value = []
    applyDraft(null)
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

async function chooseEpisode(episodeId: string): Promise<void> {
  if (selectedEpisodeId.value === episodeId && (draft.value || loading.value)) return
  selectedEpisodeId.value = episodeId
  await loadEpisode(episodeId)
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
    error.value = err instanceof Error ? err.message : 'Breakdown Run 读取失败'
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

function clampLocalSeek(shot: BreakdownShotDraft, localUs: number): number {
  const durationUs = shot.source_shot_revision_item?.duration_us
    ?? Math.max(0, shot.source_end_us - shot.source_start_us)
  return Math.max(0, Math.min(localUs, Math.max(0, durationUs - 1_000)))
}

async function selectShot(shot: BreakdownShotDraft, localUs = 0, eventId = ''): Promise<void> {
  const changingShot = selectedShotId.value !== shot.id
  selectedShotId.value = shot.id
  selectedEventId.value = eventId
  pendingSeekUs.value = clampLocalSeek(shot, localUs)
  await nextTick()
  if (!changingShot) applyPendingSeek()
}

async function jumpToEvent(shot: BreakdownShotDraft, event: BreakdownTimelineEvent): Promise<void> {
  const localUs = typeof event.shot_relative_start_us === 'number'
    ? event.shot_relative_start_us
    : Math.max(0, event.source_start_us - shot.source_start_us)
  await selectShot(shot, localUs, event.id)
}

function applyPendingSeek(): void {
  const video = videoRef.value
  if (!video || pendingSeekUs.value === null) return
  video.currentTime = pendingSeekUs.value / 1_000_000
  pendingSeekUs.value = null
}

function evidenceTitle(item: BreakdownEvidenceLink): string {
  return `${item.source_type} · ${item.role}${typeof item.confidence === 'number' ? ` · ${confidenceText(item.confidence)}` : ''}`
}

watch(
  () => props.episodes.map((item) => item.id).join('|'),
  async () => {
    if (!props.episodes.length) {
      selectedEpisodeId.value = ''
      runs.value = []
      applyDraft(null)
      return
    }
    const currentStillExists = props.episodes.some((item) => item.id === selectedEpisodeId.value)
    if (!currentStillExists) selectedEpisodeId.value = props.episodes[0].id
    await loadEpisode(selectedEpisodeId.value)
  },
  { immediate: true },
)
</script>

<template>
  <section class="breakdown-draft">
    <header class="breakdown-head">
      <div>
        <div class="breakdown-eyebrow">P3 · 02 拉片</div>
        <h2>Structured Draft</h2>
        <p>按 Scene → Shot → 匿名人物 → 时间轴事件查看 AI 拉片结果。这里是只读 Draft，不是 Final Character / Scene / Prop。</p>
      </div>
      <div v-if="draft" class="breakdown-head-stats">
        <span><b>{{ stats.segments }}</b> Scene</span>
        <span><b>{{ stats.shots }}</b> Shots</span>
        <span><b>{{ stats.subjects }}</b> 匿名主体</span>
        <span><b>{{ stats.events }}</b> 事件</span>
        <span><b>{{ stats.props }}</b> 道具提示</span>
      </div>
    </header>

    <div v-if="error" class="breakdown-alert danger">{{ error }}</div>
    <div v-if="loading" class="breakdown-loading"><span></span>正在读取 Structured Draft…</div>

    <div class="breakdown-layout">
      <aside class="breakdown-sidebar">
        <section class="breakdown-panel">
          <div class="panel-title"><strong>剧集</strong><span>{{ episodes.length }}</span></div>
          <div v-if="episodes.length" class="episode-list">
            <button
              v-for="episode in episodes"
              :key="episode.id"
              :class="['episode-button', { active: episode.id === selectedEpisodeId }]"
              @click="chooseEpisode(episode.id)"
            >
              <b>E{{ String(episode.sort_order).padStart(2, '0') }}</b>
              <span>{{ episode.title }}</span>
              <small>{{ episode.shot_count }} Shots</small>
            </button>
          </div>
          <div v-else class="mini-empty">还没有导入剧集。</div>
        </section>

        <section class="breakdown-panel run-panel">
          <div class="panel-title"><strong>Draft 历史</strong><span>{{ runs.length }}</span></div>
          <div v-if="runs.length" class="run-list">
            <button
              v-for="run in runs"
              :key="run.id"
              :class="['run-button', { active: run.id === selectedRunId }]"
              @click="chooseRun(run.id)"
            >
              <div>
                <b>{{ revisionLabel(run) }}</b>
                <i :class="runStatusClass(run.status)">{{ runStatusLabel(run.status) }}</i>
              </div>
              <span>{{ run.pipeline_profile || run.schema_version }}</span>
              <small>{{ run.source_shot_revision?.is_current ? '当前 Shot Revision' : '历史 Shot Revision' }}</small>
            </button>
          </div>
          <div v-else class="mini-empty">当前剧集还没有 Breakdown Run。</div>
        </section>

        <div class="draft-boundary-note">
          <strong>Draft 边界</strong>
          <p>人物 A/B 只是本 Scene 内的匿名主体；场景和道具也只是提示。P4/P5 才会做跨镜资产识别与正式回填。</p>
        </div>
      </aside>

      <main class="breakdown-main">
        <div v-if="!draft && !loading" class="breakdown-empty">
          <strong>暂无可读取的 Structured Draft</strong>
          <p>P3 不会伪造结果，也不会在读取时自动运行模型。完成对应剧集的 Breakdown 分析后，这里会直接展示已经持久化的 Draft。</p>
        </div>

        <template v-else-if="draft">
          <div :class="['run-banner', runStatusClass(draft.run.status)]">
            <div>
              <strong>{{ revisionLabel(draft.run) }} · {{ runStatusLabel(draft.run.status) }}</strong>
              <span>
                Draft 固定锚定 {{ draft.run.source_shot_revision?.is_current ? '当前' : '历史' }} ShotRevision；
                {{ draft.run.is_current ? '这是 Episode Current Draft。' : '这是只读历史 Draft。' }}
              </span>
            </div>
            <div class="run-banner-meta">
              <span>{{ draft.run.schema_version }}</span>
              <span v-if="unassignedCount">⚠ {{ unassignedCount }} 条未归属数据</span>
            </div>
          </div>

          <div v-if="warningLines.length" class="breakdown-alert warning">
            <strong>Run 提示</strong>
            <span v-for="line in warningLines.slice(0, 5)" :key="line">{{ line }}</span>
            <span v-if="warningLines.length > 5">还有 {{ warningLines.length - 5 }} 条提示</span>
          </div>

          <div v-if="draft.run.error_message" class="breakdown-alert danger">
            <strong>Run 错误</strong>{{ draft.run.error_message }}
          </div>

          <div v-if="draft.scene_segments.length" class="scene-stack">
            <article v-for="segment in draft.scene_segments" :key="segment.id" class="scene-card">
              <header class="scene-head">
                <div class="scene-number">SCENE {{ String(segment.ordinal).padStart(2, '0') }}</div>
                <div class="scene-title">
                  <strong>{{ sceneLabel(segment) }}</strong>
                  <span>{{ timecode(segment.source_start_us) }} → {{ timecode(segment.source_end_us) }} · {{ durationText(segment.source_start_us, segment.source_end_us) }}</span>
                </div>
                <div class="confidence">{{ confidenceText(segment.confidence) }}</div>
              </header>

              <div class="scene-copy">
                <p v-if="segment.summary"><b>场景摘要</b>{{ segment.summary }}</p>
                <p v-if="segment.environment_description"><b>环境</b>{{ segment.environment_description }}</p>
                <div class="hint-row">
                  <span v-if="segment.scene_function_hint" class="hint">功能 · {{ segment.scene_function_hint }}</span>
                  <span v-if="segment.interior_exterior" class="hint">{{ segment.interior_exterior }}</span>
                  <span v-if="segment.time_of_day" class="hint">{{ segment.time_of_day }}</span>
                </div>
              </div>

              <div v-if="segment.subjects.length" class="subject-strip">
                <div class="strip-label">匿名人物 Draft</div>
                <div class="subject-chip-list">
                  <div v-for="subject in segment.subjects" :key="subject.id" class="subject-chip">
                    <strong>{{ subject.display_label }}</strong>
                    <span>{{ subject.role_hint || '角色关系待资产阶段确认' }}</span>
                    <small v-if="subject.appearance_summary">{{ subject.appearance_summary }}</small>
                  </div>
                </div>
              </div>

              <div v-if="segment.prop_hints.length" class="prop-strip">
                <div class="strip-label">道具提示 Draft</div>
                <div class="prop-chip-list">
                  <span v-for="prop in segment.prop_hints" :key="prop.id" class="prop-chip">
                    <b>{{ prop.label_hint }}</b>
                    <small v-if="prop.importance">{{ prop.importance }}</small>
                  </span>
                </div>
              </div>

              <div class="shot-stack">
                <article
                  v-for="shot in segment.shots"
                  :key="shot.id"
                  :class="['draft-shot', { active: shot.id === selectedShotId }]"
                  @click="selectShot(shot)"
                >
                  <button class="shot-preview" type="button" @click.stop="selectShot(shot)">
                    <img v-if="shot.source_shot_revision_item?.thumbnail_url" :src="shot.source_shot_revision_item.thumbnail_url" alt="" />
                    <span v-else>SHOT</span>
                  </button>

                  <div class="shot-body">
                    <div class="shot-meta">
                      <strong>SHOT {{ String(shot.shot_ordinal_snapshot).padStart(4, '0') }}</strong>
                      <span>{{ timecode(shot.source_start_us) }} → {{ timecode(shot.source_end_us) }}</span>
                      <i>{{ confidenceText(shot.confidence) }}</i>
                    </div>

                    <p v-if="shot.summary" class="shot-summary">{{ shot.summary }}</p>
                    <p v-if="shot.visual_description" class="shot-visual">{{ shot.visual_description }}</p>

                    <div class="shot-hints">
                      <span v-if="shot.shot_type_hint">景别 · {{ shot.shot_type_hint }}</span>
                      <span v-if="shot.camera_motion_hint">运镜 · {{ shot.camera_motion_hint }}</span>
                      <span v-if="shot.narrative_function_hint">叙事 · {{ shot.narrative_function_hint }}</span>
                    </div>

                    <div v-if="shot.subjects.length" class="shot-subjects">
                      <div v-for="presence in shot.subjects" :key="presence.id" class="shot-subject-row">
                        <b>{{ presence.subject.display_label || '匿名主体' }}</b>
                        <span>{{ presence.activity_summary || presence.speaking_state || '出现在镜头中' }}</span>
                        <small>{{ presence.visibility || '可见状态未知' }} · {{ confidenceText(presence.confidence) }}</small>
                      </div>
                    </div>

                    <div v-if="shot.events.length" class="event-list">
                      <button
                        v-for="event in shot.events"
                        :key="event.id"
                        type="button"
                        :class="['event-row', event.event_type.toLowerCase(), { active: isSelectedEvent(event) }]"
                        @click.stop="jumpToEvent(shot, event)"
                      >
                        <span class="event-time">{{ timecode(event.source_start_us) }}</span>
                        <span class="event-type">{{ eventTypeLabel(event.event_type) }}</span>
                        <span class="event-copy">
                          <b v-if="eventSpeakers(event)">{{ eventSpeakers(event) }}：</b>{{ eventContent(event) }}
                        </span>
                        <span class="event-origin">{{ event.origin }}</span>
                      </button>
                    </div>
                    <div v-else class="event-empty">当前 Shot 没有时间轴事件。</div>
                  </div>
                </article>
              </div>
            </article>
          </div>

          <div v-else class="breakdown-empty compact">
            <strong>这个 Run 没有可展示的 Scene Segment</strong>
            <p>FAILED / PROCESSING 历史 Run 可能只有状态和错误信息；P3 会保留它们，但不会把不完整数据伪装成可用 Draft。</p>
          </div>
        </template>
      </main>

      <aside class="breakdown-inspector">
        <template v-if="draft && selectedShot">
          <div class="inspector-title">
            <div>
              <span>{{ revisionLabel(draft.run) }} Reference Clip</span>
              <strong>SHOT {{ String(selectedShot.shot_ordinal_snapshot).padStart(4, '0') }}</strong>
            </div>
            <i :class="runStatusClass(draft.run.status)">{{ draft.run.source_shot_revision?.is_current ? 'CURRENT REVISION' : 'HISTORY REVISION' }}</i>
          </div>

          <div class="reference-player">
            <video
              v-if="selectedReferenceUrl"
              ref="videoRef"
              :key="selectedShot.source_shot_revision_item_id"
              :src="selectedReferenceUrl"
              controls
              preload="metadata"
              @loadedmetadata="applyPendingSeek"
            ></video>
            <div v-else class="reference-missing">这个历史 ShotRevisionItem 没有可用 Reference Clip。</div>
            <div class="reference-meta">
              <span>Source {{ timecode(selectedShot.source_start_us) }} → {{ timecode(selectedShot.source_end_us) }}</span>
              <b>{{ durationText(selectedShot.source_start_us, selectedShot.source_end_us) }}</b>
            </div>
          </div>

          <div class="inspector-note">
            <strong>时间回看规则</strong>
            <p>点击左侧任意对白 / 动作 / OCR / 画面事件，会跳到这个 Draft 当时绑定的历史 Reference Clip，而不是猜当前镜头时间。</p>
          </div>

          <section class="inspector-section">
            <div class="inspector-section-title"><strong>Scene Draft</strong><span>{{ selectedSegment ? `SCENE ${String(selectedSegment.ordinal).padStart(2, '0')}` : '—' }}</span></div>
            <p>{{ selectedSegment?.summary || selectedSegment?.environment_description || '暂无场景描述' }}</p>
            <div v-if="selectedSegment" class="inspector-tags">
              <span v-if="selectedSegment.location_hint">{{ selectedSegment.location_hint }}</span>
              <span v-if="selectedSegment.interior_exterior">{{ selectedSegment.interior_exterior }}</span>
              <span v-if="selectedSegment.time_of_day">{{ selectedSegment.time_of_day }}</span>
            </div>
          </section>

          <section class="inspector-section">
            <div class="inspector-section-title"><strong>Shot Draft</strong><span>{{ confidenceText(selectedShot.confidence) }}</span></div>
            <p>{{ selectedShot.summary || '暂无 Shot 摘要' }}</p>
            <p v-if="selectedShot.visual_description" class="muted">{{ selectedShot.visual_description }}</p>
          </section>

          <section class="inspector-section">
            <div class="inspector-section-title"><strong>人物 / 动作</strong><span>{{ selectedShot.subjects.length }}</span></div>
            <div v-if="selectedShot.subjects.length" class="inspector-list">
              <div v-for="presence in selectedShot.subjects" :key="presence.id">
                <b>{{ presence.subject.display_label || '匿名主体' }}</b>
                <span>{{ presence.activity_summary || '暂无动作摘要' }}</span>
                <small>{{ presence.speaking_state || '说话状态未知' }} · {{ presence.screen_position || '位置未知' }}</small>
              </div>
            </div>
            <p v-else class="muted">当前 Shot 没有匿名人物记录。</p>
          </section>

          <section class="inspector-section">
            <div class="inspector-section-title"><strong>道具提示</strong><span>{{ selectedShot.prop_occurrences.length }}</span></div>
            <div v-if="selectedShot.prop_occurrences.length" class="inspector-list">
              <div v-for="occurrence in selectedShot.prop_occurrences" :key="occurrence.id">
                <b>{{ occurrence.prop_hint.label_hint || '未命名道具提示' }}</b>
                <span>{{ occurrence.interaction_summary || '仅检测到出现，暂无交互摘要' }}</span>
                <small>{{ occurrence.screen_position_hint || '位置未知' }} · {{ confidenceText(occurrence.confidence) }}</small>
              </div>
            </div>
            <p v-else class="muted">当前 Shot 没有道具出现提示。</p>
          </section>

          <details class="evidence-details">
            <summary>Evidence provenance <span>{{ selectedEvidenceLinks.length }}</span></summary>
            <div v-if="selectedEvidenceLinks.length" class="evidence-list">
              <div v-for="item in selectedEvidenceLinks" :key="item.id">
                <strong>{{ evidenceTitle(item) }}</strong>
                <span>{{ item.source_id }}</span>
              </div>
            </div>
            <p v-else>当前选中 Shot 没有直接挂载的 EvidenceLink；这不等于整个 Run 没有 Evidence。</p>
          </details>
        </template>

        <div v-else class="inspector-empty">
          <strong>选择一个 Shot</strong>
          <p>Reference Clip、人物活动、道具提示与 Evidence provenance 会显示在这里。</p>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.breakdown-draft { display: grid; gap: 14px; min-height: 0; color: #263247; }
.breakdown-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; padding: 4px 2px; }
.breakdown-eyebrow { color: #5872a8; font-size: 11px; font-weight: 900; letter-spacing: .08em; text-transform: uppercase; }
.breakdown-head h2 { margin: 4px 0 2px; font-size: 22px; letter-spacing: -.02em; }
.breakdown-head p { margin: 0; max-width: 760px; color: #768194; font-size: 12px; line-height: 1.55; }
.breakdown-head-stats { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
.breakdown-head-stats span { border: 1px solid #e0e6ef; border-radius: 999px; padding: 6px 9px; background: #fff; color: #7b8798; font-size: 10px; white-space: nowrap; }
.breakdown-head-stats b { margin-right: 3px; color: #344158; font-size: 12px; }
.breakdown-layout { display: grid; grid-template-columns: 210px minmax(560px, 1fr) 330px; gap: 12px; min-height: 680px; align-items: start; }
.breakdown-sidebar, .breakdown-inspector { display: grid; gap: 10px; position: sticky; top: 10px; max-height: calc(100vh - 110px); overflow: auto; }
.breakdown-panel, .breakdown-inspector { border: 1px solid #e1e6ee; border-radius: 12px; background: #fff; }
.breakdown-panel { padding: 10px; }
.panel-title { display: flex; justify-content: space-between; align-items: center; padding: 1px 2px 8px; }
.panel-title strong { font-size: 11px; }
.panel-title span { min-width: 20px; text-align: center; border-radius: 999px; background: #f1f4f8; color: #778295; font-size: 9px; padding: 2px 5px; }
.episode-list, .run-list { display: grid; gap: 5px; }
.episode-button, .run-button { width: 100%; border: 1px solid transparent; border-radius: 9px; background: #f8fafc; color: #4a566a; cursor: pointer; text-align: left; }
.episode-button { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 2px 7px; align-items: center; padding: 8px; }
.episode-button b { grid-row: 1 / span 2; font-size: 10px; color: #52617b; }
.episode-button span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; font-weight: 750; }
.episode-button small { color: #919aaa; font-size: 9px; }
.episode-button.active, .run-button.active { border-color: #8eaaeb; background: #f0f5ff; box-shadow: inset 3px 0 0 #557bd1; }
.run-panel { min-height: 0; }
.run-list { max-height: 310px; overflow: auto; }
.run-button { display: grid; gap: 4px; padding: 8px; }
.run-button > div { display: flex; justify-content: space-between; gap: 6px; align-items: center; }
.run-button b { font-size: 10px; }
.run-button i { border-radius: 999px; padding: 2px 5px; font-size: 8px; font-style: normal; font-weight: 850; }
.run-button span, .run-button small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #7f8a9b; font-size: 9px; }
.mini-empty { padding: 14px 5px; color: #919aaa; font-size: 10px; line-height: 1.5; }
.draft-boundary-note, .inspector-note { border: 1px solid #d9e4fb; border-radius: 11px; padding: 10px; background: #f5f8ff; }
.draft-boundary-note strong, .inspector-note strong { color: #4466a7; font-size: 10px; }
.draft-boundary-note p, .inspector-note p { margin: 4px 0 0; color: #6e7c94; font-size: 9px; line-height: 1.55; }
.breakdown-main { min-width: 0; display: grid; gap: 10px; }
.breakdown-empty { min-height: 420px; display: grid; place-content: center; justify-items: center; gap: 7px; border: 1px dashed #d8dfe9; border-radius: 13px; background: #fbfcfd; text-align: center; padding: 30px; }
.breakdown-empty.compact { min-height: 220px; }
.breakdown-empty strong { color: #526076; font-size: 14px; }
.breakdown-empty p { max-width: 560px; margin: 0; color: #8a95a5; font-size: 11px; line-height: 1.6; }
.breakdown-loading { display: flex; align-items: center; gap: 8px; border: 1px solid #dfe7f6; border-radius: 9px; padding: 8px 11px; background: #f6f9ff; color: #60739a; font-size: 10px; }
.breakdown-loading span { width: 10px; height: 10px; border: 2px solid #a9bce4; border-top-color: transparent; border-radius: 50%; animation: spin .8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.breakdown-alert { display: grid; gap: 3px; border-radius: 10px; padding: 9px 11px; font-size: 10px; line-height: 1.5; }
.breakdown-alert.warning { border: 1px solid #efd59a; background: #fff9eb; color: #805c1c; }
.breakdown-alert.danger { border: 1px solid #efb8b8; background: #fff3f3; color: #a14343; }
.run-banner { display: flex; justify-content: space-between; gap: 15px; align-items: center; border: 1px solid #dce3ed; border-radius: 11px; padding: 10px 12px; background: #fff; }
.run-banner > div:first-child { display: grid; gap: 2px; }
.run-banner strong { font-size: 11px; }
.run-banner span { color: #778397; font-size: 9px; line-height: 1.45; }
.run-banner.ready { border-color: #bde2ce; background: #f5fcf8; }
.run-banner.warning { border-color: #efd59a; background: #fffaf0; }
.run-banner.stale { border-color: #d5d9e1; background: #f7f8fa; }
.run-banner.danger { border-color: #efb8b8; background: #fff5f5; }
.run-banner-meta { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; }
.run-banner-meta span { border-radius: 999px; background: rgba(255,255,255,.72); padding: 4px 7px; white-space: nowrap; }
.ready { background: #e7f7ee; color: #2d7b51; }
.warning { background: #fff0c9; color: #92630b; }
.danger { background: #ffe2e2; color: #a43f3f; }
.stale { background: #eceff3; color: #697487; }
.neutral { background: #e8effb; color: #526c9d; }
.scene-stack { display: grid; gap: 12px; }
.scene-card { overflow: hidden; border: 1px solid #dfe5ed; border-radius: 13px; background: #fff; box-shadow: 0 4px 18px rgba(41, 55, 82, .035); }
.scene-head { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 10px; align-items: center; padding: 10px 12px; border-bottom: 1px solid #e8ecf2; background: #fafbfd; }
.scene-number { border-radius: 7px; background: #34445e; color: #fff; padding: 5px 7px; font-size: 9px; font-weight: 900; letter-spacing: .04em; }
.scene-title { display: grid; gap: 2px; }
.scene-title strong { font-size: 12px; color: #354156; }
.scene-title span { font-size: 9px; color: #8a94a4; }
.confidence { font-size: 9px; color: #6e7c92; font-weight: 850; }
.scene-copy { display: grid; gap: 4px; padding: 10px 12px 2px; }
.scene-copy p { display: grid; grid-template-columns: 62px minmax(0, 1fr); gap: 8px; margin: 0; color: #606c7e; font-size: 10px; line-height: 1.55; }
.scene-copy b { color: #3e4c62; }
.hint-row, .shot-hints, .inspector-tags { display: flex; flex-wrap: wrap; gap: 5px; }
.hint, .shot-hints span, .inspector-tags span { border-radius: 999px; background: #f1f4f8; color: #68758a; padding: 3px 7px; font-size: 9px; }
.subject-strip, .prop-strip { display: grid; grid-template-columns: 90px minmax(0, 1fr); gap: 8px; align-items: start; padding: 8px 12px 0; }
.strip-label { color: #8993a2; font-size: 9px; font-weight: 850; padding-top: 4px; }
.subject-chip-list, .prop-chip-list { display: flex; flex-wrap: wrap; gap: 5px; }
.subject-chip { min-width: 150px; max-width: 260px; display: grid; gap: 1px; border: 1px solid #e1e7f1; border-radius: 8px; padding: 5px 7px; background: #fafcff; }
.subject-chip strong { color: #3f5273; font-size: 9px; }
.subject-chip span, .subject-chip small { color: #7f8a9c; font-size: 8px; line-height: 1.4; }
.prop-chip { display: inline-flex; gap: 5px; align-items: center; border: 1px solid #e7dfcb; border-radius: 999px; padding: 4px 7px; background: #fffaf0; color: #7b6537; font-size: 9px; }
.prop-chip small { color: #a08a5f; }
.shot-stack { display: grid; gap: 7px; padding: 11px 12px 12px; }
.draft-shot { display: grid; grid-template-columns: 132px minmax(0, 1fr); gap: 10px; border: 1px solid #e2e7ee; border-radius: 10px; padding: 8px; background: #fff; cursor: pointer; transition: border-color .12s ease, box-shadow .12s ease; }
.draft-shot:hover { border-color: #b7c7e8; }
.draft-shot.active { border-color: #6f91dc; box-shadow: 0 0 0 2px rgba(91, 126, 203, .10); }
.shot-preview { width: 132px; aspect-ratio: 16/9; overflow: hidden; display: grid; place-items: center; border: 0; border-radius: 7px; background: #202938; color: #8e9bb0; cursor: pointer; padding: 0; }
.shot-preview img { width: 100%; height: 100%; object-fit: cover; }
.shot-preview span { font-size: 9px; font-weight: 850; }
.shot-body { min-width: 0; display: grid; gap: 5px; }
.shot-meta { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px; }
.shot-meta strong { color: #34445c; font-size: 10px; }
.shot-meta span { color: #8b96a6; font-size: 9px; }
.shot-meta i { margin-left: auto; color: #758297; font-size: 8px; font-style: normal; font-weight: 850; }
.shot-summary, .shot-visual { margin: 0; line-height: 1.45; }
.shot-summary { color: #3e4b5f; font-size: 10px; font-weight: 700; }
.shot-visual { color: #768296; font-size: 9px; }
.shot-subjects { display: grid; gap: 3px; margin-top: 2px; }
.shot-subject-row { display: grid; grid-template-columns: 68px minmax(0, 1fr) auto; gap: 6px; align-items: center; border-left: 2px solid #a8bde8; padding: 3px 6px; background: #f8faff; }
.shot-subject-row b { color: #4d628a; font-size: 9px; }
.shot-subject-row span { min-width: 0; color: #667389; font-size: 9px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.shot-subject-row small { color: #929baa; font-size: 8px; }
.event-list { display: grid; gap: 3px; margin-top: 3px; }
.event-row { width: 100%; display: grid; grid-template-columns: 70px 62px minmax(0, 1fr) 46px; gap: 6px; align-items: start; border: 1px solid #e4e8ef; border-radius: 7px; padding: 5px 6px; background: #fbfcfe; color: #566277; cursor: pointer; text-align: left; }
.event-row:hover { border-color: #aabde5; background: #f7faff; }
.event-row.active { border-color: #6f91dc; background: #edf3ff; }
.event-row.dialogue { border-left: 3px solid #7897dd; }
.event-row.action { border-left: 3px solid #7eb79c; }
.event-row.ocr { border-left: 3px solid #c1a364; }
.event-row.visual { border-left: 3px solid #9b8ac9; }
.event-row.audio_event { border-left: 3px solid #b48d8d; }
.event-time, .event-type, .event-origin { color: #8b95a5; font-size: 8px; font-variant-numeric: tabular-nums; }
.event-type { color: #536781; font-weight: 850; }
.event-copy { min-width: 0; color: #4b586c; font-size: 9px; line-height: 1.4; }
.event-copy b { color: #425b8c; }
.event-origin { justify-self: end; }
.event-empty { color: #9aa3b1; font-size: 9px; padding: 3px 0; }
.breakdown-inspector { padding: 10px; }
.inspector-title { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.inspector-title > div { display: grid; gap: 2px; }
.inspector-title span { color: #8a95a4; font-size: 8px; text-transform: uppercase; letter-spacing: .05em; }
.inspector-title strong { color: #34445d; font-size: 12px; }
.inspector-title i { border-radius: 999px; padding: 3px 6px; font-size: 7px; font-style: normal; font-weight: 900; }
.reference-player { overflow: hidden; border: 1px solid #dfe5ed; border-radius: 9px; background: #121821; }
.reference-player video { display: block; width: 100%; aspect-ratio: 16/9; background: #0c1017; }
.reference-missing { aspect-ratio: 16/9; display: grid; place-items: center; padding: 20px; color: #8793a5; font-size: 9px; text-align: center; }
.reference-meta { display: flex; justify-content: space-between; gap: 8px; padding: 6px 8px; color: #aeb8c8; background: #1a2330; font-size: 8px; }
.reference-meta b { color: #fff; }
.inspector-section { display: grid; gap: 5px; border-top: 1px solid #edf0f4; padding-top: 9px; }
.inspector-section-title { display: flex; justify-content: space-between; align-items: center; }
.inspector-section-title strong { color: #46546a; font-size: 10px; }
.inspector-section-title span { color: #8a95a5; font-size: 8px; }
.inspector-section p { margin: 0; color: #5f6c80; font-size: 9px; line-height: 1.55; }
.inspector-section p.muted, p.muted { color: #8a95a5; }
.inspector-list { display: grid; gap: 4px; }
.inspector-list > div { display: grid; gap: 2px; border: 1px solid #e6eaf0; border-radius: 7px; padding: 6px 7px; background: #fbfcfd; }
.inspector-list b { color: #475b7b; font-size: 9px; }
.inspector-list span { color: #677489; font-size: 9px; line-height: 1.4; }
.inspector-list small { color: #929baa; font-size: 8px; }
.evidence-details { border-top: 1px solid #edf0f4; padding-top: 9px; }
.evidence-details summary { cursor: pointer; color: #58677e; font-size: 9px; font-weight: 800; }
.evidence-details summary span { margin-left: 4px; border-radius: 999px; background: #eef2f7; padding: 2px 5px; }
.evidence-details p { color: #8a95a5; font-size: 8px; line-height: 1.5; }
.evidence-list { display: grid; gap: 4px; margin-top: 6px; }
.evidence-list > div { display: grid; gap: 1px; padding: 5px 6px; border-radius: 6px; background: #f7f9fc; }
.evidence-list strong { color: #596a84; font-size: 8px; }
.evidence-list span { overflow: hidden; text-overflow: ellipsis; color: #929baa; font-size: 7px; white-space: nowrap; }
.inspector-empty { min-height: 320px; display: grid; place-content: center; gap: 5px; text-align: center; padding: 20px; }
.inspector-empty strong { color: #5c697c; font-size: 11px; }
.inspector-empty p { margin: 0; color: #929baa; font-size: 9px; line-height: 1.5; }
@media (max-width: 1500px) {
  .breakdown-layout { grid-template-columns: 190px minmax(500px, 1fr) 300px; }
  .draft-shot { grid-template-columns: 110px minmax(0, 1fr); }
  .shot-preview { width: 110px; }
  .event-row { grid-template-columns: 64px 54px minmax(0, 1fr); }
  .event-origin { display: none; }
}
@media (max-width: 1180px) {
  .breakdown-layout { grid-template-columns: 180px minmax(0, 1fr); }
  .breakdown-inspector { position: static; grid-column: 1 / -1; max-height: none; }
}
@media (max-width: 820px) {
  .breakdown-head { align-items: flex-start; flex-direction: column; }
  .breakdown-head-stats { justify-content: flex-start; }
  .breakdown-layout { grid-template-columns: 1fr; }
  .breakdown-sidebar { position: static; max-height: none; grid-template-columns: 1fr 1fr; }
  .draft-boundary-note { grid-column: 1 / -1; }
  .draft-shot { grid-template-columns: 1fr; }
  .shot-preview { width: 100%; max-width: 280px; }
  .subject-strip, .prop-strip { grid-template-columns: 1fr; }
}
</style>
