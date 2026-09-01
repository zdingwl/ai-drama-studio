<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { remakeApi } from '../api/remake'
import type { GenerationAttempt, GenerationAttemptSummary, GenerationSegmentPlan, H3RuntimeStatus } from '../types/remake'

const props = defineProps<{ projectId: string; busy?: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const runtime = ref<H3RuntimeStatus | null>(null)
const segments = ref<GenerationSegmentPlan | null>(null)
const attempts = ref<GenerationAttemptSummary | null>(null)
const loading = ref(false)
const starting = ref(false)
const error = ref('')

const readySegments = computed(() => segments.value?.episodes.flatMap((episode) => episode.segments).filter((segment) => segment.status === 'READY') ?? [])
const latestSuccesses = computed(() => {
  const bySegment = new Map<string, GenerationAttempt>()
  for (const attempt of attempts.value?.attempts ?? []) {
    if (attempt.status !== 'SUCCEEDED') continue
    const current = bySegment.get(attempt.generation_segment_id)
    if (!current || attempt.attempt_number > current.attempt_number) bySegment.set(attempt.generation_segment_id, attempt)
  }
  return [...bySegment.values()]
})
const failures = computed(() => attempts.value?.attempts.filter((item) => item.status === 'FAILED') ?? [])
const canGenerate = computed(() => Boolean(runtime.value?.ready && readySegments.value.length && !props.busy && !starting.value))

async function load(): Promise<void> {
  if (!props.projectId) return
  loading.value = true
  try {
    const [runtimeResult, segmentResult] = await Promise.all([
      remakeApi.getH3RuntimeStatus(),
      remakeApi.getGenerationSegments(props.projectId),
    ])
    runtime.value = runtimeResult
    segments.value = segmentResult
    try { attempts.value = await remakeApi.listGenerationAttempts(props.projectId) } catch { attempts.value = null }
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'H3 生成状态读取失败'
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
    error.value = err instanceof Error ? err.message : 'H3 生成任务启动失败'
  } finally {
    starting.value = false
  }
}

function duration(us: number): string { return `${(us / 1_000_000).toFixed(2)}s` }
function attemptVideo(attempt: GenerationAttempt): string { return remakeApi.generationAttemptVideoUrl(attempt.id) }

watch(() => props.projectId, () => void load())
watch(() => props.busy, (busy, previous) => { if (previous && !busy) void load() })
onMounted(() => void load())
</script>

<template>
  <section class="h3-output">
    <header>
      <div><small>本地生成</small><strong>MiniMax H3</strong><span>自动准备人物/场景参考，按 GenerationSegment 顺序生成</span></div>
      <button :disabled="loading" @click="load">刷新</button>
    </header>
    <p v-if="error" class="error">{{ error }}</p>

    <div class="status-grid">
      <article :class="{ ready: runtime?.ready }"><small>H3 Runtime</small><strong>{{ runtime?.ready ? '已就绪' : '未就绪' }}</strong><span>FL2VA + Ref2VA</span></article>
      <article><small>可生成</small><strong>{{ readySegments.length }}</strong><span>当前 READY GenerationSegment</span></article>
      <article><small>成功</small><strong>{{ latestSuccesses.length }}</strong><span>当前输入下可复用</span></article>
      <article :class="{ warn: failures.length }"><small>失败记录</small><strong>{{ failures.length }}</strong><span>可再次生成，不覆盖成功版本</span></article>
    </div>

    <div class="generate-bar">
      <div>
        <strong v-if="runtime?.ready">{{ readySegments.length ? `有 ${readySegments.length} 个分段可进入 H3` : '当前没有可生成分段' }}</strong>
        <strong v-else>先启动本地 MiniMax H3 Runtime</strong>
        <span>已经成功且输入没有变化的分段会自动复用；目标人物/本土化场景参考缺失时后台自动补齐。</span>
      </div>
      <button class="primary" :disabled="!canGenerate" @click="start">{{ starting ? '正在启动…' : props.busy ? '后台任务处理中…' : '生成可用镜头' }}</button>
    </div>

    <div v-if="segments" class="segment-list">
      <header><strong>生成分段</strong><span>{{ segments.segment_count }} 段 · {{ segments.review_count }} 需确认 · {{ segments.waiting_audio_count }} 等待声音</span></header>
      <div class="segment-row" v-for="segment in segments.episodes.flatMap((episode) => episode.segments)" :key="segment.id">
        <b>Shot {{ segment.shot_ordinal }}<template v-if="segment.shot_segment_count > 1"> · {{ segment.shot_segment_index }}/{{ segment.shot_segment_count }}</template></b>
        <span>{{ segment.generation_mode }}</span>
        <span>{{ duration(segment.target_duration_us) }} → H3 {{ duration(segment.h3_duration_us) }}</span>
        <em :class="segment.status.toLowerCase()">{{ segment.status === 'READY' ? '可生成' : segment.status === 'WAITING_AUDIO' ? '等声音' : '需确认' }}</em>
      </div>
    </div>

    <div v-if="latestSuccesses.length" class="outputs">
      <header><strong>已生成镜头</strong><span>{{ latestSuccesses.length }} 个当前成功版本</span></header>
      <div class="video-grid">
        <article v-for="attempt in latestSuccesses" :key="attempt.id">
          <video controls preload="metadata" :src="attemptVideo(attempt)" />
          <div><strong>{{ attempt.mode }}</strong><span>版本 {{ attempt.attempt_number }}</span></div>
        </article>
      </div>
    </div>

    <details v-if="failures.length" class="failures">
      <summary>失败记录 · {{ failures.length }}</summary>
      <div v-for="attempt in failures" :key="attempt.id"><strong>{{ attempt.generation_segment_id }}</strong><span>{{ attempt.error_message || attempt.provider_status || '生成失败' }}</span></div>
    </details>
  </section>
</template>

<style scoped>
.h3-output{display:grid;gap:12px}.h3-output>header,.generate-bar,.segment-list,.outputs,.failures{border:1px solid #dfe5ed;border-radius:13px;background:#fff}.h3-output>header{display:flex;justify-content:space-between;align-items:center;padding:14px 16px}.h3-output>header>div{display:grid;gap:2px}.h3-output small{font-size:9px;color:#8793a4}.h3-output strong{color:#405168;font-size:11px}.h3-output span{color:#8591a2;font-size:9px}.h3-output>header button{border:1px solid #dce2e9;border-radius:8px;padding:7px 10px;background:#fff;color:#617086;font-size:9px;cursor:pointer}.status-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.status-grid article{display:grid;gap:3px;padding:11px;border:1px solid #e1e6ed;border-radius:10px;background:#fff}.status-grid article.ready{border-color:#bcdcc9;background:#f5fbf7}.status-grid article.warn{border-color:#ead0ae;background:#fffaf2}.status-grid article strong{font-size:14px}.generate-bar{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:14px 16px}.generate-bar>div{display:grid;gap:3px}.primary{min-height:38px;border:0;border-radius:8px;padding:0 16px;background:#3566d6;color:#fff;font-size:10px;font-weight:800;cursor:pointer}.primary:disabled{opacity:.45}.segment-list,.outputs{overflow:hidden}.segment-list>header,.outputs>header{display:flex;justify-content:space-between;padding:11px 13px;border-bottom:1px solid #e6eaf0}.segment-row{display:grid;grid-template-columns:1fr 90px 170px 80px;gap:10px;align-items:center;padding:8px 13px;border-top:1px solid #f0f2f5}.segment-row:first-of-type{border-top:0}.segment-row b{font-size:10px;color:#4a5c73}.segment-row em{justify-self:end;padding:4px 7px;border-radius:999px;font-size:8px;font-style:normal}.segment-row em.ready{background:#eaf7ef;color:#317653}.segment-row em.waiting_audio{background:#f3f4f6;color:#778395}.segment-row em.review{background:#fff1e2;color:#9a6313}.video-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;padding:10px}.video-grid article{overflow:hidden;border:1px solid #e3e8ee;border-radius:9px;background:#fafbfd}.video-grid video{display:block;width:100%;aspect-ratio:9/16;max-height:420px;background:#111}.video-grid article>div{display:flex;justify-content:space-between;padding:8px}.failures>summary{padding:11px 13px;cursor:pointer;font-size:10px;font-weight:800}.failures>div{display:grid;gap:2px;padding:8px 13px;border-top:1px solid #eee}.error{margin:0;padding:8px 10px;border-radius:7px;background:#fff2f2;color:#a94e4e;font-size:10px}@media(max-width:1000px){.status-grid{grid-template-columns:1fr 1fr}.generate-bar{align-items:stretch;flex-direction:column}.segment-row{grid-template-columns:1fr 70px}.video-grid{grid-template-columns:1fr 1fr}}
</style>
