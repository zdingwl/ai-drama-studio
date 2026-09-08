<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import {
  cancelProjectTask,
  getProject,
  getProjectPlan,
  listProjectTasks,
  resumeProjectTask,
  retryProjectTask,
  startP4AcceptanceTask,
  type P4AcceptanceScenario,
} from '@/features/projects/api'
import {
  projectTypeLabel,
  type PlanStepStatus,
  type ProjectExecutionPlan,
  type ProjectRead,
  type TaskRead,
  type TaskStatus,
} from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id))
const project = ref<ProjectRead | null>(null)
const plan = ref<ProjectExecutionPlan | null>(null)
const tasks = ref<TaskRead[]>([])
const loading = ref(true)
const refreshingTasks = ref(false)
const taskActionId = ref('')
const p4Starting = ref('')
const errorMessage = ref('')
const planErrorMessage = ref('')
const taskErrorMessage = ref('')
const p4AcceptanceMessage = ref('')
let taskPollTimer: number | null = null

const statusText: Record<PlanStepStatus, string> = {
  COMPLETED: '已完成',
  READY: '可开始',
  BLOCKED_DEPENDENCY: '等待上一步',
  WAITING_CAPABILITY: '等待能力接入',
}

const taskStatusText: Record<TaskStatus, string> = {
  queued: '排队中',
  running: '处理中',
  succeeded: '已完成',
  failed: '失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

async function loadWorkspace(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  planErrorMessage.value = ''
  try {
    const [projectResult, taskResult, planResult] = await Promise.all([
      getProject(projectId.value),
      listProjectTasks(projectId.value),
      getProjectPlan(projectId.value).catch((error: unknown) => {
        planErrorMessage.value = error instanceof Error ? error.message : '执行计划暂不可用'
        return null
      }),
    ])
    project.value = projectResult
    tasks.value = taskResult
    plan.value = planResult
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '项目加载失败'
  } finally {
    loading.value = false
  }
}

async function refreshTasks(): Promise<void> {
  refreshingTasks.value = true
  taskErrorMessage.value = ''
  try {
    tasks.value = await listProjectTasks(projectId.value)
  } catch (error) {
    taskErrorMessage.value = error instanceof Error ? error.message : '任务状态刷新失败'
  } finally {
    refreshingTasks.value = false
  }
}

function stopTaskPolling(): void {
  if (taskPollTimer !== null) {
    window.clearInterval(taskPollTimer)
    taskPollTimer = null
  }
}

function startTaskPolling(): void {
  if (taskPollTimer !== null) return
  taskPollTimer = window.setInterval(async () => {
    await refreshTasks()
    const hasActiveTask = tasks.value.some((task) => task.status === 'queued' || task.status === 'running')
    if (!hasActiveTask) stopTaskPolling()
  }, 500)
}

function replaceTask(updated: TaskRead): void {
  const index = tasks.value.findIndex((item) => item.id === updated.id)
  if (index >= 0) {
    tasks.value[index] = updated
  } else {
    tasks.value.unshift(updated)
  }
}

function newAcceptanceKey(label: string): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
  return `p4-${label}-${suffix}`.slice(0, 128)
}

async function startAcceptanceScenario(scenario: P4AcceptanceScenario): Promise<void> {
  p4Starting.value = scenario
  p4AcceptanceMessage.value = ''
  taskErrorMessage.value = ''
  try {
    const task = await startP4AcceptanceTask(projectId.value, scenario, newAcceptanceKey(scenario))
    replaceTask(task)
    startTaskPolling()
  } catch (error) {
    taskErrorMessage.value = error instanceof Error ? error.message : 'P4 验收任务启动失败'
  } finally {
    p4Starting.value = ''
  }
}

async function verifyDuplicateProtection(): Promise<void> {
  p4Starting.value = 'dedupe'
  p4AcceptanceMessage.value = ''
  taskErrorMessage.value = ''
  const key = newAcceptanceKey('dedupe')
  try {
    const [first, second] = await Promise.all([
      startP4AcceptanceTask(projectId.value, 'success', key),
      startP4AcceptanceTask(projectId.value, 'success', key),
    ])
    replaceTask(first)
    p4AcceptanceMessage.value = first.id === second.id
      ? '重复提交保护：通过。两次相同提交只产生了 1 个任务。'
      : '重复提交保护：未通过。两次相同提交产生了不同任务。'
    startTaskPolling()
  } catch (error) {
    taskErrorMessage.value = error instanceof Error ? error.message : '重复提交保护测试失败'
  } finally {
    p4Starting.value = ''
  }
}

async function runTaskAction(task: TaskRead, action: 'retry' | 'cancel' | 'resume'): Promise<void> {
  taskActionId.value = task.id
  taskErrorMessage.value = ''
  try {
    const updated = action === 'retry'
      ? await retryProjectTask(projectId.value, task.id)
      : action === 'cancel'
        ? await cancelProjectTask(projectId.value, task.id)
        : await resumeProjectTask(projectId.value, task.id)
    replaceTask(updated)
    if (updated.status === 'queued' || updated.status === 'running') startTaskPolling()
  } catch (error) {
    taskErrorMessage.value = error instanceof Error ? error.message : '任务操作失败'
  } finally {
    taskActionId.value = ''
  }
}

onMounted(loadWorkspace)
onBeforeUnmount(stopTaskPolling)
</script>

<template>
  <section class="workspace">
    <RouterLink to="/" class="back-link">← 返回项目</RouterLink>

    <p v-if="loading" class="muted">正在加载项目…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>

    <template v-else-if="project">
      <header class="workspace-header">
        <div>
          <span class="project-type">{{ projectTypeLabel(project.project_type) }}</span>
          <h1>{{ project.name }}</h1>
          <p>{{ project.target_language }} · {{ project.target_region }}</p>
        </div>
        <div v-if="plan" class="skill-card">
          <small>当前根技能</small>
          <strong>{{ plan.skill_title }}</strong>
          <span>{{ plan.skill_id }}</span>
        </div>
        <div v-else class="skill-card">
          <small>执行计划</small>
          <strong>尚未生成</strong>
          <span>任务验收仍可独立进行</span>
        </div>
      </header>

      <section class="acceptance-section">
        <div class="section-heading">
          <div>
            <p class="eyebrow">开发验收工具</p>
            <h2>P4 任务执行机制</h2>
          </div>
        </div>
        <p class="acceptance-note">
          这里只运行本地模拟任务，不调用真实模型、不产生费用。用于人工检查排队、进度、失败重试、中断继续、取消和重复提交保护。
        </p>
        <div class="acceptance-actions">
          <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('success')">
            {{ p4Starting === 'success' ? '启动中…' : '测试正常完成' }}
          </button>
          <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('retry')">
            {{ p4Starting === 'retry' ? '启动中…' : '测试失败 → 重试' }}
          </button>
          <button type="button" :disabled="Boolean(p4Starting)" @click="startAcceptanceScenario('resume')">
            {{ p4Starting === 'resume' ? '启动中…' : '测试中断 → 继续' }}
          </button>
          <button type="button" :disabled="Boolean(p4Starting)" @click="verifyDuplicateProtection">
            {{ p4Starting === 'dedupe' ? '测试中…' : '测试防重复提交' }}
          </button>
        </div>
        <p v-if="p4AcceptanceMessage" class="success-message">{{ p4AcceptanceMessage }}</p>
      </section>

      <section class="task-section">
        <div class="section-heading">
          <div>
            <p class="eyebrow">任务状态</p>
            <h2>当前执行任务</h2>
          </div>
          <button class="secondary-button" type="button" :disabled="refreshingTasks" @click="refreshTasks">
            {{ refreshingTasks ? '刷新中…' : '刷新任务' }}
          </button>
        </div>

        <p v-if="taskErrorMessage" class="error-message">{{ taskErrorMessage }}</p>
        <div v-if="tasks.length" class="task-list">
          <article v-for="task in tasks" :key="task.id" class="task-card">
            <div class="task-heading">
              <div>
                <h3>{{ task.task_name }}</h3>
                <span class="task-status" :class="`task-${task.status}`">{{ taskStatusText[task.status] }}</span>
              </div>
              <strong>{{ task.progress_percent }}%</strong>
            </div>
            <div class="progress-track" aria-hidden="true">
              <div class="progress-value" :style="{ width: `${task.progress_percent}%` }"></div>
            </div>
            <p v-if="task.last_error" class="task-error">{{ task.last_error }}</p>
            <div v-if="task.can_retry || task.can_cancel || task.can_resume" class="task-actions">
              <button
                v-if="task.can_retry"
                type="button"
                :disabled="taskActionId === task.id"
                @click="runTaskAction(task, 'retry')"
              >
                重试
              </button>
              <button
                v-if="task.can_resume"
                type="button"
                :disabled="taskActionId === task.id"
                @click="runTaskAction(task, 'resume')"
              >
                继续
              </button>
              <button
                v-if="task.can_cancel"
                type="button"
                :disabled="taskActionId === task.id"
                @click="runTaskAction(task, 'cancel')"
              >
                取消
              </button>
            </div>
          </article>
        </div>
        <p v-else class="muted task-empty">当前没有执行任务。</p>
      </section>

      <section v-if="plan" class="plan-section">
        <div class="section-heading">
          <div>
            <p class="eyebrow">执行计划</p>
            <h2>系统根据 Skill 和现有资产生成的正式计划</h2>
          </div>
          <span class="revision">版本 {{ plan.workflow_revision }}</span>
        </div>

        <div class="plan-list">
          <article v-for="(step, index) in plan.steps" :key="step.id" class="plan-step">
            <div class="step-number">{{ String(index + 1).padStart(2, '0') }}</div>
            <div class="step-content">
              <div class="step-heading">
                <div>
                  <span class="phase">{{ step.phase }}</span>
                  <h3>{{ step.title }}</h3>
                </div>
                <span class="status" :class="step.status.toLowerCase()">{{ statusText[step.status] }}</span>
              </div>
              <p>{{ step.description }}</p>
              <p v-if="step.status === 'BLOCKED_DEPENDENCY'" class="dependency-note">
                完成上游正式结果后会自动解锁，不会通过页面刷新偷偷启动任务。
              </p>
            </div>
          </article>
        </div>
      </section>
      <section v-else class="plan-section">
        <div class="plan-empty">
          <strong>当前还没有可显示的执行计划</strong>
          <span>{{ planErrorMessage || '任务区与 P4 验收工具仍然可以独立使用。' }}</span>
        </div>
      </section>
    </template>
  </section>
</template>

<style scoped>
.workspace { display: grid; gap: 24px; }
.back-link { color: #5b4ee8; text-decoration: none; font-weight: 700; }
.workspace-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; padding: 24px; border: 1px solid #e7e7ef; border-radius: 20px; background: #fff; }
.workspace-header h1 { margin: 10px 0 6px; font-size: 32px; }
.workspace-header p { margin: 0; color: #667085; }
.project-type { display: inline-flex; padding: 5px 9px; border-radius: 999px; background: #f1f0ff; color: #5b4ee8; font-size: 12px; font-weight: 800; }
.skill-card { min-width: 230px; display: grid; gap: 5px; padding: 16px; border-radius: 14px; background: #f8f8fb; }
.skill-card small, .skill-card span { color: #667085; }
.acceptance-section { display: grid; gap: 14px; padding: 20px; border: 1px solid #ddd9ff; border-radius: 16px; background: #faf9ff; }
.acceptance-note { margin: 0; color: #667085; line-height: 1.7; }
.acceptance-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.acceptance-actions button { border: 1px solid #c9c2ff; border-radius: 10px; background: #fff; padding: 10px 14px; font-weight: 800; cursor: pointer; }
.acceptance-actions button:disabled { cursor: wait; opacity: .55; }
.success-message { margin: 0; color: #027a48; font-weight: 700; }
.task-section, .plan-section { display: grid; gap: 16px; }
.section-heading { display: flex; justify-content: space-between; align-items: end; gap: 16px; }
.section-heading h2 { margin: 3px 0 0; font-size: 22px; }
.eyebrow { margin: 0; color: #6d5dfc; font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.revision { color: #667085; font-size: 13px; }
.secondary-button, .task-actions button { border: 1px solid #d0d5dd; border-radius: 10px; background: #fff; padding: 8px 12px; font-weight: 700; cursor: pointer; }
.secondary-button:disabled, .task-actions button:disabled { cursor: wait; opacity: .55; }
.task-list { display: grid; gap: 10px; }
.task-card { display: grid; gap: 12px; padding: 18px; border: 1px solid #e7e7ef; border-radius: 14px; background: #fff; }
.task-heading { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.task-heading > div { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.task-heading h3 { margin: 0; font-size: 16px; }
.task-heading > strong { color: #344054; }
.task-status { padding: 4px 8px; border-radius: 999px; font-size: 12px; font-weight: 800; background: #f2f4f7; color: #667085; }
.task-running, .task-queued { background: #eff8ff; color: #175cd3; }
.task-succeeded { background: #ecfdf3; color: #027a48; }
.task-failed { background: #fef3f2; color: #b42318; }
.task-interrupted { background: #fffaeb; color: #b54708; }
.task-cancelled { background: #f2f4f7; color: #667085; }
.progress-track { width: 100%; height: 8px; overflow: hidden; border-radius: 999px; background: #f2f4f7; }
.progress-value { height: 100%; border-radius: inherit; background: #6d5dfc; transition: width .2s ease; }
.task-error { margin: 0; color: #b42318; font-size: 13px; line-height: 1.5; }
.task-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.task-empty { margin: 0; padding: 16px 18px; border: 1px dashed #d0d5dd; border-radius: 12px; background: #fff; }
.plan-list { display: grid; gap: 10px; }
.plan-step { display: grid; grid-template-columns: 48px 1fr; gap: 14px; padding: 18px; border: 1px solid #e7e7ef; border-radius: 14px; background: #fff; }
.step-number { display: grid; place-items: center; width: 42px; height: 42px; border-radius: 12px; background: #f4f4f6; color: #667085; font-weight: 800; }
.step-content { display: grid; gap: 8px; }
.step-heading { display: flex; justify-content: space-between; gap: 12px; }
.phase { color: #667085; font-size: 12px; }
.step-heading h3 { margin: 2px 0 0; }
.step-content > p { margin: 0; color: #667085; line-height: 1.6; }
.status { align-self: start; padding: 5px 9px; border-radius: 999px; font-size: 12px; font-weight: 800; }
.status.ready { background: #ecfdf3; color: #027a48; }
.status.completed { background: #eff8ff; color: #175cd3; }
.status.blocked_dependency, .status.waiting_capability { background: #f2f4f7; color: #667085; }
.dependency-note { font-size: 12px; }
.plan-empty { display: grid; gap: 6px; padding: 18px; border: 1px dashed #d0d5dd; border-radius: 12px; background: #fff; }
.plan-empty span { color: #667085; }
.error-message { color: #b42318; }
.muted { color: #667085; }
@media (max-width: 720px) { .workspace-header, .section-heading { display: grid; } .skill-card { min-width: 0; } .plan-step { grid-template-columns: 1fr; } .step-heading { align-items: flex-start; } .task-heading { display: grid; } }
</style>
