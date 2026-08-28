<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type {
  BreakdownEvidenceLink,
  BreakdownRunSummary,
  BreakdownSceneSegment,
  BreakdownShotDraft,
  BreakdownTimelineEvent,
  BreakdownUnassigned,
} from '../types/breakdown'
import {
  eventOriginLabel,
  eventTypeLabel,
  evidenceRoleLabel,
  evidenceSourceTypeLabel,
  participantRoleLabel,
} from '../utils/breakdownUiText'

const props = defineProps<{
  run: BreakdownRunSummary | null
  segment: BreakdownSceneSegment | null
  shot: BreakdownShotDraft | null
  event: BreakdownTimelineEvent | null
  evidenceLinks: BreakdownEvidenceLink[]
  unassigned: BreakdownUnassigned | null
  seekUs: number | null
  seekToken: number
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const referenceUrl = computed(() => props.shot?.source_shot_revision_item?.reference_url ?? '')
const unassignedStats = computed(() => {
  const value = props.unassigned
  if (!value) return []
  return [
    ['镜头', value.shots.length],
    ['匿名主体', value.subjects.length],
    ['人物出现记录', value.subject_presences.length],
    ['事件', value.events.length],
    ['事件参与者', value.event_participants.length],
    ['道具提示', value.prop_hints.length],
    ['道具出现记录', value.prop_occurrences.length],
  ] as Array<[string, number]>
})
const unassignedCount = computed(() => unassignedStats.value.reduce((sum, item) => sum + item[1], 0))

watch(
  () => [props.seekToken, props.shot?.id],
  async () => {
    await nextTick()
    applySeek()
  },
)

function applySeek(): void {
  const video = videoRef.value
  if (!video || props.seekUs === null) return
  const durationUs = props.shot?.source_shot_revision_item?.duration_us
    ?? Math.max(0, (props.shot?.source_end_us ?? 0) - (props.shot?.source_start_us ?? 0))
  const targetUs = Math.max(0, Math.min(props.seekUs, Math.max(0, durationUs - 1_000)))
  video.currentTime = targetUs / 1_000_000
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
  return `${Math.max(0, (endUs - startUs) / 1_000_000).toFixed(2)} 秒`
}

function confidenceText(value: number | null | undefined): string {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—'
}

function revisionLabel(run: BreakdownRunSummary | null): string {
  return run?.source_shot_revision ? `R${run.source_shot_revision.revision}` : 'R?'
}

function eventSpeakers(event: BreakdownTimelineEvent): string {
  const speakers = event.participants
    .filter((item) => item.role === 'SPEAKER')
    .map((item) => item.subject.display_label)
    .filter((item): item is string => Boolean(item))
  return Array.from(new Set(speakers)).join('、')
}

function eventContent(event: BreakdownTimelineEvent): string {
  return event.content_text?.trim() || '未提供文本内容'
}

function eventOriginClass(event: BreakdownTimelineEvent): string {
  const origin = event.origin.toUpperCase()
  if (event.event_type === 'OCR' || origin.includes('OCR')) return 'ocr'
  if (event.event_type === 'DIALOGUE' || origin.includes('ASR')) return 'asr'
  if (event.event_type === 'ACTION') return 'action'
  if (origin.includes('VLM') || event.event_type === 'VISUAL') return 'vlm'
  return 'other'
}

function evidenceTitle(item: BreakdownEvidenceLink): string {
  return `${evidenceSourceTypeLabel(item.source_type)} · ${evidenceRoleLabel(item.role)}`
}
</script>

<template>
  <aside class="breakdown-inspector-v1">
    <div v-if="!run || !shot" class="inspector-empty">
      <strong>选择一个镜头</strong>
      <p>参考片段、当前证据和证据来源追溯会固定显示在这里。</p>
    </div>

    <template v-else>
      <section class="inspector-card reference-card">
        <header class="reference-head">
          <div>
            <span>{{ revisionLabel(run) }} · 参考片段</span>
            <strong>镜头 {{ String(shot.shot_ordinal_snapshot).padStart(4, '0') }}</strong>
          </div>
          <i>{{ run.source_shot_revision?.is_current ? '当前镜头版本' : '历史镜头版本' }}</i>
        </header>

        <div class="reference-video">
          <video
            v-if="referenceUrl"
            ref="videoRef"
            :key="shot.source_shot_revision_item_id"
            :src="referenceUrl"
            controls
            preload="metadata"
            @loadedmetadata="applySeek"
          ></video>
          <div v-else class="reference-missing">这个历史镜头版本没有可用参考片段。</div>
        </div>

        <div class="reference-meta">
          <span>原片时间 {{ timecode(shot.source_start_us) }} → {{ timecode(shot.source_end_us) }}</span>
          <b>{{ durationText(shot.source_start_us, shot.source_end_us) }}</b>
        </div>
      </section>

      <section class="inspector-card selection-card">
        <header class="inspector-card-title">
          <div>
            <span>{{ event ? '当前选中证据' : '镜头快速信息' }}</span>
            <strong>{{ event ? eventTypeLabel(event.event_type) : `镜头 ${String(shot.shot_ordinal_snapshot).padStart(4, '0')}` }}</strong>
          </div>
          <i v-if="event" :class="eventOriginClass(event)">{{ eventOriginLabel(event.origin) }}</i>
        </header>

        <div v-if="event" class="event-detail-grid">
          <div><span>类型</span><b>{{ eventTypeLabel(event.event_type) }}</b></div>
          <div><span>来源</span><b>{{ eventOriginLabel(event.origin) }}</b></div>
          <div><span>开始时间</span><b>{{ timecode(event.source_start_us) }}</b></div>
          <div><span>结束时间</span><b>{{ timecode(event.source_end_us) }}</b></div>
          <div><span>镜头内时间</span><b>{{ timecode(event.shot_relative_start_us) }}</b></div>
          <div><span>持续时间</span><b>{{ durationText(event.source_start_us, event.source_end_us) }}</b></div>
          <div><span>语言</span><b>{{ event.language || '—' }}</b></div>
          <div><span>置信度</span><b>{{ confidenceText(event.confidence) }}</b></div>
        </div>

        <div v-if="event" class="event-content-box">
          <span v-if="eventSpeakers(event)">匿名说话人草稿 · {{ eventSpeakers(event) }}</span>
          <p>{{ eventContent(event) }}</p>
          <div v-if="event.participants.length" class="event-participants">
            <span v-for="participant in event.participants" :key="participant.id">
              {{ participantRoleLabel(participant.role) }} · {{ participant.subject.display_label || '匿名主体' }} · {{ confidenceText(participant.confidence) }}
            </span>
          </div>
          <small v-if="event.emotion_hint || event.speaking_style_hint">
            {{ event.emotion_hint ? `情绪 · ${event.emotion_hint}` : '' }}
            {{ event.emotion_hint && event.speaking_style_hint ? ' · ' : '' }}
            {{ event.speaking_style_hint ? `说话风格 · ${event.speaking_style_hint}` : '' }}
          </small>
        </div>

        <div v-else class="quick-stats-grid">
          <div><b>{{ shot.subjects.length }}</b><span>匿名人物</span></div>
          <div><b>{{ shot.prop_occurrences.length }}</b><span>道具提示</span></div>
          <div><b>{{ shot.events.length }}</b><span>事件</span></div>
          <div><b>{{ shot.events.filter((item) => item.event_type === 'OCR').length }}</b><span>OCR 文字</span></div>
          <div><b>{{ shot.events.filter((item) => item.event_type === 'DIALOGUE').length }}</b><span>对白</span></div>
          <div><b>{{ confidenceText(shot.confidence) }}</b><span>AI 置信度</span></div>
        </div>

        <div v-if="!event && segment" class="scene-mini-context">
          <span>所属场景</span>
          <b>场景 {{ String(segment.ordinal).padStart(2, '0') }} · {{ segment.location_hint || '场景信息待补充' }}</b>
          <small>在中间“镜头时间轴”点击任意 VLM 画面 / 对白 / OCR 文字 / 动作事件，可查看完整证据详情并同步视频时间。</small>
        </div>
      </section>

      <details class="inspector-card provenance-card" open>
        <summary>
          <span>证据来源追溯</span>
          <b>{{ evidenceLinks.length }}</b>
        </summary>
        <div v-if="evidenceLinks.length" class="provenance-list">
          <div v-for="item in evidenceLinks" :key="item.id" class="provenance-row" :title="item.source_uri || item.source_id">
            <div>
              <strong>{{ evidenceTitle(item) }}</strong>
              <span>{{ item.source_id }}</span>
              <small v-if="item.source_uri">{{ item.source_uri }}</small>
            </div>
            <b>{{ confidenceText(item.confidence) }}</b>
          </div>
        </div>
        <p v-else class="provenance-empty">当前选择没有直接证据关联；这不代表整个运行记录没有原始证据。</p>
      </details>

      <details v-if="unassignedCount" class="inspector-card unassigned-card">
        <summary>
          <span>未归属数据</span>
          <b>⚠ {{ unassignedCount }}</b>
        </summary>
        <div class="unassigned-grid">
          <div v-for="item in unassignedStats" :key="item[0]" v-show="item[1]">
            <span>{{ item[0] }}</span><b>{{ item[1] }}</b>
          </div>
        </div>
      </details>
    </template>
  </aside>
</template>

<style scoped>
.breakdown-inspector-v1 { min-width: 0; height: 100%; min-height: 0; overflow: auto; display: grid; align-content: start; gap: 10px; padding-right: 2px; }
.inspector-card { border: 1px solid #dfe5ef; border-radius: 14px; background: #fff; box-shadow: 0 8px 28px rgba(45, 62, 94, .045); overflow: hidden; }
.inspector-empty { min-height: 420px; display: grid; place-content: center; justify-items: center; gap: 7px; border: 1px dashed #d9e1ed; border-radius: 14px; background: #fbfcfe; text-align: center; padding: 24px; }
.inspector-empty strong { color: #43526b; font-size: 16px; }
.inspector-empty p { margin: 0; color: #8491a4; font-size: 12px; line-height: 1.55; }
.reference-head, .inspector-card-title { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 13px 13px 10px; }
.reference-head > div, .inspector-card-title > div { min-width: 0; display: grid; gap: 2px; }
.reference-head span, .inspector-card-title span { color: #7e8ca2; font-size: 11px; font-weight: 750; letter-spacing: .03em; }
.reference-head strong, .inspector-card-title strong { color: #243650; font-size: 14px; }
.reference-head i { flex: none; border-radius: 999px; padding: 4px 7px; background: #e8f7ef; color: #16814f; font-size: 10px; font-style: normal; font-weight: 850; }
.reference-video { margin: 0 12px; border-radius: 10px; overflow: hidden; background: #10151d; }
.reference-video video { width: 100%; aspect-ratio: 16 / 9; display: block; background: #10151d; object-fit: contain; }
.reference-missing { min-height: 180px; display: grid; place-items: center; padding: 20px; color: #bbc3cf; font-size: 12px; text-align: center; }
.reference-meta { display: flex; justify-content: space-between; gap: 10px; padding: 9px 13px 12px; color: #657590; font-size: 11px; }
.reference-meta b { color: #2f4466; }
.inspector-card-title { border-bottom: 1px solid #edf0f5; }
.inspector-card-title i { border-radius: 999px; padding: 4px 8px; font-size: 10px; font-style: normal; font-weight: 850; }
.inspector-card-title i.vlm { background: #efeaff; color: #6748bf; }
.inspector-card-title i.asr { background: #e9f2ff; color: #376dbc; }
.inspector-card-title i.ocr { background: #fff3d8; color: #93620d; }
.inspector-card-title i.action { background: #e8f7f2; color: #1c805f; }
.inspector-card-title i.other { background: #eef1f5; color: #697589; }
.event-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: #edf0f5; }
.event-detail-grid > div { min-width: 0; display: grid; gap: 3px; padding: 9px 11px; background: #fff; }
.event-detail-grid span { color: #8794a7; font-size: 10px; }
.event-detail-grid b { overflow: hidden; text-overflow: ellipsis; color: #354862; font-size: 11px; }
.event-content-box { margin: 10px 12px 12px; border-radius: 10px; padding: 10px 11px; background: #f7f9fd; }
.event-content-box > span { color: #5e7090; font-size: 11px; font-weight: 800; }
.event-content-box p { margin: 5px 0 0; color: #33465f; font-size: 13px; line-height: 1.5; }
.event-participants { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 8px; }
.event-participants span { border-radius: 999px; padding: 4px 7px; background: #edf2fb; color: #526887; font-size: 10px; font-weight: 700; }
.event-content-box small { display: block; margin-top: 7px; color: #7f8ca0; font-size: 10px; }
.quick-stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: #edf0f5; }
.quick-stats-grid > div { display: grid; gap: 2px; padding: 11px 8px; background: #fff; text-align: center; }
.quick-stats-grid b { color: #294b7e; font-size: 14px; }
.quick-stats-grid span { color: #8592a5; font-size: 10px; }
.scene-mini-context { display: grid; gap: 3px; border-top: 1px solid #edf0f5; padding: 10px 12px; }
.scene-mini-context span { color: #8793a5; font-size: 10px; }
.scene-mini-context b { color: #40516a; font-size: 11px; }
.scene-mini-context small { color: #8390a3; font-size: 10px; line-height: 1.45; }
details > summary { list-style: none; cursor: pointer; }
details > summary::-webkit-details-marker { display: none; }
.provenance-card summary, .unassigned-card summary { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 12px 13px; color: #3c4f6d; font-size: 12px; font-weight: 850; }
.provenance-card[open] summary, .unassigned-card[open] summary { border-bottom: 1px solid #edf0f5; }
.provenance-card summary b { min-width: 24px; border-radius: 999px; padding: 2px 6px; background: #eef2f8; color: #718098; font-size: 10px; text-align: center; }
.provenance-list { display: grid; gap: 7px; padding: 10px; }
.provenance-row { display: flex; justify-content: space-between; gap: 10px; align-items: flex-start; border-radius: 9px; padding: 9px 10px; background: #f6f8fc; }
.provenance-row > div { min-width: 0; display: grid; gap: 3px; }
.provenance-row strong { color: #394c68; font-size: 11px; }
.provenance-row span, .provenance-row small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #8491a4; font-size: 9px; }
.provenance-row > b { flex: none; color: #607492; font-size: 11px; }
.provenance-empty { margin: 0; padding: 14px; color: #8793a5; font-size: 11px; line-height: 1.5; }
.unassigned-card summary b { color: #ad6e12; font-size: 11px; }
.unassigned-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: #edf0f5; }
.unassigned-grid > div { display: flex; justify-content: space-between; gap: 8px; padding: 9px 10px; background: #fff; }
.unassigned-grid span { color: #7f8ca0; font-size: 10px; }
.unassigned-grid b { color: #5d6d84; font-size: 11px; }
</style>