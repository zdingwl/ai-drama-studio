<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import type { ContentAnalysisRun, Episode, F05ModelStatus, Project, Shot, ShotRevision } from '../types/studio'

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.projectId)
const project = ref<Project | null>(null)
const activeStage = ref(1)
const loading = ref(true)
const busy = ref('')
const error = ref('')
const draggedId = ref<string | null>(null)
const selectedEpisodeId = ref('')
const shots = ref<Shot[]>([])
const selectedShot = ref<Shot | null>(null)
const shotEditorOpen = ref(false)
const shotVideoRef = ref<HTMLVideoElement | null>(null)
const startBoundarySeconds = ref(0)
const endBoundarySeconds = ref(0)
const editBusy = ref('')
const shotRevisions = ref<ShotRevision[]>([])
const revisionPanelOpen = ref(false)
const contentRun = ref<ContentAnalysisRun | null>(null)
const f05Models = ref<F05ModelStatus | null>(null)
const assetView = ref<'shot' | 'characters' | 'scenes' | 'props'>('shot')

/**
 * 用户工作区只保留“需要决策 / 可以修改 / 对下游影响大”的业务阶段。
 * FFmpeg、Proxy、Audio、Media Info、Embedding 等技术中间结果全部后台化。
 */
const stages = [
  ['01', '剧集管理', '批量导入 / 排序 / 替换'],
  ['02', '拉片', '自动切镜 / 必要时人工修正'],
  ['03', '资产', '人物 / 场景 / 道具 + Shot 绑定'],
  ['04', '内容剧本', '对白 / Speaker / 动作 / 结构化剧本'],
  ['05', '重制设计', '角色 / 场景 / 本土化 / Shot Spec'],
  ['06', '生成 / 导出', 'Video / Voice / LipSync / QC / Export'],
]

const episodes = computed(() => project.value?.episodes ?? [])
const selectedEpisode = computed(() => episodes.value.find((item) => item.id === selectedEpisodeId.value) ?? null)
const selectedShotIndex = computed(() => selectedShot.value ? shots.value.findIndex((item) => item.id === selectedShot.value?.id) : -1)
const suspiciousShotCount = computed(() => shots.value.filter((shot) => shot.duration_us < 500_000).length)
const currentShotRevision = computed(() => shotRevisions.value.find((item) => item.is_current) ?? null)

/** 正式人物候选必须至少有一条露脸 Track；body-only 只能作为辅助 Evidence。 */
const reliableCharacters = computed(() => {
  return (contentRun.value?.characters ?? [])
    .filter((character) => character.tracks.some((track) => track.face_visible))
    .sort((left, right) => right.shot_count - left.shot_count || right.track_count - left.track_count)
})
const hiddenBodyOnlyCandidates = computed(() => Math.max(0, (contentRun.value?.characters.length ?? 0) - reliableCharacters.value.length))
const orderedScenes = computed(() => [...(contentRun.value?.scenes ?? [])].sort((left, right) => right.shot_count - left.shot_count))
const shotCharacters = computed(() => selectedShot.value ? reliableCharacters.value.filter((character) => character.tracks.some((track) => track.shot_id === selectedShot.value?.id)) : [])
const shotScenes = computed(() => selectedShot.value ? orderedScenes.value.filter((scene) => scene.shot_ids.includes(selectedShot.value!.id)) : [])
const selectedShotScene = computed(() => shotScenes.value[0] ?? null)

function charactersForShot(shotId: string) {
  return reliableCharacters.value.filter((character) => character.tracks.some((track) => track.shot_id === shotId))
}
function scenesForShot(shotId: string) {
  return orderedScenes.value.filter((scene) => scene.shot_ids.includes(shotId))
}
function seconds(us: number | null) {
  if (us === null || us === undefined) return '—'
  return `${(us / 1_000_000).toFixed(2)}s`
}
function revisionKind(kind: string) {
  const labels: Record<string, string> = { AUTO: '自动拉片', MANUAL: '人工修正', RESTORE: '历史恢复', BASELINE: '历史基线' }
  return labels[kind] || kind
}
function stageReady(index: number) { return index <= 3 }
function componentText(key: string) {
  if (contentRun.value?.status === 'STALE') return '需重新提取'
  const status = contentRun.value?.component_status[key] || '未执行'
  const labels: Record<string, string> = {
    READY: '已完成', PENDING: '等待中', NOT_CONFIGURED: '未配置', NOT_AVAILABLE: '依赖未安装',
    MODEL_NOT_READY: '模型未准备', MODEL_MISSING: '模型路径不存在', NO_CHARACTER: '未识别人',
    NO_SCENE: '未识别场景', FAILED: '失败', BASIC: '基础描述',
  }
  return labels[status] || status
}
function componentClass(key: string) {
  if (contentRun.value?.status === 'STALE') return 'planned'
  const status = contentRun.value?.component_status[key]
  return status === 'READY' || status === 'NO_CHARACTER' || status === 'NO_SCENE' ? 'ready' : 'planned'
}
function shotMediaUrl(url: string) {
  const shot = selectedShot.value
  if (!shot) return url
  return `${url}?v=${shot.start_us}-${shot.end_us}`
}
function thumbnailUrl(shot: Shot) {
  return shot.thumbnail_url ? `${shot.thumbnail_url}?v=${shot.start_us}-${shot.end_us}` : ''
}
function selectShot(shot: Shot | null) {
  selectedShot.value = shot
  if (shot) {
    startBoundarySeconds.value = shot.start_us / 1_000_000
    endBoundarySeconds.value = shot.end_us / 1_000_000
  }
}

async function reloadProject() {
  project.value = await api.getProject(projectId)
  if (!selectedEpisodeId.value && project.value.episodes.length) selectedEpisodeId.value = project.value.episodes[0].id
}
async function loadAssets() {
  const [models, current] = await Promise.all([api.getF05ModelStatus(), api.getCurrentContentAnalysis(projectId)])
  f05Models.value = models
  contentRun.value = current
}
async function loadRevisions(episodeId = selectedEpisodeId.value) {
  shotRevisions.value = episodeId ? await api.listShotRevisions(episodeId) : []
}
async function run(label: string, action: () => Promise<unknown>, after?: () => Promise<void>) {
  busy.value = label
  error.value = ''
  try {
    await action()
    await reloadProject()
    if (after) await after()
  } catch (err) {
    error.value = err instanceof Error ? err.message : `${label}失败`
  } finally {
    busy.value = ''
  }
}
async function uploadFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (!files.length) return
  await run('正在导入视频', () => api.uploadEpisodes(projectId, files))
  input.value = ''
}
function dragStart(episodeId: string) { draggedId.value = episodeId }
async function dropOn(targetId: string) {
  const sourceId = draggedId.value
  draggedId.value = null
  if (!sourceId || sourceId === targetId || !project.value) return
  const reordered = [...project.value.episodes]
  const sourceIndex = reordered.findIndex((item) => item.id === sourceId)
  const targetIndex = reordered.findIndex((item) => item.id === targetId)
  const [moved] = reordered.splice(sourceIndex, 1)
  reordered.splice(targetIndex, 0, moved)
  project.value.episodes = reordered.map((item, index) => ({ ...item, sort_order: index + 1 }))
  await run('正在保存剧集顺序', () => api.reorderEpisodes(projectId, reordered.map((item) => item.id)))
}
async function removeEpisode(episode: Episode) {
  if (!window.confirm(`删除「${episode.title}」及其分析结果？`)) return
  await run('正在删除剧集', () => api.deleteEpisode(episode.id), async () => {
    if (selectedEpisodeId.value === episode.id) {
      selectedEpisodeId.value = project.value?.episodes[0]?.id ?? ''
      shots.value = []
      shotRevisions.value = []
      selectShot(null)
    }
  })
}
async function loadShots(episodeId = selectedEpisodeId.value) {
  if (!episodeId) {
    shots.value = []
    selectShot(null)
    return
  }
  const previous = selectedShot.value?.id
  shots.value = await api.listShots(episodeId)
  selectShot(shots.value.find((shot) => shot.id === previous) ?? shots.value[0] ?? null)
}
async function chooseEpisode(episodeId: string) {
  selectedEpisodeId.value = episodeId
  shotEditorOpen.value = false
  revisionPanelOpen.value = false
  await Promise.all([loadShots(episodeId), loadRevisions(episodeId)])
}
async function analyzeSingle(episode: Episode) {
  selectedEpisodeId.value = episode.id
  shotEditorOpen.value = false
  revisionPanelOpen.value = false
  await run('正在启动单集拉片', () => api.startEpisodeShotsTask(episode.id))
}
async function analyzeBatch() {
  shotEditorOpen.value = false
  revisionPanelOpen.value = false
  await run('正在启动顺序批量拉片', () => api.startBatchShotsTask(projectId))
}

/** 应用一次人工 Shot 编辑；成功后后端同时创建新的 MANUAL Revision。 */
async function applyShotEdit(label: string, action: () => Promise<Shot[]>, preferredShotId?: string) {
  editBusy.value = label
  error.value = ''
  try {
    const updated = await action()
    shots.value = updated
    selectShot(updated.find((item) => item.id === preferredShotId) ?? updated[Math.max(0, Math.min(selectedShotIndex.value, updated.length - 1))] ?? null)
    await Promise.all([reloadProject(), loadAssets(), loadRevisions()])
  } catch (err) {
    error.value = err instanceof Error ? err.message : `${label}失败`
  } finally {
    editBusy.value = ''
  }
}
async function saveStartBoundary() {
  const shot = selectedShot.value
  if (!shot) return
  await applyShotEdit('正在修改开始边界', () => api.adjustShotBoundary(shot.id, 'start', Math.round(startBoundarySeconds.value * 1_000_000)), shot.id)
}
async function saveEndBoundary() {
  const shot = selectedShot.value
  if (!shot) return
  await applyShotEdit('正在修改结束边界', () => api.adjustShotBoundary(shot.id, 'end', Math.round(endBoundarySeconds.value * 1_000_000)), shot.id)
}
async function splitAtPlayhead() {
  const shot = selectedShot.value
  const video = shotVideoRef.value
  if (!shot || !video) return
  const splitUs = shot.start_us + Math.round(video.currentTime * 1_000_000)
  await applyShotEdit('正在拆分镜头', () => api.splitShot(shot.id, splitUs), shot.id)
}
async function mergePrevious() {
  const index = selectedShotIndex.value
  if (index <= 0) return
  const left = shots.value[index - 1]
  await applyShotEdit('正在合并上一镜', () => api.mergeShotWithNext(left.id), left.id)
}
async function mergeNext() {
  const shot = selectedShot.value
  if (!shot || selectedShotIndex.value >= shots.value.length - 1) return
  await applyShotEdit('正在合并下一镜', () => api.mergeShotWithNext(shot.id), shot.id)
}
async function restoreRevision(revision: ShotRevision) {
  if (revision.is_current) return
  if (!window.confirm(`恢复 R${revision.revision}（${revisionKind(revision.kind)}）？系统会创建一个新的恢复版本，不会覆盖历史。`)) return
  await applyShotEdit(`正在恢复 R${revision.revision}`, () => api.restoreShotRevision(revision.id))
  shotEditorOpen.value = false
}

async function prepareModels() {
  await run('正在准备人物视觉模型', () => api.prepareF05Models(), loadAssets)
}
async function analyzeContent() {
  await run(contentRun.value ? '正在启动重新提取资产' : '正在启动资产提取', () => api.startAssetExtractionTask(projectId))
}

onMounted(async () => {
  try {
    await reloadProject()
    await Promise.all([loadShots(), loadAssets(), loadRevisions()])
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目读取失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div v-if="loading" class="screen-loading">正在打开项目工作台…</div>
  <div v-else-if="!project" class="screen-loading">项目不存在</div>
  <div v-else class="studio-shell">
    <aside class="studio-sidebar">
      <button class="back-link" @click="router.push('/')">← 返回项目</button>
      <div class="studio-brand">
        <span>AI DRAMA STUDIO</span>
        <strong>{{ project.name }}</strong>
        <small>{{ project.source_language }} → {{ project.target_language }} · {{ project.target_region }}</small>
      </div>
      <nav class="stage-nav">
        <button v-for="(stage, index) in stages" :key="stage[0]" :class="['stage-item', { active: activeStage === index + 1 }]" @click="activeStage = index + 1">
          <span class="stage-code">{{ stage[0] }}</span>
          <span class="stage-copy"><strong>{{ stage[1] }}</strong><small>{{ stage[2] }}</small></span>
          <span :class="['stage-dot', stageReady(index + 1) ? 'ready' : 'planned']"></span>
        </button>
      </nav>
    </aside>

    <main class="studio-main">
      <header class="workspace-header">
        <div><div class="eyebrow">{{ stages[activeStage - 1][0] }} · {{ stages[activeStage - 1][1] }}</div><h1>{{ stages[activeStage - 1][2] }}</h1></div>
        <div class="header-meta"><span>{{ episodes.length }} 集</span><span>{{ episodes.reduce((sum, item) => sum + item.shot_count, 0) }} Shots</span><span>Format V{{ project.project_format_version }}</span></div>
      </header>

      <p v-if="error" class="error-banner">{{ error }}</p>
      <div v-if="busy" class="busy-banner"><span class="spinner"></span>{{ busy }}…</div>
      <div v-if="editBusy" class="busy-banner"><span class="spinner"></span>{{ editBusy }}，正在保存新的 Shot Revision…</div>

      <section v-if="activeStage === 1" class="workspace-panel">
        <div class="section-title">
          <div><span>01</span><h2>剧集管理</h2></div>
          <label class="primary-button file-button">导入多个视频<input type="file" multiple accept="video/*" @change="uploadFiles" /></label>
        </div>
        <p class="section-help">一个项目代表一部短剧。批量导入后可直接拖动调整剧集顺序；后续批量拉片严格按照这里的顺序逐集执行。</p>
        <div v-if="episodes.length === 0" class="empty-state large"><strong>还没有剧集</strong><span>一次选择多个视频导入即可，拉片时系统会自动准备分析素材。</span></div>
        <div v-else class="episode-list">
          <div v-for="episode in episodes" :key="episode.id" class="episode-row" draggable="true" @dragstart="dragStart(episode.id)" @dragover.prevent @drop="dropOn(episode.id)">
            <div class="drag-handle">⋮⋮</div>
            <div class="episode-index">{{ String(episode.sort_order).padStart(2, '0') }}</div>
            <div class="episode-main"><strong>{{ episode.title }}</strong><small>{{ episode.original_filename }}</small></div>
            <div class="episode-meta"><span>{{ seconds(episode.duration_us) }}</span><span>{{ episode.preprocess_status === 'READY' ? '分析素材已准备' : '拉片时自动准备' }}</span><span>{{ episode.shot_count }} Shots</span></div>
            <button class="danger-text" @click="removeEpisode(episode)">删除</button>
          </div>
        </div>
        <div class="architecture-note"><strong>项目设置</strong><p>{{ project.name }} · {{ project.source_language }} → {{ project.target_language }} · {{ project.target_region }}。项目语言和目标市场属于项目属性，不再占一个生产阶段。</p></div>
      </section>

      <section v-else-if="activeStage === 2" class="workspace-panel shots-workspace">
        <div class="section-title">
          <div><span>02</span><h2>拉片</h2></div>
          <button class="primary-button" :disabled="!episodes.length || !!busy || !!editBusy" @click="analyzeBatch">顺序批量拉片</button>
        </div>
        <p class="section-help">自动结果不要求逐镜确认。重新自动拉片先完整生成新 Run，成功后才切换 Current；失败时当前人工版本保持不变。</p>
        <div class="episode-tabs"><button v-for="episode in episodes" :key="episode.id" :class="{ active: selectedEpisodeId === episode.id }" @click="chooseEpisode(episode.id)">E{{ String(episode.sort_order).padStart(2, '0') }} · {{ episode.shot_count }} Shots</button></div>
        <div v-if="selectedEpisode" class="shot-action-bar">
          <div>
            <strong>{{ selectedEpisode.title }}</strong>
            <span v-if="selectedEpisode.shot_count && suspiciousShotCount === 0">{{ selectedEpisode.shot_count }} Shots · 未发现明显短镜头，无需逐镜审核</span>
            <span v-else-if="selectedEpisode.shot_count">{{ selectedEpisode.shot_count }} Shots · {{ suspiciousShotCount }} 个短镜头建议检查</span>
            <span v-else>首次拉片会自动完成视频初始化</span>
          </div>
          <div class="shot-action-buttons">
            <button v-if="selectedEpisode.shot_count" class="ghost-button" :disabled="!!busy || !!editBusy" @click="revisionPanelOpen = !revisionPanelOpen">版本历史 {{ shotRevisions.length }}</button>
            <button v-if="selectedEpisode.shot_count" class="ghost-button" :disabled="!!busy || !!editBusy" @click="shotEditorOpen = !shotEditorOpen">{{ shotEditorOpen ? '关闭修正' : '修正镜头' }}</button>
            <button class="ghost-button" :disabled="!!busy || !!editBusy" @click="analyzeSingle(selectedEpisode)">{{ selectedEpisode.shot_count ? '重新自动拉片' : '单独拉片' }}</button>
          </div>
        </div>

        <div v-if="currentShotRevision" class="shot-revision-current">
          <div><span>CURRENT</span><strong>R{{ currentShotRevision.revision }} · {{ revisionKind(currentShotRevision.kind) }}</strong><small>{{ currentShotRevision.shot_count }} Shots · {{ currentShotRevision.note || '当前生产版本' }}</small></div>
          <button class="ghost-button" @click="revisionPanelOpen = !revisionPanelOpen">{{ revisionPanelOpen ? '收起历史' : '查看历史' }}</button>
        </div>

        <div v-if="revisionPanelOpen && shotRevisions.length" class="shot-revision-history">
          <div class="shot-revision-heading"><strong>Shot Revision 历史</strong><span>历史版本只读；恢复会生成新的 RESTORE Revision。</span></div>
          <div class="shot-revision-list">
            <div v-for="revision in shotRevisions" :key="revision.id" :class="['shot-revision-row', { current: revision.is_current }]">
              <div class="shot-revision-number">R{{ revision.revision }}</div>
              <div class="shot-revision-copy"><strong>{{ revisionKind(revision.kind) }}</strong><small>{{ revision.shot_count }} Shots · {{ revision.note || '—' }}</small></div>
              <span :class="['status-pill', revision.is_current ? 'ready' : 'planned']">{{ revision.is_current ? 'CURRENT' : 'HISTORY' }}</span>
              <button v-if="!revision.is_current" class="ghost-button" :disabled="!!editBusy || !!busy" @click="restoreRevision(revision)">恢复为新版本</button>
            </div>
          </div>
        </div>

        <div v-if="shots.length === 0" class="empty-state large"><strong>当前剧集还没有 Shot</strong><span>直接执行拉片即可；Proxy / Audio 会自动准备。</span></div>
        <div v-else-if="!shotEditorOpen" class="shot-result-summary">
          <div :class="['shot-summary-icon', suspiciousShotCount ? 'warning' : 'ready']">{{ suspiciousShotCount ? '!' : '✓' }}</div>
          <div><strong>{{ suspiciousShotCount ? `有 ${suspiciousShotCount} 个短镜头建议看一下` : '拉片已完成，无需逐镜确认' }}</strong><p>Shot 结果已经可以供后续资产分析使用。只有肉眼发现 Cut 有问题时才进入人工修正。</p></div>
          <button class="primary-button" @click="shotEditorOpen = true">修正镜头</button>
        </div>
        <div v-else class="shot-layout">
          <div class="shot-grid">
            <button v-for="shot in shots" :key="shot.id" :class="['shot-card', { active: selectedShot?.id === shot.id, warning: shot.duration_us < 500000 }]" @click="selectShot(shot)">
              <img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" :alt="`Shot ${shot.ordinal}`" />
              <div class="shot-card-copy"><strong>SHOT {{ String(shot.ordinal).padStart(4, '0') }}</strong><span>{{ seconds(shot.duration_us) }}</span><em v-if="shot.duration_us < 500000">短镜头</em></div>
            </button>
          </div>
          <aside v-if="selectedShot" class="shot-preview shot-editor-inspector">
            <video ref="shotVideoRef" :key="`${selectedShot.id}-${selectedShot.start_us}-${selectedShot.end_us}`" :src="shotMediaUrl(selectedShot.reference_url)" controls preload="metadata"></video>
            <div class="preview-heading"><strong>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</strong><span>{{ seconds(selectedShot.duration_us) }}</span></div>
            <div class="shot-boundary-editor">
              <label><span>Source Start</span><input v-model.number="startBoundarySeconds" type="number" step="0.001" min="0" /></label>
              <button class="ghost-button" :disabled="selectedShotIndex <= 0 || !!editBusy" @click="saveStartBoundary">保存开始边界</button>
              <label><span>Source End</span><input v-model.number="endBoundarySeconds" type="number" step="0.001" min="0" /></label>
              <button class="ghost-button" :disabled="selectedShotIndex >= shots.length - 1 || !!editBusy" @click="saveEndBoundary">保存结束边界</button>
            </div>
            <div class="shot-edit-actions">
              <button class="ghost-button" :disabled="selectedShotIndex <= 0 || !!editBusy" @click="mergePrevious">合并上一镜</button>
              <button class="primary-button" :disabled="!!editBusy" @click="splitAtPlayhead">在播放头拆分</button>
              <button class="ghost-button" :disabled="selectedShotIndex >= shots.length - 1 || !!editBusy" @click="mergeNext">合并下一镜</button>
            </div>
            <div class="architecture-note compact"><strong>每次修正都会产生新版本</strong><p>旧 Shot Timeline 和历史 Reference Clip 不覆盖；修改后已有资产 Evidence 会标记为 STALE。</p></div>
          </aside>
        </div>
      </section>

      <section v-else-if="activeStage === 3" class="workspace-panel f05-workspace asset-workspace">
        <div class="section-title asset-title">
          <div><span>03</span><h2>资产</h2></div>
          <div class="section-actions">
            <button v-if="!f05Models?.ready" class="ghost-button" :disabled="!!busy" @click="prepareModels">准备人物模型</button>
            <button class="primary-button" :disabled="!episodes.length || !!busy" @click="analyzeContent">{{ contentRun ? '重新提取资产' : '开始提取资产' }}</button>
          </div>
        </div>
        <p class="section-help asset-help">后台从每个 Shot 提取人物 / 场景 / 道具 Evidence。当前页面先用于检查绑定；人工合并、拆分、改名和 Shot Binding 修改会继续接到这里。</p>

        <div v-if="contentRun?.status === 'STALE'" class="asset-warning"><div><strong>Shot Current Revision 已变化，当前资产结果已过期</strong><span>旧 Evidence 仍保留用于对照，但重新提取后才可作为当前资产结果。</span></div><button class="primary-button" :disabled="!!busy" @click="analyzeContent">重新提取资产</button></div>
        <div v-if="hiddenBodyOnlyCandidates > 0" class="asset-warning"><div><strong>当前旧 Run 含 {{ hiddenBodyOnlyCandidates }} 个无 Face/SFace 身份锚点的 body-only 候选</strong><span>这些候选已从正式人物列表隐藏。旧算法会把花、衣服、背景纹理等 HOG 误检当成人物。</span></div><button class="primary-button" :disabled="!!busy" @click="analyzeContent">使用新人物策略重跑</button></div>

        <div v-if="!contentRun" class="empty-state large asset-empty"><strong>还没有资产提取结果</strong><span>完成拉片后，从这里顺序分析各集 Shot，并建立人物 / 场景 / 道具 Evidence。</span></div>
        <template v-else>
          <div class="analysis-run-bar asset-run-bar"><div><strong>{{ contentRun.status }}</strong><span>Run {{ contentRun.id.slice(-10) }} · {{ contentRun.profile_version }}</span></div><div class="analysis-counts"><span>{{ reliableCharacters.length }} 人物</span><span>{{ orderedScenes.length }} 场景候选</span><span>{{ contentRun.props.length }} 道具</span></div></div>
          <div class="asset-status-strip"><div><span>人物</span><strong :class="['status-text', componentClass('characters')]">{{ componentText('characters') }}</strong><small>{{ reliableCharacters.length }} 个有身份锚点候选</small></div><div><span>场景</span><strong :class="['status-text', componentClass('scenes')]">{{ componentText('scenes') }}</strong><small>{{ orderedScenes.length }} 个视觉候选</small></div><div><span>道具</span><strong :class="['status-text', componentClass('props')]">{{ componentText('props') }}</strong><small>{{ contentRun.props.length }} 个候选</small></div></div>
          <div class="asset-view-tabs"><button :class="{ active: assetView === 'shot' }" @click="assetView = 'shot'">按 Shot 检查</button><button :class="{ active: assetView === 'characters' }" @click="assetView = 'characters'">人物库 {{ reliableCharacters.length }}</button><button :class="{ active: assetView === 'scenes' }" @click="assetView = 'scenes'">场景库 {{ orderedScenes.length }}</button><button :class="{ active: assetView === 'props' }" @click="assetView = 'props'">道具库 {{ contentRun.props.length }}</button></div>

          <div v-if="assetView === 'shot'" class="asset-manager-grid">
            <aside class="asset-episode-panel"><div class="asset-panel-heading"><div><span>EPISODES</span><strong>剧集</strong></div><b>{{ episodes.length }}</b></div><div class="asset-episode-list"><button v-for="episode in episodes" :key="episode.id" :class="{ active: selectedEpisodeId === episode.id }" @click="chooseEpisode(episode.id)"><span class="asset-episode-index">E{{ String(episode.sort_order).padStart(2, '0') }}</span><span class="asset-episode-copy"><strong>{{ episode.title }}</strong><small>{{ episode.shot_count }} Shots</small></span><i :class="episode.shot_count ? 'ready' : ''"></i></button></div></aside>
            <main class="asset-shot-panel"><div class="asset-panel-heading asset-shot-heading"><div><span>SHOT BROWSER</span><strong>{{ selectedEpisode?.title || '请选择剧集' }}</strong></div><b>{{ shots.length }} Shots</b></div><div v-if="shots.length === 0" class="asset-panel-empty"><strong>当前剧集没有 Shot</strong><span>请先完成拉片。</span></div><div v-else class="asset-shot-list"><button v-for="shot in shots" :key="shot.id" :class="{ active: selectedShot?.id === shot.id }" @click="selectShot(shot)"><img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" alt="" /><span v-else class="asset-shot-thumb-empty">SHOT</span><span class="asset-shot-copy"><strong>SHOT {{ String(shot.ordinal).padStart(4, '0') }}</strong><small>{{ seconds(shot.start_us) }} → {{ seconds(shot.end_us) }} · {{ seconds(shot.duration_us) }}</small><span class="asset-shot-badges"><em>{{ charactersForShot(shot.id).length }} 人物</em><em>{{ scenesForShot(shot.id).length ? scenesForShot(shot.id)[0].auto_label : '场景待定' }}</em><em>道具 {{ contentRun?.props.length ? '待绑定' : '0' }}</em></span></span></button></div></main>
            <aside v-if="selectedShot" class="asset-inspector"><div class="asset-inspector-head"><div><span>SHOT INSPECTOR</span><strong>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</strong></div><b>AI EVIDENCE</b></div><video :key="`${selectedShot.id}-${selectedShot.start_us}-${selectedShot.end_us}`" :src="shotMediaUrl(selectedShot.reference_url)" controls preload="metadata"></video><div class="asset-inspector-meta"><span>{{ seconds(selectedShot.start_us) }} → {{ seconds(selectedShot.end_us) }}</span><span>{{ seconds(selectedShot.duration_us) }}</span></div>
              <section class="asset-binding-section"><div class="asset-binding-title"><strong>人物</strong><span>{{ shotCharacters.length }}</span></div><div v-if="shotCharacters.length" class="asset-binding-list"><div v-for="character in shotCharacters" :key="character.id" class="asset-binding-row"><img v-if="character.cover_url" :src="character.cover_url" alt="" /><span v-else class="asset-mini-placeholder">人</span><div><strong>{{ character.auto_label }}</strong><small>{{ character.shot_count }} Shots · {{ character.track_count }} Tracks</small></div><b>AUTO</b></div></div><div v-else class="asset-binding-empty">当前 Shot 没有可信人物身份 Evidence</div></section>
              <section class="asset-binding-section"><div class="asset-binding-title"><strong>场景</strong><span>{{ shotScenes.length }}</span></div><div v-if="selectedShotScene" class="asset-scene-binding"><img v-if="selectedShotScene.cover_url" :src="selectedShotScene.cover_url" alt="" /><div><strong>{{ selectedShotScene.auto_label }}</strong><small>{{ selectedShotScene.shot_count }} Shots · AI 候选场景</small></div></div><div v-else class="asset-binding-empty">当前 Shot 尚未归入场景候选</div></section>
              <section class="asset-binding-section"><div class="asset-binding-title"><strong>关键道具</strong><span>{{ contentRun.props.length }}</span></div><div class="asset-binding-empty">对象模型尚未配置时不伪造剧情道具。</div></section>
              <div class="asset-manual-note"><strong>人工修正层</strong><p>这里已经按 Shot 组织 Evidence。下一步接入添加/移除人物、修改场景、绑定道具，不覆盖 AI 原始证据。</p></div>
            </aside>
          </div>

          <div v-else-if="assetView === 'characters'" class="asset-library-list"><div v-if="reliableCharacters.length === 0" class="asset-panel-empty"><strong>没有可信人物候选</strong><span>人物身份必须拥有 Face/SFace 锚点；请重新提取资产。</span></div><article v-for="character in reliableCharacters" :key="character.id" class="asset-library-row"><img v-if="character.cover_url" :src="character.cover_url" alt="" /><span v-else class="asset-library-placeholder">人</span><div class="asset-library-copy"><strong>{{ character.auto_label }}</strong><small>{{ character.shot_count }} Shots · {{ character.track_count }} Tracks</small></div><div class="asset-library-metrics"><span>Face Anchor</span><strong>{{ character.confidence === null ? '单独候选' : character.confidence.toFixed(3) }}</strong></div><span class="status-pill ready">AUTO EVIDENCE</span></article></div>
          <div v-else-if="assetView === 'scenes'" class="asset-library-list"><div v-if="orderedScenes.length === 0" class="asset-panel-empty"><strong>没有场景候选</strong><span>请重新执行资产提取。</span></div><article v-for="scene in orderedScenes" :key="scene.id" class="asset-library-row scene-row"><img v-if="scene.cover_url" :src="scene.cover_url" alt="" /><span v-else class="asset-library-placeholder">景</span><div class="asset-library-copy"><strong>{{ scene.auto_label }}</strong><small>{{ scene.shot_count }} Shots</small></div><div class="asset-library-metrics"><span>类型</span><strong>AI 候选</strong></div><span class="status-pill planned">待人工命名 / 合并</span></article></div>
          <div v-else class="asset-panel-empty asset-prop-empty"><strong>关键道具模型尚未配置</strong><span>道具必须是剧情重要或重制时需要保持一致的对象。没有可靠模型时不把普通环境物体伪装成正式资产。</span></div>
        </template>
      </section>

      <section v-else class="workspace-panel planned-panel">
        <div class="planned-icon">{{ stages[activeStage - 1][0] }}</div><h2>{{ stages[activeStage - 1][1] }}</h2><p>{{ stages[activeStage - 1][2] }}</p><span class="status-pill planned">待开发</span><div class="architecture-note"><strong>只在高风险结果停下来</strong><p>Whisper、OCR、VLM、SAM、Camera Motion 等自动能力都在后台执行；页面只开放真正需要人工决策和修改的业务结果。</p></div>
      </section>
    </main>
  </div>
</template>
