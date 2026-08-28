<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { BreakdownSceneSegment, BreakdownShotDraft, BreakdownTimelineEvent } from '../types/breakdown'

const props = defineProps<{
  segment: BreakdownSceneSegment | null
  shot: BreakdownShotDraft | null
  selectedEventId: string
}>()

const emit = defineEmits<{
  (event: 'select-event', item: BreakdownTimelineEvent): void
}>()

const eventFilter = ref('ALL')

watch(
  () => props.shot?.id,
  () => { eventFilter.value = 'ALL' },
)

const filterDefinitions = computed(() => {
  const events = props.shot?.events ?? []
  const count = (key: string) => events.filter((event) => matchesFilter(event, key)).length
  return [
    { key: 'ALL', label: '全部', count: events.length },
    { key: 'VLM', label: 'VLM', count: count('VLM') },
    { key: 'DIALOGUE', label: '对白', count: count('DIALOGUE') },
    { key: 'OCR', label: 'OCR', count: count('OCR') },
    { key: 'ACTION', label: '动作', count: count('ACTION') },
    { key: 'AUDIO_EVENT', label: '声音', count: count('AUDIO_EVENT') },
  ]
})

const visibleEvents = computed(() => {
  const events = props.shot?.events ?? []
  if (eventFilter.value === 'ALL') return events
  return events.filter((event) => matchesFilter(event, eventFilter.value))
})

const hasSceneSupplement = computed(() => {
  const segment = props.segment
  if (!segment) return false
  const hasSubjectDetail = segment.subjects.some((item) => (
    Boolean(item.appearance_summary) || Boolean(item.speaking_state_summary) || typeof item.confidence === 'number'
  ))
  const hasPropDetail = segment.prop_hints.some((item) => (
    Boolean(item.narrative_reason) || Boolean(item.normalized_hint) || typeof item.confidence === 'number'
  ))
  return hasSubjectDetail || hasPropDetail
})

function matchesFilter(event: BreakdownTimelineEvent, key: string): boolean {
  if (key === 'VLM') return event.origin.toUpperCase().includes('VLM') || event.event_type === 'VISUAL'
  return event.event_type === key
}

function timecode(us: number | null | undefined): string {
  if (us === null || us === undefined) return '—'
  const totalMs = Math.max(0, Math.round(us / 1000))
  const minutes = Math.floor(totalMs / 60_000)
  const seconds = Math.floor((totalMs % 60_000) / 1000)
  const ms = totalMs % 1000
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function durationText(startUs: number, endUs: number): string {
  return `${Math.max(0, (endUs - startUs) / 1_000_000).toFixed(2)}s`
}

function confidenceText(value: number | null | undefined): string {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—'
}

function sceneTitle(segment: BreakdownSceneSegment): string {
  return [segment.location_hint, segment.interior_exterior, segment.time_of_day].filter(Boolean).join(' · ') || '场景信息待补充'
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

function originClass(event: BreakdownTimelineEvent): string {
  const origin = event.origin.toUpperCase()
  if (event.event_type === 'OCR' || origin.includes('OCR')) return 'ocr'
  if (event.event_type === 'DIALOGUE' || origin.includes('ASR')) return 'asr'
  if (event.event_type === 'ACTION') return 'action'
  if (origin.includes('VLM') || event.event_type === 'VISUAL') return 'vlm'
  return 'other'
}
</script>

<template>
  <main class="shot-workspace-v1">
    <div v-if="!segment || !shot" class="workspace-empty">
      <strong>选择一个 Scene / Shot</strong>
      <p>左侧选择镜头后，这里会显示该历史 Draft 的 Scene Context、Shot 语义、匿名人物和 Evidence Timeline。</p>
    </div>

    <template v-else>
      <section class="scene-context-card">
        <header class="context-head">
          <div class="context-title">
            <span>SCENE {{ String(segment.ordinal).padStart(2, '0') }}</span>
            <strong>{{ sceneTitle(segment) }}</strong>
            <small>{{ timecode(segment.source_start_us) }} → {{ timecode(segment.source_end_us) }} · {{ durationText(segment.source_start_us, segment.source_end_us) }}</small>
          </div>
          <div class="context-confidence">AI Confidence {{ confidenceText(segment.confidence) }}</div>
        </header>

        <div class="scene-description-grid">
          <div>
            <span>场景摘要</span>
            <p>{{ segment.summary || '暂无场景摘要' }}</p>
          </div>
          <div>
            <span>环境描述</span>
            <p>{{ segment.environment_description || '暂无环境描述' }}</p>
          </div>
          <div>
            <span>叙事功能</span>
            <p>{{ segment.scene_function_hint || '暂无叙事功能提示' }}</p>
          </div>
        </div>

        <div class="scene-draft-row">
          <div class="scene-draft-group">
            <span class="group-label">匿名人物 Draft（本场景）</span>
            <div v-if="segment.subjects.length" class="subject-chips">
              <span v-for="subject in segment.subjects" :key="subject.id" class="subject-chip">
                <b>{{ subject.display_label }}</b>
                <small v-if="subject.role_hint">{{ subject.role_hint }}</small>
              </span>
            </div>
            <small v-else class="muted-inline">本场景没有匿名人物记录</small>
          </div>

          <div class="scene-draft-group props-group">
            <span class="group-label">道具提示 Draft（本场景）</span>
            <div v-if="segment.prop_hints.length" class="prop-chips">
              <span v-for="prop in segment.prop_hints" :key="prop.id" class="prop-chip">
                <b>{{ prop.label_hint }}</b>
                <small v-if="prop.importance">{{ prop.importance }}</small>
              </span>
            </div>
            <small v-else class="muted-inline">本场景没有道具提示</small>
          </div>
        </div>

        <details v-if="hasSceneSupplement" class="scene-supplement">
          <summary>场景人物 / 道具补充信息 <span>展开查看 appearance、说话状态、叙事原因和置信度</span></summary>
          <div class="scene-supplement-grid">
            <div v-for="subject in segment.subjects" :key="`subject-detail-${subject.id}`" class="supplement-item">
              <strong>{{ subject.display_label }}</strong>
              <p>{{ subject.appearance_summary || subject.role_hint || '暂无外观/角色关系补充' }}</p>
              <small>说话状态 {{ subject.speaking_state_summary || 'UNKNOWN' }} · Confidence {{ confidenceText(subject.confidence) }}</small>
            </div>
            <div v-for="prop in segment.prop_hints" :key="`prop-detail-${prop.id}`" class="supplement-item prop-detail">
              <strong>{{ prop.label_hint }}</strong>
              <p>{{ prop.narrative_reason || prop.normalized_hint || '暂无叙事原因补充' }}</p>
              <small>{{ prop.importance || 'importance 未标注' }} · Confidence {{ confidenceText(prop.confidence) }}</small>
            </div>
          </div>
        </details>
      </section>

      <section class="shot-detail-card">
        <header class="shot-detail-head">
          <div>
            <strong>SHOT {{ String(shot.shot_ordinal_snapshot).padStart(4, '0') }}</strong>
            <span>{{ timecode(shot.source_start_us) }} → {{ timecode(shot.source_end_us) }} · {{ durationText(shot.source_start_us, shot.source_end_us) }}</span>
          </div>
          <div class="shot-hint-badges">
            <span v-if="shot.shot_type_hint">景别 · {{ shot.shot_type_hint }}</span>
            <span v-if="shot.camera_motion_hint">运镜 · {{ shot.camera_motion_hint }}</span>
            <span v-if="shot.narrative_function_hint">叙事 · {{ shot.narrative_function_hint }}</span>
            <span class="shot-confidence">Confidence · {{ confidenceText(shot.confidence) }}</span>
          </div>
        </header>

        <div class="shot-overview-grid">
          <div class="shot-image">
            <img v-if="shot.source_shot_revision_item?.thumbnail_url" :src="shot.source_shot_revision_item.thumbnail_url" alt="Shot thumbnail" />
            <div v-else class="shot-image-empty">SHOT</div>
          </div>

          <div class="shot-copy">
            <span>Shot 摘要</span>
            <strong>{{ shot.summary || '暂无 Shot 摘要' }}</strong>
            <span>视觉描述</span>
            <p>{{ shot.visual_description || '暂无视觉描述' }}</p>
          </div>

          <div class="shot-subject-panel">
            <span class="panel-kicker">镜头中人物 Draft</span>
            <div v-if="shot.subjects.length" class="shot-subject-list">
              <div v-for="presence in shot.subjects" :key="presence.id" class="shot-subject-item">
                <div>
                  <b>{{ presence.subject.display_label || '匿名主体' }}</b>
                  <i>{{ presence.visibility || 'UNKNOWN' }}</i>
                </div>
                <p>{{ presence.activity_summary || '暂无动作摘要' }}</p>
                <small>
                  位置 {{ presence.screen_position || '未知' }} · 说话状态 {{ presence.speaking_state || 'UNKNOWN' }} · Confidence {{ confidenceText(presence.confidence) }}
                </small>
              </div>
            </div>
            <p v-else class="panel-empty">当前 Shot 没有匿名人物记录。</p>

            <div v-if="shot.prop_occurrences.length" class="shot-prop-box">
              <span>道具出现 / 交互 Draft</span>
              <div class="shot-prop-list">
                <div v-for="item in shot.prop_occurrences" :key="item.id" class="shot-prop-item">
                  <b>{{ item.prop_hint.label_hint || '未命名道具' }}</b>
                  <small>{{ item.interaction_summary || '仅检测到出现' }}</small>
                  <small>位置 {{ item.screen_position_hint || '未知' }} · Confidence {{ confidenceText(item.confidence) }}</small>
                </div>
              </div>
            </div>
          </div>
        </div>

        <section class="timeline-section">
          <header class="timeline-head">
            <div>
              <strong>镜头时间轴</strong>
              <span>Evidence · 点击事件会同步右侧详情并跳转 Reference Clip</span>
            </div>
            <div class="timeline-filters">
              <button
                v-for="filter in filterDefinitions"
                :key="filter.key"
                type="button"
                :class="{ active: eventFilter === filter.key }"
                :disabled="filter.count === 0 && filter.key !== 'ALL'"
                @click="eventFilter = filter.key"
              >{{ filter.label }} <b>{{ filter.count }}</b></button>
            </div>
          </header>

          <div v-if="visibleEvents.length" class="timeline-list">
            <button
              v-for="event in visibleEvents"
              :key="event.id"
              type="button"
              :class="['timeline-row', originClass(event), { active: selectedEventId === event.id }]"
              :title="`${eventTypeLabel(event.event_type)} · ${eventContent(event)} · Confidence ${confidenceText(event.confidence)}`"
              @click="emit('select-event', event)"
            >
              <span class="timeline-play">▶</span>
              <span class="timeline-time">{{ timecode(event.source_start_us) }}</span>
              <span class="timeline-badge">{{ eventTypeLabel(event.event_type) }}</span>
              <span class="timeline-speaker">{{ eventSpeakers(event) || event.origin }}</span>
              <span class="timeline-copy">{{ eventContent(event) }}</span>
              <span class="timeline-origin">{{ event.origin }}</span>
              <span class="timeline-arrow">›</span>
            </button>
          </div>
          <div v-else class="timeline-empty">当前筛选没有 Timeline Event。</div>
        </section>
      </section>
    </template>
  </main>
</template>

<style scoped>
.shot-workspace-v1 { min-width: 0; height: 100%; min-height: 0; overflow: auto; display: grid; align-content: start; gap: 10px; padding-right: 2px; }
.workspace-empty { min-height: 520px; display: grid; place-content: center; justify-items: center; gap: 7px; border: 1px dashed #d9e1ed; border-radius: 14px; background: #fbfcfe; text-align: center; padding: 30px; }
.workspace-empty strong { color: #42516a; font-size: 17px; }
.workspace-empty p { max-width: 560px; margin: 0; color: #8290a4; font-size: 13px; line-height: 1.6; }
.scene-context-card, .shot-detail-card { border: 1px solid #dfe5ef; border-radius: 14px; background: #fff; box-shadow: 0 8px 28px rgba(45, 62, 94, .045); }
.context-head { display: flex; justify-content: space-between; gap: 14px; align-items: center; padding: 10px 14px; border-bottom: 1px solid #edf0f5; }
.context-title { min-width: 0; display: flex; flex-wrap: wrap; gap: 6px 9px; align-items: center; }
.context-title > span { border-radius: 7px; padding: 4px 7px; background: #253b5d; color: #fff; font-size: 12px; font-weight: 850; }
.context-title strong { color: #21324d; font-size: 16px; }
.context-title small { color: #7e8ca2; font-size: 11px; }
.context-confidence { flex: none; border-radius: 999px; padding: 4px 8px; background: #f2f5fa; color: #75839a; font-size: 11px; }
.scene-description-grid { display: grid; grid-template-columns: 1.1fr 1.2fr .9fr; gap: 12px; padding: 10px 14px 9px; }
.scene-description-grid > div { min-width: 0; }
.scene-description-grid span, .shot-copy > span, .panel-kicker, .group-label { display: block; margin-bottom: 4px; color: #66758e; font-size: 12px; font-weight: 800; }
.scene-description-grid p { margin: 0; color: #35465f; font-size: 12px; line-height: 1.45; }
.scene-draft-row { display: grid; grid-template-columns: .9fr 1.4fr; gap: 10px; padding: 0 14px 10px; }
.scene-draft-group { min-width: 0; border-top: 1px solid #eef1f5; padding-top: 8px; }
.subject-chips, .prop-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.subject-chip, .prop-chip { display: inline-flex; gap: 5px; align-items: center; border-radius: 999px; padding: 4px 7px; font-size: 11px; }
.subject-chip { background: #efebff; color: #55429b; }
.prop-chip { border: 1px solid #ecd8aa; background: #fff8e9; color: #795a1d; }
.subject-chip b, .prop-chip b { font-size: 11px; }
.subject-chip small, .prop-chip small { opacity: .72; font-size: 10px; }
.muted-inline { color: #8d99aa; font-size: 11px; }
.scene-supplement { border-top: 1px solid #edf0f5; }
.scene-supplement summary { list-style: none; cursor: pointer; padding: 8px 14px; color: #52637d; font-size: 11px; font-weight: 800; }
.scene-supplement summary::-webkit-details-marker { display: none; }
.scene-supplement summary span { margin-left: 5px; color: #8996a8; font-weight: 500; }
.scene-supplement-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; padding: 0 14px 10px; }
.supplement-item { min-width: 0; border-radius: 9px; padding: 8px 9px; background: #f7f9fd; }
.supplement-item strong { color: #3b4f6c; font-size: 11px; }
.supplement-item p { margin: 3px 0; color: #566780; font-size: 11px; line-height: 1.4; }
.supplement-item small { color: #8592a5; font-size: 10px; }
.supplement-item.prop-detail { background: #fffaf0; }
.shot-detail-card { overflow: hidden; }
.shot-detail-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 10px 14px; border-bottom: 1px solid #edf0f5; }
.shot-detail-head > div:first-child { display: flex; gap: 9px; align-items: baseline; min-width: 0; }
.shot-detail-head strong { color: #21324c; font-size: 16px; }
.shot-detail-head span { color: #8290a4; font-size: 11px; }
.shot-hint-badges { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 4px; }
.shot-hint-badges span { border-radius: 999px; padding: 4px 7px; background: #f1f5fb; color: #5d6f8c; font-size: 10px; }
.shot-hint-badges .shot-confidence { background: #eef7f1; color: #327459; }
.shot-overview-grid { display: grid; grid-template-columns: 150px minmax(250px, 1fr) minmax(220px, .78fr); gap: 12px; align-items: start; padding: 10px 14px 10px; }
.shot-image { width: 150px; height: 190px; min-height: 0; align-self: start; border-radius: 10px; overflow: hidden; background: #edf1f6; }
.shot-image img { width: 100%; height: 100%; min-height: 0; object-fit: cover; display: block; }
.shot-image-empty { height: 190px; display: grid; place-items: center; color: #8490a1; font-size: 13px; font-weight: 850; }
.shot-copy { min-width: 0; }
.shot-copy strong { display: block; margin-bottom: 8px; color: #233653; font-size: 14px; line-height: 1.45; }
.shot-copy p { margin: 0; color: #4f5f77; font-size: 12px; line-height: 1.5; }
.shot-subject-panel { min-width: 0; border-left: 1px solid #edf0f4; padding-left: 12px; }
.shot-subject-list { display: grid; gap: 5px; }
.shot-subject-item { border-radius: 9px; padding: 7px 8px; background: #f8faff; }
.shot-subject-item > div { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
.shot-subject-item b { color: #334968; font-size: 11px; }
.shot-subject-item i { border-radius: 999px; padding: 2px 6px; background: #eef2f8; color: #718098; font-size: 9px; font-style: normal; }
.shot-subject-item p { margin: 3px 0 2px; color: #4f607a; font-size: 11px; line-height: 1.35; }
.shot-subject-item small { color: #8592a6; font-size: 10px; line-height: 1.35; }
.panel-empty { color: #8a96a8; font-size: 11px; }
.shot-prop-box { margin-top: 8px; border-top: 1px solid #edf0f4; padding-top: 7px; }
.shot-prop-box > span { color: #66758e; font-size: 10px; font-weight: 800; }
.shot-prop-list { display: grid; gap: 4px; margin-top: 5px; }
.shot-prop-item { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 2px 6px; align-items: center; border-radius: 8px; padding: 5px 7px; background: #f5f2ff; }
.shot-prop-item b { grid-row: 1 / span 2; color: #5e4ca1; font-size: 10px; }
.shot-prop-item small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #786f9b; font-size: 9px; }
.timeline-section { border-top: 1px solid #dfe5ef; padding: 10px 14px 12px; background: #fbfcfe; }
.timeline-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 8px; }
.timeline-head > div:first-child { display: flex; flex-wrap: wrap; gap: 5px; align-items: baseline; }
.timeline-head strong { color: #273a58; font-size: 14px; }
.timeline-head span { color: #8a96a8; font-size: 10px; }
.timeline-filters { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 4px; }
.timeline-filters button { border: 1px solid #e1e6ef; border-radius: 999px; padding: 4px 7px; background: #fff; color: #6a7890; cursor: pointer; font-size: 10px; }
.timeline-filters button b { margin-left: 2px; font-size: 9px; }
.timeline-filters button.active { border-color: #9eb9f1; background: #edf4ff; color: #3565bc; }
.timeline-filters button:disabled { opacity: .4; cursor: default; }
.timeline-list { display: grid; gap: 4px; max-height: 260px; overflow: auto; padding-right: 2px; }
.timeline-row { --accent: #9aa6b7; width: 100%; display: grid; grid-template-columns: 20px 68px 68px 86px minmax(0, 1fr) 50px 12px; gap: 7px; align-items: center; border: 1px solid #e5e9f0; border-left: 3px solid var(--accent); border-radius: 8px; padding: 7px 8px 7px 7px; background: #fff; color: #41516a; cursor: pointer; text-align: left; }
.timeline-row:hover { background: #f9fbfe; }
.timeline-row.active { border-color: #a9c0f0; border-left-color: var(--accent); background: #f2f7ff; box-shadow: 0 0 0 2px rgba(76, 124, 221, .06); }
.timeline-row.vlm { --accent: #7954da; }
.timeline-row.asr { --accent: #3c7be0; }
.timeline-row.ocr { --accent: #d59624; }
.timeline-row.action { --accent: #28a278; }
.timeline-play { width: 17px; height: 17px; display: grid; place-items: center; border: 1px solid #bdd0f3; border-radius: 50%; color: #4778d2; font-size: 7px; }
.timeline-time { color: #8090a7; font-size: 10px; font-variant-numeric: tabular-nums; }
.timeline-badge { justify-self: start; border-radius: 999px; padding: 3px 6px; background: color-mix(in srgb, var(--accent) 12%, white); color: var(--accent); font-size: 9px; font-weight: 850; }
.timeline-speaker { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #54647c; font-size: 10px; font-weight: 750; }
.timeline-copy { min-width: 0; color: #34465f; font-size: 11px; line-height: 1.4; }
.timeline-origin { justify-self: end; color: #8190a5; font-size: 9px; }
.timeline-arrow { color: #9aa6b6; font-size: 15px; }
.timeline-empty { border: 1px dashed #dce3ed; border-radius: 9px; padding: 18px; color: #8c98a9; font-size: 11px; text-align: center; }
@media (max-width: 1420px) {
  .scene-description-grid { grid-template-columns: 1fr 1fr; }
  .scene-description-grid > div:last-child { grid-column: 1 / -1; }
  .shot-overview-grid { grid-template-columns: 145px minmax(240px, 1fr); }
  .shot-image { width: 145px; height: 180px; }
  .shot-image-empty { height: 180px; }
  .shot-subject-panel { grid-column: 1 / -1; border-left: 0; border-top: 1px solid #edf0f4; padding: 9px 0 0; }
  .shot-subject-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .shot-prop-list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 1100px) {
  .scene-supplement-grid { grid-template-columns: 1fr; }
  .shot-overview-grid { grid-template-columns: 135px 1fr; }
  .shot-image { width: 135px; height: 170px; }
  .shot-image-empty { height: 170px; }
  .timeline-row { grid-template-columns: 20px 64px 62px minmax(0, 1fr) 44px 12px; }
  .timeline-speaker { display: none; }
}
</style>