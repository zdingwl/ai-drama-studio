<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import type { BackgroundTask, ContentAnalysisRun, Episode, F05ModelStatus } from '../types/studio'
import AssetReviewMatrixV4 from './AssetReviewMatrixV4.vue'
import CharacterPersonGalleryV10 from './CharacterPersonGalleryV10.vue'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

type CharacterModelStatus = F05ModelStatus & {
  tracking_runtime?: {
    ready?: boolean
    tracker?: string | null
    package?: string
    frame_rate?: number
    error?: string
  }
  final_policy?: string
}

const status = ref<CharacterModelStatus | null>(null)
const loading = ref(true)
const preparing = ref(false)
const error = ref('')
const resolvedCount = ref(0)
const unresolvedEvidenceCount = ref(0)
const analysisProfile = ref('')

const missingModels = computed(() => (status.value?.models ?? []).filter((item) => !item.ready))
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

async function refreshModelStatus(): Promise<void> {
  try {
    status.value = await api.getF05ModelStatus() as CharacterModelStatus
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物模型状态读取失败'
  } finally {
    loading.value = false
  }
}

async function refreshPersonCompleteness(): Promise<void> {
  try {
    const analysis: ContentAnalysisRun | null = await api.getCurrentContentAnalysis(props.projectId)
    if (!analysis) {
      resolvedCount.value = 0
      unresolvedEvidenceCount.value = 0
      analysisProfile.value = ''
      return
    }
    analysisProfile.value = analysis.profile_version || ''
    resolvedCount.value = Number(analysis.counts?.resolved_character_candidates || 0)
    unresolvedEvidenceCount.value = Number(analysis.counts?.unresolved_character_candidates || 0)
  } catch {
    resolvedCount.value = 0
    unresolvedEvidenceCount.value = 0
  }
}

async function prepareModels(): Promise<void> {
  preparing.value = true
  error.value = ''
  try {
    status.value = await api.prepareF05Models() as CharacterModelStatus
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物 V10.1 模型准备失败'
  } finally {
    preparing.value = false
  }
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== props.projectId) return
  if (task.task_type !== 'ASSET_EXTRACTION_V3') return
  void refreshPersonCompleteness()
}

onMounted(async () => {
  window.addEventListener('studio-task-finished', onTaskFinished)
  await Promise.all([refreshModelStatus(), refreshPersonCompleteness()])
})

onUnmounted(() => {
  window.removeEventListener('studio-task-finished', onTaskFinished)
})
</script>

<template>
  <div class="asset-stage-v4">
    <div v-if="!loading && status && !status.ready" class="character-v4-banner warning">
      <div>
        <strong>人物识别 V10.1 运行时未准备完整</strong>
        <span>V10.1 需要 YOLOX / YoutuReID + Mature MOT。未准备完整时不要重新提取资产，旧 Current 会继续保留。</span>
        <small v-if="missingModels.length">缺少模型：{{ missingModels.map((item) => item.filename).join('、') }}</small>
        <small v-if="status.tracking_runtime && !status.tracking_runtime.ready">MOT：{{ status.tracking_runtime.error || 'trackers/supervision 未准备' }}</small>
      </div>
      <button :disabled="preparing" @click="prepareModels">{{ preparing ? '正在准备模型…' : '准备人物 V10.1 模型' }}</button>
    </div>

    <div v-else-if="!loading && status?.ready" class="character-v4-banner ready">
      <div>
        <strong>人物识别 V10.1 · READY · {{ runtimeLabel }} · {{ trackingLabel }}</strong>
        <span>先采集每个 Person Instance，再用人物模型分类：正面 / 侧身 / 背影 / 多人同框拆出的单人图都保留。</span>
        <small>YoutuReID 作为跨视角人物分类主模型；服装 / Body / Face(可选) 作为支持。整帧永远不直接做人身份比较。</small>
        <small>强污染 / 大面积边缘人物图不会再被永久挡在待归属区，但必须通过更严格的 ≥3 Shot ReID 一致性才能形成新人。</small>
        <small>弱 Partial 仍只保留 Evidence / 挂回已有角色，不能单独创建新人。</small>
        <small v-if="analysisProfile">当前 Asset Run：{{ analysisProfile }}</small>
        <small v-if="status.runtime?.fallback">⚠ CUDA 未实际启用，当前已自动降级 CPU；结果逻辑不变，但分析会明显变慢。</small>
      </div>
    </div>

    <div v-if="resolvedCount || unresolvedEvidenceCount" class="character-v4-banner identity-summary">
      <div>
        <strong>人物分类：{{ resolvedCount }} 个 Final Character</strong>
        <span>人物数量只统计模型确认的身份类别；人物内容先保存、后分类。</span>
        <small v-if="unresolvedEvidenceCount">待归属 Evidence：{{ unresolvedEvidenceCount }} 条（已保留，不计入人物数量）</small>
      </div>
    </div>

    <div v-if="error" class="character-v4-error">{{ error }}</div>
    <CharacterPersonGalleryV10 :project-id="props.projectId" />
    <AssetReviewMatrixV4 :project-id="props.projectId" :episodes="props.episodes" />
  </div>
</template>

<style scoped>
.asset-stage-v4{min-height:100%}.character-v4-banner{margin:14px 22px 0;padding:10px 13px;border:1px solid;border-radius:11px;display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:12px}.character-v4-banner>div{min-width:0;display:grid;gap:2px}.character-v4-banner strong{font-size:13px}.character-v4-banner span,.character-v4-banner small{line-height:1.45}.character-v4-banner.warning{background:#fff9eb;border-color:#f1d58d;color:#73510b}.character-v4-banner.warning span,.character-v4-banner.warning small{color:#8b6a25}.character-v4-banner.ready{background:#effbf5;border-color:#bfe7d2;color:#176a45}.character-v4-banner.ready span{color:#49806a}.character-v4-banner.ready small{color:#557c6b}.character-v4-banner.identity-summary{background:#f1f6ff;border-color:#c7d7f7;color:#2754a5}.character-v4-banner.identity-summary span,.character-v4-banner.identity-summary small{color:#5873a5}.character-v4-banner button{flex:0 0 auto;border:0;border-radius:8px;padding:8px 12px;background:#2f60e8;color:#fff;font-weight:750;cursor:pointer}.character-v4-banner button:disabled{opacity:.6;cursor:wait}.character-v4-error{margin:8px 22px 0;padding:8px 11px;border-radius:8px;background:#fff0f0;color:#b53a3a;font-size:12px}
</style>
