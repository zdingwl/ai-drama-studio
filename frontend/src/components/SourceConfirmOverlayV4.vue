<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { remakeApi } from '../api/remake'
import SourceShotReviewWorkspaceV2 from './SourceShotReviewWorkspaceV2.vue'
import PersonKeyframeReviewV1 from './PersonKeyframeReviewV1.vue'
import type { ProjectFlowStage, ProjectFlowState } from '../types/project-flow-state'
import type { ReviewIssue } from '../types/remake'
import type { Project } from '../types/studio'

const props = defineProps<{ projectId: string }>()
const route = useRoute()
const router = useRouter()

type ReviewTab = 'people' | 'shots'

const project = ref<Project | null>(null)
const flow = ref<ProjectFlowState | null>(null)
const issues = ref<ReviewIssue[]>([])
const loading = ref(true)
const error = ref('')
const focusEpisodeId = computed(() => typeof route.query.episode === 'string' ? route.query.episode : '')
const focusShotOrdinal = computed<number | null>(() => {
  const value = Number(route.query.shot || 0)
  return Number.isInteger(value) && value > 0 ? value : null
})
const reviewTab = ref<ReviewTab>(
  String(route.query.confirm_tab || '') === 'shots' || focusShotOrdinal.value !== null ? 'shots' : 'people',
)

const sourceIssueTypes = new Set(['CHARACTER_IDENTITY', 'ASSET_BINDING', 'SPEAKER'])
function stage(key: string): ProjectFlowStage | null { return flow.value?.stages.find((item) => item.stage_key === key) || null }
const sourceAssetsStage = computed(() => stage('source_assets'))
const sourceSnapshotStage = computed(() => stage('source_snapshot'))
const sourceReady = computed(() => Boolean(sourceAssetsStage.value?.consumable && sourceSnapshotStage.value?.consumable))
const sourceIssues = computed(() => issues.value.filter((item) => sourceIssueTypes.has(item.issue_type)))

async function refresh(): Promise<void> {
  if (!props.projectId) return
  try {
    const [projectResult, flowResult, issueResult] = await Promise.all([
      api.getProject(props.projectId),
      getProjectFlowState(props.projectId),
      remakeApi.listReviewIssues(props.projectId, 'OPEN'),
    ])
    project.value = projectResult
    flow.value = flowResult
    issues.value = issueResult
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '原片确认数据读取失败'
  } finally {
    loading.value = false
  }
}

function close(): void {
  const { mode: _mode, confirm_tab: _confirmTab, asset_tab: _assetTab, ...query } = route.query
  void router.replace({ name: 'breakdown', params: { projectId: props.projectId }, query })
}
function enterRemake(): void { if (sourceReady.value) void router.push({ name: 'remake', params: { projectId: props.projectId } }) }
function onWorkspaceChanged(): void { void refresh() }
function onWorkspaceCompleted(): void { void refresh() }
function onTruthChanged(event: Event): void {
  const detail = (event as CustomEvent<{ project_id?: string }>).detail
  if (detail?.project_id && detail.project_id !== props.projectId) return
  void refresh()
}
function onTaskFinished(event: Event): void {
  const detail = (event as CustomEvent<{ project_id?: string }>).detail
  if (detail?.project_id && detail.project_id !== props.projectId) return
  void refresh()
}
function onKeydown(event: KeyboardEvent): void { if (event.key === 'Escape') close() }

let previousBodyOverflow = ''
onMounted(() => {
  previousBodyOverflow = document.body.style.overflow
  document.body.style.overflow = 'hidden'
  window.addEventListener('studio-project-truth-changed', onTruthChanged)
  window.addEventListener('studio-task-finished', onTaskFinished)
  window.addEventListener('keydown', onKeydown)
  void refresh()
})
onBeforeUnmount(() => {
  document.body.style.overflow = previousBodyOverflow
  window.removeEventListener('studio-project-truth-changed', onTruthChanged)
  window.removeEventListener('studio-task-finished', onTaskFinished)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="source-confirm-overlay-v4" @click.self="close">
    <section class="source-confirm-dialog-v4" role="dialog" aria-modal="true" aria-label="原片确认">
      <header class="confirm-head">
        <div>
          <small>03 · 原片确认</small>
          <strong>原片审核工作区</strong>
          <span>按依赖顺序处理：人物身份 → 场景 / 道具 → 对白说话人；人物未确认时，对白不会允许确认。</span>
        </div>
        <div class="head-actions">
          <span v-if="!loading" :class="['pending-chip', { ready: sourceReady }]">{{ sourceReady ? '已完成' : '待确认' }}</span>
          <button type="button" aria-label="关闭原片确认" @click="close">×</button>
        </div>
      </header>

      <div v-if="error" class="confirm-error">{{ error }}</div>

      <main class="confirm-body">
        <nav class="review-tabs"><button :class="{selected:reviewTab==='people'}" @click="reviewTab='people'">人物关键帧审核</button><button :class="{selected:reviewTab==='shots'}" @click="reviewTab='shots'">逐镜头确认（人物 → 场景 / 道具 → 对白）</button></nav>
        <div v-if="loading && !project" class="confirm-loading">正在读取原片确认状态…</div>
        <PersonKeyframeReviewV1 v-else-if="project && reviewTab==='people'" :project-id="project.id" @changed="onWorkspaceChanged" />
        <SourceShotReviewWorkspaceV2
          v-else-if="project"
          :project-id="project.id"
          :episodes="project.episodes"
          :focus-episode-id="focusEpisodeId"
          :focus-shot-ordinal="focusShotOrdinal"
          @changed="onWorkspaceChanged"
          @completed="onWorkspaceCompleted"
        />
      </main>

      <footer v-if="reviewTab === 'shots'" class="confirm-footer">
        <div>
          <strong>{{ sourceReady ? '原片确认完成' : '只剩下真正需要人工判断的内容' }}</strong>
          <span>{{ sourceReady ? 'SourceDramaSnapshot 已满足进入视频重做条件。' : `当前仍有 ${sourceIssues.length} 项底层待确认事实。` }}</span>
        </div>
        <div class="footer-actions">
          <button type="button" class="secondary" @click="close">返回拉片</button>
          <button type="button" class="primary" :disabled="!sourceReady" @click="enterRemake">进入视频重做 →</button>
        </div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.source-confirm-overlay-v4 .source-confirm-dialog-v4{display:flex;flex-direction:column}.source-confirm-dialog-v4>.confirm-head,.source-confirm-dialog-v4>.confirm-footer{flex-shrink:0}.source-confirm-dialog-v4>.confirm-body{flex:1;min-height:0}
.confirm-body{display:flex;flex-direction:column;gap:10px}.confirm-body>.person-review,.confirm-body>.source-shot-review-v2{flex:1;min-height:0;height:auto}.review-tabs{display:flex;gap:8px;flex-shrink:0}.review-tabs button{border:1px solid #dce3ed;border-radius:7px;background:white;padding:8px 14px;color:#586a83;cursor:pointer}.review-tabs .selected{background:#eaf1ff;color:#1769ff;border-color:#85acff}
.source-confirm-overlay-v4{position:fixed;inset:0;z-index:1200;display:grid;place-items:center;padding:16px;background:rgba(17,27,43,.48);backdrop-filter:blur(3px)}.source-confirm-dialog-v4{width:min(1560px,calc(100vw - 32px));height:min(960px,calc(100vh - 32px));display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;border:1px solid #dfe5ed;border-radius:15px;background:#f5f7fa;box-shadow:0 28px 80px rgba(17,32,58,.28);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#263850}.confirm-head{min-height:70px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:11px 16px;border-bottom:1px solid #e5e9ef;background:#fff}.confirm-head>div:first-child{min-width:0;display:grid;gap:2px}.confirm-head small{color:#1769ff;font-size:9px;font-weight:850}.confirm-head strong{font-size:18px;line-height:1.25}.confirm-head span{color:#7b8899;font-size:10px}.head-actions{display:flex;align-items:center;gap:9px}.head-actions>button{width:34px;height:34px;border:1px solid #dbe2ec;border-radius:8px;background:#fff;color:#60708a;font-size:20px;cursor:pointer}.pending-chip{padding:5px 8px;border-radius:99px;background:#fff1da;color:#97631a;font-size:9px!important;font-weight:800}.pending-chip.ready{background:#eaf8ef;color:#2b9a58}.confirm-error{margin:8px 12px 0;padding:8px 11px;border:1px solid #efcaca;border-radius:8px;background:#fff2f2;color:#a54848;font-size:10px}.confirm-body{min-height:0;overflow:hidden;padding:10px 12px 0}.confirm-loading{height:100%;display:grid;place-items:center;color:#7d8998;font-size:11px}.confirm-footer{min-height:62px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 16px;border-top:1px solid #e3e8ef;background:#fff}.confirm-footer>div:first-child{display:grid;gap:1px}.confirm-footer strong{font-size:11px}.confirm-footer span{color:#8793a3;font-size:9px}.footer-actions{display:flex;gap:8px}.footer-actions button{min-height:36px;border-radius:8px;padding:0 13px;font-size:10px;font-weight:800;cursor:pointer}.footer-actions .secondary{border:1px solid #d8e0ea;background:#fff;color:#5c6d84}.footer-actions .primary{border:0;background:#1769ff;color:#fff}.footer-actions .primary:disabled{opacity:.42;cursor:not-allowed}@media(max-width:760px){.source-confirm-overlay-v4{padding:0}.source-confirm-dialog-v4{width:100vw;height:100vh;border:0;border-radius:0}.confirm-head,.confirm-footer{align-items:stretch;flex-direction:column}.head-actions,.footer-actions{justify-content:space-between}.confirm-body{padding:8px 8px 0}}
</style>
