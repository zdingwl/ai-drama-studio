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

const props = defineProps<{
  projectId: string
}>()

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

function stage(key: string): ProjectFlowStage | null {
  return flow.value?.stages.find((item) => item.stage_key === key) || null
}

const sourceAssetsStage = computed(() => stage('source_assets'))
const sourceSnapshotStage = computed(() => stage('source_snapshot'))
const sourceReady = computed(() => Boolean(sourceAssetsStage.value?.consumable && sourceSnapshotStage.value?.consumable))

const sourceIssues = computed(() => issues.value.filter((item) => sourceIssueTypes.has(item.issue_type)))
const speakerIssues = computed(() => sourceIssues.value.filter((item) => item.issue_type === 'SPEAKER'))
const assetIssues = computed(() => sourceIssues.value.filter((item) => item.issue_type !== 'SPEAKER'))

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
  const episodeText = episode ? `EP${String(episode.sort_order).padStart(2, '0')}` : '当前剧集'
  const shotText = selectedShotOrdinal.value ? ` · Shot ${String(selectedShotOrdinal.value).padStart(2, '0')}` : ''
  return `${episodeText}${shotText}`
})

const blockingReason = computed(() => {
  if (sourceReady.value) return '原片人物、场景、道具和正式事实快照均已就绪。'
  const assetStage = sourceAssetsStage.value
  if (assetStage && !assetStage.consumable) return assetStage.reason
  const snapshotStage = sourceSnapshotStage.value
  if (snapshotStage && !snapshotStage.consumable) return snapshotStage.reason
  return '原片确认状态尚未就绪，请先处理待确认问题。'
})

const sourceMetrics = computed(() => {
  const snapshot = sourceSnapshotStage.value?.metrics || {}
  const assets = sourceAssetsStage.value?.metrics || {}
  const readNumber = (value: unknown): number => {
    const parsed = Number(value || 0)
    return Number.isFinite(parsed) ? Math.max(0, parsed) : 0
  }
  return {
    episodes: readNumber(snapshot.episode_count),
    shots: readNumber(snapshot.shot_count),
    characters: readNumber(snapshot.resolved_character_count ?? assets.character_count),
    scenes: readNumber(snapshot.scene_count ?? assets.scene_count),
    dialogues: readNumber(snapshot.source_dialogue_count),
  }
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

function openTab(tab: ConfirmTab): void {
  activeTab.value = tab
  void router.replace({ query: { ...route.query, mode: 'confirm', confirm_tab: tab } })
}

function openIssue(issue: ReviewIssue): void {
  openTab(issue.issue_type === 'SPEAKER' ? 'speaker' : 'assets')
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
    <section class="source-confirm-dialog" role="dialog" aria-modal="true" aria-label="原片确认">
      <header class="source-confirm-head">
        <div>
          <small>03 · 原片确认</small>
          <strong>直接在拉片页面处理</strong>
          <span>{{ locationLabel }} · 这里只处理真正影响后续视频重做的问题，修改后立即写回当前原片事实。</span>
        </div>
        <button type="button" aria-label="关闭原片确认" @click="close">×</button>
      </header>

      <div class="source-confirm-summary">
        <div><small>剧集</small><strong>{{ sourceMetrics.episodes || project?.episodes.length || 0 }}</strong></div>
        <div><small>镜头</small><strong>{{ sourceMetrics.shots }}</strong></div>
        <div><small>人物</small><strong>{{ sourceMetrics.characters }}</strong></div>
        <div><small>场景</small><strong>{{ sourceMetrics.scenes }}</strong></div>
        <div><small>源对白</small><strong>{{ sourceMetrics.dialogues }}</strong></div>
        <div :class="{ warning: sourceIssues.length }"><small>待处理</small><strong>{{ sourceIssues.length }}</strong></div>
      </div>

      <div v-if="error" class="source-confirm-message danger">{{ error }}</div>
      <div v-else-if="loading" class="source-confirm-message">正在读取当前原片确认状态…</div>
      <div v-else :class="['source-confirm-message', sourceReady ? 'success' : 'warning']">
        <strong>{{ sourceReady ? '原片已经可以进入视频重做' : '原片还不能进入视频重做' }}</strong>
        <span>{{ blockingReason }}</span>
      </div>

      <nav class="source-confirm-tabs" aria-label="原片确认工具">
        <button type="button" :class="{ active: activeTab === 'pending' }" @click="openTab('pending')">
          <strong>待处理</strong><span>{{ sourceIssues.length }} 项</span>
        </button>
        <button type="button" :class="{ active: activeTab === 'assets' }" @click="openTab('assets')">
          <strong>人物 / 场景 / 道具</strong><span>{{ assetIssues.length ? `${assetIssues.length} 项需要判断` : '查看或修改绑定' }}</span>
        </button>
        <button type="button" :class="{ active: activeTab === 'speaker' }" @click="openTab('speaker')">
          <strong>对白说话人</strong><span>{{ speakerIssues.length ? `${speakerIssues.length} 条待确认` : '没有待确认说话人' }}</span>
        </button>
      </nav>

      <main class="source-confirm-body">
        <template v-if="activeTab === 'pending'">
          <section v-if="sourceIssues.length" class="source-confirm-issues">
            <article v-for="issue in sourceIssues" :key="issue.id" :class="{ current: issueIsCurrent(issue) }">
              <div>
                <small>{{ issueLocation(issue) }}<template v-if="issueIsCurrent(issue)"> · 当前定位</template></small>
                <strong>{{ issueTitle(issue) }}</strong>
                <p>{{ issue.reason }}</p>
              </div>
              <button type="button" @click="openIssue(issue)">处理</button>
            </article>
          </section>
          <section v-else class="source-confirm-empty">
            <span>✓</span>
            <strong>没有需要人工处理的原片问题</strong>
            <p>系统能够确定的内容已经自动采用，不需要逐镜头点击确认。</p>
          </section>

          <section v-if="sourceSnapshotStage?.warnings.length" class="source-confirm-warnings">
            <strong>非阻塞提示</strong>
            <p v-for="warning in sourceSnapshotStage.warnings" :key="warning">{{ warning }}</p>
          </section>
        </template>

        <AssetStageV4
          v-else-if="activeTab === 'assets' && project"
          :project-id="project.id"
          :episodes="project.episodes"
        />

        <template v-else-if="activeTab === 'speaker'">
          <SpeakerReviewEditorV1
            v-if="speakerIssues.length"
            :issues="speakerIssues"
            @changed="refresh"
            @open-asset-editor="openTab('assets')"
          />
          <section v-else class="source-confirm-empty">
            <span>✓</span>
            <strong>没有待确认的对白说话人</strong>
            <p>已经确定的说话人不会要求你重复确认。</p>
          </section>
        </template>
      </main>

      <footer class="source-confirm-footer">
        <div>
          <strong>{{ sourceReady ? '原片确认完成' : `还需处理 ${sourceIssues.length} 项` }}</strong>
          <span>{{ sourceReady ? '后续本土化、配音和 H3 生成将使用当前 SourceDramaSnapshot。' : blockingReason }}</span>
        </div>
        <div class="source-confirm-actions">
          <button class="secondary" type="button" @click="close">继续看拉片</button>
          <button class="primary" type="button" :disabled="!sourceReady" @click="enterRemake">原片确认完成，进入视频重做 →</button>
        </div>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.source-confirm-overlay{position:fixed;inset:0;z-index:1200;display:flex;align-items:center;justify-content:center;padding:28px;background:rgba(18,28,45,.48);backdrop-filter:blur(3px)}
.source-confirm-dialog{width:min(1480px,calc(100vw - 56px));height:min(900px,calc(100vh - 56px));display:grid;grid-template-rows:auto auto auto auto minmax(0,1fr) auto;overflow:hidden;border:1px solid #dfe5ee;border-radius:16px;background:#f7f9fc;box-shadow:0 28px 80px rgba(17,32,58,.28);font-family:Inter,ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#263850}
.source-confirm-head{min-height:78px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:14px 18px;border-bottom:1px solid #e4e9f0;background:#fff}.source-confirm-head>div{display:grid;gap:2px}.source-confirm-head small{color:#1769ff;font-size:10px;font-weight:800}.source-confirm-head strong{font-size:20px;color:#1f3048}.source-confirm-head span{color:#7b899b;font-size:11px}.source-confirm-head>button{width:36px;height:36px;border:1px solid #dce3ec;border-radius:9px;background:#fff;color:#6f7d90;font-size:22px;cursor:pointer}
.source-confirm-summary{display:grid;grid-template-columns:repeat(6,minmax(92px,1fr));gap:8px;padding:10px 14px;background:#f7f9fc}.source-confirm-summary>div{display:grid;gap:1px;padding:8px 10px;border:1px solid #e1e6ed;border-radius:9px;background:#fff}.source-confirm-summary small{color:#8a96a6;font-size:9px}.source-confirm-summary strong{font-size:15px;color:#34465f}.source-confirm-summary .warning{border-color:#eed8ad;background:#fff9ed}.source-confirm-summary .warning strong{color:#a56a18}
.source-confirm-message{margin:0 14px 10px;padding:9px 11px;display:flex;align-items:center;gap:8px;border:1px solid #dce4ef;border-radius:8px;background:#fff;color:#65758a;font-size:10px}.source-confirm-message strong{color:#33465f}.source-confirm-message.success{border-color:#c9e6d7;background:#f4fbf7;color:#4f7a64}.source-confirm-message.warning{border-color:#ecd7af;background:#fff9ed;color:#8c6a31}.source-confirm-message.danger{border-color:#efc9cf;background:#fff5f6;color:#a84c58}
.source-confirm-tabs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:0 14px 10px}.source-confirm-tabs button{min-height:54px;display:grid;gap:2px;align-content:center;padding:8px 12px;border:1px solid #dde4ed;border-radius:10px;background:#fff;text-align:left;cursor:pointer}.source-confirm-tabs button.active{border-color:#91b3ee;background:#eef5ff;box-shadow:inset 3px 0 0 #1769ff}.source-confirm-tabs strong{font-size:12px;color:#344a66}.source-confirm-tabs span{font-size:9px;color:#8490a1}
.source-confirm-body{min-height:0;overflow:auto;padding:0 14px 14px}.source-confirm-issues{display:grid;gap:8px}.source-confirm-issues article{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 13px;border:1px solid #e0e5ec;border-radius:10px;background:#fff}.source-confirm-issues article.current{border-color:#9bb9ec;box-shadow:0 0 0 2px rgba(74,116,190,.08)}.source-confirm-issues article>div{display:grid;gap:3px;min-width:0}.source-confirm-issues small{color:#7d8a9c;font-size:9px}.source-confirm-issues strong{font-size:12px;color:#334861}.source-confirm-issues p{margin:0;color:#6f7f92;font-size:10px;line-height:1.55}.source-confirm-issues button{flex:none;min-height:34px;padding:0 13px;border:1px solid #bcd0f4;border-radius:8px;background:#f4f8ff;color:#2564c7;font-size:10px;font-weight:800;cursor:pointer}
.source-confirm-empty{min-height:230px;display:grid;place-items:center;align-content:center;gap:8px;border:1px dashed #d8e1eb;border-radius:12px;background:#fff;text-align:center}.source-confirm-empty>span{width:44px;height:44px;display:grid;place-items:center;border-radius:50%;background:#eaf8f0;color:#27935c;font-size:22px}.source-confirm-empty strong{font-size:15px;color:#365069}.source-confirm-empty p{margin:0;color:#8190a3;font-size:10px}.source-confirm-warnings{margin-top:10px;padding:11px 12px;border:1px solid #ead9b6;border-radius:10px;background:#fffaf0}.source-confirm-warnings strong{font-size:10px;color:#7e612e}.source-confirm-warnings p{margin:4px 0 0;color:#90784d;font-size:9px;line-height:1.5}
.source-confirm-footer{min-height:70px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:12px 16px;border-top:1px solid #e1e6ed;background:#fff}.source-confirm-footer>div:first-child{display:grid;gap:2px;min-width:0}.source-confirm-footer strong{font-size:11px;color:#354a65}.source-confirm-footer span{max-width:760px;color:#7d899a;font-size:9px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.source-confirm-actions{display:flex;gap:8px;flex:none}.source-confirm-actions button{min-height:38px;padding:0 14px;border-radius:8px;font-size:10px;font-weight:800;cursor:pointer}.source-confirm-actions .secondary{border:1px solid #d6dee9;background:#fff;color:#52637a}.source-confirm-actions .primary{border:1px solid #1769ff;background:#1769ff;color:#fff}.source-confirm-actions .primary:disabled{opacity:.45;cursor:not-allowed}
@media(max-width:900px){.source-confirm-overlay{padding:10px}.source-confirm-dialog{width:calc(100vw - 20px);height:calc(100vh - 20px)}.source-confirm-summary{grid-template-columns:repeat(3,minmax(0,1fr))}.source-confirm-tabs{grid-template-columns:1fr}.source-confirm-footer{align-items:stretch;flex-direction:column}.source-confirm-footer span{white-space:normal}.source-confirm-actions{justify-content:flex-end}}
</style>
