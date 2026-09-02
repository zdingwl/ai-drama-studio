<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { remakeApi, type AutoOutputState } from '../api/remake'
import type {
  EpisodeOutputPlan,
  GenerationQualitySummary,
  GenerationSegmentPlan,
  H3RuntimeStatus,
  LipSyncRuntimeStatus,
  PostProductionPlan,
} from '../types/remake'

const props = defineProps<{ projectId: string; busy?: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const autoState = ref<AutoOutputState | null>(null)
const outputs = ref<EpisodeOutputPlan | null>(null)
const postproduction = ref<PostProductionPlan | null>(null)
const lipSyncRuntime = ref<LipSyncRuntimeStatus | null>(null)
const h3Segments = ref<GenerationSegmentPlan | null>(null)
const h3Runtime = ref<H3RuntimeStatus | null>(null)
const h3Quality = ref<GenerationQualitySummary | null>(null)
const loading = ref(false)
const startingAuto = ref(false)
const autoAttempted = ref(false)
const error = ref('')
const readIncomplete = ref(false)

const reviewCount = computed(() => autoState.value?.review_issue_count ?? 0)
const episodes = computed(() => outputs.value?.episodes ?? [])
const completed = computed(() => episodes.value.filter((item) => item.status === 'SUCCEEDED'))
const knownEpisodeCount = computed(() => autoState.value?.episode_count ?? outputs.value?.episode_count ?? h3Segments.value?.episode_count ?? episodes.value.length)
const completedEpisodeCount = computed(() => Math.max(completed.value.length, autoState.value?.completed_episode_count ?? 0))
const remainingEpisodeCount = computed(() => Math.max(0, knownEpisodeCount.value - completedEpisodeCount.value))
const allCompleted = computed(() => autoState.value?.stage === 'complete' || (knownEpisodeCount.value > 0 && completedEpisodeCount.value === knownEpisodeCount.value))
const postReadyCount = computed(() => postproduction.value?.episodes.flatMap((episode) => episode.segments).filter((segment) => segment.status === 'READY').length ?? 0)
const postReviewCount = computed(() => postproduction.value?.review_count ?? 0)
const postWaitingCount = computed(() => postproduction.value?.waiting_count ?? 0)
const needsLipSync = computed(() => postproduction.value?.episodes.some((episode) => episode.segments.some((segment) => (
  segment.status === 'READY' && ['LATENTSYNC_FULL_SEGMENT', 'LATENTSYNC_TARGET_FACE_ROI'].includes(segment.lip_sync_mode)
))) ?? false)

const needsContinuation = computed(() => !allCompleted.value)
const hasActiveOutputWork = computed(() => Boolean(autoState.value?.active_task || startingAuto.value))
const localModelLabel = computed(() => {
  if (loading.value) return '检查中'
  if (autoState.value?.stage === 'h3_generation') return h3Runtime.value?.ready ? 'H3 已就绪' : 'H3 未就绪'
  if (autoState.value?.stage === 'postproduction' && needsLipSync.value) return lipSyncRuntime.value?.ready ? '口型模型已就绪' : '口型模型未就绪'
  return '按需使用'
})
const localModelWarning = computed(() => Boolean(
  (autoState.value?.stage === 'h3_generation' && h3Runtime.value && !h3Runtime.value.ready)
  || (autoState.value?.stage === 'postproduction' && needsLipSync.value && lipSyncRuntime.value && !lipSyncRuntime.value.ready),
))

const outputSteps = [
  { title: '理解原短剧', detail: '镜头、人物、场景、道具、对白' },
  { title: '设计目标版本', detail: '目标人物与场景本土化' },
  { title: '对白与时长', detail: '翻译、配音、Timing 与镜头分段' },
  { title: 'MiniMax H3 重拍', detail: '按原镜头导演参考生成目标镜头' },
  { title: '口型与后期', detail: '质检、口型、目标音轨与字幕' },
  { title: '最终成片', detail: '整集拼接、播放与下载' },
] as const

function stageTitle(state: AutoOutputState | null): string {
  const labels: Record<string, string> = {
    review_gate: '等待必要确认',
    target_localization: '正在设计目标人物与场景',
    target_dialogue: '正在生成目标对白',
    tts: '正在生成目标语音',
    generation_segments: '正在适配对白时长与镜头',
    h3_generation: '正在用 MiniMax H3 重拍镜头',
    postproduction: '正在执行口型、音轨和字幕后期',
    episode_output: '正在拼接最终剧集',
    complete: '全部成片已经完成',
  }
  return labels[state?.stage ?? ''] || '正在检查成片进度'
}

function stageStepIndex(state: AutoOutputState | null): number {
  if (!state) return 0
  const mapping: Record<string, number> = {
    review_gate: 0,
    target_localization: 1,
    target_dialogue: 2,
    tts: 2,
    generation_segments: 2,
    h3_generation: 3,
    postproduction: 4,
    episode_output: 5,
    complete: outputSteps.length,
  }
  return mapping[state.stage] ?? 0
}

const currentStepIndex = computed(() => stageStepIndex(autoState.value))

function progressStepClass(index: number): Record<string, boolean> {
  const finished = currentStepIndex.value >= outputSteps.length || index < currentStepIndex.value
  const current = currentStepIndex.value < outputSteps.length && index === currentStepIndex.value
  return {
    done: finished,
    current,
    review: current && reviewCount.value > 0,
    warning: current && localModelWarning.value,
  }
}

function progressStepLabel(index: number): string {
  if (currentStepIndex.value >= outputSteps.length || index < currentStepIndex.value) return '已完成'
  if (index > currentStepIndex.value) return '等待'
  if (reviewCount.value > 0) return '待确认'
  if (localModelWarning.value) return '等待模型'
  if (loading.value) return '检查中'
  if (hasActiveOutputWork.value) return '处理中'
  return '准备继续'
}

function progressStepMark(index: number): string {
  if (currentStepIndex.value >= outputSteps.length || index < currentStepIndex.value) return '✓'
  return String(index + 1).padStart(2, '0')
}

const continuationState = computed(() => {
  if (allCompleted.value) return {
    tone: 'ready',
    title: '成片已经完成',
    detail: '最终剧集可以直接播放和下载。',
  }
  if (reviewCount.value > 0) return {
    tone: 'review',
    title: `有 ${reviewCount.value} 项需要你确认`,
    detail: autoState.value?.message || '处理真实业务问题后，系统会从当前进度继续，不会重新拉片。',
  }
  if (hasActiveOutputWork.value) return {
    tone: 'running',
    title: autoState.value?.active_task?.stage_label || stageTitle(autoState.value),
    detail: autoState.value?.active_task?.message || autoState.value?.message || '系统正在从当前有效结果继续。',
  }
  if (autoState.value?.stage === 'h3_generation' && h3Runtime.value && !h3Runtime.value.ready) return {
    tone: 'warning',
    title: '等待本地 MiniMax H3',
    detail: '恢复 H3 Runtime 后即可从当前镜头继续，上游结果不会重做。',
  }
  if (autoState.value?.stage === 'postproduction' && needsLipSync.value && lipSyncRuntime.value && !lipSyncRuntime.value.ready) return {
    tone: 'warning',
    title: '等待本地 LatentSync',
    detail: '恢复口型 Runtime 后即可继续，已经通过质检的 H3 镜头不会重做。',
  }
  if (autoAttempted.value) return {
    tone: 'warning',
    title: '自动生成尚未继续',
    detail: autoState.value?.message || '本次自动任务没有走到最终成片，请查看顶部后台任务；恢复对应运行环境后可从当前进度重试。',
  }
  return {
    tone: 'running',
    title: '准备继续自动生成',
    detail: autoState.value?.message || '点击“继续自动生成”后，系统会从当前有效结果继续，不会重新拉片。',
  }
})

function clearUnavailableResources(state: AutoOutputState): void {
  if (!state.can_read_generation_segments) h3Segments.value = null
  if (!state.can_read_h3_quality) h3Quality.value = null
  if (!state.can_read_postproduction) {
    postproduction.value = null
    lipSyncRuntime.value = null
  }
  if (!state.can_read_outputs) outputs.value = null
  if (state.stage !== 'h3_generation' && !state.can_read_h3_quality) h3Runtime.value = null
}

async function startAutomaticOutput(): Promise<void> {
  if (!props.projectId || startingAuto.value || reviewCount.value > 0 || allCompleted.value || autoState.value?.active_task) return
  autoAttempted.value = true
  startingAuto.value = true
  try {
    await remakeApi.startAutoOutput(props.projectId)
    error.value = ''
    emit('changed')
    await load()
  } catch (err) {
    const message = err instanceof Error ? err.message : ''
    if (!message.includes('已有本地重任务')) {
      error.value = message || '自动成片任务启动失败，请查看后台任务状态后重试'
    }
  } finally {
    startingAuto.value = false
  }
}

async function loadAvailableResources(state: AutoOutputState): Promise<void> {
  const requests: Array<Promise<void>> = []

  if (state.can_read_outputs) requests.push(remakeApi.getEpisodeOutputs(props.projectId).then((value) => { outputs.value = value }))
  if (state.can_read_postproduction) {
    requests.push(remakeApi.getPostProduction(props.projectId).then((value) => { postproduction.value = value }))
    requests.push(remakeApi.getLipSyncRuntimeStatus().then((value) => { lipSyncRuntime.value = value }))
  }
  if (state.can_read_generation_segments) requests.push(remakeApi.getGenerationSegments(props.projectId).then((value) => { h3Segments.value = value }))
  if (state.can_read_h3_quality) requests.push(remakeApi.getH3Quality(props.projectId).then((value) => { h3Quality.value = value }))
  if (state.stage === 'h3_generation') requests.push(remakeApi.getH3RuntimeStatus().then((value) => { h3Runtime.value = value }))

  const results = await Promise.allSettled(requests)
  if (results.some((result) => result.status === 'rejected')) readIncomplete.value = true
}

async function load(): Promise<void> {
  if (!props.projectId) return
  loading.value = true
  readIncomplete.value = false
  error.value = ''
  try {
    const state = await remakeApi.getAutoOutputState(props.projectId)
    autoState.value = state
    clearUnavailableResources(state)
    await loadAvailableResources(state)
  } catch (err) {
    autoState.value = null
    readIncomplete.value = true
    error.value = err instanceof Error ? err.message : '自动成片状态读取失败'
  } finally {
    loading.value = false
  }
}

async function retryAutomaticOutput(): Promise<void> {
  await load()
}

function duration(us: number): string {
  const total = Math.max(0, Math.round(us / 1_000_000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  return minutes ? `${minutes}:${seconds.toString().padStart(2, '0')}` : `${seconds}s`
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    SUCCEEDED: '已成片',
    READY: '等待自动拼接',
    WAITING_POSTPRODUCTION: '等待自动后期',
    PROCESSING: '处理中',
    FAILED: '可从当前进度重试',
    STALE: '自动重新生成中',
  }
  return labels[status] || status
}

function episodeVideo(episodeId: string): string {
  return remakeApi.episodeFinalVideoUrl(props.projectId, episodeId)
}

function episodeSubtitle(episodeId: string): string {
  return remakeApi.episodeSubtitleUrl(props.projectId, episodeId)
}

watch(() => props.projectId, () => {
  autoAttempted.value = false
  void load()
})
watch(() => props.busy, (busy, previous) => {
  if (previous && !busy) void load()
})
onMounted(() => void load())
</script>

<template>
  <section class="final-output">
    <header class="output-status-head">
      <div>
        <small>当前生成状态</small>
        <strong>{{ stageTitle(autoState) }}</strong>
        <span>{{ autoState?.message || '正在读取当前项目的真实生成进度。' }}</span>
      </div>
      <button :disabled="loading || startingAuto" @click="retryAutomaticOutput">刷新状态</button>
    </header>

    <nav class="output-progress" aria-label="成片生成进度">
      <article
        v-for="(step, index) in outputSteps"
        :key="step.title"
        :class="progressStepClass(index)"
      >
        <div class="step-marker">{{ progressStepMark(index) }}</div>
        <div class="step-copy">
          <strong>{{ step.title }}</strong>
          <span>{{ step.detail }}</span>
        </div>
        <em>{{ progressStepLabel(index) }}</em>
      </article>
    </nav>

    <p v-if="error" class="error">{{ error }}</p>

    <section :class="['continuation', `tone-${continuationState.tone}`]">
      <div>
        <small>当前要做的事</small>
        <strong>{{ continuationState.title }}</strong>
        <span>{{ continuationState.detail }}</span>
      </div>
      <button
        v-if="needsContinuation && !autoState?.active_task && !startingAuto && reviewCount === 0"
        class="primary"
        @click="startAutomaticOutput"
      >{{ autoAttempted ? '重新继续自动生成' : '继续自动生成' }}</button>
    </section>

    <div class="summary">
      <article class="success"><small>已成片</small><strong>{{ completedEpisodeCount }}</strong><span>可直接播放和下载</span></article>
      <article><small>待成片</small><strong>{{ remainingEpisodeCount }}</strong><span>自动生成、质检或后期中</span></article>
      <article :class="{ warn: reviewCount || postReviewCount }"><small>需要确认</small><strong>{{ Math.max(reviewCount, postReviewCount) }}</strong><span>只统计真正需要人工决定的问题</span></article>
      <article :class="{ warn: localModelWarning }"><small>本地模型</small><strong>{{ localModelLabel }}</strong><span>MiniMax H3 / LatentSync 按需使用</span></article>
    </div>

    <section v-if="episodes.length" class="episode-list">
      <article v-for="(episode, index) in episodes" :key="episode.episode_id" class="episode-card" :class="episode.status.toLowerCase()">
        <div class="episode-heading">
          <div class="number">{{ String(index + 1).padStart(2, '0') }}</div>
          <div class="title">
            <strong>{{ episode.episode_title }}</strong>
            <span>{{ episode.segment_count }} 个镜头分段 · {{ duration(episode.target_duration_us) }}</span>
          </div>
          <em>{{ statusLabel(episode.status) }}</em>
        </div>

        <div v-if="episode.status === 'SUCCEEDED'" class="finished">
          <video controls preload="metadata" :src="episodeVideo(episode.episode_id)" />
          <div class="finished-actions">
            <div>
              <strong>最终成片已完成</strong>
              <span>已使用目标语言对白、口型后期、目标时间轴和整集字幕。</span>
            </div>
            <div class="buttons">
              <a class="primary" :href="episodeVideo(episode.episode_id)" download>下载 MP4</a>
              <a :href="episodeSubtitle(episode.episode_id)" download>下载字幕</a>
            </div>
          </div>
        </div>

        <div v-else class="pending">
          <div>
            <strong>{{ episode.reason }}</strong>
            <span v-if="reviewCount || postReviewCount">存在真正需要人工确认的问题，请到“待确认”处理。</span>
            <span v-else-if="autoState?.stage === 'h3_generation' && h3Runtime && !h3Runtime.ready">等待本地 MiniMax H3；恢复后从当前镜头继续。</span>
            <span v-else-if="needsLipSync && lipSyncRuntime && !lipSyncRuntime.ready">等待本地 LatentSync；已生成镜头不会重做。</span>
            <span v-else-if="hasActiveOutputWork">系统正在继续镜头生成、质检、口型、字幕和整集拼接。</span>
            <span v-else>点击“继续自动生成”后，系统会从当前有效结果继续。</span>
          </div>
          <span class="auto-badge">{{ hasActiveOutputWork ? '自动处理中' : '等待继续' }}</span>
        </div>
      </article>
    </section>

    <section v-else class="empty">
      <strong>{{ hasActiveOutputWork ? '正在自动生成第一版成片' : '等待继续自动生成' }}</strong>
      <span v-if="reviewCount">还有 {{ reviewCount }} 项真实问题需要先确认。</span>
      <span v-else-if="readIncomplete">部分已就绪结果暂时读取失败，请查看顶部后台任务；未生成阶段不会作为错误展示。</span>
      <span v-else-if="hasActiveOutputWork">{{ autoState?.message || '系统正在继续目标对白、H3、口型和整集输出。' }}</span>
      <span v-else>{{ autoState?.message || '点击“继续自动生成”后，从当前有效结果继续。' }}</span>
    </section>

    <details v-if="postproduction" class="diagnostics">
      <summary>高级诊断 · 后期分段 {{ postproduction.segment_count }}</summary>
      <div class="diag-grid">
        <span>已完成 {{ postproduction.succeeded_count }}</span>
        <span>可执行 {{ postReadyCount }}</span>
        <span>等待 {{ postWaitingCount }}</span>
        <span>需确认 {{ postReviewCount }}</span>
      </div>
      <div v-for="segment in postproduction.episodes.flatMap((episode) => episode.segments).filter((item) => item.status !== 'SUCCEEDED')" :key="segment.id" class="diag-row">
        <strong>{{ segment.generation_segment_id }}</strong>
        <em>{{ segment.status }}</em>
        <span>{{ segment.reason }}</span>
      </div>
    </details>
  </section>
</template>

<style scoped>
:global(.studio .panel > .pipeline){display:none!important}
.final-output{display:grid;gap:14px}.output-status-head,.output-progress,.episode-list,.empty,.continuation,.diagnostics{border:1px solid #dfe5ed;border-radius:14px;background:#fff}.output-status-head{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:16px 18px}.output-status-head>div{display:grid;gap:3px}.final-output small{font-size:11px;color:#7e8c9f}.final-output strong{color:#344a65;font-size:13px}.final-output span{color:#7c899b;font-size:11px;line-height:1.5}.output-status-head strong{font-size:17px}.output-status-head button,.buttons a{min-height:36px;border:1px solid #dce2e9;border-radius:9px;padding:0 12px;background:#fff;color:#617086;font-size:11px;cursor:pointer;text-decoration:none}.output-progress{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));overflow:hidden}.output-progress article{position:relative;min-height:108px;display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:10px;row-gap:7px;align-content:center;padding:14px 13px;border-right:1px solid #e7ebf0;background:#fff}.output-progress article:last-child{border-right:0}.output-progress article.done{background:#f6fbf8}.output-progress article.current{background:#f5f8ff}.output-progress article.review,.output-progress article.warning{background:#fffaf1}.output-progress article.current::after,.output-progress article.done::after{content:'';position:absolute;left:0;right:0;bottom:0;height:3px;background:#6d8ed8}.output-progress article.done::after{background:#5eaa7d}.step-marker{grid-row:1/3;width:30px;height:30px;display:grid;place-items:center;border-radius:50%;background:#eef2f7;color:#6d7b8e;font-size:10px;font-weight:900}.done .step-marker{background:#dff1e6;color:#2d7a51}.current .step-marker{background:#dfe9ff;color:#315cae}.review .step-marker,.warning .step-marker{background:#f9e9c5;color:#946112}.step-copy{min-width:0;display:grid;gap:3px}.step-copy strong{font-size:12px;line-height:1.35}.step-copy span{font-size:10px;line-height:1.35}.output-progress em{grid-column:2;width:max-content;padding:3px 7px;border-radius:999px;background:#f0f3f7;color:#7b8797;font-size:9px;font-style:normal}.done em{background:#e8f5ed;color:#3f7f5b}.current em{background:#e7efff;color:#4668aa}.review em,.warning em{background:#f9edcf;color:#946112}.continuation{display:flex;justify-content:space-between;align-items:center;gap:14px;min-height:86px;padding:17px 19px}.continuation>div{display:grid;gap:5px}.continuation strong{font-size:17px}.continuation.tone-running{border-color:#cbd9f3;background:#f6f9ff}.continuation.tone-ready{border-color:#bcdcc9;background:#f5fbf7}.continuation.tone-warning,.continuation.tone-review{border-color:#ead0ae;background:#fffaf2}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:0;overflow:hidden;border:1px solid #e1e6ed;border-radius:14px;background:#fff}.summary article{display:grid;gap:3px;min-height:82px;padding:14px 16px;border-right:1px solid #e7ebf0;background:transparent}.summary article:last-child{border-right:0}.summary article.success{background:#f6fbf8}.summary article.warn{background:#fffaf2}.summary article strong{font-size:20px}.episode-list{display:grid;overflow:hidden}.episode-card{padding:18px 20px;border-top:1px solid #e8ecf1}.episode-card:first-child{border-top:0}.episode-heading{display:grid;grid-template-columns:42px 1fr auto;gap:13px;align-items:center}.number{display:grid;place-items:center;width:38px;height:38px;border-radius:10px;background:#f0f4fa;color:#52667f;font-size:13px;font-weight:900}.title{display:grid;gap:3px}.title strong{font-size:15px}.episode-heading em{padding:6px 10px;border-radius:999px;background:#f1f3f6;color:#69778a;font-size:10px;font-style:normal}.episode-card.succeeded .episode-heading em{background:#eaf7ef;color:#317653}.episode-card.ready .episode-heading em{background:#eaf0ff;color:#3a5ca8}.episode-card.failed .episode-heading em{background:#fff1e2;color:#9a6313}.finished{display:grid;grid-template-columns:minmax(220px,320px) 1fr;gap:20px;margin-top:16px;padding-left:55px}.finished video{width:100%;aspect-ratio:9/16;max-height:480px;border-radius:10px;background:#111}.finished-actions{display:flex;justify-content:space-between;align-items:flex-end;gap:12px}.finished-actions>div:first-child{display:grid;gap:3px}.finished-actions strong{font-size:15px}.buttons{display:flex;gap:7px;flex-wrap:wrap}.buttons a.primary,.primary{min-height:40px;display:inline-flex;align-items:center;border:0;border-radius:9px;padding:0 13px;background:#3566d6;color:#fff;font-size:11px;font-weight:800;text-decoration:none;cursor:pointer}.primary:disabled{opacity:.45;cursor:not-allowed}.pending{display:flex;justify-content:space-between;align-items:center;gap:14px;margin:14px 0 0 55px;padding:14px 16px;border-radius:10px;background:#f8fafc}.pending>div{display:grid;gap:3px}.pending strong{font-size:13px}.auto-badge{padding:6px 9px;border-radius:999px;background:#eef4ff;color:#5270aa!important;font-size:10px;font-weight:800;white-space:nowrap}.empty{min-height:132px;display:grid;place-content:center;gap:5px;padding:30px;text-align:center}.empty strong{font-size:17px}.diagnostics>summary{padding:13px 15px;cursor:pointer;font-size:11px;font-weight:800;color:#506176}.diag-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;padding:0 13px 10px}.diag-grid span{padding:8px;border-radius:8px;background:#f7f9fb;text-align:center}.diag-row{display:grid;grid-template-columns:minmax(180px,1fr) 100px minmax(260px,2fr);gap:8px;align-items:center;padding:8px 13px;border-top:1px solid #eef1f4}.diag-row em{font-size:9px;font-style:normal;color:#718096}.error{margin:0;padding:9px 11px;border-radius:8px;background:#fff2f2;color:#a94e4e;font-size:11px}@media(max-width:1180px){.output-progress{grid-template-columns:repeat(3,minmax(0,1fr))}.output-progress article:nth-child(3){border-right:0}.output-progress article:nth-child(-n+3){border-bottom:1px solid #e7ebf0}}@media(max-width:900px){.output-progress{grid-template-columns:1fr}.output-progress article{min-height:82px;border-right:0;border-bottom:1px solid #e7ebf0}.output-progress article:last-child{border-bottom:0}.summary{grid-template-columns:1fr 1fr}.summary article:nth-child(2){border-right:0}.summary article:nth-child(-n+2){border-bottom:1px solid #e7ebf0}.finished{grid-template-columns:1fr;padding-left:0}.finished video{max-height:520px}.finished-actions,.pending,.continuation,.output-status-head{align-items:stretch;flex-direction:column}.pending{margin-left:0}.diag-row{grid-template-columns:1fr}.diag-grid{grid-template-columns:1fr 1fr}}
</style>
