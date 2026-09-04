<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { remakeApi } from '../api/remake'
import AssetReviewInboxV1 from './AssetReviewInboxV1.vue'
import AssetReviewMatrixV4 from './AssetReviewMatrixV4.vue'
import CharacterAssetsWorkbenchV1 from './CharacterAssetsWorkbenchV1.vue'
import SpeakerReviewEditorV1 from './SpeakerReviewEditorV1.vue'
import type { ProjectFlowStage, ProjectFlowState } from '../types/project-flow-state'
import type { ReviewIssue } from '../types/remake'
import type { Project } from '../types/studio'

type ConfirmTab = 'people' | 'assets' | 'speaker'
type AssetView = 'inbox' | 'matrix'

const props = defineProps<{ projectId: string }>()
const route = useRoute()
const router = useRouter()

const project = ref<Project | null>(null)
const flow = ref<ProjectFlowState | null>(null)
const issues = ref<ReviewIssue[]>([])
const loading = ref(true)
const error = ref('')
const activeTab = ref<ConfirmTab>('people')
const assetView = ref<AssetView>('inbox')

function tabFromQuery(): ConfirmTab {
  const confirmTab = String(route.query.confirm_tab || '')
  const assetTab = String(route.query.asset_tab || '')
  if (confirmTab === 'speaker') return 'speaker'
  if (assetTab === 'people') return 'people'
  if (confirmTab === 'assets' || assetTab === 'inbox' || assetTab === 'matrix') return 'assets'
  return 'people'
}

function assetViewFromQuery(): AssetView {
  return String(route.query.asset_tab || '') === 'matrix' ? 'matrix' : 'inbox'
}

function stage(key: string): ProjectFlowStage | null {
  return flow.value?.stages.find((item) => item.stage_key === key) || null
}

const sourceAssetsStage = computed(() => stage('source_assets'))
const sourceSnapshotStage = computed(() => stage('source_snapshot'))
const sourceReady = computed(() => Boolean(sourceAssetsStage.value?.consumable && sourceSnapshotStage.value?.consumable))
const speakerIssues = computed(() => issues.value.filter((item) => item.issue_type === 'SPEAKER'))

const selectedEpisode = computed(() => {
  const episodeId = String(route.query.episode || '')
  return project.value?.episodes.find((item) => item.id === episodeId) || null
})

const selectedShotOrdinal = computed(() => {
  const value = Number(route.query.shot || 0)
  return Number.isInteger(value) && value > 0 ? value : null
})

const locationLabel = computed(() => {
  const episode = selectedEpisode.value
  const episodeText = episode ? `EP${String(episode.sort_order).padStart(2, '0')}` : '当前项目'
  const shotText = selectedShotOrdinal.value ? ` · Shot ${String(selectedShotOrdinal.value).padStart(2, '0')}` : ''
  return `${episodeText}${shotText}`
})

const blockingReason = computed(() => {
  if (sourceReady.value) return '原片事实已经可以进入视频重做。'
  if (sourceAssetsStage.value && !sourceAssetsStage.value.consumable) return sourceAssetsStage.value.reason
  if (sourceSnapshotStage.value && !sourceSnapshotStage.value.consumable) return sourceSnapshotStage.value.reason
  return '还有原片内容需要确认。'
})

const tabHint = computed(() => {
  if (activeTab.value === 'people') return '直接处理无法自动确定的人物，不再经过概览页和“开始处理”页。'
  if (activeTab.value === 'speaker') return '只显示无法自动确定的对白说话人。'
  if (assetView.value === 'matrix') return '完整绑定只用于抽查或高级修改；普通处理优先看待处理镜头。'
  return '直接处理场景 / 道具的冲突、缺绑定和低置信度镜头。'
})

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

function replaceConfirmQuery(tab: ConfirmTab): void {
  const { confirm_tab: _confirmTab, asset_tab: _assetTab, ...rest } = route.query
  const query: Record<string, unknown> = { ...rest, mode: 'confirm' }
  if (tab === 'speaker') {
    query.confirm_tab = 'speaker'
  } else {
    query.confirm_tab = 'assets'
    query.asset_tab = tab === 'people' ? 'people' : assetView.value
  }
  void router.replace({ query })
}

function openTab(tab: ConfirmTab): void {
  activeTab.value = tab
  if (tab === 'assets') assetView.value = 'inbox'
  replaceConfirmQuery(tab)
}

function openAssetMatrix(): void {
  activeTab.value = 'assets'
  assetView.value = 'matrix'
  replaceConfirmQuery('assets')
}

function openAssetInbox(): void {
  activeTab.value = 'assets'
  assetView.value = 'inbox'
  replaceConfirmQuery('assets')
}

function close(): void {
  const { mode: _mode, confirm_tab: _confirmTab, asset_tab: _assetTab, ...query } = route.query
  void router.replace({ name: 'breakdown', params: { projectId: props.projectId }, query })
}

function enterRemake(): void {
  if (!sourceReady.value) return
  void router.push({ name: 'remake', params: { projectId: props.projectId } })
}

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

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') close()
}

let previousBodyOverflow = ''

onMounted(() => {
  activeTab.value = tabFromQuery()
  assetView.value = assetViewFromQuery()
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
  <div class="source-confirm-overlay" @click.self="close">
    <section class="source-confirm-dialog" role="dialog" aria-modal="true" aria-label="原片确认">
      <header class="source-confirm-head">
        <div class="head-copy">
          <small>03 · 原片确认 · {{ locationLabel }}</small>
          <div class="title-row">
            <strong>直接修改需要确认的内容</strong>
            <span :class="['ready-chip', { ready: sourceReady }]">
              {{ sourceReady ? '已就绪' : '待确认' }}
            </span>
          </div>
          <span>{{ tabHint }}</span>
        </div>
        <button type="button" class="close-button" aria-label="关闭原片确认" @click="close">×</button>
      </header>

      <nav class="confirm-tabs" aria-label="原片确认类型">
        <button type="button" :class="{ active: activeTab === 'people' }" @click="openTab('people')">
          人物
        </button>
        <button type="button" :class="{ active: activeTab === 'assets' }" @click="openTab('assets')">
          场景 / 道具
        </button>
        <button type="button" :class="{ active: activeTab === 'speaker' }" @click="openTab('speaker')">
          对白说话人
          <b v-if="speakerIssues.length">{{ speakerIssues.length }}</b>
        </button>
        <button
          v-if="activeTab === 'assets' && assetView === 'matrix'"
          type="button"
          class="back-to-pending"
          @click="openAssetInbox"
        >
          ← 只看待处理
        </button>
      </nav>

      <div v-if="error" class="state-line danger">{{ error }}</div>
      <div v-else-if="loading" class="state-line">正在读取当前原片状态…</div>

      <main class="source-confirm-body">
        <CharacterAssetsWorkbenchV1
          v-if="activeTab === 'people'"
          :project-id="props.projectId"
          @changed="refresh"
          @back-to-library="close"
          @next-stage="openTab('assets')"
        />

        <AssetReviewInboxV1
          v-else-if="activeTab === 'assets' && assetView === 'inbox' && project"
          :project-id="project.id"
          :episodes="project.episodes"
          @open-matrix="openAssetMatrix"
        />

        <AssetReviewMatrixV4
          v-else-if="activeTab === 'assets' && assetView === 'matrix' && project"
          :project-id="project.id"
          :episodes="project.episodes"
        />

        <template v-else-if="activeTab === 'speaker'">
          <SpeakerReviewEditorV1
            v-if="speakerIssues.length"
            :issues="speakerIssues"
            @changed="refresh"
            @open-asset-editor="openTab('people')"
          />
          <section v-else class="simple-empty">
            <span>✓</span>
            <div>
              <strong>对白说话人已经确认完成</strong>
              <p>没有需要人工处理的说话人。</p>
            </div>
          </section>
        </template>
      </main>

      <footer class="source-confirm-footer">
        <div class="footer-state">
          <strong>{{ sourceReady ? '原片确认完成' : '还有内容需要确认' }}</strong>
          <span>{{ blockingReason }}</span>
        </div>
        <div class="source-confirm-actions">
          <button class="secondary" type="button" @click="close">返回拉片</button>
          <button class="primary" type="button" :disabled="!sourceReady" @click="enterRemake">进入视频重做 →</button>
        </div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.source-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(18, 28, 45, .46);
  backdrop-filter: blur(3px);
}
.source-confirm-dialog {
  width: min(1540px, calc(100vw - 32px));
  height: min(950px, calc(100vh - 32px));
  display: grid;
  grid-template-rows: auto auto auto minmax(0, 1fr) auto;
  overflow: hidden;
  border: 1px solid #dfe5ee;
  border-radius: 15px;
  background: #f6f8fb;
  box-shadow: 0 28px 80px rgba(17, 32, 58, .28);
  color: #263850;
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}
.source-confirm-head {
  min-height: 70px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e9ef;
  background: #fff;
}
.head-copy { min-width: 0; display: grid; gap: 2px; }
.head-copy > small { color: #1769ff; font-size: 10px; font-weight: 850; }
.head-copy > span { color: #7c899b; font-size: 11px; }
.title-row { display: flex; align-items: center; gap: 9px; }
.title-row strong { color: #243851; font-size: 20px; }
.ready-chip { padding: 4px 8px; border-radius: 999px; background: #fff0d9; color: #9d6300; font-size: 10px; font-weight: 850; }
.ready-chip.ready { background: #e8f7ee; color: #22724a; }
.close-button { width: 36px; height: 36px; border: 1px solid #dce3ec; border-radius: 9px; background: #fff; color: #6f7e91; font-size: 19px; cursor: pointer; }
.confirm-tabs {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 16px;
  border-bottom: 1px solid #e4e9f0;
  background: #fff;
}
.confirm-tabs button { min-height: 36px; padding: 0 14px; border: 1px solid #dbe3ee; border-radius: 8px; background: #fff; color: #4d6078; font-size: 12px; font-weight: 800; cursor: pointer; }
.confirm-tabs button.active { border-color: #8eaeef; background: #eef4ff; color: #1769ff; }
.confirm-tabs button b { margin-left: 5px; padding: 1px 5px; border-radius: 999px; background: #e8eef8; font-size: 9px; }
.confirm-tabs .back-to-pending { margin-left: auto; font-weight: 700; }
.state-line { padding: 8px 16px; border-bottom: 1px solid #e8edf3; background: #f9fbfd; color: #6f7e92; font-size: 11px; }
.state-line.danger { background: #fff2f2; color: #b13e3e; }
.source-confirm-body { min-height: 0; overflow: auto; padding: 12px 16px 18px; }
.simple-empty { min-height: 240px; display: flex; align-items: center; justify-content: center; gap: 12px; border: 1px solid #e0e6ee; border-radius: 12px; background: #fff; color: #6f7f93; }
.simple-empty > span { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 50%; background: #e8f7ee; color: #26734d; font-weight: 900; }
.simple-empty strong { display: block; color: #334862; font-size: 14px; }
.simple-empty p { margin: 4px 0 0; font-size: 11px; }
.source-confirm-footer { min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 16px; border-top: 1px solid #e2e7ee; background: #fff; }
.footer-state { min-width: 0; display: grid; gap: 1px; }
.footer-state strong { color: #314760; font-size: 12px; }
.footer-state span { overflow: hidden; color: #7f8b9b; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.source-confirm-actions { display: flex; gap: 8px; }
.source-confirm-actions button { min-height: 38px; padding: 0 14px; border-radius: 8px; font-size: 11px; font-weight: 800; cursor: pointer; }
.source-confirm-actions .secondary { border: 1px solid #dbe3ec; background: #fff; color: #53657c; }
.source-confirm-actions .primary { border: 1px solid #1769ff; background: #1769ff; color: #fff; }
.source-confirm-actions .primary:disabled { border-color: #aebfe3; background: #aebfe3; cursor: not-allowed; }

/* 原片确认里直接进入人物工作台，隐藏重复的“返回上一层”按钮。 */
.source-confirm-body :deep(.identity-review .review-topbar .back-button) { display: none; }
/* 人物完成后不再显示“查看人物资产库”这一层，只保留继续场景/道具。 */
.source-confirm-body :deep(.identity-review .completion-actions button:first-child) { display: none; }

@media (max-width: 900px) {
  .source-confirm-overlay { padding: 0; }
  .source-confirm-dialog { width: 100vw; height: 100vh; border-radius: 0; }
  .source-confirm-head { align-items: flex-start; }
  .title-row strong { font-size: 17px; }
  .confirm-tabs { overflow-x: auto; }
  .confirm-tabs button { white-space: nowrap; }
  .footer-state { display: none; }
  .source-confirm-footer { justify-content: flex-end; }
}
</style>
