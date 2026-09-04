<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { remakeApi } from '../api/remake'
import AssetStageV4 from './AssetStageV4.vue'
import SpeakerReviewEditorV1 from './SpeakerReviewEditorV1.vue'
import type { ProjectFlowStage, ProjectFlowState } from '../types/project-flow-state'
import type { ReviewIssue } from '../types/remake'
import type { Project } from '../types/studio'

type ConfirmTab = 'pending' | 'assets' | 'speaker'
type AssetTab = 'inbox' | 'people' | 'matrix'

const props = defineProps<{ projectId: string }>()
const route = useRoute()
const router = useRouter()

const project = ref<Project | null>(null)
const flow = ref<ProjectFlowState | null>(null)
const issues = ref<ReviewIssue[]>([])
const loading = ref(true)
const error = ref('')
const activeTab = ref<ConfirmTab>('pending')

const sourceIssueTypes = new Set(['CHARACTER_IDENTITY', 'ASSET_BINDING', 'SPEAKER'])

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function tabFromQuery(): ConfirmTab {
  const value = String(route.query.confirm_tab || '')
  if (value === 'assets' || value === 'speaker') return value
  return 'pending'
}

function assetTabFromQuery(): AssetTab {
  const value = String(route.query.asset_tab || '')
  if (value === 'people' || value === 'matrix') return value
  return 'inbox'
}

function stage(key: string): ProjectFlowStage | null {
  return flow.value?.stages.find((item) => item.stage_key === key) || null
}

const sourceAssetsStage = computed(() => stage('source_assets'))
const sourceSnapshotStage = computed(() => stage('source_snapshot'))
const sourceReady = computed(() => Boolean(sourceAssetsStage.value?.consumable && sourceSnapshotStage.value?.consumable))
const sourceIssues = computed(() => issues.value.filter((item) => sourceIssueTypes.has(item.issue_type)))
const speakerIssues = computed(() => sourceIssues.value.filter((item) => item.issue_type === 'SPEAKER'))
const assetIssues = computed(() => sourceIssues.value.filter((item) => item.issue_type !== 'SPEAKER'))
const characterIssues = computed(() => sourceIssues.value.filter((item) => item.issue_type === 'CHARACTER_IDENTITY'))

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
  if (sourceReady.value) return '原片事实已经可以供后续视频重做使用。'
  const assetStage = sourceAssetsStage.value
  if (assetStage && !assetStage.consumable) return assetStage.reason
  const snapshotStage = sourceSnapshotStage.value
  if (snapshotStage && !snapshotStage.consumable) return snapshotStage.reason
  return '请先处理仍会影响后续重做的原片问题。'
})

const dialogTitle = computed(() => {
  if (activeTab.value === 'speaker') return '核对对白说话人'
  if (activeTab.value === 'assets') {
    const assetTab = assetTabFromQuery()
    if (assetTab === 'people') return '核对原片人物'
    if (assetTab === 'matrix') return '核对场景与道具绑定'
    return '处理原片资产问题'
  }
  return '原片确认'
})

const dialogHint = computed(() => {
  if (activeTab.value === 'speaker') return '只处理无法自动确定说话人的对白。'
  if (activeTab.value === 'assets' && assetTabFromQuery() === 'people') return '把无法唯一确定的人物归并到正确的原片人物资产。'
  if (activeTab.value === 'assets') return '检查真正有冲突或缺失的 Final Binding。'
  return '系统能确定的内容自动采用，这里只保留需要你判断的部分。'
})

function issueTitle(issue: ReviewIssue): string {
  if (issue.issue_type === 'CHARACTER_IDENTITY') return '人物身份待确认'
  if (issue.issue_type === 'ASSET_BINDING') return '人物 / 场景 / 道具绑定待确认'
  if (issue.issue_type === 'SPEAKER') return '对白说话人待确认'
  return issue.issue_type || '原片事实待确认'
}

function issueLocation(issue: ReviewIssue): string {
  const suggestion = isRecord(issue.ai_suggestion) ? issue.ai_suggestion : null
  const episodeOrder = Number(suggestion?.episode_order || 0)
  const shotOrdinal = Number(suggestion?.shot_ordinal || 0)
  const parts: string[] = []
  if (episodeOrder > 0) parts.push(`第 ${String(episodeOrder).padStart(2, '0')} 集`)
  if (shotOrdinal > 0) parts.push(`Shot ${String(shotOrdinal).padStart(2, '0')}`)
  if (!parts.length && issue.episode_id) {
    const episode = project.value?.episodes.find((item) => item.id === issue.episode_id)
    if (episode) parts.push(`第 ${String(episode.sort_order).padStart(2, '0')} 集`)
  }
  return parts.join(' · ') || '当前项目'
}

function issueIsCurrent(issue: ReviewIssue): boolean {
  const suggestion = isRecord(issue.ai_suggestion) ? issue.ai_suggestion : null
  const episodeMatches = !selectedEpisode.value || !issue.episode_id || issue.episode_id === selectedEpisode.value.id
  const suggestedShot = Number(suggestion?.shot_ordinal || 0)
  const shotMatches = !selectedShotOrdinal.value || !suggestedShot || suggestedShot === selectedShotOrdinal.value
  return episodeMatches && shotMatches
}

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

function openTab(tab: ConfirmTab, assetTab?: AssetTab): void {
  activeTab.value = tab
  void router.replace({
    query: {
      ...route.query,
      mode: 'confirm',
      confirm_tab: tab,
      ...(assetTab ? { asset_tab: assetTab } : {}),
    },
  })
}

function openIssue(issue: ReviewIssue): void {
  if (issue.issue_type === 'SPEAKER') {
    openTab('speaker')
    return
  }
  if (issue.issue_type === 'CHARACTER_IDENTITY') {
    openTab('assets', 'people')
    return
  }
  openTab('assets', 'inbox')
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
    <section class="source-confirm-dialog" role="dialog" aria-modal="true" :aria-label="dialogTitle">
      <header class="source-confirm-head">
        <div class="head-copy">
          <small>03 · 原片确认 · {{ locationLabel }}</small>
          <div class="title-row">
            <strong>{{ dialogTitle }}</strong>
            <span :class="['ready-chip', { ready: sourceReady }]">
              {{ sourceReady ? '已就绪' : `${sourceIssues.length} 项待处理` }}
            </span>
          </div>
          <span>{{ dialogHint }}</span>
        </div>
        <button type="button" class="close-button" aria-label="关闭原片确认" @click="close">×</button>
      </header>

      <div class="source-confirm-toolbar">
        <nav class="source-confirm-tabs" aria-label="原片确认工具">
          <button type="button" :class="{ active: activeTab === 'pending' }" @click="openTab('pending')">
            待处理 <b>{{ sourceIssues.length }}</b>
          </button>
          <button type="button" :class="{ active: activeTab === 'assets' }" @click="openTab('assets', characterIssues.length ? 'people' : 'inbox')">
            人物 / 场景 / 道具 <b>{{ assetIssues.length }}</b>
          </button>
          <button type="button" :class="{ active: activeTab === 'speaker' }" @click="openTab('speaker')">
            对白说话人 <b>{{ speakerIssues.length }}</b>
          </button>
        </nav>

        <div v-if="error" class="state-line danger">{{ error }}</div>
        <div v-else-if="loading" class="state-line">正在读取当前原片状态…</div>
        <div v-else-if="!sourceReady" class="state-line warning">{{ blockingReason }}</div>
      </div>

      <main class="source-confirm-body">
        <template v-if="activeTab === 'pending'">
          <section v-if="sourceIssues.length" class="source-confirm-issues">
            <article v-for="issue in sourceIssues" :key="issue.id" :class="{ current: issueIsCurrent(issue) }">
              <div>
                <small>{{ issueLocation(issue) }}<template v-if="issueIsCurrent(issue)"> · 当前定位</template></small>
                <strong>{{ issueTitle(issue) }}</strong>
                <p>{{ issue.reason }}</p>
              </div>
              <button type="button" @click="openIssue(issue)">处理 →</button>
            </article>
          </section>

          <section v-else class="source-confirm-empty">
            <span>✓</span>
            <div>
              <strong>没有需要人工处理的原片问题</strong>
              <p>系统能够确定的内容已经自动采用，不需要逐镜头重复确认。</p>
            </div>
          </section>

          <section v-if="sourceSnapshotStage?.warnings.length" class="source-confirm-warnings">
            <strong>非阻塞提示</strong>
            <p v-for="warning in sourceSnapshotStage.warnings" :key="warning">{{ warning }}</p>
          </section>
        </template>

        <AssetStageV4
          v-else-if="activeTab === 'assets' && project"
          compact
          :project-id="project.id"
          :episodes="project.episodes"
        />

        <template v-else-if="activeTab === 'speaker'">
          <SpeakerReviewEditorV1
            v-if="speakerIssues.length"
            :issues="speakerIssues"
            @changed="refresh"
            @open-asset-editor="openTab('assets', 'people')"
          />
          <section v-else class="source-confirm-empty">
            <span>✓</span>
            <div>
              <strong>没有待确认的对白说话人</strong>
              <p>已经确定的说话人不会要求你重复确认。</p>
            </div>
          </section>
        </template>
      </main>

      <footer class="source-confirm-footer">
        <div class="footer-state">
          <strong>{{ sourceReady ? '原片确认完成' : `还需处理 ${sourceIssues.length} 项` }}</strong>
          <span>{{ sourceReady ? '当前原片事实可直接进入视频重做。' : blockingReason }}</span>
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
  padding: 20px;
  background: rgba(18, 28, 45, .46);
  backdrop-filter: blur(3px);
}
.source-confirm-dialog {
  width: min(1540px, calc(100vw - 40px));
  height: min(940px, calc(100vh - 40px));
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr) auto;
  overflow: hidden;
  border: 1px solid #dfe5ee;
  border-radius: 15px;
  background: #f6f8fb;
  box-shadow: 0 28px 80px rgba(17, 32, 58, .28);
  font-family: Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #263850;
}
.source-confirm-head {
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e9ef;
  background: #fff;
}
.head-copy { min-width: 0; display: grid; gap: 2px; }
.head-copy > small { color: #1769ff; font-size: 9px; font-weight: 850; }
.title-row { display: flex; align-items: center; gap: 8px; }
.title-row > strong { color: #20334e; font-size: 19px; }
.head-copy > span { color: #7d8999; font-size: 10px; }
.ready-chip { padding: 3px 7px; border-radius: 999px; background: #fff3df; color: #986a25; font-size: 9px; font-weight: 800; }
.ready-chip.ready { background: #e7f6ed; color: #31754c; }
.close-button { width: 34px; height: 34px; display: grid; place-items: center; border: 1px solid #dce3ec; border-radius: 9px; background: #fff; color: #6f7d90; font-size: 21px; cursor: pointer; }
.source-confirm-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 52px; padding: 8px 14px; border-bottom: 1px solid #e6eaf0; background: #fafbfd; }
.source-confirm-tabs { display: flex; align-items: center; gap: 6px; }
.source-confirm-tabs button { min-height: 34px; border: 1px solid #dce3ec; border-radius: 8px; padding: 6px 11px; background: #fff; color: #53637a; font-size: 10px; font-weight: 750; cursor: pointer; }
.source-confirm-tabs button.active { border-color: #7fa2e9; background: #edf4ff; color: #315fae; }
.source-confirm-tabs b { display: inline-grid; min-width: 18px; height: 18px; place-items: center; margin-left: 4px; border-radius: 999px; background: #f0f3f7; color: #607089; font-size: 9px; }
.source-confirm-tabs button.active b { background: #dbe8ff; color: #315fae; }
.state-line { max-width: 580px; overflow: hidden; color: #778499; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.state-line.warning { color: #8a672c; }.state-line.danger { color: #a84444; }
.source-confirm-body { min-height: 0; overflow: auto; padding: 12px 14px 16px; }
.source-confirm-issues { display: grid; gap: 8px; max-width: 980px; margin: 0 auto; }
.source-confirm-issues article { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 12px 13px; border: 1px solid #dfe5ed; border-radius: 10px; background: #fff; }
.source-confirm-issues article.current { border-color: #8eadeb; background: #f4f8ff; }
.source-confirm-issues article > div { min-width: 0; display: grid; gap: 2px; }
.source-confirm-issues small { color: #8090a4; font-size: 9px; }.source-confirm-issues strong { color: #324866; font-size: 12px; }.source-confirm-issues p { margin: 0; color: #738197; font-size: 10px; line-height: 1.45; }
.source-confirm-issues button { flex: 0 0 auto; border: 1px solid #9db6e5; border-radius: 8px; padding: 7px 10px; background: #fff; color: #4069b5; font-size: 10px; font-weight: 800; cursor: pointer; }
.source-confirm-empty { min-height: 180px; display: flex; align-items: center; justify-content: center; gap: 12px; border: 1px solid #cce4d6; border-radius: 11px; background: #f3fbf7; }
.source-confirm-empty > span { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 50%; background: #dff3e7; color: #317d50; font-size: 20px; font-weight: 900; }
.source-confirm-empty > div { display: grid; gap: 3px; }.source-confirm-empty strong { color: #315c45; font-size: 14px; }.source-confirm-empty p { margin: 0; color: #759180; font-size: 10px; }
.source-confirm-warnings { max-width: 980px; display: grid; gap: 4px; margin: 10px auto 0; padding: 10px 12px; border: 1px solid #ead8b3; border-radius: 9px; background: #fff9ee; }
.source-confirm-warnings strong { color: #795f2e; font-size: 10px; }.source-confirm-warnings p { margin: 0; color: #8e7750; font-size: 9px; }
.source-confirm-footer { min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 10px 14px; border-top: 1px solid #e3e8ef; background: #fff; }
.footer-state { min-width: 0; display: grid; gap: 2px; }.footer-state strong { color: #344964; font-size: 11px; }.footer-state span { overflow: hidden; color: #7c899a; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.source-confirm-actions { display: flex; gap: 7px; flex: 0 0 auto; }.source-confirm-actions button { min-height: 36px; border-radius: 8px; padding: 0 12px; font-size: 10px; font-weight: 800; cursor: pointer; }.source-confirm-actions .secondary { border: 1px solid #d9e1eb; background: #fff; color: #5b6d84; }.source-confirm-actions .primary { border: 1px solid #4c78df; background: #4c78df; color: #fff; }.source-confirm-actions button:disabled { opacity: .48; cursor: not-allowed; }
@media (max-width: 900px) {
  .source-confirm-overlay { padding: 8px; }
  .source-confirm-dialog { width: calc(100vw - 16px); height: calc(100vh - 16px); }
  .source-confirm-toolbar { align-items: flex-start; flex-direction: column; }
  .source-confirm-tabs { width: 100%; overflow-x: auto; }
  .state-line { max-width: 100%; }
  .source-confirm-footer { align-items: flex-start; flex-direction: column; }
  .source-confirm-actions { width: 100%; }.source-confirm-actions button { flex: 1; }
}
</style>
