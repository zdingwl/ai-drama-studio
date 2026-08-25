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

const status = ref<F05ModelStatus | null>(null)
const loading = ref(true)
const preparing = ref(false)
const error = ref('')
const unresolvedShots = ref<UnresolvedShot[]>([])

const missingModels = computed(() => (status.value?.models ?? []).filter((item) => !item.ready))
const unresolvedPreview = computed(() => unresolvedShots.value.slice(0, 12))
const runtimeLabel = computed(() => {
  const runtime = status.value?.runtime
  if (!runtime) return '运行时未知'
  if (runtime.device === 'GPU') return `GPU · CUDA · ${runtime.provider || 'CUDAExecutionProvider'}`
  return `CPU fallback · ${runtime.provider || 'CPUExecutionProvider'}`
})

/**
 * 职责：只读取人物 V5 固定模型和推理设备状态，不触发联网。
 * 输入：无；输出：YuNet / SFace / YOLOX / YoutuReID + GPU/CPU 状态。
 * 为什么：正式资产 Run 不能在后台静默下载模型，也不能静默从 GPU 降级 CPU。
 */
async function refreshModelStatus(): Promise<void> {
  try {
    status.value = await api.getF05ModelStatus()
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物模型状态读取失败'
  } finally {
    loading.value = false
  }
}

/**
 * 职责：从当前不可变 Character Evidence 中找出“Person Track 已建立，但没有任何 Face identity anchor”的 Shot。
 * 输入：Current ContentAnalysisRun + Current Shot；输出：需要人工关注的 EP / Shot 列表。
 * 为什么：V5 允许身份暂时不确定，但绝不允许把检测到的人静默当成“无人”。
 */
async function refreshPersonCompleteness(): Promise<void> {
  try {
    const analysis: ContentAnalysisRun | null = await api.getCurrentContentAnalysis(props.projectId)
    if (!analysis) {
      unresolvedShots.value = []
      return
    }
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
      if (candidate.tracks.some((track) => track.face_visible)) continue
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

/** 用户显式准备人物 V5 所需全部固定模型。 */
async function prepareModels(): Promise<void> {
  preparing.value = true
  error.value = ''
  try {
    status.value = await api.prepareF05Models()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物 V5 模型准备失败'
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
        <strong>人物识别 V5 模型未准备完整</strong>
        <span>Track First 需要 YOLOX Person Detection + YuNet/SFace + YoutuReID。模型未准备前不要重新提取资产，旧 Current 会继续保留。</span>
        <small v-if="missingModels.length">缺少：{{ missingModels.map((item) => item.filename).join('、') }}</small>
      </div>
      <button :disabled="preparing" @click="prepareModels">{{ preparing ? '正在准备模型…' : '准备人物 V5 模型' }}</button>
    </div>

    <div v-else-if="!loading && status?.ready" class="character-v4-banner ready">
      <div>
        <strong>人物识别 V5 · READY · {{ runtimeLabel }}</strong>
        <span>Track First → Clean Track Gallery → Character Gallery；多人镜头的正式人物图库只保存目标人物自己的干净代表图。</span>
        <small v-if="status.runtime?.fallback">⚠ CUDA 未实际启用，当前已自动降级 CPU；结果不受影响，但人物 Track 分析会明显变慢。</small>
      </div>
    </div>

    <div v-if="unresolvedShots.length" class="character-v4-banner unresolved">
      <div>
        <strong>⚠ 人物完整性：{{ unresolvedShots.length }} 个 Shot 检测到人物 Track，但身份尚未确定</strong>
        <span>这些 Track 不会被自动创建成假人物，也不会静默当成“无人”；后续镜头出现更强 Face/ReID Evidence 时仍可归并到已有 Character_ID。</span>
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
.asset-stage-v4{min-height:100%}.character-v4-banner{margin:14px 22px 0;padding:10px 13px;border:1px solid;border-radius:11px;display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:12px}.character-v4-banner>div{min-width:0;display:grid;gap:2px}.character-v4-banner strong{font-size:13px}.character-v4-banner span,.character-v4-banner small{line-height:1.45}.character-v4-banner.warning{background:#fff9eb;border-color:#f1d58d;color:#73510b}.character-v4-banner.warning span,.character-v4-banner.warning small{color:#8b6a25}.character-v4-banner.ready{background:#effbf5;border-color:#bfe7d2;color:#176a45}.character-v4-banner.ready span{color:#49806a}.character-v4-banner.ready small{color:#7a5a13}.character-v4-banner.unresolved{background:#fff8ee;border-color:#efc982;color:#7b4d08}.character-v4-banner.unresolved span{color:#835f28}.character-v4-banner button{flex:0 0 auto;border:0;border-radius:8px;padding:8px 12px;background:#2f60e8;color:#fff;font-weight:750;cursor:pointer}.character-v4-banner button:disabled{opacity:.6;cursor:wait}.character-v4-error{margin:8px 22px 0;padding:8px 11px;border-radius:8px;background:#fff0f0;color:#b53a3a;font-size:12px}.unresolved-shot-list{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px}.unresolved-shot-list span,.unresolved-shot-list em{padding:3px 7px;border-radius:999px;background:#fff;border:1px solid #efd7a9;font-style:normal;font-size:10px;font-weight:700;color:#815a18}
</style>