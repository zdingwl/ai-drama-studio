<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getProject, listProjectTasks } from '@/features/projects/api'
import {
  acceptReplicaTargetAssets,
  getReplicaTargetAssets,
  listReplicaTargetAssetCandidates,
  regenerateReplicaTargetAssets,
  rejectReplicaTargetAssets,
  startReplicaTargetAssets,
  type ReplicaTargetAssetsContent,
  type ReplicaTargetAssetsRead,
  type TargetAssetsCandidateRead,
} from '@/features/projects/targetAssets'
import { getReplicaTargetBible, type ReplicaTargetBibleRead } from '@/features/projects/targetBible'
import type { ProjectRead, TaskRead } from '@/features/projects/types'

const TARGET_ASSET_TASK_NAMES = new Set(['生成目标资产候选', '重新生成目标资产候选'])
const ACTIVE_TASK_STATUSES = new Set<TaskRead['status']>(['queued', 'running', 'interrupted'])

const route = useRoute()
const project = ref<ProjectRead | null>(null)
const targetBible = ref<ReplicaTargetBibleRead | null>(null)
const result = ref<ReplicaTargetAssetsRead | null>(null)
const candidates = ref<TargetAssetsCandidateRead[]>([])
const activeTask = ref<TaskRead | null>(null)
const reviewReason = ref('')
const loading = ref(false)
const starting = ref(false)
const reviewing = ref(false)
const errorMessage = ref('')
let pollTimer: number | null = null

const projectId = computed(() => String(route.params.id || ''))
const visible = computed(() => project.value?.project_type === 'REPLICA')
const p11Ready = computed(() => targetBible.value?.status === 'CURRENT' && Boolean(targetBible.value?.target_bible.artifact_id))
const pendingCandidate = computed(() => candidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const previewContent = computed<ReplicaTargetAssetsContent | null>(() => pendingCandidate.value?.content ?? result.value?.content ?? null)
const hasFormalAssets = computed(() => Boolean(result.value?.artifact_id))
const shouldRegenerate = computed(() => hasFormalAssets.value || result.value?.status === 'STALE' || candidates.value.length > 0)
const active = computed(() => Boolean(activeTask.value && ACTIVE_TASK_STATUSES.has(activeTask.value.status)))
const finalizingCandidate = computed(() => Boolean(
  activeTask.value?.status === 'succeeded'
  && !candidates.value.some((item) => item.generated_by_task_id === activeTask.value?.id),
))
const busy = computed(() => active.value || finalizingCandidate.value)
const canReview = computed(() => Boolean(pendingCandidate.value && reviewReason.value.trim() && !reviewing.value))
const statusText = computed(() => {
  if (active.value) return `正在生成目标资产候选 ${activeTask.value?.progress_percent ?? 0}%`
  if (finalizingCandidate.value) return '正在整理目标资产候选…'
  if (!p11Ready.value) return '等待当前有效的目标设定'
  if (pendingCandidate.value) return '有一版目标资产候选待确认'
  if (result.value?.status === 'CURRENT') return '正式目标资产已确认'
  if (result.value?.status === 'STALE') return '目标设定已有更新，需要重新生成并确认资产'
  return '可以生成目标资产候选'
})

function clearPoll() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

function newKey(prefix: string): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${prefix}-${Date.now()}`
}

function isTargetAssetsTask(task: TaskRead): boolean {
  return TARGET_ASSET_TASK_NAMES.has(task.task_name)
}

function recoverTargetAssetsTask(tasks: TaskRead[], nextCandidates: TargetAssetsCandidateRead[]): TaskRead | null {
  const latest = tasks.find(isTargetAssetsTask)
  if (!latest) return null
  if (ACTIVE_TASK_STATUSES.has(latest.status)) return latest
  if (
    latest.status === 'succeeded'
    && !nextCandidates.some((item) => item.generated_by_task_id === latest.id)
  ) {
    return latest
  }
  return null
}

async function refreshAssets() {
  if (!projectId.value || !visible.value) return
  const [formal, nextCandidates] = await Promise.all([
    getReplicaTargetAssets(projectId.value),
    listReplicaTargetAssetCandidates(projectId.value),
  ])
  result.value = formal
  candidates.value = nextCandidates
}

async function pollTask() {
  if (!activeTask.value || !projectId.value) return
  const tasks = await listProjectTasks(projectId.value)
  const current = tasks.find((item) => item.id === activeTask.value?.id)
  if (!current) {
    clearPoll()
    activeTask.value = null
    return
  }
  activeTask.value = current
  if (current.status === 'succeeded') {
    await refreshAssets()
    if (candidates.value.some((item) => item.generated_by_task_id === current.id)) {
      clearPoll()
      activeTask.value = null
    }
  } else if (current.status === 'failed' || current.status === 'cancelled') {
    clearPoll()
    activeTask.value = null
    errorMessage.value = current.last_error || '目标资产候选生成失败，请重试。'
    await refreshAssets()
  }
}

function beginPoll() {
  clearPoll()
  pollTimer = window.setInterval(() => {
    void pollTask()
  }, 1500)
}

async function load() {
  clearPoll()
  targetBible.value = null
  result.value = null
  candidates.value = []
  activeTask.value = null
  reviewReason.value = ''
  errorMessage.value = ''
  if (!projectId.value) return
  loading.value = true
  try {
    project.value = await getProject(projectId.value)
    if (project.value.project_type === 'REPLICA') {
      const [bible, formal, nextCandidates, tasks] = await Promise.all([
        getReplicaTargetBible(projectId.value),
        getReplicaTargetAssets(projectId.value),
        listReplicaTargetAssetCandidates(projectId.value),
        listProjectTasks(projectId.value),
      ])
      targetBible.value = bible
      result.value = formal
      candidates.value = nextCandidates
      activeTask.value = recoverTargetAssetsTask(tasks, nextCandidates)
      if (activeTask.value) beginPoll()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标资产加载失败。'
  } finally {
    loading.value = false
  }
}

async function generate(regenerate: boolean) {
  if (!projectId.value || !p11Ready.value || busy.value || starting.value) return
  starting.value = true
  errorMessage.value = ''
  try {
    activeTask.value = regenerate
      ? await regenerateReplicaTargetAssets(projectId.value, newKey('target-assets-regenerate'))
      : await startReplicaTargetAssets(projectId.value, newKey('target-assets'))
    if (activeTask.value.status === 'succeeded') {
      await refreshAssets()
      if (!candidates.value.some((item) => item.generated_by_task_id === activeTask.value?.id)) {
        beginPoll()
      } else {
        activeTask.value = null
      }
    } else if (activeTask.value.status === 'failed') {
      errorMessage.value = activeTask.value.last_error || '目标资产候选生成失败，请重试。'
      activeTask.value = null
    } else {
      beginPoll()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标资产候选生成失败。'
  } finally {
    starting.value = false
  }
}

async function review(accept: boolean) {
  const candidate = pendingCandidate.value
  const bibleArtifactId = targetBible.value?.target_bible.artifact_id
  if (!candidate || !bibleArtifactId || !projectId.value || !reviewReason.value.trim()) return
  reviewing.value = true
  errorMessage.value = ''
  const payload = {
    expected_target_bible_artifact_id: bibleArtifactId,
    expected_generation_sequence: candidate.generation_sequence,
    reason: reviewReason.value.trim(),
  }
  try {
    if (accept) {
      result.value = await acceptReplicaTargetAssets(projectId.value, candidate.id, payload)
    } else {
      await rejectReplicaTargetAssets(projectId.value, candidate.id, payload)
    }
    reviewReason.value = ''
    await refreshAssets()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标资产审核失败。'
  } finally {
    reviewing.value = false
  }
}

watch(projectId, () => {
  void load()
}, { immediate: true })

onBeforeUnmount(clearPoll)
</script>

<template>
  <section v-if="visible" class="target-assets-workspace">
    <div class="workspace-header">
      <div>
        <p class="eyebrow">目标版本</p>
        <h2>目标资产</h2>
        <p class="subtitle">把已确认的目标人物、场景和关键道具固化为跨镜可复用的视觉身份包。已确认的目标设定是语义基线，目标资产只负责视觉实现。</p>
      </div>
      <div class="workspace-actions">
        <span class="status-pill" :class="result?.status?.toLowerCase()">{{ statusText }}</span>
        <button
          v-if="p11Ready && !pendingCandidate && !busy"
          type="button"
          class="primary-action"
          :disabled="loading || starting"
          @click="generate(shouldRegenerate)"
        >
          {{ starting ? '正在启动…' : (shouldRegenerate ? '重新生成候选' : '生成目标资产') }}
        </button>
      </div>
    </div>

    <p class="provider-note">资产说明与审核内容默认使用中文；人物名、地名、品牌、型号和金额保留目标地区真实写法。真正进入图片或视频生成时，系统会再按生成模型需要整理执行提示。当前尚未接入已验收的参考图生成，因此不会显示或伪造参考图。</p>
    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <p v-if="loading" class="empty-state">正在读取目标资产…</p>

    <section v-if="pendingCandidate" class="review-panel">
      <div>
        <strong>候选版本 {{ pendingCandidate.generation_sequence }} · 待人工确认</strong>
        <p>自动生成完成不会直接成为正式资产。请核对人物外形、场景布局、道具形态和连续性约束后再确认。</p>
      </div>
      <textarea v-model="reviewReason" rows="2" placeholder="填写本次确认或拒绝原因（必填）" />
      <div class="review-actions">
        <button type="button" class="secondary-action" :disabled="!canReview" @click="review(false)">拒绝候选</button>
        <button type="button" class="primary-action" :disabled="!canReview" @click="review(true)">确认并作为正式资产</button>
        <button type="button" class="secondary-action" :disabled="busy || starting" @click="generate(true)">重新生成另一版</button>
      </div>
    </section>

    <template v-if="previewContent">
      <div class="asset-section">
        <h3>人物资产</h3>
        <article v-for="asset in previewContent.characters" :key="asset.target_asset_id" class="asset-card">
          <div class="asset-heading"><strong>{{ asset.display_name }}</strong><span>rev {{ asset.target_asset_revision }}</span></div>
          <p><b>面部</b> {{ asset.face_direction }}</p>
          <p><b>发型 / 体态</b> {{ asset.hair_direction }} · {{ asset.body_direction }}</p>
          <p><b>服装基线</b> {{ asset.wardrobe_baseline }}</p>
          <div class="chips"><span v-for="item in asset.signature_visual_features" :key="item">{{ item }}</span></div>
          <details><summary>连续性与生成约束</summary><ul><li v-for="item in asset.continuity_constraints" :key="item">{{ item }}</li></ul><ul><li v-for="item in asset.negative_constraints" :key="item">避免：{{ item }}</li></ul></details>
        </article>
      </div>

      <div class="asset-section">
        <h3>场景资产</h3>
        <article v-for="asset in previewContent.scenes" :key="asset.target_asset_id" class="asset-card">
          <div class="asset-heading"><strong>{{ asset.display_name }}</strong><span>rev {{ asset.target_asset_revision }}</span></div>
          <p><b>布局</b> {{ asset.layout }}</p>
          <p><b>建筑 / 空间风格</b> {{ asset.architecture_style }} · {{ asset.interior_exterior_style }}</p>
          <p><b>光照基线</b> {{ asset.lighting_baseline }} · {{ asset.time_of_day_baseline }}</p>
          <div class="chips"><span v-for="item in asset.fixed_landmarks" :key="item">{{ item }}</span></div>
          <details><summary>连续性与生成约束</summary><ul><li v-for="item in asset.continuity_constraints" :key="item">{{ item }}</li></ul><ul><li v-for="item in asset.negative_constraints" :key="item">避免：{{ item }}</li></ul></details>
        </article>
      </div>

      <div class="asset-section">
        <h3>道具资产</h3>
        <article v-for="asset in previewContent.props" :key="asset.target_asset_id" class="asset-card">
          <div class="asset-heading"><strong>{{ asset.display_name }}</strong><span>rev {{ asset.target_asset_revision }}</span></div>
          <p><b>视觉形态</b> {{ asset.visual_form }}</p>
          <p><b>尺度</b> {{ asset.scale_reference }}</p>
          <div class="chips"><span v-for="item in [...asset.materials, ...asset.color_palette]" :key="item">{{ item }}</span></div>
          <details><summary>连续性与生成约束</summary><ul><li v-for="item in asset.continuity_constraints" :key="item">{{ item }}</li></ul><ul><li v-for="item in asset.negative_constraints" :key="item">避免：{{ item }}</li></ul></details>
        </article>
      </div>
    </template>

    <div v-else-if="!loading" class="empty-state">
      <p v-if="p11Ready">目标设定已就绪。点击“生成目标资产”会创建待确认候选；页面刷新不会自动启动生成。</p>
      <p v-else>请先完成并保持当前有效的目标设定，再生成目标资产。</p>
    </div>
  </section>
</template>

<style scoped>
.target-assets-workspace { margin: 28px auto 0; max-width: 1240px; padding: 24px; border: 1px solid var(--border-color, #e5e7eb); border-radius: 18px; background: var(--surface-color, #fff); }
.workspace-header { display: flex; gap: 24px; justify-content: space-between; align-items: flex-start; }
.eyebrow { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; opacity: .55; }
h2, h3, p { margin-top: 0; }
.subtitle { max-width: 760px; opacity: .72; }
.workspace-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
.status-pill { padding: 6px 10px; border-radius: 999px; background: #f3f4f6; font-size: 13px; white-space: nowrap; }
.status-pill.current { background: #ecfdf5; }
.status-pill.stale { background: #fff7ed; }
.primary-action, .secondary-action { border-radius: 10px; padding: 10px 16px; font-weight: 700; cursor: pointer; }
.primary-action { border: 0; background: #111827; color: #fff; }
.secondary-action { border: 1px solid #d1d5db; background: #fff; color: #111827; }
button:disabled { cursor: default; opacity: .5; }
.provider-note { margin: 16px 0 0; padding: 10px 12px; border-radius: 10px; background: #f8fafc; font-size: 13px; opacity: .75; }
.error-message { margin-top: 16px; padding: 10px 12px; border-radius: 10px; background: #fef2f2; }
.empty-state { margin: 18px 0 0; padding: 22px; border-radius: 12px; background: #f9fafb; opacity: .72; }
.review-panel { margin-top: 18px; padding: 16px; border: 1px solid #f59e0b55; border-radius: 12px; background: #fffbeb; }
.review-panel p { margin: 6px 0 12px; opacity: .72; }
.review-panel textarea { box-sizing: border-box; width: 100%; resize: vertical; border: 1px solid #d1d5db; border-radius: 9px; padding: 10px; font: inherit; }
.review-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.asset-section { margin-top: 22px; padding-top: 18px; border-top: 1px solid #eef0f3; }
.asset-card { margin-top: 12px; padding: 16px; border-radius: 12px; background: #f8fafc; }
.asset-heading { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.asset-heading span { opacity: .55; font-size: 13px; }
.asset-card p { margin-bottom: 8px; line-height: 1.55; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
.chips span { padding: 4px 8px; border-radius: 999px; background: #fff; font-size: 12px; }
details { margin-top: 10px; }
details ul { margin: 8px 0; padding-left: 22px; }
@media (max-width: 720px) {
  .target-assets-workspace { padding: 18px; }
  .workspace-header { flex-direction: column; }
  .workspace-actions { align-items: stretch; width: 100%; }
}
</style>
