<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '../api/client'
import { getProjectFlowState } from '../api/project-flow-state'
import FinalOutputV1 from '../components/FinalOutputV1.vue'
import type { ProjectFlowState } from '../types/project-flow-state'
import type { BackgroundTask, Project } from '../types/studio'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))
const project = ref<Project | null>(null)
const flow = ref<ProjectFlowState | null>(null)
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
  if (values.length && values.every((item) => item?.consumable)) return '已完成'
  if (values.some((item) => item?.execution === 'PROCESSING' || item?.execution === 'QUEUED')) return '处理中'
  if (values.some((item) => item?.readiness === 'BLOCKED_REVIEW')) return '待确认'
  return number === 5 ? '进行中' : '未开始'
}
function goStage(path: string): void { void router.push(`/projects/${encodeURIComponent(projectId.value)}${path}`) }

async function refresh(): Promise<void> {
  if (!projectId.value) return
  try {
    const [projectResult, flowResult, taskResult] = await Promise.all([
      api.getProject(projectId.value),
      getProjectFlowState(projectId.value),
      api.listProjectTasks(projectId.value, 40),
    ])
    project.value = projectResult
    flow.value = flowResult
    tasks.value = taskResult
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '成片输出状态读取失败'
  } finally {
    loading.value = false
  }
}
function onTaskEvent(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  void refresh()
}
onMounted(() => {
  window.addEventListener('studio-task-created', onTaskEvent)
  window.addEventListener('studio-task-finished', onTaskEvent)
  void refresh()
})
onUnmounted(() => {
  window.removeEventListener('studio-task-created', onTaskEvent)
  window.removeEventListener('studio-task-finished', onTaskEvent)
})
</script>

<template>
  <div class="workflow-stage-page">
    <header class="workflow-stage-topbar">
      <div class="workflow-stage-brand">◈ AI Drama Studio <small>项目管理　›　成片输出</small></div>
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
          <button v-for="item in stages" :key="item.number" :class="{ active: item.number === 5, complete: stageComplete(item.keys) }" @click="goStage(item.path)">
            <b class="workflow-stage-index">{{ item.number }}</b><strong>{{ item.label }}</strong><span>{{ item.description }}</span><em>{{ stageStatus(item.keys, item.number) }}</em>
          </button>
        </nav>
        <button class="workflow-stage-back" @click="router.push('/')">← 返回项目列表</button>
      </aside>

      <main class="workflow-stage-main">
        <section class="workflow-stage-hero">
          <div><h1>成片输出</h1><p>查看当前自动生成进度，完成后直接播放和下载每一集最终视频与字幕。</p></div>
          <div class="workflow-stage-hero-actions"><button class="workflow-stage-button" @click="goStage('/remake')">← 返回视频重做</button></div>
        </section>
        <p v-if="error" class="workflow-stage-error">{{ error }}</p>
        <p v-if="activeTask" class="workflow-stage-note">{{ activeTask.stage_label || activeTask.title }} · {{ activeTask.message || '后台处理中' }}</p>
        <section v-if="loading && !project" class="workflow-stage-card"><div class="workflow-stage-empty">正在读取成片状态…</div></section>
        <section v-else-if="project" class="workflow-stage-card">
          <FinalOutputV1 :project-id="project.id" :busy="Boolean(activeTask)" @changed="refresh" />
        </section>
      </main>
    </div>
  </div>
</template>
