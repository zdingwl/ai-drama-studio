<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { ContentAnalysisRun, Episode, F05ModelStatus, Shot } from '../types/studio'
import AssetReviewMatrixV4 from './AssetReviewMatrixV4.vue'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

type UnresolvedShot = {
  shotId: string
  episodeOrder: number
  shotOrdinal: number
  candidateLabel: string
}

type V6ModelStatus = F05ModelStatus & {
  tracking_runtime?: {
    ready?: boolean
    tracker?: string | null
    package?: string
    frame_rate?: number
    error?: string
  }
  final_policy?: string
}

const status = ref<V6ModelStatus | null>(null)
const loading = ref(true)
const preparing = ref(false)
const error = ref('')
const unresolvedShots = ref<UnresolvedShot[]>([])
const resolvedCount = ref(0)
const unresolvedEvidenceCount = ref(0)

const missingModels = computed(() => (status.value?.models ?? []).filter((item) => !item.ready))
const unresolvedPreview = computed(() => unresolvedShots.value.slice(0, 12))
const runtimeLabel = computed(() => {
  const runtime = status.value?.runtime
  if (!runtime) return '运行时未知'
  if (runtime.device === 'GPU') return `GPU · CUDA · ${runtime.provider || 'CUDAExecutionProvider'}`
  return `CPU fallback · ${runtime.provider || 'CPUExecutionProvider'}`
})
const trackingLabel = computed(() => {
  const tracking = status.value?.tracking_runtime
  if (!tracking) return 'MOT 未知'
  if (!tracking.ready) return 'MOT 未准备'
  return `${tracking.tracker || 'Mature MOT'} · ${tracking.frame_rate || 12}fps`
})

/**
 * 职责：读取 Character V6 固定模型、GPU 与 Mature MOT 状态，不触发联网。
 */
async function refreshModelStatus(): Promise<void> {
  try {
    status.value = await api.getF05ModelStatus() as V6ModelStatus
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物模型状态读取失败'
  } finally {
    loading.value = false
  }
}

/**
 * 职责：读取 V6 Global Identity 结果，把 Final-ready 与 Unresolved Evidence 分开显示。
 * Unresolved 即使出现过一次脸也不能变成 Final Character。
 */
async function refreshPersonCompleteness(): Promise<void> {
  try {
    const analysis: ContentAnalysisRun | null = await api.getCurrentContentAnalysis(props.projectId)
    if (!analysis) {
      unresolvedShots.value = []
      resolvedCount.value = 0
      unresolvedEvidenceCount.value = 0
      return
    }
    resolvedCount.value = Number(analysis.counts?.resolved_character_candidates || 0)
    unresolvedEvidenceCount.value = Number(analysis.counts?.unresolved_character_candidates || 0)

    const groups = await Promise.all(props.episodes.map((episode) => api.listShots(episode.id)))
    const shotMeta = new Map<string, { episodeOrder: number; shotOrdinal: number }>()
    props.episodes.forEach((episode, episodeIndex) => {
      const episodeShots: Shot[] = groups[episodeIndex] ?? []
      for (const shot of episodeShots) {
        shotMeta.set(shot.id, { episodeOrder: episode.sort_order, shotOrdinal: shot.ordinal })
      }
    })

    const seen = new Set<string>()
    const result: UnresolvedShot[] = []
    for (const candidate of analysis.characters) {
      // V6 持久化会把 Unresolved 明确命名为“待解析人物 xxx”。
      // 兼容历史 Run：完全没有 Face anchor 的 Candidate 仍视为 unresolved。
      const unresolved = candidate.auto_label.startsWith('待解析人物')
        || !candidate.tracks.some((track) => track.face_visible)
      if (!unresolved) continue
      for (const track of candidate.tracks) {
        if (seen.has(track.shot_id)) continue
        const meta = shotMeta.get(track.shot_id)
        if (!meta) continue
        seen.add(track.shot_id)
        result.push({
          shotId: track.shot_id,
          episodeOrder: meta.episodeOrder,
          shotOrdinal: meta.shotOrdinal,
          candidateLabel: candidate.auto_label,
        })
      }
    }
    unresolvedShots.value = result.sort((left, right) => (
      left.episodeOrder - right.episodeOrder || left.shotOrdinal - right.shotOrdinal
    ))
  } catch {
    unresolvedShots.value = []
  }
}

async function prepareModels(): Promise<void> {
  preparing.value = true
  error.value = ''
  try {
    status.value = await api.prepareF05Models() as V6ModelStatus
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物 V6 模型准备失败'
  } finally {
    preparing.value = false
  }
}

onMounted(async () => {
  await Promise.all([refreshModelStatus(), refreshPersonCompleteness()])
})
</script>

<template>
  <div class="asset-stage-v4">
    <div v-if="!loading && status && !status.ready" class="character-v4-banner warning">
      <div>
        <strong>人物识别 V6 运行时未准备完整</strong>
        <span>V6 需要 YOLOX / YuNet-SFace / YoutuReID + trackers Mature MOT。未准备完整时不要重新提取资产，旧 Current 会继续保留。</span>
        <small v-if="missingModels.length">缺少模型：{{ missingModels.map((item) => item.filename).join('、') }}</small>
        <small v-if="status.tracking_runtime && !status.tracking_runtime.ready">MOT：{{ status.tracking_runtime.error || 'trackers/supervision 未准备' }}</small>
      </div>
      <button :disabled="preparing" @click="prepareModels">{{ preparing ? '正在准备模型…' : '准备人物 V6 模型' }}</button>
    </div>

    <div v-else-if="!loading && status?.ready" class="character-v4-banner ready">
      <div>
        <strong>人物识别 V6 · READY · {{ runtimeLabel }} · {{ trackingLabel }}</strong>
        <span>12fps Person → Mature MOT → Clean Track Gallery → Global Identity Graph；只有 RESOLVED Identity 才进入 Final Character。</span>
        <small>Face provider：{{ status.face_runtime?.detail || 'YuNet + SFace' }}；Global Identity 已与 Face provider 解耦，可后续替换有授权的更强模型。</small>
        <small v-if="status.runtime?.fallback">⚠ CUDA 未实际启用，当前已自动降级 CPU；结果逻辑不变，但分析会明显变慢。</small>
      </div>
    </div>

    <div v-if="resolvedCount || unresolvedEvidenceCount" class="character-v4-banner identity-summary">
      <div>
        <strong>Global Identity：{{ resolvedCount }} 个 Final-ready 人物 · {{ unresolvedEvidenceCount }} 个待解析 Evidence</strong>
        <span>待解析碎片不会再计入人物资产数量；后续更强 Face/连续镜头 Evidence 可以把它们归回已有 Character。</span>
      </div>
    </div>

    <div v-if="unresolvedShots.length" class="character-v4-banner unresolved">
      <div>
        <strong>⚠ {{ unresolvedShots.length }} 个 Shot 含未解析人物 Evidence</strong>
        <span>这些 Track 被明确保留，但不会自动制造“人物020 / 人物032”这类 Final Character。</span>
        <div class="unresolved-shot-list">
          <span v-for="item in unresolvedPreview" :key="item.shotId">
            E{{ String(item.episodeOrder).padStart(2, '0') }} · SHOT {{ String(item.shotOrdinal).padStart(4, '0') }}
          </span>
          <em v-if="unresolvedShots.length > unresolvedPreview.length">+{{ unresolvedShots.length - unresolvedPreview.length }}</em>
        </div>
      </div>
    </div>

    <div v-if="error" class="character-v4-error">{{ error }}</div>
    <AssetReviewMatrixV4 :project-id="props.projectId" :episodes="props.episodes" />
  </div>
</template>

<style scoped>
.asset-stage-v4{min-height:100%}.character-v4-banner{margin:14px 22px 0;padding:10px 13px;border:1px solid;border-radius:11px;display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:12px}.character-v4-banner>div{min-width:0;display:grid;gap:2px}.character-v4-banner strong{font-size:13px}.character-v4-banner span,.character-v4-banner small{line-height:1.45}.character-v4-banner.warning{background:#fff9eb;border-color:#f1d58d;color:#73510b}.character-v4-banner.warning span,.character-v4-banner.warning small{color:#8b6a25}.character-v4-banner.ready{background:#effbf5;border-color:#bfe7d2;color:#176a45}.character-v4-banner.ready span{color:#49806a}.character-v4-banner.ready small{color:#557c6b}.character-v4-banner.identity-summary{background:#f1f6ff;border-color:#c7d7f7;color:#2754a5}.character-v4-banner.identity-summary span{color:#5873a5}.character-v4-banner.unresolved{background:#fff8ee;border-color:#efc982;color:#7b4d08}.character-v4-banner.unresolved span{color:#835f28}.character-v4-banner button{flex:0 0 auto;border:0;border-radius:8px;padding:8px 12px;background:#2f60e8;color:#fff;font-weight:750;cursor:pointer}.character-v4-banner button:disabled{opacity:.6;cursor:wait}.character-v4-error{margin:8px 22px 0;padding:8px 11px;border-radius:8px;background:#fff0f0;color:#b53a3a;font-size:12px}.unresolved-shot-list{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px}.unresolved-shot-list span,.unresolved-shot-list em{padding:3px 7px;border-radius:999px;background:#fff;border:1px solid #efd7a9;font-style:normal;font-size:10px;font-weight:700;color:#815a18}
</style>