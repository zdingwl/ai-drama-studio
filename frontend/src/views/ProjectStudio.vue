<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import type { Episode, Project, Shot } from '../types/studio'

const route = useRoute()
const router = useRouter()
const projectId = String(route.params.projectId)
const project = ref<Project | null>(null)
const activeStage = ref(2)
const loading = ref(true)
const busy = ref('')
const error = ref('')
const draggedId = ref<string | null>(null)
const selectedEpisodeId = ref('')
const shots = ref<Shot[]>([])
const selectedShot = ref<Shot | null>(null)

const stages = [
  ['F01', '项目设置', '项目语言与目标市场'],
  ['F02', '剧集管理', '批量导入与顺序'],
  ['F03', '视频预处理', 'Proxy / Audio / Media Info'],
  ['F04', '自动拉片', 'Shot + Reference Clip'],
  ['F05', '智能内容识别', '人物 / 场景 / 道具 / 台词'],
  ['F06', '拉片审核', '人工修正与绑定'],
  ['F07', '替换素材', '人物 / 场景 / 道具资产'],
  ['F08', '本地化与声音', '翻译 / Voice / TTS'],
  ['F09', '重制任务规划', '按镜头选择处理策略'],
  ['F10', '视频重制', 'Reference Video 生成'],
  ['F11', '弹性时间轴', '重新计算整集 Timeline'],
  ['F12', '质量检查', '失败 Shot 与自动 QC'],
  ['F13', '导出', '视频 / 字幕 / 数据'],
]

const episodes = computed(() => project.value?.episodes ?? [])
const selectedEpisode = computed(() => episodes.value.find((item) => item.id === selectedEpisodeId.value) ?? null)

function seconds(us: number | null) {
  if (!us) return '—'
  return `${(us / 1_000_000).toFixed(2)}s`
}

async function reloadProject() {
  project.value = await api.getProject(projectId)
  if (!selectedEpisodeId.value && project.value.episodes.length) selectedEpisodeId.value = project.value.episodes[0].id
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
  if (!window.confirm(`删除「${episode.title}」及其预处理和拉片结果？`)) return
  await run('正在删除剧集', () => api.deleteEpisode(episode.id), async () => {
    if (selectedEpisodeId.value === episode.id) {
      selectedEpisodeId.value = project.value?.episodes[0]?.id ?? ''
      shots.value = []
      selectedShot.value = null
    }
  })
}

async function loadShots(episodeId = selectedEpisodeId.value) {
  if (!episodeId) {
    shots.value = []
    selectedShot.value = null
    return
  }
  shots.value = await api.listShots(episodeId)
  selectedShot.value = shots.value[0] ?? null
}

async function chooseEpisode(episodeId: string) {
  selectedEpisodeId.value = episodeId
  await loadShots(episodeId)
}

async function analyzeSingle(episode: Episode) {
  selectedEpisodeId.value = episode.id
  await run('正在自动拉片', () => api.analyzeEpisodeShots(episode.id), () => loadShots(episode.id))
}

function stageReady(index: number) { return index <= 4 }

onMounted(async () => {
  try {
    await reloadProject()
    await loadShots()
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
      <div v-if="busy" class="busy-banner"><span class="spinner"></span>{{ busy }}，按顺序处理，请不要重复点击。</div>

      <section v-if="activeStage === 1" class="workspace-panel">
        <div class="section-title"><div><span>F01</span><h2>项目基础信息</h2></div><span class="status-pill ready">已建立</span></div>
        <div class="info-grid">
          <div><span>项目名称</span><strong>{{ project.name }}</strong></div>
          <div><span>原项目语言</span><strong>{{ project.source_language }}</strong></div>
          <div><span>目标语言</span><strong>{{ project.target_language }}</strong></div>
          <div><span>目标地区</span><strong>{{ project.target_region }}</strong></div>
        </div>
        <div class="architecture-note"><strong>V2 规则</strong><p>项目只保存本地化目标；视频不再绑定在 Project 上，而是作为多个 Episode 独立存在。</p></div>
      </section>

      <section v-else-if="activeStage === 2" class="workspace-panel">
        <div class="section-title">
          <div><span>F02</span><h2>剧集导入与排序</h2></div>
          <label class="primary-button file-button">导入多个视频<input type="file" multiple accept="video/*" @change="uploadFiles" /></label>
        </div>
        <p class="section-help">批量导入后可直接拖动调整剧集顺序。后续“批量处理”始终按照这里的顺序逐集执行，不会并行跑多个视频。</p>
        <div v-if="episodes.length === 0" class="empty-state large"><strong>还没有剧集</strong><span>一次选择多个视频导入即可。</span></div>
        <div v-else class="episode-list">
          <div v-for="episode in episodes" :key="episode.id" class="episode-row" draggable="true" @dragstart="dragStart(episode.id)" @dragover.prevent @drop="dropOn(episode.id)">
            <div class="drag-handle">⋮⋮</div>
            <div class="episode-index">{{ String(episode.sort_order).padStart(2, '0') }}</div>
            <div class="episode-main"><strong>{{ episode.title }}</strong><small>{{ episode.original_filename }}</small></div>
            <div class="episode-meta"><span>{{ seconds(episode.duration_us) }}</span><span>{{ episode.preprocess_status || '未预处理' }}</span><span>{{ episode.shot_count }} Shots</span></div>
            <button class="danger-text" @click="removeEpisode(episode)">删除</button>
          </div>
        </div>
      </section>

      <section v-else-if="activeStage === 3" class="workspace-panel">
        <div class="section-title"><div><span>F03</span><h2>视频预处理</h2></div><button class="primary-button" :disabled="!episodes.length || !!busy" @click="run('正在顺序批量预处理', () => api.preprocessBatch(projectId))">顺序批量预处理</button></div>
        <p class="section-help">为每集生成标准化 Proxy、独立 Audio 和媒体信息。批量模式严格按 F02 的顺序一集一集处理。</p>
        <div class="task-table">
          <div v-for="episode in episodes" :key="episode.id" class="task-row">
            <div><strong>第 {{ episode.sort_order }} 集 · {{ episode.title }}</strong><small>{{ episode.width || '—' }}×{{ episode.height || '—' }} · {{ episode.fps?.toFixed(2) || '—' }} fps</small></div>
            <span :class="['status-pill', episode.preprocess_status === 'READY' ? 'ready' : 'planned']">{{ episode.preprocess_status || '未处理' }}</span>
            <button class="ghost-button" :disabled="!!busy" @click="run('正在预处理单集', () => api.preprocessEpisode(episode.id))">单独处理</button>
          </div>
        </div>
      </section>

      <section v-else-if="activeStage === 4" class="workspace-panel shots-workspace">
        <div class="section-title"><div><span>F04</span><h2>Shot + Reference Clip</h2></div><button class="primary-button" :disabled="!episodes.length || !!busy" @click="run('正在按顺序批量拉片', () => api.analyzeBatchShots(projectId), loadShots)">顺序批量拉片</button></div>
        <p class="section-help">这里不做“大而全文字拉片”。核心产物是准确 Shot 边界和每个镜头独立的 Reference Video，后续识别与重制都绑定 Shot。</p>
        <div class="episode-tabs"><button v-for="episode in episodes" :key="episode.id" :class="{ active: selectedEpisodeId === episode.id }" @click="chooseEpisode(episode.id)">E{{ String(episode.sort_order).padStart(2, '0') }} · {{ episode.shot_count }} Shots</button></div>
        <div v-if="selectedEpisode" class="shot-action-bar"><div><strong>{{ selectedEpisode.title }}</strong><span>{{ selectedEpisode.preprocess_status === 'READY' ? '已具备拉片条件' : '请先完成 F03' }}</span></div><button class="ghost-button" :disabled="selectedEpisode.preprocess_status !== 'READY' || !!busy" @click="analyzeSingle(selectedEpisode)">单独拉片 / 重新拉片</button></div>
        <div v-if="shots.length === 0" class="empty-state large"><strong>当前剧集还没有 Shot</strong><span>完成预处理后执行自动拉片。</span></div>
        <div v-else class="shot-layout">
          <div class="shot-grid">
            <button v-for="shot in shots" :key="shot.id" :class="['shot-card', { active: selectedShot?.id === shot.id }]" @click="selectedShot = shot">
              <img v-if="shot.thumbnail_url" :src="shot.thumbnail_url" :alt="`Shot ${shot.ordinal}`" />
              <div class="shot-card-copy"><strong>SHOT {{ String(shot.ordinal).padStart(4, '0') }}</strong><span>{{ seconds(shot.duration_us) }}</span></div>
            </button>
          </div>
          <aside v-if="selectedShot" class="shot-preview">
            <video :key="selectedShot.id" :src="selectedShot.reference_url" controls preload="metadata"></video>
            <div class="preview-heading"><strong>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</strong><span>{{ seconds(selectedShot.duration_us) }}</span></div>
            <div class="preview-meta">
              <div><span>Source Start</span><strong>{{ seconds(selectedShot.start_us) }}</strong></div><div><span>Source End</span><strong>{{ seconds(selectedShot.end_us) }}</strong></div><div><span>Reference</span><strong>正式资产</strong></div><div><span>状态</span><strong>{{ selectedShot.status }}</strong></div>
            </div>
            <div class="architecture-note compact"><strong>后续 F05</strong><p>人物、Scene、关键道具、Dialogue、Track/Mask 会绑定到这个 Shot，而不是把动作和机位重新写成冗长文字。</p></div>
          </aside>
        </div>
      </section>

      <section v-else class="workspace-panel planned-panel">
        <div class="planned-icon">{{ stages[activeStage - 1][0] }}</div>
        <h2>{{ stages[activeStage - 1][1] }}</h2>
        <p>{{ stages[activeStage - 1][2] }}</p>
        <span class="status-pill planned">待开发</span>
        <div class="architecture-note"><strong>已经锁定接口边界</strong><p>后端 V2 数据库已经预留 Character、Scene、Prop、Dialogue、Asset、Voice、Generation 等核心实体。该阶段会在 F04 数据验收后继续实现，不使用旧版功能冒充完成。</p></div>
      </section>
    </main>
  </div>
</template>
