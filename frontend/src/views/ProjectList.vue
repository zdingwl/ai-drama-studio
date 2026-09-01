<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { breakdownApi } from '../api/breakdown'
import { localizationApi } from '../api/localization'
import { api } from '../api/client'
import type { BreakdownRunSummary } from '../types/breakdown'
import type { LocalizationDraftView } from '../types/localization'
import type { AssetWorkspace, BackgroundTask, ContentAnalysisRun, Episode, Project } from '../types/studio'
import { deriveStageStates, stageStateLabels, type StudioStageState } from '../utils/stageStatus'

interface ProjectOverview {
  states: Record<number, StudioStageState>
  overallLabel: string
  overallTone: string
  reviewCount: number
  activeTaskCount: number
  nextStage: number
  nextLabel: string
}

const router = useRouter()
const projects = ref<Project[]>([])
const overviews = reactive<Record<string, ProjectOverview>>({})
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const form = reactive({ name: '', source_language: 'zh-CN', target_language: 'en-US', target_region: 'US' })

const languageOptions = [
  ['zh-CN', '中文（简体）'], ['en-US', '英语'], ['ja-JP', '日语'], ['ko-KR', '韩语'], ['es-ES', '西班牙语'], ['pt-BR', '葡萄牙语'],
]
const regionOptions = [
  ['US', '美国'], ['GB', '英国'], ['CA', '加拿大'], ['AU', '澳大利亚'], ['JP', '日本'], ['KR', '韩国'], ['SG', '新加坡'], ['BR', '巴西'],
]
const stageNames: Record<number, string> = { 1: '源片', 2: '剧情与镜头', 3: '人物·场景·道具', 4: '本土化剧本' }

async function readBreakdownRuns(episodes: Episode[]): Promise<BreakdownRunSummary[]> {
  const results = await Promise.allSettled(episodes.map((episode) => breakdownApi.listRuns(episode.id)))
  return results.flatMap((result) => result.status === 'fulfilled' ? result.value : [])
}

async function readLocalizationDrafts(episodes: Episode[]): Promise<LocalizationDraftView[]> {
  const results = await Promise.allSettled(episodes.map((episode) => localizationApi.getCurrentDraft(episode.id)))
  return results.flatMap((result) => result.status === 'fulfilled' && result.value ? [result.value] : [])
}

function makeOverview(
  project: Project,
  tasks: BackgroundTask[],
  analysis: ContentAnalysisRun | null,
  breakdownRuns: BreakdownRunSummary[],
  workspace: AssetWorkspace | null,
  localizationDrafts: LocalizationDraftView[],
): ProjectOverview {
  const states = deriveStageStates({
    episodes: project.episodes,
    tasks,
    analysis,
    breakdownRuns,
    assetWorkspace: workspace,
    localizationDrafts,
  })
  const currentStates = [states[1], states[2], states[3], states[4]]
  const reviewCount = currentStates.filter((state) => state === 'review' || state === 'blocked').length
  const activeTaskCount = tasks.filter((task) => task.status === 'QUEUED' || task.status === 'PROCESSING').length

  let overallLabel = '进行中'
  let overallTone = 'active'
  if (!project.episodes.length) {
    overallLabel = '未开始'
    overallTone = 'idle'
  } else if (currentStates.includes('blocked')) {
    overallLabel = '存在阻塞'
    overallTone = 'blocked'
  } else if (currentStates.includes('processing')) {
    overallLabel = '处理中'
    overallTone = 'processing'
  } else if (currentStates.includes('review')) {
    overallLabel = '待复核'
    overallTone = 'review'
  } else if (currentStates.every((state) => state === 'completed')) {
    overallLabel = '当前流程完成'
    overallTone = 'completed'
  } else if (currentStates.includes('editing')) {
    overallLabel = '本土化编辑中'
  }

  if (!project.episodes.length) {
    return { states, overallLabel, overallTone, reviewCount, activeTaskCount, nextStage: 1, nextLabel: '导入源片' }
  }
  for (const stageId of [1, 2, 3, 4]) {
    const state = states[stageId]
    if (state === 'blocked') return { states, overallLabel, overallTone, reviewCount, activeTaskCount, nextStage: stageId, nextLabel: `处理${stageNames[stageId]}阻塞` }
    if (state === 'processing') return { states, overallLabel, overallTone, reviewCount, activeTaskCount, nextStage: stageId, nextLabel: `查看${stageNames[stageId]}进度` }
    if (state === 'review') return { states, overallLabel, overallTone, reviewCount, activeTaskCount, nextStage: stageId, nextLabel: `复核${stageNames[stageId]}` }
    if (state === 'editing') return { states, overallLabel, overallTone, reviewCount, activeTaskCount, nextStage: stageId, nextLabel: `继续${stageNames[stageId]}` }
    if (state === 'not_started') return { states, overallLabel, overallTone, reviewCount, activeTaskCount, nextStage: stageId, nextLabel: `开始${stageNames[stageId]}` }
  }
  return { states, overallLabel, overallTone, reviewCount, activeTaskCount, nextStage: 4, nextLabel: '查看本土化定稿' }
}

async function loadOverview(project: Project): Promise<void> {
  const [taskResult, analysisResult, runsResult, workspaceResult, localizationResult] = await Promise.allSettled([
    api.listProjectTasks(project.id, 30),
    api.getCurrentContentAnalysis(project.id),
    readBreakdownRuns(project.episodes),
    api.getAssetWorkspace(project.id),
    readLocalizationDrafts(project.episodes),
  ])
  const tasks = taskResult.status === 'fulfilled' ? taskResult.value : []
  const analysis = analysisResult.status === 'fulfilled' ? analysisResult.value : null
  const breakdownRuns = runsResult.status === 'fulfilled' ? runsResult.value : []
  const workspace = workspaceResult.status === 'fulfilled' ? workspaceResult.value : null
  const localizationDrafts = localizationResult.status === 'fulfilled' ? localizationResult.value : []
  overviews[project.id] = makeOverview(project, tasks, analysis, breakdownRuns, workspace, localizationDrafts)
}

async function loadProjects() {
  loading.value = true
  error.value = ''
  try {
    projects.value = await api.listProjects()
    loading.value = false
    await Promise.allSettled(projects.value.map((project) => loadOverview(project)))
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目列表读取失败'
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!form.name.trim()) return
  saving.value = true
  error.value = ''
  try {
    const project = await api.createProject({ ...form, name: form.name.trim() })
    await router.push(`/projects/${project.id}?stage=1`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目创建失败'
  } finally { saving.value = false }
}

function episodeSummary(project: Project) {
  const shots = project.episodes.reduce((sum, item) => sum + item.shot_count, 0)
  return `${project.episodes.length} 集 · ${shots} 个镜头`
}

function openProject(project: Project): void {
  const overview = overviews[project.id]
  const stage = overview?.nextStage ?? 1
  const query: Record<string, string> = { stage: String(stage) }

  if (stage === 2) {
    const episode = project.episodes.find((item) => item.shot_count > 0) ?? project.episodes[0]
    query.breakdown_view = project.episodes.some((item) => item.shot_count > 0) ? 'result' : 'shots'
    if (episode) query.episode = episode.id
  } else if (stage === 3) {
    query.asset_tab = 'inbox'
  } else if (stage === 4) {
    const episode = project.episodes[0]
    if (episode) query.episode = episode.id
  }

  void router.push({ path: `/projects/${project.id}`, query })
}

function stateLabel(projectId: string, stageId: number): string {
  const state = overviews[projectId]?.states[stageId]
  return state ? stageStateLabels[state] : '读取中'
}

onMounted(loadProjects)
</script>

<template>
  <main class="home-shell">
    <section class="home-hero home-hero-simple">
      <div>
        <div class="eyebrow">短剧本地化重制</div>
        <h1>从原片到可重制镜头</h1>
        <p>按顺序完成源片、剧情与镜头、人物场景道具、本土化剧本。首页会直接告诉你每个项目下一步该做什么。</p>
      </div>
    </section>

    <section class="home-grid">
      <div class="panel create-panel">
        <div class="panel-heading">
          <div><h2>新建项目</h2><p class="panel-subtitle">先确定原语言、目标语言和目标地区。</p></div>
        </div>
        <form class="project-form" @submit.prevent="submit">
          <label><span>项目名称</span><input v-model="form.name" placeholder="例如：霸总短剧 · 美国版" maxlength="200" /></label>
          <label><span>原项目语言</span><select v-model="form.source_language"><option v-for="item in languageOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <label><span>目标语言</span><select v-model="form.target_language"><option v-for="item in languageOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <label><span>目标地区</span><select v-model="form.target_region"><option v-for="item in regionOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <button class="primary-button" :disabled="saving || !form.name.trim()">{{ saving ? '正在创建…' : '创建并进入工作台' }}</button>
        </form>
        <p v-if="error" class="error-banner">{{ error }}</p>
      </div>

      <div class="panel projects-panel">
        <div class="panel-heading">
          <div><h2>项目进度</h2><p class="panel-subtitle">点击项目会直接进入当前最需要处理的位置。</p></div>
          <button class="ghost-button" @click="loadProjects">刷新</button>
        </div>
        <div v-if="loading" class="empty-state">正在读取项目…</div>
        <div v-else-if="projects.length === 0" class="empty-state"><strong>还没有项目</strong><span>从左侧创建第一个本地化重制项目。</span></div>
        <div v-else class="project-list project-dashboard-list">
          <button v-for="project in projects" :key="project.id" class="project-card project-dashboard-card" @click="openProject(project)">
            <div class="project-card-top">
              <strong>{{ project.name }}</strong>
              <span v-if="overviews[project.id]" :class="['project-overall-pill', `tone-${overviews[project.id].overallTone}`]">{{ overviews[project.id].overallLabel }}</span>
              <span v-else class="project-overall-pill">读取状态…</span>
            </div>
            <div class="project-locale">{{ project.source_language }} <span>→</span> {{ project.target_language }} · {{ project.target_region }}</div>

            <div class="project-stage-progress">
              <div v-for="stageId in [1, 2, 3, 4]" :key="stageId" :class="['project-stage-chip', `state-${overviews[project.id]?.states[stageId] || 'loading'}`]">
                <span>{{ String(stageId).padStart(2, '0') }}</span>
                <strong>{{ stageNames[stageId] }}</strong>
                <small>{{ stateLabel(project.id, stageId) }}</small>
              </div>
            </div>

            <div class="project-dashboard-footer">
              <span>{{ episodeSummary(project) }}</span>
              <span v-if="overviews[project.id]?.activeTaskCount" class="project-running-task">{{ overviews[project.id].activeTaskCount }} 个任务进行中</span>
              <span v-else-if="overviews[project.id]?.reviewCount" class="project-review-count">{{ overviews[project.id].reviewCount }} 个阶段待处理</span>
              <strong>{{ overviews[project.id]?.nextLabel || '读取下一步…' }} →</strong>
            </div>
          </button>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.home-hero-simple { align-items: flex-start; }
.home-hero-simple > div { max-width: 980px; }
.panel-heading > div { min-width: 0; }
.panel-subtitle { margin: 4px 0 0; color: #7c8798; font-size: 12px; }
.project-dashboard-card { display: grid; gap: 10px; }
.project-overall-pill {
  flex: none;
  min-height: 24px;
  display: inline-flex;
  align-items: center;
  padding: 0 8px;
  border-radius: 999px;
  background: #f0f2f5;
  color: #657185 !important;
  font-size: 10px !important;
  font-weight: 800;
}
.project-overall-pill.tone-processing { background: #edf2ff; color: #315ec4 !important; }
.project-overall-pill.tone-review { background: #fff5dc; color: #96630e !important; }
.project-overall-pill.tone-blocked { background: #fff0f1; color: #b33b3b !important; }
.project-overall-pill.tone-completed { background: #eaf8f2; color: #16835b !important; }
.project-stage-progress {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 7px;
  margin-top: 2px;
}
.project-stage-chip {
  min-width: 0;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  grid-template-rows: auto auto;
  column-gap: 6px;
  align-items: center;
  padding: 8px 9px;
  border: 1px solid #e5e9ef;
  border-radius: 9px;
  background: #fafbfc;
}
.project-stage-chip > span {
  grid-row: 1 / 3;
  color: #8793a4;
  font-size: 10px;
  font-weight: 850;
}
.project-stage-chip > strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #445164;
  font-size: 11px;
}
.project-stage-chip > small { color: #8a95a6; font-size: 9px; }
.project-stage-chip.state-processing { border-color: #cdd9f8; background: #f4f7ff; }
.project-stage-chip.state-processing > small { color: #315ec4; }
.project-stage-chip.state-editing { border-color: #d8cff5; background: #f8f5ff; }
.project-stage-chip.state-editing > small { color: #6f55c5; }
.project-stage-chip.state-review { border-color: #eedca7; background: #fffaf0; }
.project-stage-chip.state-review > small { color: #96630e; }
.project-stage-chip.state-blocked { border-color: #efcccc; background: #fff6f6; }
.project-stage-chip.state-blocked > small { color: #b33b3b; }
.project-stage-chip.state-completed { border-color: #cfe8dc; background: #f4fbf7; }
.project-stage-chip.state-completed > small { color: #16835b; }
.project-dashboard-footer {
  display: flex;
  align-items: center;
  gap: 9px;
  color: #7c8798;
  font-size: 10px;
}
.project-dashboard-footer > strong { margin-left: auto; color: #3156bd; font-size: 11px; }
.project-running-task,
.project-review-count { padding: 3px 6px; border-radius: 999px; font-weight: 750; }
.project-running-task { background: #edf2ff; color: #315ec4; }
.project-review-count { background: #fff5dc; color: #96630e; }
</style>
