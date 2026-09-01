<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { remakeApi } from '../api/remake'
import type {
  GenerationAttempt,
  GenerationAttemptSummary,
  GenerationQualityCheck,
  GenerationQualitySummary,
  GenerationSegmentPlan,
  GenerationSelection,
  H3RuntimeStatus,
} from '../types/remake'

const props = defineProps<{ projectId: string; busy?: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const runtime = ref<H3RuntimeStatus | null>(null)
const segments = ref<GenerationSegmentPlan | null>(null)
const attempts = ref<GenerationAttemptSummary | null>(null)
const quality = ref<GenerationQualitySummary | null>(null)
const loading = ref(false)
const starting = ref(false)
const error = ref('')

const readySegments = computed(() => segments.value?.episodes.flatMap((episode) => episode.segments).filter((segment) => segment.status === 'READY') ?? [])
const attemptById = computed(() => new Map((attempts.value?.attempts ?? []).map((attempt) => [attempt.id, attempt])))
const checkById = computed(() => new Map((quality.value?.checks ?? []).map((check) => [check.id, check])))
const selectedOutputs = computed(() => (quality.value?.selections ?? []).map((selection) => ({
  selection,
  attempt: attemptById.value.get(selection.selected_attempt_id) ?? null,
  check: selection.quality_check_id ? checkById.value.get(selection.quality_check_id) ?? null : null,
})).filter((item) => item.attempt !== null))
const generationFailures = computed(() => attempts.value?.attempts.filter((item) => item.status === 'FAILED') ?? [])
const qcAttention = computed(() => (quality.value?.retry_count ?? 0) + (quality.value?.review_count ?? 0) + (quality.value?.waiting_model_count ?? 0))
const canGenerate = computed(() => Boolean(runtime.value?.ready && readySegments.value.length && !props.busy && !starting.value))

async function load(): Promise<void> {
  if (!props.projectId) return
  loading.value = true
  try {
    const [runtimeResult, segmentResult, attemptResult, qualityResult] = await Promise.all([
      remakeApi.getH3RuntimeStatus(),
      remakeApi.getGenerationSegments(props.projectId),
      remakeApi.listGenerationAttempts(props.projectId),
      remakeApi.getH3Quality(props.projectId),
    ])
    runtime.value = runtimeResult
    segments.value = segmentResult
    attempts.value = attemptResult
    quality.value = qualityResult
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'H3 生成 / QC 状态读取失败'
  } finally {
    loading.value = false
  }
}

async function start(): Promise<void> {
  if (!canGenerate.value) return
  starting.value = true
  try {
    await remakeApi.startH3Generation(props.projectId)
    error.value = ''
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'H3 生成 / QC 任务启动失败'
  } finally {
    starting.value = false
  }
}

function duration(us: number): string { return `${(us / 1_000_000).toFixed(2)}s` }
function attemptVideo(attempt: GenerationAttempt): string { return remakeApi.generationAttemptVideoUrl(attempt.id) }
function score(value: number | null | undefined): string { return value == null ? '—' : `${Math.round(value * 100)}%` }
function selectionLabel(selection: GenerationSelection): string { return selection.selection_source === 'AUTO' ? '自动质检通过' : '人工采用' }
function qcLabel(check: GenerationQualityCheck): string {
  const labels: Record<string, string> = { PASS: '通过', RETRY: '需重试', REVIEW: '待确认', WAITING_MODEL: '等质检模型', STALE: '已失效' }
  return labels[check.status] || check.status
}

watch(() => props.projectId, () => void load())
watch(() => props.busy, (busy, previous) => { if (previous && !busy) void load() })
onMounted(() => void load())
</script>

<template>
  <section class="h3-output">
    <header>
      <div><small>本地生成</small><strong>MiniMax H3 + 自动质检</strong><span>只有 QC 通过或人工明确采用的版本，才进入后续口型与整集成片</span></div>
      <button :disabled="loading" @click="load">刷新</button>
    </header>
    <p v-if="error" class="error">{{ error }}</p>

    <div class="status-grid">
      <article :class="{ ready: runtime?.ready }"><small>H3 Runtime</small><strong>{{ runtime?.ready ? '已就绪' : '未就绪' }}</strong><span>FL2VA + Ref2VA</span></article>
      <article><small>可生成</small><strong>{{ readySegments.length }}</strong><span>当前 READY GenerationSegment</span></article>
      <article class="ready"><small>已选中</small><strong>{{ quality?.selected_count ?? 0 }}</strong><span>可进入后续成片的镜头</span></article>
      <article :class="{ warn: qcAttention || generationFailures.length }"><small>需处理</small><strong>{{ qcAttention + generationFailures.length }}</strong><span>自动重试 / 待模型 / 待人工确认</span></article>
    </div>

    <div class="generate-bar">
      <div>
        <strong v-if="runtime?.ready">{{ readySegments.length ? `有 ${readySegments.length} 个分段可执行 H3 生成 + QC` : '当前没有可生成分段' }}</strong>
        <strong v-else>先启动本地 MiniMax H3 Runtime</strong>
        <span>生成后先检查解码与真实时长，再由本地 Qwen3-VL 检查人物、场景、动作/镜头和连续性；不通过会自动换 seed 并按 QC 建议重试。</span>
      </div>
      <button class="primary" :disabled="!canGenerate" @click="start">{{ starting ? '正在启动…' : props.busy ? '后台任务处理中…' : '生成并质检可用镜头' }}</button>
    </div>

    <div v-if="segments" class="segment-list">
      <header><strong>生成分段</strong><span>{{ segments.segment_count }} 段 · {{ quality?.selected_count ?? 0 }} 已选中 · {{ segments.review_count }} 上游需确认 · {{ segments.waiting_audio_count }} 等声音</span></header>
      <div class="segment-row" v-for="segment in segments.episodes.flatMap((episode) => episode.segments)" :key="segment.id">
        <b>Shot {{ segment.shot_ordinal }}<template v-if="segment.shot_segment_count > 1"> · {{ segment.shot_segment_index }}/{{ segment.shot_segment_count }}</template></b>
        <span>{{ segment.generation_mode }}</span>
        <span>{{ duration(segment.target_duration_us) }} → H3 {{ duration(segment.h3_duration_us) }}</span>
        <em :class="segment.status.toLowerCase()">{{ segment.status === 'READY' ? '可生成' : segment.status === 'WAITING_AUDIO' ? '等声音' : '需确认' }}</em>
      </div>
    </div>

    <div v-if="selectedOutputs.length" class="outputs">
      <header><strong>当前可用镜头</strong><span>{{ selectedOutputs.length }} 个 Selected Output</span></header>
      <div class="video-grid">
        <article v-for="item in selectedOutputs" :key="item.selection.id">
          <video v-if="item.attempt" controls preload="metadata" :src="attemptVideo(item.attempt)" />
          <div class="video-meta">
            <div><strong>{{ item.attempt?.mode }}</strong><span>版本 {{ item.attempt?.attempt_number }}</span></div>
            <em :class="item.selection.selection_source.toLowerCase()">{{ selectionLabel(item.selection) }}</em>
          </div>
          <div class="score"><span>QC {{ score(item.selection.quality_score) }}</span><span>{{ item.check ? qcLabel(item.check) : '人工结构校验通过' }}</span></div>
        </article>
      </div>
    </div>

    <section v-else-if="quality && readySegments.length" class="empty-output">
      <strong>还没有通过质检的可用镜头</strong>
      <span>H3 技术生成成功不等于成片可用；完成 QC 后这里只展示 Selected Output。</span>
    </section>

    <details v-if="quality?.checks.length" class="qc-history">
      <summary>质检历史 · {{ quality.check_count }}</summary>
      <div v-for="check in quality.checks" :key="check.id" class="qc-row">
        <strong>{{ check.generation_segment_id }}</strong>
        <em :class="check.status.toLowerCase()">{{ qcLabel(check) }}</em>
        <span>质量 {{ score(check.quality_score) }}</span>
        <p>{{ check.reason }}</p>
      </div>
    </details>

    <details v-if="generationFailures.length" class="failures">
      <summary>生成运行失败 · {{ generationFailures.length }}</summary>
      <div v-for="attempt in generationFailures" :key="attempt.id"><strong>{{ attempt.generation_segment_id }}</strong><span>{{ attempt.error_message || attempt.provider_status || '生成失败' }}</span></div>
    </details>
  </section>
</template>

<style scoped>
.h3-output{display:grid;gap:12px}.h3-output>header,.generate-bar,.segment-list,.outputs,.qc-history,.failures,.empty-output{border:1px solid #dfe5ed;border-radius:13px;background:#fff}.h3-output>header{display:flex;justify-content:space-between;align-items:center;padding:14px 16px}.h3-output>header>div{display:grid;gap:2px}.h3-output small{font-size:9px;color:#8793a4}.h3-output strong{color:#405168;font-size:11px}.h3-output span{color:#8591a2;font-size:9px}.h3-output>header button{border:1px solid #dce2e9;border-radius:8px;padding:7px 10px;background:#fff;color:#617086;font-size:9px;cursor:pointer}.status-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.status-grid article{display:grid;gap:3px;padding:11px;border:1px solid #e1e6ed;border-radius:10px;background:#fff}.status-grid article.ready{border-color:#bcdcc9;background:#f5fbf7}.status-grid article.warn{border-color:#ead0ae;background:#fffaf2}.status-grid article strong{font-size:14px}.generate-bar{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:14px 16px}.generate-bar>div{display:grid;gap:3px}.primary{min-height:38px;border:0;border-radius:8px;padding:0 16px;background:#3566d6;color:#fff;font-size:10px;font-weight:800;cursor:pointer}.primary:disabled{opacity:.45}.segment-list,.outputs{overflow:hidden}.segment-list>header,.outputs>header{display:flex;justify-content:space-between;padding:11px 13px;border-bottom:1px solid #e6eaf0}.segment-row{display:grid;grid-template-columns:1fr 90px 170px 80px;gap:10px;align-items:center;padding:8px 13px;border-top:1px solid #f0f2f5}.segment-row:first-of-type{border-top:0}.segment-row b{font-size:10px;color:#4a5c73}.segment-row em,.qc-row em,.video-meta em{justify-self:end;padding:4px 7px;border-radius:999px;font-size:8px;font-style:normal}.segment-row em.ready,.qc-row em.pass,.video-meta em.auto{background:#eaf7ef;color:#317653}.segment-row em.waiting_audio,.qc-row em.waiting_model,.qc-row em.stale{background:#f3f4f6;color:#778395}.segment-row em.review,.qc-row em.review,.qc-row em.retry,.video-meta em.manual{background:#fff1e2;color:#9a6313}.video-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;padding:10px}.video-grid article{overflow:hidden;border:1px solid #e3e8ee;border-radius:9px;background:#fafbfd}.video-grid video{display:block;width:100%;aspect-ratio:9/16;max-height:420px;background:#111}.video-meta,.score{display:flex;justify-content:space-between;align-items:center;padding:8px}.video-meta>div{display:grid;gap:2px}.score{padding-top:0}.empty-output{display:grid;gap:3px;padding:16px}.qc-history>summary,.failures>summary{padding:11px 13px;cursor:pointer;font-size:10px;font-weight:800}.qc-row{display:grid;grid-template-columns:minmax(180px,1fr) 80px 90px minmax(280px,2fr);gap:8px;align-items:center;padding:8px 13px;border-top:1px solid #eee}.qc-row p{margin:0;color:#6e7b8d;font-size:9px}.failures>div{display:grid;gap:2px;padding:8px 13px;border-top:1px solid #eee}.error{margin:0;padding:8px 10px;border-radius:7px;background:#fff2f2;color:#a94e4e;font-size:10px}@media(max-width:1000px){.status-grid{grid-template-columns:1fr 1fr}.generate-bar{align-items:stretch;flex-direction:column}.segment-row{grid-template-columns:1fr 70px}.video-grid{grid-template-columns:1fr 1fr}.qc-row{grid-template-columns:1fr 80px}}
</style>
