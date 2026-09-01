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
const userStatus = computed(() => {
  if (loading.value) return { title: '正在读取资产状态', detail: '正在检查人物、场景和道具结果。', tone: 'neutral' }
  if (!status.value) return { title: '资产状态暂时不可用', detail: '可以继续查看已经保存的结果。', tone: 'warning' }
  if (!status.value.ready) return { title: '需要先准备识别环境', detail: '现有资产结果不会丢失；重新提取前先完成模型准备。', tone: 'warning' }
  if (unresolvedEvidenceCount.value > 0) return { title: '有内容需要人工确认', detail: `${unresolvedEvidenceCount.value} 条人物证据还没有安全归属到最终人物。`, tone: 'review' }
  if (resolvedCount.value > 0) return { title: '资产结果可继续使用', detail: `当前已有 ${resolvedCount.value} 个最终人物，继续检查场景、道具和镜头绑定。`, tone: 'ready' }
  return { title: '等待资产提取结果', detail: '完成资产提取后，这里会汇总人物、场景和道具的确认状态。', tone: 'neutral' }
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
    <section :class="['asset-user-summary', `tone-${userStatus.tone}`]">
      <div class="asset-user-summary-copy">
        <small>03 · 人物 / 场景 / 道具</small>
        <strong>{{ userStatus.title }}</strong>
        <span>{{ userStatus.detail }}</span>
      </div>

      <div class="asset-user-stats">
        <div>
          <small>最终人物</small>
          <strong>{{ resolvedCount }}</strong>
        </div>
        <div :class="{ attention: unresolvedEvidenceCount > 0 }">
          <small>待归属</small>
          <strong>{{ unresolvedEvidenceCount }}</strong>
        </div>
        <div>
          <small>识别环境</small>
          <strong>{{ loading ? '读取中' : status?.ready ? '可用' : '需准备' }}</strong>
        </div>
      </div>

      <button v-if="!loading && status && !status.ready" class="asset-prepare-button" :disabled="preparing" @click="prepareModels">
        {{ preparing ? '正在准备…' : '准备识别环境' }}
      </button>
    </section>

    <div v-if="error" class="character-v4-error">{{ error }}</div>

    <details v-if="status" class="asset-runtime-details">
      <summary>识别技术信息</summary>
      <div class="asset-runtime-grid">
        <div><span>人物识别</span><strong>Character V10.1</strong></div>
        <div><span>计算设备</span><strong>{{ runtimeLabel }}</strong></div>
        <div><span>人物跟踪</span><strong>{{ trackingLabel }}</strong></div>
        <div><span>当前分析</span><strong>{{ analysisProfile || '暂无 Current Asset Run' }}</strong></div>
      </div>
      <p v-if="missingModels.length">缺少模型：{{ missingModels.map((item) => item.filename).join('、') }}</p>
      <p v-if="status.tracking_runtime && !status.tracking_runtime.ready">MOT：{{ status.tracking_runtime.error || 'trackers/supervision 未准备' }}</p>
      <p v-if="status.runtime?.fallback">当前正在使用 CPU fallback；结果逻辑不变，但处理速度会更慢。</p>
      <p>人物身份仍遵守 Final Character Gate：动态表情、动作、姿态、说话状态和画面位置不能作为身份主键。</p>
    </details>

    <CharacterPersonGalleryV10 :project-id="props.projectId" />
    <AssetReviewMatrixV4 :project-id="props.projectId" :episodes="props.episodes" />
  </div>
</template>

<style scoped>
.asset-stage-v4 { min-height: 100%; }
.asset-user-summary {
  margin: 14px 22px 0;
  min-height: 78px;
  display: grid;
  grid-template-columns: minmax(280px, 1fr) auto auto;
  gap: 18px;
  align-items: center;
  padding: 13px 15px;
  border: 1px solid #dfe5ed;
  border-radius: 12px;
  background: #fff;
}
.asset-user-summary.tone-review { border-color: #ead7a0; background: #fffaf0; }
.asset-user-summary.tone-warning { border-color: #efcf9b; background: #fff8eb; }
.asset-user-summary.tone-ready { border-color: #c8e5d7; background: #f5fbf8; }
.asset-user-summary-copy { min-width: 0; display: grid; gap: 2px; }
.asset-user-summary-copy small { color: #8793a4; font-size: 10px; font-weight: 850; letter-spacing: .04em; }
.asset-user-summary-copy strong { color: #2f4059; font-size: 15px; }
.asset-user-summary-copy span { color: #738095; font-size: 11px; }
.asset-user-stats { display: grid; grid-template-columns: repeat(3, minmax(84px, 1fr)); gap: 7px; }
.asset-user-stats > div {
  min-width: 84px;
  display: grid;
  gap: 1px;
  padding: 7px 9px;
  border: 1px solid #e3e8ef;
  border-radius: 9px;
  background: rgba(255,255,255,.8);
}
.asset-user-stats small { color: #8994a4; font-size: 9px; }
.asset-user-stats strong { color: #3d4c61; font-size: 12px; }
.asset-user-stats > div.attention { border-color: #ead7a0; background: #fff7e6; }
.asset-user-stats > div.attention strong { color: #96630e; }
.asset-prepare-button {
  min-height: 38px;
  border: 0;
  border-radius: 9px;
  padding: 0 13px;
  background: #2f60e8;
  color: #fff;
  font-size: 11px;
  font-weight: 800;
  cursor: pointer;
}
.asset-prepare-button:disabled { opacity: .6; cursor: wait; }
.character-v4-error { margin: 8px 22px 0; padding: 8px 11px; border-radius: 8px; background: #fff0f0; color: #b53a3a; font-size: 12px; }
.asset-runtime-details {
  margin: 8px 22px 0;
  border: 1px solid #e1e6ed;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.asset-runtime-details > summary { padding: 8px 11px; color: #7e8999; font-size: 10px; font-weight: 800; cursor: pointer; }
.asset-runtime-details[open] > summary { border-bottom: 1px solid #edf0f4; background: #fafbfc; }
.asset-runtime-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; padding: 10px 11px 6px; }
.asset-runtime-grid > div { min-width: 0; display: grid; gap: 2px; padding: 8px; border-radius: 8px; background: #f7f9fb; }
.asset-runtime-grid span { color: #8793a4; font-size: 9px; }
.asset-runtime-grid strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #4c596b; font-size: 10px; }
.asset-runtime-details p { margin: 0; padding: 3px 11px; color: #758196; font-size: 10px; line-height: 1.45; }
.asset-runtime-details p:last-child { padding-bottom: 10px; }
@media (max-width: 1350px) {
  .asset-user-summary { grid-template-columns: minmax(240px, 1fr) auto; }
  .asset-prepare-button { grid-column: 1 / -1; justify-self: start; }
  .asset-runtime-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
