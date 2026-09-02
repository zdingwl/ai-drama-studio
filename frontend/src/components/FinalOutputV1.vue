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
const allCompleted = computed(() => autoState.value?.stage === 'complete' || (knownEpisodeCount.value > 0 && completed.value.length === knownEpisodeCount.value))
const postReadyCount = computed(() => postproduction.value?.episodes.flatMap((episode) => episode.segments).filter((segment) => segment.status === 'READY').length ?? 0)
const postReviewCount = computed(() => postproduction.value?.review_count ?? 0)
const postWaitingCount = computed(() => postproduction.value?.waiting_count ?? 0)
const needsLipSync = computed(() => postproduction.value?.episodes.some((episode) => episode.segments.some((segment) => (
  segment.status === 'READY' && ['LATENTSYNC_FULL_SEGMENT', 'LATENTSYNC_TARGET_FACE_ROI'].includes(segment.lip_sync_mode)
))) ?? false)

const selectedSegmentIds = computed(() => new Set((h3Quality.value?.selections ?? []).map((item) => item.generation_segment_id)))
const pendingH3Segments = computed(() => (
  h3Segments.value?.episodes
    .flatMap((episode) => episode.segments)
    .filter((segment) => segment.status === 'READY' && !selectedSegmentIds.value.has(segment.id)) ?? []
))

const needsContinuation = computed(() => !allCompleted.value)
const hasActiveOutputWork = computed(() => Boolean(autoState.value?.active_task || startingAuto.value))
const localModelLabel = computed(() => {
  if (loading.value) return '检查中'
  if (autoState.value?.stage === 'h3_generation') return h3Runtime.value?.ready ? 'H3 就绪' : 'H3 未就绪'
  if (autoState.value?.stage === 'postproduction' && needsLipSync.value) return lipSyncRuntime.value?.ready ? '口型就绪' : '口型未就绪'
  return '按需自动启动'
})
const localModelWarning = computed(() => Boolean(
  (autoState.value?.stage === 'h3_generation' && h3Runtime.value && !h3Runtime.value.ready)
  || (autoState.value?.stage === 'postproduction' && needsLipSync.value && lipSyncRuntime.value && !lipSyncRuntime.value.ready),
))

function stageTitle(state: AutoOutputState | null): string {
  const labels: Record<string, string> = {
    review_gate: '等待必要确认',
    target_localization: '准备目标人物与场景',
    target_dialogue: '生成目标对白',
    tts: '生成目标语音',
    generation_segments: '准备目标时间轴与镜头',
    h3_generation: 'MiniMax H3 生成与质检',
    postproduction: '口型、音轨与字幕后期',
    episode_output: '拼接最终剧集',
    complete: '成片已经完成',
  }
  return labels[state?.stage ?? ''] || '检查自动成片进度'
}

const continuationState = computed(() => {
  if (allCompleted.value) return {
    tone: 'ready',
    title: '成片已经完成',
    detail: '最终剧集可以直接播放和下载。',
  }
  if (reviewCount.value > 0) return {
    tone: 'review',
    title: `还有 ${reviewCount.value} 项真正需要确认`,
    detail: autoState.value?.message || '完成真实业务修改后，系统会从当前进度继续，不会重新拉片。',
  }
  if (hasActiveOutputWork.value) return {
    tone: 'running',
    title: autoState.value?.active_task?.stage_label || stageTitle(autoState.value),
    detail: autoState.value?.active_task?.message || autoState.value?.message || '系统正在从当前有效结果继续。',
  }
  if (autoState.value?.stage === 'h3_generation' && h3Runtime.value && !h3Runtime.value.ready) return {
    tone: 'warning',
    title: '等待本地 MiniMax H3',
    detail: 'H3 Runtime 恢复后点击“重新继续自动生成”即可；上游对白、Timing 和镜头计划不会重做。',
  }
  if (autoState.value?.stage === 'postproduction' && needsLipSync.value && lipSyncRuntime.value && !lipSyncRuntime.value.ready) return {
    tone: 'warning',
    title: '等待本地 LatentSync',
    detail: '口型 Runtime 恢复后点击“重新继续自动生成”即可；已经通过质检的 H3 镜头不会重做。',
  }
  if (autoAttempted.value) return {
    tone: 'warning',
    title: stageTitle(autoState.value),
    detail: autoState.value?.message || '本次自动任务没有走到最终成片，请查看底部后台任务；恢复对应运行环境后可从当前进度重试。',
  }
  return {
    tone: 'running',
    title: stageTitle(autoState.value),
    detail: autoState.value?.message || '无需手动逐阶段操作，系统会自动从当前有效结果继续。',
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

  if (state.can_read_outputs) {
    requests.push(remakeApi.getEpisodeOutputs(props.projectId).then((value) => { outputs.value = value }))
  }
  if (state.can_read_postproduction) {
    requests.push(remakeApi.getPostProduction(props.projectId).then((value) => { postproduction.value = value }))
    requests.push(remakeApi.getLipSyncRuntimeStatus().then((value) => { lipSyncRuntime.value = value }))
  }
  if (state.can_read_generation_segments) {
    requests.push(remakeApi.getGenerationSegments(props.projectId).then((value) => { h3Segments.value = value }))
  }
  if (state.can_read_h3_quality) {
    requests.push(remakeApi.getH3Quality(props.projectId).then((value) => { h3Quality.value = value }))
  }
  if (state.stage === 'h3_generation') {
    requests.push(remakeApi.getH3RuntimeStatus().then((value) => { h3Runtime.value = value }))
  }

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

  if (autoState.value && !autoState.value.active_task && !autoAttempted.value && reviewCount.value === 0 && !allCompleted.value) {
    await startAutomaticOutput()
  }
}

async function retryAutomaticOutput(): Promise<void> {
  autoAttempted.value = false
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
    <header class="topbar">
      <div>
        <small>成片</small>
        <strong>本土化短剧输出</strong>
        <span>系统会从当前有效进度自动继续；正常情况下不需要你逐阶段点击生成。</span>
      </div>
      <button :disabled="loading || startingAuto" @click="retryAutomaticOutput">重新检查</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <section :class="['continuation', `tone-${continuationState.tone}`]">
      <div>
        <small>自动成片</small>
        <strong>{{ continuationState.title }}</strong>
        <span>{{ continuationState.detail }}</span>
      </div>
      <button
        v-if="needsContinuation && !autoState?.active_task && !startingAuto && reviewCount === 0 && autoAttempted"
        class="primary"
        @click="retryAutomaticOutput"
      >
        重新继续自动生成
      </button>
    </section>

    <div class="summary">
      <article class="success"><small>已成片</small><strong>{{ Math.max(completed.length, autoState?.completed_episode_count ?? 0) }}</strong><span>可直接播放和下载</span></article>
      <article><small>待成片</small><strong>{{ Math.max(0, knownEpisodeCount - Math.max(completed.length, autoState?.completed_episode_count ?? 0)) }}</strong><span>系统自动生成、质检或后期中</span></article>
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
            <span v-else-if="autoState?.stage === 'h3_generation' && h3Runtime && !h3Runtime.ready">等待本地 MiniMax H3 Runtime；恢复后可从当前镜头继续。</span>
            <span v-else-if="needsLipSync && lipSyncRuntime && !lipSyncRuntime.ready">等待本地 LatentSync Runtime；已生成镜头不会重做。</span>
            <span v-else>系统会自动继续镜头生成、质检、口型、字幕和整集拼接。</span>
          </div>
          <span class="auto-badge">自动处理</span>
        </div>
      </article>
    </section>

    <section v-else class="empty">
      <strong>{{ hasActiveOutputWork ? '正在自动生成第一版成片' : stageTitle(autoState) }}</strong>
      <span v-if="reviewCount">还有 {{ reviewCount }} 项真实问题需要先确认。</span>
      <span v-else-if="readIncomplete">已就绪的结果读取失败，请查看后台任务；未生成阶段不会再被当作 409 冲突读取。</span>
      <span v-else>{{ autoState?.message || '系统正在检查目标对白、H3、口型和整集输出状态。' }}</span>
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
.final-output{display:grid;gap:12px}.topbar,.episode-list,.empty,.continuation,.diagnostics{border:1px solid #dfe5ed;border-radius:13px;background:#fff}.topbar{display:flex;justify-content:space-between;align-items:center;padding:14px 16px}.topbar>div{display:grid;gap:2px}.final-output small{font-size:9px;color:#8793a4}.final-output strong{color:#405168;font-size:11px}.final-output span{color:#8591a2;font-size:9px}.topbar button,.buttons a{border:1px solid #dce2e9;border-radius:8px;padding:7px 10px;background:#fff;color:#617086;font-size:9px;cursor:pointer;text-decoration:none}.continuation{display:flex;justify-content:space-between;align-items:center;gap:14px;padding:12px 14px}.continuation>div{display:grid;gap:3px}.continuation.tone-running{border-color:#cbd9f3;background:#f6f9ff}.continuation.tone-ready{border-color:#bcdcc9;background:#f5fbf7}.continuation.tone-warning{border-color:#ead0ae;background:#fffaf2}.continuation.tone-review{border-color:#ead0ae;background:#fff8ec}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.summary article{display:grid;gap:3px;padding:11px;border:1px solid #e1e6ed;border-radius:10px;background:#fff}.summary article.success{border-color:#bcdcc9;background:#f5fbf7}.summary article.warn{border-color:#ead0ae;background:#fffaf2}.summary article strong{font-size:15px}.episode-list{display:grid;overflow:hidden}.episode-card{padding:14px 16px;border-top:1px solid #e8ecf1}.episode-card:first-child{border-top:0}.episode-heading{display:grid;grid-template-columns:36px 1fr auto;gap:10px;align-items:center}.number{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:#f0f4fa;color:#52667f;font-size:11px;font-weight:900}.title{display:grid;gap:3px}.episode-heading em{padding:5px 8px;border-radius:999px;background:#f1f3f6;color:#69778a;font-size:8px;font-style:normal}.episode-card.succeeded .episode-heading em{background:#eaf7ef;color:#317653}.episode-card.ready .episode-heading em{background:#eaf0ff;color:#3a5ca8}.episode-card.failed .episode-heading em{background:#fff1e2;color:#9a6313}.finished{display:grid;grid-template-columns:minmax(220px,320px) 1fr;gap:15px;margin-top:12px;padding-left:46px}.finished video{width:100%;aspect-ratio:9/16;max-height:480px;border-radius:10px;background:#111}.finished-actions{display:flex;justify-content:space-between;align-items:flex-end;gap:12px}.finished-actions>div:first-child{display:grid;gap:3px}.buttons{display:flex;gap:7px;flex-wrap:wrap}.buttons a.primary,.primary{border:0;border-radius:8px;padding:9px 13px;background:#3566d6;color:#fff;font-size:9px;font-weight:800;text-decoration:none;cursor:pointer}.primary:disabled{opacity:.45;cursor:not-allowed}.pending{display:flex;justify-content:space-between;align-items:center;gap:14px;margin:12px 0 0 46px;padding:12px 13px;border-radius:10px;background:#f8fafc}.pending>div{display:grid;gap:3px}.auto-badge{padding:5px 8px;border-radius:999px;background:#eef4ff;color:#5270aa!important;font-weight:800;white-space:nowrap}.empty{display:grid;gap:4px;padding:22px}.diagnostics>summary{padding:11px 13px;cursor:pointer;font-size:10px;font-weight:800;color:#506176}.diag-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;padding:0 13px 10px}.diag-grid span{padding:8px;border-radius:8px;background:#f7f9fb;text-align:center}.diag-row{display:grid;grid-template-columns:minmax(180px,1fr) 100px minmax(260px,2fr);gap:8px;align-items:center;padding:8px 13px;border-top:1px solid #eef1f4}.diag-row em{font-size:8px;font-style:normal;color:#718096}.error{margin:0;padding:8px 10px;border-radius:7px;background:#fff2f2;color:#a94e4e;font-size:10px}@media(max-width:900px){.summary{grid-template-columns:1fr 1fr}.finished{grid-template-columns:1fr;padding-left:0}.finished video{max-height:520px}.finished-actions,.pending,.continuation{align-items:stretch;flex-direction:column}.pending{margin-left:0}.diag-row{grid-template-columns:1fr}.diag-grid{grid-template-columns:1fr 1fr}}
</style>
