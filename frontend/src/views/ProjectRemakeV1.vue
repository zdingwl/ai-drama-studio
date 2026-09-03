<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import { remakeApi, type AutoOutputState } from '../api/remake'
import FinalOutputV1 from '../components/FinalOutputV1.vue'
import H3QcReviewV1 from '../components/H3QcReviewV1.vue'
import LipSyncReviewV1 from '../components/LipSyncReviewV1.vue'
import SpeakerReviewEditorV1 from '../components/SpeakerReviewEditorV1.vue'
import TargetLocalizationReviewV1 from '../components/TargetLocalizationReviewV1.vue'
import TimingReviewV1 from '../components/TimingReviewV1.vue'
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
const autoState = ref<AutoOutputState | null>(null)
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
const busy = computed(() => Boolean(activeTask.value))
const issueTypes = computed(() => new Set(issues.value.map((item) => item.issue_type)))
const speakerIssues = computed(() => issues.value.filter((item) => item.issue_type === 'SPEAKER'))
const hasLocalizationReview = computed(() => ['TARGET_CHARACTER', 'SCENE_LOCALIZATION', 'LOCALIZATION'].some((type) => issueTypes.value.has(type)))
const hasTimingReview = computed(() => issueTypes.value.has('DIALOGUE_TIMING'))
const hasH3Review = computed(() => issueTypes.value.has('H3_QC'))
const hasLipReview = computed(() => issueTypes.value.has('LIP_SYNC_QC'))
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
  if (number === 4 && activeTask.value) return '处理中'
  if (values.length && values.every((item) => item?.consumable)) return '已完成'
  if (values.some((item) => item?.readiness === 'BLOCKED_REVIEW')) return '待确认'
  if (values.some((item) => item?.execution === 'PROCESSING' || item?.execution === 'QUEUED')) return '处理中'
  if (number === 4) return '进行中'
  return '未开始'
}

function goStage(path: string): void {
  void router.push(`/projects/${encodeURIComponent(projectId.value)}${path}`)
}

async function refresh(): Promise<void> {
  if (!projectId.value) return
  try {
    const [projectResult, flowResult, issueResult, taskResult, stateResult] = await Promise.all([
      api.getProject(projectId.value),
      getProjectFlowState(projectId.value),
      remakeApi.listReviewIssues(projectId.value, 'OPEN'),
      api.listProjectTasks(projectId.value, 40),
      remakeApi.getAutoOutputState(projectId.value),
    ])
    project.value = projectResult
    flow.value = flowResult
    issues.value = issueResult
    tasks.value = taskResult
    autoState.value = stateResult
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '视频重做状态读取失败'
  } finally {
    loading.value = false
  }
}

function onTaskEvent(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  void refresh()
}
function onTruthChanged(): void { void refresh() }

onMounted(() => {
  window.addEventListener('studio-task-created', onTaskEvent)
  window.addEventListener('studio-task-finished', onTaskEvent)
  window.addEventListener('studio-project-truth-changed', onTruthChanged)
  void refresh()
})
onUnmounted(() => {
  window.removeEventListener('studio-task-created', onTaskEvent)
  window.removeEventListener('studio-task-finished', onTaskEvent)
  window.removeEventListener('studio-project-truth-changed', onTruthChanged)
})
</script>

<template>
  <div class="workflow-stage-page">
    <header class="workflow-stage-topbar">
      <div class="workflow-stage-brand">◈ AI Drama Studio <small>项目管理　›　视频重做</small></div>
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
          <button v-for="item in stages" :key="item.number" :class="{ active: item.number === 4, complete: stageComplete(item.keys) }" @click="goStage(item.path)">
            <b class="workflow-stage-index">{{ item.number }}</b><strong>{{ item.label }}</strong><span>{{ item.description }}</span><em>{{ stageStatus(item.keys, item.number) }}</em>
          </button>
        </nav>
        <button class="workflow-stage-back" @click="router.push('/')">← 返回项目列表</button>
      </aside>

      <main class="workflow-stage-main">
        <section class="workflow-stage-hero">
          <div>
            <h1>视频重做</h1>
            <p>从原片确认结果继续本土化、目标对白、配音、Timing、MiniMax H3 重拍和口型后期。自动能完成的直接跑，只有阻塞问题才需要人工处理。</p>
          </div>
          <div class="workflow-stage-hero-actions">
            <button class="workflow-stage-button" @click="goStage('/source-confirm')">← 原片确认</button>
            <button class="workflow-stage-button primary" @click="goStage('/output')">成片输出 →</button>
          </div>
        </section>

        <p v-if="error" class="workflow-stage-error">{{ error }}</p>
        <p v-if="activeTask" class="workflow-stage-note">{{ activeTask.stage_label || activeTask.title }} · {{ activeTask.message || '后台处理中' }}</p>
        <p v-else-if="issues.length" class="workflow-stage-note">当前有 {{ issues.length }} 项需要人工处理。处理完成后点击下方“继续自动生成”，系统会从当前有效进度继续，不会重新拉片。</p>
        <p v-else class="workflow-stage-note">当前没有人工阻塞项。下方“继续自动生成”会直接从 {{ autoState?.stage || '当前阶段' }} 继续。</p>

        <section v-if="loading && !project" class="workflow-stage-card"><div class="workflow-stage-empty">正在读取视频重做状态…</div></section>

        <template v-else-if="project">
          <section v-if="speakerIssues.length || hasLocalizationReview || hasTimingReview || hasH3Review || hasLipReview" class="workflow-stage-card">
            <div class="workflow-stage-card-head"><div><strong>需要人工处理</strong><span>只显示真正阻塞自动流程的项目</span></div><span>{{ issues.length }} 项</span></div>
            <div class="workflow-stage-review-stack">
              <SpeakerReviewEditorV1 v-if="speakerIssues.length" :issues="issues" @changed="refresh" @open-asset-editor="goStage('/source-confirm')" />
              <TargetLocalizationReviewV1 v-if="hasLocalizationReview" :project-id="project.id" @changed="refresh" />
              <TimingReviewV1 v-if="hasTimingReview" :project-id="project.id" @changed="refresh" />
              <H3QcReviewV1 v-if="hasH3Review" :project-id="project.id" @changed="refresh" />
              <LipSyncReviewV1 v-if="hasLipReview" :project-id="project.id" :busy="busy" @changed="refresh" />
            </div>
          </section>

          <section class="workflow-stage-card">
            <div class="workflow-stage-card-head"><div><strong>自动重做流水线</strong><span>目标设计 → 对白/配音 → Timing → H3 → 口型/后期 → 成片</span></div><span>MiniMax H3 Local</span></div>
            <FinalOutputV1 :project-id="project.id" :busy="busy" @changed="refresh" />
          </section>
        </template>
      </main>
    </div>
  </div>
</template>
