<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import type { BackgroundTask, ContentAnalysisRun, Episode, F05ModelStatus } from '../types/studio'
import AssetReviewInboxV1 from './AssetReviewInboxV1.vue'
import AssetReviewMatrixV4 from './AssetReviewMatrixV4.vue'
import CharacterPersonGalleryV10 from './CharacterPersonGalleryV10.vue'

const props = withDefaults(defineProps<{
  projectId: string
  episodes: Episode[]
  compact?: boolean
}>(), {
  compact: false,
})

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

type AssetWorkspaceMode = 'inbox' | 'matrix' | 'people'

const route = useRoute()
const router = useRouter()
const status = ref<CharacterModelStatus | null>(null)
const loading = ref(true)
const preparing = ref(false)
const error = ref('')
const resolvedCount = ref(0)
const unresolvedEvidenceCount = ref(0)
const analysisProfile = ref('')
const workspaceMode = ref<AssetWorkspaceMode>(workspaceModeFromRoute())

function workspaceModeFromRoute(): AssetWorkspaceMode {
  const requested = String(route.query.asset_tab || '')
  if (requested === 'people') return 'people'
  if (requested === 'matrix') return 'matrix'
  return 'inbox'
}

const missingModels = computed(() => (status.value?.models ?? []).filter((item) => !item.ready))
const runtimeLabel = computed(() => {
  const runtime = status.value?.runtime
  if (!runtime) return '未知'
  if (runtime.device === 'GPU') return `GPU · ${runtime.provider || 'CUDA'}`
  return `CPU · ${runtime.provider || 'fallback'}`
})
const trackingLabel = computed(() => {
  const tracking = status.value?.tracking_runtime
  if (!tracking) return '未知'
  if (!tracking.ready) return '未准备'
  return `${tracking.tracker || 'MOT'} · ${tracking.frame_rate || 12}fps`
})
const userStatus = computed(() => {
  if (loading.value) {
    return { title: '正在读取原片资产', detail: '正在检查人物、场景、道具和需要人工判断的问题。', tone: 'neutral' }
  }
  if (!status.value) {
    return { title: '已有资产仍可查看', detail: '识别环境状态暂时读取失败，不影响已经保存的 Final Asset。', tone: 'warning' }
  }
  if (!status.value.ready) {
    return { title: '识别环境需要准备', detail: '现有结果不会丢失；只有重新提取人物时才需要准备模型。', tone: 'warning' }
  }
  if (resolvedCount.value > 0) {
    return {
      title: `已形成 ${resolvedCount.value} 个正式人物资产`,
      detail: '人物页会继续完成跨分镜归并和 Shot Binding；真正有歧义的内容才进入人工处理。',
      tone: 'ready',
    }
  }
  if (unresolvedEvidenceCount.value > 0) {
    return {
      title: '已有视觉人物证据',
      detail: '这些仍是识别 Evidence，不会直接冒充正式人物资产；请进入人物资产查看归并结果。',
      tone: 'neutral',
    }
  }
  return { title: '等待资产提取', detail: '完成拉片后执行资产提取，系统会自动形成原片人物、场景和道具资产。', tone: 'neutral' }
})

function selectWorkspaceMode(next: AssetWorkspaceMode): void {
  workspaceMode.value = next
  if (String(route.query.asset_tab || '') !== next) {
    void router.replace({ query: { ...route.query, asset_tab: next } })
  }
}

function syncWorkspaceModeFromRoute(): void {
  const next = workspaceModeFromRoute()
  if (workspaceMode.value !== next) workspaceMode.value = next
}

async function refreshModelStatus(): Promise<void> {
  try {
    status.value = await api.getF05ModelStatus() as CharacterModelStatus
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
    error.value = err instanceof Error ? err.message : '人物识别环境准备失败'
  } finally {
    preparing.value = false
  }
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== props.projectId || task.task_type !== 'ASSET_EXTRACTION_V3') return
  void refreshPersonCompleteness()
}

watch(() => route.query.asset_tab, syncWorkspaceModeFromRoute)

onMounted(async () => {
  window.addEventListener('studio-task-finished', onTaskFinished)
  syncWorkspaceModeFromRoute()
  await Promise.all([refreshModelStatus(), refreshPersonCompleteness()])
})

onUnmounted(() => {
  window.removeEventListener('studio-task-finished', onTaskFinished)
})
</script>

<template>
  <div :class="['asset-stage-v4', { compact: props.compact }]">
    <section v-if="!props.compact" :class="['asset-user-summary', `tone-${userStatus.tone}`]">
      <div class="asset-user-summary-copy">
        <small>03 · 原片资产</small>
        <strong>{{ userStatus.title }}</strong>
        <span>{{ userStatus.detail }}</span>
      </div>
      <div class="asset-user-stats">
        <div>
          <small>正式人物</small>
          <strong>{{ resolvedCount }}</strong>
        </div>
        <div>
          <small>待归属视觉证据</small>
          <strong>{{ unresolvedEvidenceCount }}</strong>
        </div>
      </div>
      <button
        v-if="!loading && status && !status.ready"
        class="asset-prepare-button"
        :disabled="preparing"
        type="button"
        @click="prepareModels"
      >
        {{ preparing ? '正在准备…' : '准备识别环境' }}
      </button>
    </section>

    <div v-if="error" class="asset-error">{{ error }}</div>

    <nav :class="['asset-workspace-tabs', { compact: props.compact }]" aria-label="原片资产工作区">
      <button :class="{ active: workspaceMode === 'inbox' }" type="button" @click="selectWorkspaceMode('inbox')">
        <strong>待处理</strong>
        <span v-if="!props.compact">只处理真正有冲突、缺绑定或低置信度的问题</span>
      </button>
      <button :class="{ active: workspaceMode === 'people' }" type="button" @click="selectWorkspaceMode('people')">
        <strong>人物</strong>
        <span v-if="!props.compact">跨分镜归并、人物资产库、Shot Binding 与替换人物入口</span>
      </button>
      <button :class="{ active: workspaceMode === 'matrix' }" type="button" @click="selectWorkspaceMode('matrix')">
        <strong>场景 / 道具 / 完整绑定</strong>
        <span v-if="!props.compact">高级查看全部人物、场景和道具 Final Binding</span>
      </button>
    </nav>

    <AssetReviewInboxV1
      v-if="workspaceMode === 'inbox'"
      :project-id="props.projectId"
      :episodes="props.episodes"
      @open-matrix="selectWorkspaceMode('matrix')"
    />
    <CharacterPersonGalleryV10
      v-else-if="workspaceMode === 'people'"
      :project-id="props.projectId"
      @next-stage="selectWorkspaceMode('matrix')"
    />
    <AssetReviewMatrixV4
      v-else
      :project-id="props.projectId"
      :episodes="props.episodes"
    />

    <details v-if="status && !props.compact" class="asset-runtime-details">
      <summary>高级 · 识别技术信息</summary>
      <div class="asset-runtime-grid">
        <div><span>人物识别</span><strong>Character V10.1</strong></div>
        <div><span>计算设备</span><strong>{{ runtimeLabel }}</strong></div>
        <div><span>人物跟踪</span><strong>{{ trackingLabel }}</strong></div>
        <div><span>当前分析</span><strong>{{ analysisProfile || '暂无' }}</strong></div>
      </div>
      <p v-if="missingModels.length">缺少模型：{{ missingModels.map((item) => item.filename).join('、') }}</p>
      <p v-if="status.tracking_runtime && !status.tracking_runtime.ready">MOT：{{ status.tracking_runtime.error || '未准备' }}</p>
      <p>动态表情、动作、姿态、说话状态和画面位置不能作为人物身份主键。</p>
    </details>
  </div>
</template>

<style scoped>
.asset-stage-v4 { min-height: 100%; }
.asset-stage-v4.compact { padding: 0; background: transparent; }
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
.asset-user-summary.tone-warning { border-color: #efcf9b; background: #fff8eb; }
.asset-user-summary.tone-ready { border-color: #c8e5d7; background: #f5fbf8; }
.asset-user-summary-copy { min-width: 0; display: grid; gap: 2px; }
.asset-user-summary-copy small { color: #8793a4; font-size: 10px; font-weight: 850; letter-spacing: .04em; }
.asset-user-summary-copy strong { color: #2f4059; font-size: 15px; }
.asset-user-summary-copy span { color: #738095; font-size: 11px; line-height: 1.5; }
.asset-user-stats { display: grid; grid-template-columns: repeat(2, minmax(105px, 1fr)); gap: 7px; }
.asset-user-stats > div { display: grid; gap: 1px; padding: 7px 9px; border: 1px solid #e3e8ef; border-radius: 9px; background: rgba(255,255,255,.8); }
.asset-user-stats small { color: #8994a4; font-size: 9px; }
.asset-user-stats strong { color: #3d4c61; font-size: 13px; }
.asset-prepare-button { min-height: 38px; border: 0; border-radius: 9px; padding: 0 13px; background: #2f60e8; color: #fff; font-size: 11px; font-weight: 800; cursor: pointer; }
.asset-prepare-button:disabled { opacity: .6; cursor: wait; }
.asset-error { margin: 8px 22px 0; padding: 8px 11px; border-radius: 8px; background: #fff0f0; color: #b53a3a; font-size: 12px; }
.compact .asset-error { margin: 8px 0; }
.asset-workspace-tabs { margin: 10px 22px 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.asset-workspace-tabs button { min-width: 0; min-height: 54px; display: grid; gap: 2px; align-content: center; border: 1px solid #dde3eb; border-radius: 10px; padding: 8px 12px; background: #fff; color: #536176; text-align: left; cursor: pointer; }
.asset-workspace-tabs button:hover { border-color: #bfcce0; background: #fafcff; }
.asset-workspace-tabs button.active { border-color: #8fa9df; background: #eef4ff; box-shadow: inset 3px 0 0 #5d82d6; }
.asset-workspace-tabs strong { color: #354965; font-size: 13px; }
.asset-workspace-tabs span { overflow: hidden; color: #8490a2; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.asset-workspace-tabs.compact { margin: 0 0 10px; display: flex; gap: 6px; }
.asset-workspace-tabs.compact button { min-height: 36px; width: auto; display: block; padding: 7px 12px; border-radius: 8px; text-align: center; }
.asset-workspace-tabs.compact button.active { box-shadow: none; }
.asset-workspace-tabs.compact strong { font-size: 11px; }
.asset-runtime-details { margin: 10px 22px 18px; border: 1px solid #e1e6ed; border-radius: 10px; background: #fff; overflow: hidden; }
.asset-runtime-details > summary { padding: 8px 11px; color: #7e8999; font-size: 10px; font-weight: 800; cursor: pointer; }
.asset-runtime-details[open] > summary { border-bottom: 1px solid #edf0f4; background: #fafbfc; }
.asset-runtime-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; padding: 10px 11px 6px; }
.asset-runtime-grid > div { min-width: 0; display: grid; gap: 2px; padding: 8px; border-radius: 8px; background: #f7f9fb; }
.asset-runtime-grid span { color: #8994a4; font-size: 9px; }
.asset-runtime-grid strong { overflow: hidden; color: #4c5d73; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.asset-runtime-details p { margin: 0; padding: 4px 11px 9px; color: #8792a1; font-size: 9px; }
@media (max-width: 980px) {
  .asset-user-summary { grid-template-columns: 1fr; }
  .asset-user-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .asset-workspace-tabs:not(.compact) { grid-template-columns: 1fr; }
  .asset-workspace-tabs span { white-space: normal; }
  .asset-workspace-tabs.compact { flex-wrap: wrap; }
  .asset-runtime-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
