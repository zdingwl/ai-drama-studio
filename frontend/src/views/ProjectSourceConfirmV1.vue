<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { remakeApi } from '../api/remake'
import CharacterAssetsWorkbenchV1 from '../components/CharacterAssetsWorkbenchV1.vue'
import AssetStageV4 from '../components/AssetStageV4.vue'
import SpeakerReviewEditorV1 from '../components/SpeakerReviewEditorV1.vue'
import type { ProjectFlowState } from '../types/project-flow-state'
import type { ReviewIssue } from '../types/remake'
import type { BackgroundTask, Project } from '../types/studio'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))
const project = ref<Project | null>(null)
const flow = ref<ProjectFlowState | null>(null)
const issues = ref<ReviewIssue[]>([])
const tasks = ref<BackgroundTask[]>([])
const loading = ref(true)
const error = ref('')

const stages = [
  { number: 1, label: '原短剧视频', description: '上传、排序与镜头检测', keys: ['project_setup', 'source_split'], path: '' },
  { number: 2, label: 'AI 拉片', description: '剧情、对白与镜头理解', keys: ['source_understanding'], path: '/breakdown' },
  { number: 3, label: '原片确认', description: '人物 / 场景 / 道具确认', keys: ['source_assets', 'source_snapshot'], path: '/source-confirm' },
  { number: 4, label: '视频重做', description: '本土化、配音与视频生成', keys: ['target_design', 'target_dialogue', 'remake_timing', 'h3_generation'], path: '/remake' },
  { number: 5, label: '成片输出', description: '后期检查与最终导出', keys: ['postproduction_output'], path: '/output' },
] as const

const activeTask = computed(() => tasks.value.find((item) => item.status === 'QUEUED' || item.status === 'PROCESSING') || null)
const speakerIssues = computed(() => issues.value.filter((item) => item.issue_type === 'SPEAKER'))
const overallProgress = computed(() => {
  const values = flow.value?.stages || []
  if (!values.length) return 0
  return Math.round(values.filter((item) => item.consumable).length / values.length * 100)
})

function stageComplete(keys: readonly string[]): boolean {
  const values = keys.map((key) => flow.value?.stages.find((item) => item.stage_key === key)).filter(Boolean)
  return Boolean(values.length && values.every((item) => item?.consumable))
}

function stageStatus(keys: readonly string[], number: number): string {
  const values = keys.map((key) => flow.value?.stages.find((item) => item.stage_key === key)).filter(Boolean)
  if (number === 3) return values.some((item) => item?.readiness === 'BLOCKED_REVIEW') ? '待确认' : '进行中'
  if (values.length && values.every((item) => item?.consumable)) return '已完成'
  if (values.some((item) => item?.execution === 'PROCESSING' || item?.execution === 'QUEUED')) return '处理中'
  if (values.some((item) => item?.readiness === 'BLOCKED_REVIEW')) return '待确认'
  if (values.some((item) => item?.readiness === 'READY')) return '可开始'
  return '未开始'
}

function goStage(path: string): void {
  void router.push(`/projects/${encodeURIComponent(projectId.value)}${path}`)
}

async function refresh(): Promise<void> {
  if (!projectId.value) return
  try {
    const [projectResult, flowResult, issueResult, taskResult] = await Promise.all([
      api.getProject(projectId.value),
      getProjectFlowState(projectId.value),
      remakeApi.listReviewIssues(projectId.value, 'OPEN'),
      api.listProjectTasks(projectId.value, 40),
    ])
    project.value = projectResult
    flow.value = flowResult
    issues.value = issueResult
    tasks.value = taskResult
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '原片确认数据读取失败'
  } finally {
    loading.value = false
  }
}

function onTruthChanged(event: Event): void {
  const detail = (event as CustomEvent<{ project_id?: string }>).detail
  if (detail?.project_id && detail.project_id !== projectId.value) return
  void refresh()
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  void refresh()
}

onMounted(() => {
  window.addEventListener('studio-project-truth-changed', onTruthChanged)
  window.addEventListener('studio-task-finished', onTaskFinished)
  void refresh()
})
onUnmounted(() => {
  window.removeEventListener('studio-project-truth-changed', onTruthChanged)
  window.removeEventListener('studio-task-finished', onTaskFinished)
})
</script>

<template>
  <div class="workflow-stage-page">
    <header class="workflow-stage-topbar">
      <div class="workflow-stage-brand">◈ AI Drama Studio <small>项目管理　›　原片确认</small></div>
      <button class="workflow-stage-help">? 操作说明</button>
    </header>

    <div class="workflow-stage-layout">
      <aside class="workflow-stage-sidebar">
        <div class="workflow-stage-progress">
          <strong>项目进度</strong>
          <div class="workflow-stage-progress-row"><span>整体进度</span><b>{{ overallProgress }}%</b></div>
          <div class="workflow-stage-progress-track"><i :style="{ width: `${overallProgress}%` }" /></div>
        </div>
        <nav class="workflow-stage-nav">
          <button v-for="item in stages" :key="item.number" :class="{ active: item.number === 3, complete: stageComplete(item.keys) }" @click="goStage(item.path)">
            <b class="workflow-stage-index">{{ item.number }}</b>
            <strong>{{ item.label }}</strong>
            <span>{{ item.description }}</span>
            <em>{{ stageStatus(item.keys, item.number) }}</em>
          </button>
        </nav>
        <button class="workflow-stage-back" @click="router.push('/')">← 返回项目列表</button>
      </aside>

      <main class="workflow-stage-main">
        <section class="workflow-stage-hero">
          <div>
            <h1>原片确认</h1>
            <p>先将不同分镜里属于同一人的观察归并为原片人物资产，再设计替换人物并生成四视图。人物确认通过原片快照供后续重做使用。</p>
          </div>
          <div class="workflow-stage-hero-actions">
            <button class="workflow-stage-button" @click="goStage('/breakdown')">← 返回 AI 拉片</button>
            <button class="workflow-stage-button primary" :disabled="loading" @click="goStage('/remake')">进入视频重做 →</button>
          </div>
        </section>

        <p v-if="error" class="workflow-stage-error">{{ error }}</p>
        <p v-if="activeTask" class="workflow-stage-note">后台任务：{{ activeTask.stage_label || activeTask.title }} · {{ activeTask.message || '处理中' }}</p>
        <p v-else class="workflow-stage-note">修改会直接写入 Final Asset / Shot Binding；不覆盖原始 AI Evidence，也不需要重新拉片。</p>

        <section v-if="loading && !project" class="workflow-stage-card"><div class="workflow-stage-empty">正在读取项目和原片确认数据…</div></section>

        <template v-else-if="project">
          <CharacterAssetsWorkbenchV1 :project-id="project.id" @changed="refresh" />
          <section class="workflow-stage-card">
            <div class="workflow-stage-card-head">
              <div><strong>人物 / 场景 / 道具</strong><span>可新建、重命名、合并、拆分、删除、改封面，并逐镜头修改绑定</span></div>
              <span>{{ project.episodes.length }} 集</span>
            </div>
            <AssetStageV4 :project-id="project.id" :episodes="project.episodes" />
          </section>

          <section v-if="speakerIssues.length" class="workflow-stage-card">
            <div class="workflow-stage-card-head"><div><strong>对白说话人确认</strong><span>修正原片真实说话人，后续翻译、音色与口型会使用这里的结果</span></div><span>{{ speakerIssues.length }} 条</span></div>
            <div class="workflow-stage-review-stack">
              <SpeakerReviewEditorV1 :issues="issues" @changed="refresh" @open-asset-editor="() => undefined" />
            </div>
          </section>
        </template>
      </main>
    </div>
  </div>
</template>
