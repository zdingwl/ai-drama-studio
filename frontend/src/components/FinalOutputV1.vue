<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { remakeApi } from '../api/remake'
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

const outputs = ref<EpisodeOutputPlan | null>(null)
const postproduction = ref<PostProductionPlan | null>(null)
const lipSyncRuntime = ref<LipSyncRuntimeStatus | null>(null)
const h3Segments = ref<GenerationSegmentPlan | null>(null)
const h3Runtime = ref<H3RuntimeStatus | null>(null)
const h3Quality = ref<GenerationQualitySummary | null>(null)
const loading = ref(false)
const starting = ref<'h3' | 'post' | ''>('')
const error = ref('')

const episodes = computed(() => outputs.value?.episodes ?? [])
const completed = computed(() => episodes.value.filter((item) => item.status === 'SUCCEEDED'))
const ready = computed(() => episodes.value.filter((item) => item.status === 'READY'))
const postReadyCount = computed(() => postproduction.value?.episodes.flatMap((episode) => episode.segments).filter((segment) => segment.status === 'READY').length ?? 0)
const postReviewCount = computed(() => postproduction.value?.review_count ?? 0)
const postWaitingCount = computed(() => postproduction.value?.waiting_count ?? 0)
const needsLipSync = computed(() => postproduction.value?.episodes.some((episode) => episode.segments.some((segment) => (
  segment.status === 'READY' && ['LATENTSYNC_FULL_SEGMENT', 'LATENTSYNC_TARGET_FACE_ROI'].includes(segment.lip_sync_mode)
))) ?? false)
const hasRunnablePostWork = computed(() => ready.value.length > 0 || postReadyCount.value > 0)
const canStartPost = computed(() => Boolean(
  hasRunnablePostWork.value
  && !props.busy
  && !starting.value
  && (!needsLipSync.value || lipSyncRuntime.value?.ready),
))

const selectedSegmentIds = computed(() => new Set((h3Quality.value?.selections ?? []).map((item) => item.generation_segment_id)))
const pendingH3Segments = computed(() => (
  h3Segments.value?.episodes
    .flatMap((episode) => episode.segments)
    .filter((segment) => segment.status === 'READY' && !selectedSegmentIds.value.has(segment.id)) ?? []
))
const canStartH3 = computed(() => Boolean(
  pendingH3Segments.value.length
  && h3Runtime.value?.ready
  && !props.busy
  && !starting.value,
))
const primaryAction = computed<'post' | 'h3' | ''>(() => {
  if (hasRunnablePostWork.value) return 'post'
  if (pendingH3Segments.value.length) return 'h3'
  return ''
})

async function load(): Promise<void> {
  if (!props.projectId) return
  loading.value = true
  try {
    const [outputResult, postResult, lipRuntimeResult, segmentResult, h3RuntimeResult, qualityResult] = await Promise.all([
      remakeApi.getEpisodeOutputs(props.projectId),
      remakeApi.getPostProduction(props.projectId),
      remakeApi.getLipSyncRuntimeStatus(),
      remakeApi.getGenerationSegments(props.projectId),
      remakeApi.getH3RuntimeStatus(),
      remakeApi.getH3Quality(props.projectId),
    ])
    outputs.value = outputResult
    postproduction.value = postResult
    lipSyncRuntime.value = lipRuntimeResult
    h3Segments.value = segmentResult
    h3Runtime.value = h3RuntimeResult
    h3Quality.value = qualityResult
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '成片状态读取失败'
  } finally {
    loading.value = false
  }
}

async function startPost(): Promise<void> {
  if (!canStartPost.value) return
  starting.value = 'post'
  try {
    await remakeApi.startPostProduction(props.projectId)
    error.value = ''
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '成片任务启动失败'
  } finally {
    starting.value = ''
  }
}

async function startH3(): Promise<void> {
  if (!canStartH3.value) return
  starting.value = 'h3'
  try {
    await remakeApi.startH3Generation(props.projectId)
    error.value = ''
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '短剧镜头生成任务启动失败'
  } finally {
    starting.value = ''
  }
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
    READY: '可生成成片',
    WAITING_POSTPRODUCTION: '等待镜头完成',
    PROCESSING: '处理中',
    FAILED: '可重试',
    STALE: '需重新生成',
  }
  return labels[status] || status
}

function episodeVideo(episodeId: string): string {
  return remakeApi.episodeFinalVideoUrl(props.projectId, episodeId)
}

function episodeSubtitle(episodeId: string): string {
  return remakeApi.episodeSubtitleUrl(props.projectId, episodeId)
}

watch(() => props.projectId, () => void load())
watch(() => props.busy, (busy, previous) => { if (previous && !busy) void load() })
onMounted(() => void load())
</script>

<template>
  <section class="final-output">
    <header class="topbar">
      <div>
        <small>成片</small>
        <strong>本土化短剧输出</strong>
        <span>这里优先展示最终剧集。镜头生成、口型和拼接都在后台完成。</span>
      </div>
      <button :disabled="loading" @click="load">刷新</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="summary">
      <article class="success"><small>已成片</small><strong>{{ completed.length }}</strong><span>可直接播放和下载</span></article>
      <article><small>待成片</small><strong>{{ Math.max(0, episodes.length - completed.length) }}</strong><span>镜头生成、后期或拼接中</span></article>
      <article :class="{ warn: postReviewCount }"><small>需要确认</small><strong>{{ postReviewCount }}</strong><span>只显示真正需要人工判断的口型问题</span></article>
      <article :class="{ warn: (needsLipSync && !lipSyncRuntime?.ready) || (pendingH3Segments.length && !h3Runtime?.ready) }"><small>本地模型</small><strong>{{ pendingH3Segments.length ? (h3Runtime?.ready ? 'H3 就绪' : 'H3 未就绪') : (lipSyncRuntime?.ready ? '口型就绪' : '口型未就绪') }}</strong><span>MiniMax H3 / LatentSync</span></article>
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
            <span v-if="episode.error_message">{{ episode.error_message }}</span>
            <span v-else-if="postReviewCount">存在需要人工确认的口型定位，请到“待确认”处理。</span>
            <span v-else-if="pendingH3Segments.length && !h3Runtime?.ready">还有镜头未生成，需要先启动本地 MiniMax H3 Runtime。</span>
            <span v-else-if="pendingH3Segments.length">还有 {{ pendingH3Segments.length }} 个目标镜头待生成和自动质检。</span>
            <span v-else-if="needsLipSync && !lipSyncRuntime?.ready">需要先启动本地 LatentSync 1.6 Runtime。</span>
            <span v-else>系统会继续完成口型、最终目标音轨、字幕和整集拼接。</span>
          </div>
          <button v-if="primaryAction === 'h3'" class="primary" :disabled="!canStartH3" @click="startH3">
            {{ starting === 'h3' ? '正在启动…' : props.busy ? '后台处理中…' : '生成短剧镜头' }}
          </button>
          <button v-else class="primary" :disabled="!canStartPost" @click="startPost">
            {{ starting === 'post' ? '正在启动…' : props.busy ? '后台处理中…' : episode.status === 'READY' ? '生成整集成片' : '继续生成' }}
          </button>
        </div>
      </article>
    </section>

    <section v-else class="empty">
      <strong>还没有可展示的剧集成片</strong>
      <span v-if="pendingH3Segments.length">项目准备已经完成，还有 {{ pendingH3Segments.length }} 个目标镜头等待 MiniMax H3 生成。</span>
      <span v-else>先完成项目准备；有可用目标镜头后，这里会自动进入口型和整集成片。</span>
      <button v-if="pendingH3Segments.length" class="primary empty-action" :disabled="!canStartH3" @click="startH3">
        {{ starting === 'h3' ? '正在启动…' : h3Runtime?.ready ? '生成短剧镜头' : 'MiniMax H3 未就绪' }}
      </button>
    </section>

    <div v-if="primaryAction" class="actionbar">
      <div v-if="primaryAction === 'h3'">
        <strong>{{ pendingH3Segments.length }} 个镜头等待生成和自动质检</strong>
        <span v-if="!h3Runtime?.ready">本地 MiniMax H3 Runtime 未就绪。</span>
        <span v-else>生成完成且自动质检通过后，会继续进入口型和整集成片。</span>
      </div>
      <div v-else>
        <strong>{{ ready.length ? `${ready.length} 集可以直接拼成成片` : `${postReadyCount} 个镜头可继续后期` }}</strong>
        <span v-if="needsLipSync && !lipSyncRuntime?.ready">当前可见对白需要 LatentSync，但本地口型 Runtime 未就绪。</span>
        <span v-else>点击一次即可继续后台处理，不需要逐镜头操作。</span>
      </div>
      <button v-if="primaryAction === 'h3'" class="primary" :disabled="!canStartH3" @click="startH3">{{ starting === 'h3' ? '正在启动…' : '生成短剧镜头' }}</button>
      <button v-else class="primary" :disabled="!canStartPost" @click="startPost">{{ starting === 'post' ? '正在启动…' : '继续完成成片' }}</button>
    </div>

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
.final-output{display:grid;gap:12px}.topbar,.episode-list,.empty,.actionbar,.diagnostics{border:1px solid #dfe5ed;border-radius:13px;background:#fff}.topbar{display:flex;justify-content:space-between;align-items:center;padding:14px 16px}.topbar>div{display:grid;gap:2px}.final-output small{font-size:9px;color:#8793a4}.final-output strong{color:#405168;font-size:11px}.final-output span{color:#8591a2;font-size:9px}.topbar button,.buttons a{border:1px solid #dce2e9;border-radius:8px;padding:7px 10px;background:#fff;color:#617086;font-size:9px;cursor:pointer;text-decoration:none}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.summary article{display:grid;gap:3px;padding:11px;border:1px solid #e1e6ed;border-radius:10px;background:#fff}.summary article.success{border-color:#bcdcc9;background:#f5fbf7}.summary article.warn{border-color:#ead0ae;background:#fffaf2}.summary article strong{font-size:15px}.episode-list{display:grid;overflow:hidden}.episode-card{padding:14px 16px;border-top:1px solid #e8ecf1}.episode-card:first-child{border-top:0}.episode-heading{display:grid;grid-template-columns:36px 1fr auto;gap:10px;align-items:center}.number{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:#f0f4fa;color:#52667f;font-size:11px;font-weight:900}.title{display:grid;gap:3px}.episode-heading em{padding:5px 8px;border-radius:999px;background:#f1f3f6;color:#69778a;font-size:8px;font-style:normal}.episode-card.succeeded .episode-heading em{background:#eaf7ef;color:#317653}.episode-card.ready .episode-heading em{background:#eaf0ff;color:#3a5ca8}.episode-card.failed .episode-heading em{background:#fff1e2;color:#9a6313}.finished{display:grid;grid-template-columns:minmax(220px,320px) 1fr;gap:15px;margin-top:12px;padding-left:46px}.finished video{width:100%;aspect-ratio:9/16;max-height:480px;border-radius:10px;background:#111}.finished-actions{display:flex;justify-content:space-between;align-items:flex-end;gap:12px}.finished-actions>div:first-child{display:grid;gap:3px}.buttons{display:flex;gap:7px;flex-wrap:wrap}.buttons a.primary,.primary{border:0;border-radius:8px;padding:9px 13px;background:#3566d6;color:#fff;font-size:9px;font-weight:800;text-decoration:none;cursor:pointer}.primary:disabled{opacity:.45;cursor:not-allowed}.pending{display:flex;justify-content:space-between;align-items:center;gap:14px;margin:12px 0 0 46px;padding:12px 13px;border-radius:10px;background:#f8fafc}.pending>div{display:grid;gap:3px}.empty{display:grid;gap:4px;padding:22px}.empty-action{justify-self:start;margin-top:8px}.actionbar{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:14px 16px}.actionbar>div{display:grid;gap:3px}.diagnostics>summary{padding:11px 13px;cursor:pointer;font-size:10px;font-weight:800;color:#506176}.diag-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;padding:0 13px 10px}.diag-grid span{padding:8px;border-radius:8px;background:#f7f9fb;text-align:center}.diag-row{display:grid;grid-template-columns:minmax(180px,1fr) 100px minmax(260px,2fr);gap:8px;align-items:center;padding:8px 13px;border-top:1px solid #eef1f4}.diag-row em{font-size:8px;font-style:normal;color:#718096}.error{margin:0;padding:8px 10px;border-radius:7px;background:#fff2f2;color:#a94e4e;font-size:10px}@media(max-width:900px){.summary{grid-template-columns:1fr 1fr}.finished{grid-template-columns:1fr;padding-left:0}.finished video{max-height:520px}.finished-actions,.pending,.actionbar{align-items:stretch;flex-direction:column}.pending{margin-left:0}.diag-row{grid-template-columns:1fr}.diag-grid{grid-template-columns:1fr 1fr}}
</style>
