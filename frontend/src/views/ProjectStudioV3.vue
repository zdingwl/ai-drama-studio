<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { breakdownApi } from '../api/breakdown'
import AssetStageV4 from '../components/AssetStageV4.vue'
import BreakdownStageV1 from '../components/BreakdownStageV1.vue'
import EpisodeManagerV3 from '../components/EpisodeManagerV3.vue'
import { api } from '../api/client'
import type { BreakdownRunSummary } from '../types/breakdown'
import type { BackgroundTask, ContentAnalysisRun, Episode, Project } from '../types/studio'
import { deriveStageStates, stageStateLabels } from '../utils/stageStatus'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))
const project = ref<Project | null>(null)
const tasks = ref<BackgroundTask[]>([])
const analysis = ref<ContentAnalysisRun | null>(null)
const breakdownRuns = ref<BreakdownRunSummary[]>([])
const loading = ref(true)
const error = ref('')
const shotRefreshToken = ref(0)

const stages = [
  { id: 1, title: '源片与剧集', subtitle: '导入 / 排序 / 预处理', implemented: true },
  { id: 2, title: '剧情与镜头', subtitle: '镜头管理 / 拉片结果', implemented: true },
  { id: 3, title: '人物·场景·道具', subtitle: '资产确认 / Shot 绑定', implemented: true },
  { id: 4, title: '本土化剧本', subtitle: '对白 / 动作 / 结构化剧本', implemented: false },
  { id: 5, title: '镜头重制方案', subtitle: '本土化 / 镜头规格 / 生成计划', implemented: false },
  { id: 6, title: '生成·质检·交付', subtitle: '视频 / 语音 / 质检 / 导出', implemented: false },
]

function stageFromRoute(): number {
  const value = Number(route.query.stage)
  return stages.some((stage) => stage.id === value && stage.implemented) ? value : 1
}

const activeStage = ref(stageFromRoute())
const stageStates = computed(() => deriveStageStates({
  episodes: project.value?.episodes ?? [],
  tasks: tasks.value,
  analysis: analysis.value,
  breakdownRuns: breakdownRuns.value,
}))

function stageState(stageId: number) {
  return stageStates.value[stageId] || 'not_started'
}

async function readBreakdownRuns(episodes: Episode[]): Promise<BreakdownRunSummary[]> {
  const results = await Promise.allSettled(episodes.map((episode) => breakdownApi.listRuns(episode.id)))
  return results.flatMap((result) => result.status === 'fulfilled' ? result.value : [])
}

async function refreshProject(): Promise<void> {
  if (!projectId.value) return
  try {
    const nextProject = await api.getProject(projectId.value)
    project.value = nextProject
    const [taskResult, analysisResult, runsResult] = await Promise.allSettled([
      api.listProjectTasks(projectId.value, 30),
      api.getCurrentContentAnalysis(projectId.value),
      readBreakdownRuns(nextProject.episodes),
    ])
    if (taskResult.status === 'fulfilled') tasks.value = taskResult.value
    if (analysisResult.status === 'fulfilled') analysis.value = analysisResult.value
    if (runsResult.status === 'fulfilled') breakdownRuns.value = runsResult.value
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目读取失败'
  } finally {
    loading.value = false
  }
}

function onTaskCreated(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)]
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  void refreshProject()
  if (task.task_type === 'EPISODE_SHOTS' || task.task_type === 'BATCH_SHOTS') {
    shotRefreshToken.value += 1
  }
}

function selectStage(stageId: number): void {
  const stage = stages.find((item) => item.id === stageId)
  if (!stage?.implemented) return
  activeStage.value = stageId
  void router.replace({ query: { ...route.query, stage: String(stageId) } })
}

watch(
  () => route.query.stage,
  () => {
    activeStage.value = stageFromRoute()
  },
)

onMounted(() => {
  window.addEventListener('studio-task-created', onTaskCreated)
  window.addEventListener('studio-task-finished', onTaskFinished)
  if (String(route.query.stage || '') !== String(activeStage.value)) {
    void router.replace({ query: { ...route.query, stage: String(activeStage.value) } })
  }
  void refreshProject()
})

onUnmounted(() => {
  window.removeEventListener('studio-task-created', onTaskCreated)
  window.removeEventListener('studio-task-finished', onTaskFinished)
})
</script>

<template>
  <div v-if="project" class="studio-shell">
    <aside class="studio-sidebar">
      <button class="back-link" @click="router.push('/')">← 返回项目</button>
      <div class="studio-brand"><span>AI DRAMA STUDIO</span><strong>{{ project.name }}</strong><small>{{ project.source_language }} → {{ project.target_language }} · {{ project.target_region }}</small></div>
      <nav class="stage-nav">
        <button
          v-for="stage in stages"
          :key="stage.id"
          :class="['stage-item', `stage-state-${stageState(stage.id)}`, { active: activeStage === stage.id, planned: !stage.implemented }]"
          :disabled="!stage.implemented"
          :aria-label="`${stage.title} · ${stageStateLabels[stageState(stage.id)]}`"
          @click="selectStage(stage.id)"
        >
          <span class="stage-code">{{ String(stage.id).padStart(2, '0') }}</span>
          <span class="stage-copy">
            <strong>{{ stage.title }}</strong>
            <small>{{ stage.subtitle }}</small>
            <em>{{ stageStateLabels[stageState(stage.id)] }}</em>
          </span>
          <i class="stage-dot"></i>
        </button>
      </nav>
      <div class="sidebar-footer">
        <span>参考视频 V2.5</span>
        <small>{{ project.episodes.length }} 集 · 本地工作流</small>
      </div>
    </aside>

    <main :class="['studio-main', { 'shot-stage-main': activeStage === 2, 'asset-stage-main': activeStage === 3 }]">
      <EpisodeManagerV3 v-if="activeStage === 1" :project="project" @refresh="refreshProject" />
      <BreakdownStageV1
        v-else-if="activeStage === 2"
        :project-id="project.id"
        :episodes="project.episodes"
        :refresh-token="shotRefreshToken"
        @refresh-project="refreshProject"
      />
      <AssetStageV4 v-else-if="activeStage === 3" :project-id="project.id" :episodes="project.episodes" />
    </main>
  </div>

  <div v-else-if="loading" class="screen-loading">正在读取项目…</div>
  <div v-else class="screen-loading"><strong>项目无法打开</strong><span>{{ error }}</span><button class="ghost-button" @click="router.push('/')">返回项目列表</button></div>
</template>

<style scoped>
.stage-copy em {
  margin-top: 2px;
  color: #8996a8;
  font-size: 10px;
  font-style: normal;
  font-weight: 750;
}
.stage-item .stage-dot { background: #a9b2bf; }
.stage-item.stage-state-processing .stage-dot { background: #4f7ee0; box-shadow: 0 0 0 4px rgba(79, 126, 224, .12); }
.stage-item.stage-state-review .stage-dot { background: #d89a28; box-shadow: 0 0 0 4px rgba(216, 154, 40, .12); }
.stage-item.stage-state-completed .stage-dot { background: #25a56a; box-shadow: 0 0 0 4px rgba(37, 165, 106, .1); }
.stage-item.stage-state-blocked .stage-dot { background: #d75b5b; box-shadow: 0 0 0 4px rgba(215, 91, 91, .1); }
.stage-item.stage-state-planned .stage-dot { background: #c3c9d2; box-shadow: none; }
.stage-item.planned { opacity: .58; cursor: not-allowed; }
.stage-item.planned:hover { background: transparent; }
.stage-item.planned .stage-copy em { color: #9aa4b2; }
</style>
