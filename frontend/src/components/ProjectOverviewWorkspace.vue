<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getEpisodeShotBoundary, getProject, listProjectEpisodes } from '@/features/projects/api'
import { getGenerationSelection, type GenerationSelectionRead } from '@/features/projects/production'
import {
  getAssetImages,
  getH3Prompts,
  getLocalizedStoryboard,
  type AssetImagesRead,
  type H3PromptsRead,
  type LocalizedStoryboardRead,
  type PipelineResultStatus,
} from '@/features/projects/replicaFiveStep'
import { getSourceAnalysisStatus, type SourceAnalysisStatusRead } from '@/features/projects/sourceAnalysis'
import {
  LANGUAGE_OPTIONS,
  REGION_OPTIONS,
  projectTypeLabel,
  type EpisodeRead,
  type EpisodeShotBoundaryRead,
  type ProjectRead,
} from '@/features/projects/types'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.id ?? ''))

const project = ref<ProjectRead | null>(null)
const episodes = ref<EpisodeRead[]>([])
const boundaries = ref<Record<string, EpisodeShotBoundaryRead | null>>({})
const sourceStatus = ref<SourceAnalysisStatusRead | null>(null)
const localized = ref<LocalizedStoryboardRead | null>(null)
const assets = ref<AssetImagesRead | null>(null)
const prompts = ref<H3PromptsRead | null>(null)
const selection = ref<GenerationSelectionRead | null>(null)
const loading = ref(true)
const error = ref('')

const sourceStageStatus = computed<PipelineResultStatus>(() => {
  if (sourceStatus.value?.state === 'NEEDS_REFRESH') return 'STALE'
  if (sourceStatus.value?.state !== 'READY') return 'NOT_BUILT'
  if (!episodes.value.length) return 'NOT_BUILT'
  return episodes.value.every(item => boundaries.value[item.id]?.status === 'CURRENT') ? 'CURRENT' : 'NOT_BUILT'
})
const stageRows = computed(() => [
  { id: 'source', number: 1, label: '原片分镜', hint: '分析视频，确认镜头、画面与对白', status: sourceStageStatus.value },
  { id: 'localize', number: 2, label: '本土化分镜', hint: '中文审核描述与目标语言对白', status: localized.value?.status ?? 'NOT_BUILT' },
  { id: 'assets', number: 3, label: '视觉资产', hint: '人物、场景、道具参考图', status: assets.value?.status ?? 'NOT_BUILT' },
  { id: 'prompts', number: 4, label: 'H3 提示词', hint: '多参考图音画生成提示词', status: prompts.value?.status ?? 'NOT_BUILT' },
  { id: 'generation', number: 5, label: '视频生成', hint: '生成、技术 QC 与人工审核', status: selection.value?.status ?? 'NOT_BUILT' },
])
const totalDurationUs = computed(() => episodes.value.reduce((sum, item) => sum + item.duration_us, 0))
const totalShots = computed(() => episodes.value.reduce((sum, item) => sum + (boundaries.value[item.id]?.shot_count ?? 0), 0))
const completedStages = computed(() => stageRows.value.filter(item => item.status === 'CURRENT').length)
const targetLanguage = computed(() => LANGUAGE_OPTIONS.find(item => item.value === project.value?.target_language)?.label ?? project.value?.target_language ?? '—')
const targetRegion = computed(() => REGION_OPTIONS.find(item => item.value === project.value?.target_region)?.label ?? project.value?.target_region ?? '—')

function duration(us: number) {
  const seconds = Math.max(0, Math.round(us / 1_000_000))
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}
function stageText(status: PipelineResultStatus) {
  if (status === 'CURRENT') return '已完成'
  if (status === 'STALE') return '需更新'
  return '未开始'
}
function episodeQuery(episode?: EpisodeRead) {
  const selected = episode ?? episodes.value[0]
  return selected ? { episode: selected.id, ep: String(selected.episode_order) } : {}
}
function openStage(id: string, episode?: EpisodeRead) {
  void router.push({ path: `/projects/${projectId.value}/${id}`, query: episodeQuery(episode) })
}
function openEpisodes() { void router.push({ path: `/projects/${projectId.value}/episodes` }) }

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [projectResult, episodeRows] = await Promise.all([getProject(projectId.value), listProjectEpisodes(projectId.value)])
    project.value = projectResult
    episodes.value = [...episodeRows].sort((a, b) => a.episode_order - b.episode_order)
    const boundaryRows = await Promise.all(episodes.value.map(async episode => {
      try { return [episode.id, await getEpisodeShotBoundary(projectId.value, episode.id)] as const }
      catch { return [episode.id, null] as const }
    }))
    boundaries.value = Object.fromEntries(boundaryRows)
    const [sourceResult, localizedResult, assetResult, promptResult, selectionResult] = await Promise.all([
      getSourceAnalysisStatus(projectId.value).catch(() => null),
      getLocalizedStoryboard(projectId.value).catch(() => null),
      getAssetImages(projectId.value).catch(() => null),
      getH3Prompts(projectId.value).catch(() => null),
      getGenerationSelection(projectId.value).catch(() => null),
    ])
    sourceStatus.value = sourceResult
    localized.value = localizedResult
    assets.value = assetResult
    prompts.value = promptResult
    selection.value = selectionResult
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '项目概览读取失败'
  } finally { loading.value = false }
}

onMounted(() => { void load() })
</script>

<template>
  <section class="overview" data-testid="project-overview-workspace">
    <div v-if="loading" class="state-box">正在读取项目概览…</div>
    <p v-else-if="error" class="state-box error">{{ error }}</p>
    <template v-else-if="project">
      <header class="overview-hero">
        <div><p class="eyebrow">项目概览</p><h2>{{ project.name }}</h2><p>查看项目整体进度、剧集状态和五步制作链，选择一集即可继续制作。</p></div>
        <button type="button" @click="openEpisodes">管理剧集</button>
      </header>

      <div class="summary-grid">
        <article><span>项目类型</span><strong>{{ projectTypeLabel(project.project_type) }}</strong><small>{{ project.status === 'ACTIVE' ? '进行中' : '已归档' }}</small></article>
        <article><span>剧集</span><strong>{{ episodes.length }}</strong><small>总时长 {{ duration(totalDurationUs) }}</small></article>
        <article><span>已识别镜头</span><strong>{{ totalShots }}</strong><small>{{ episodes.filter(item => boundaries[item.id]?.status === 'CURRENT').length }} / {{ episodes.length }} 集完成原片分析</small></article>
        <article><span>制作进度</span><strong>{{ completedStages }} / 5</strong><small>按当前正式结果统计</small></article>
      </div>

      <div class="overview-grid">
        <section class="panel production-panel">
          <div class="panel-heading"><div><span>制作流程</span><h3>五步生产链</h3></div><small>点击进入对应工作区</small></div>
          <button v-for="stage in stageRows" :key="stage.id" type="button" class="stage-row" @click="openStage(stage.id)">
            <span class="stage-number">{{ stage.number }}</span><span class="stage-copy"><strong>{{ stage.label }}</strong><small>{{ stage.hint }}</small></span><span class="stage-state" :class="stage.status.toLowerCase()">{{ stageText(stage.status) }}</span><b>›</b>
          </button>
        </section>
        <section class="panel project-info">
          <div class="panel-heading"><div><span>项目设置</span><h3>本土化目标</h3></div></div>
          <dl><dt>源语言</dt><dd>{{ LANGUAGE_OPTIONS.find(item => item.value === project?.source_language)?.label ?? project.source_language ?? '自动识别' }}</dd><dt>目标语言</dt><dd>{{ targetLanguage }}</dd><dt>目标地区</dt><dd>{{ targetRegion }}</dd><dt>场景策略</dt><dd>{{ project.scene_strategy === 'KEEP' ? '保留原场景' : project.scene_strategy === 'LOCALIZE' ? '本土化场景' : '混合策略' }}</dd><dt>视觉风格</dt><dd>{{ project.visual_style || '写实电影感' }}</dd></dl>
        </section>
      </div>

      <section class="panel episode-panel">
        <div class="panel-heading"><div><span>剧集进度</span><h3>{{ episodes.length ? `${episodes.length} 集` : '还没有剧集' }}</h3></div><button type="button" class="text-button" @click="openEpisodes">查看全部剧集 →</button></div>
        <div v-if="episodes.length" class="episode-grid">
          <article v-for="episode in episodes" :key="episode.id" class="episode-card">
            <div class="episode-top"><span>第 {{ episode.episode_order }} 集</span><em :class="boundaries[episode.id]?.status === 'CURRENT' ? 'ready' : ''">{{ boundaries[episode.id]?.status === 'CURRENT' ? '原片已分析' : '待分析' }}</em></div>
            <strong :title="episode.source_asset.original_filename">{{ episode.source_asset.original_filename.replace(/\.[^.]+$/, '') }}</strong><small>{{ boundaries[episode.id]?.shot_count ?? 0 }} 镜 · {{ duration(episode.duration_us) }} · {{ episode.width }}×{{ episode.height }}</small><button type="button" @click="openStage('source', episode)">进入本集制作 →</button>
          </article>
        </div>
        <div v-else class="empty">先到“剧集管理”上传完整 Episode 视频。</div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.overview{display:grid;gap:14px;min-width:0;color:#263653}.overview-hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 24px;border:1px solid #e1e4ec;border-radius:14px;background:linear-gradient(135deg,#fff 0%,#f8f7ff 100%)}.overview-hero h2{margin:3px 0 6px;color:#17294a;font-size:26px;letter-spacing:-.025em}.overview-hero p:last-child{margin:0;color:#758198;font-size:12px}.eyebrow{margin:0;color:#6552e8;font-size:10px;font-weight:850;letter-spacing:.08em}.overview-hero>button,.episode-card button{min-height:38px;padding:0 15px;border:0;border-radius:9px;background:#6552e8;color:#fff;font-size:11px;font-weight:800;cursor:pointer}.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.summary-grid article{display:grid;gap:3px;padding:15px 17px;border:1px solid #e4e6ed;border-radius:12px;background:#fff}.summary-grid span{color:#8791a3;font-size:10px}.summary-grid strong{color:#1e3153;font-size:22px}.summary-grid small{color:#7b879b;font-size:9px;line-height:1.45}.overview-grid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(300px,.7fr);gap:12px}.panel{border:1px solid #e3e5ec;border-radius:13px;background:#fff;overflow:hidden}.panel-heading{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:14px 16px;border-bottom:1px solid #eceef3}.panel-heading span{color:#8b95a7;font-size:9px;font-weight:800}.panel-heading h3{margin:2px 0 0;color:#213454;font-size:15px}.panel-heading>small{color:#9aa3b2;font-size:9px}.stage-row{display:grid;grid-template-columns:34px minmax(0,1fr) auto 18px;align-items:center;gap:11px;width:100%;padding:10px 14px;border:0;border-bottom:1px solid #f0f1f5;background:#fff;color:#344562;text-align:left;cursor:pointer}.stage-row:last-child{border-bottom:0}.stage-row:hover{background:#faf9ff}.stage-number{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:#f0eff8;color:#6256b7;font-size:10px;font-weight:850}.stage-copy{display:grid;gap:2px}.stage-copy strong{font-size:11px}.stage-copy small{color:#8a94a5;font-size:9px}.stage-state{padding:4px 7px;border-radius:999px;background:#f1f2f5;color:#737d8e;font-size:8px;font-weight:800}.stage-state.current{background:#eaf7ee;color:#2f7b46}.stage-state.stale{background:#fff2dd;color:#93631c}.stage-row>b{color:#a1a8b5;font-size:16px}.project-info dl{display:grid;grid-template-columns:76px minmax(0,1fr);gap:11px 12px;margin:0;padding:16px}.project-info dt{color:#8a94a4;font-size:10px}.project-info dd{margin:0;color:#344664;font-size:10px;line-height:1.45}.episode-panel{padding-bottom:14px}.text-button{border:0;background:transparent;color:#6552e8;font-size:10px;font-weight:800;cursor:pointer}.episode-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;padding:12px 14px 0}.episode-card{display:grid;gap:7px;padding:13px;border:1px solid #e5e7ee;border-radius:11px;background:#fbfcfe}.episode-top{display:flex;align-items:center;justify-content:space-between}.episode-top span{color:#5e4fe0;font-size:10px;font-weight:850}.episode-top em{padding:3px 6px;border-radius:999px;background:#f0f1f4;color:#7b8494;font-size:8px;font-style:normal}.episode-top em.ready{background:#e8f6ec;color:#34784a}.episode-card>strong{overflow:hidden;color:#273a59;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.episode-card>small{color:#8791a3;font-size:9px}.episode-card button{justify-self:start;min-height:31px;padding:0 10px;font-size:9px}.state-box,.empty{padding:26px;border:1px dashed #ccd2dd;border-radius:12px;background:#fff;color:#6d788c}.error{color:#a33b32}@media(max-width:1050px){.summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.overview-grid{grid-template-columns:1fr}}@media(max-width:620px){.overview-hero{align-items:stretch;flex-direction:column}.summary-grid{grid-template-columns:1fr 1fr}.episode-grid{grid-template-columns:1fr}.overview-hero>button{width:100%}}
</style>
