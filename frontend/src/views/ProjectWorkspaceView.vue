<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { getProject, getProjectPlan } from '@/features/projects/api'
import { projectTypeLabel, type PlanStepStatus, type ProjectExecutionPlan, type ProjectRead } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id))
const project = ref<ProjectRead | null>(null)
const plan = ref<ProjectExecutionPlan | null>(null)
const loading = ref(true)
const errorMessage = ref('')

const statusText: Record<PlanStepStatus, string> = {
  COMPLETED: '已完成',
  READY: '可开始',
  BLOCKED_DEPENDENCY: '等待上一步',
}

async function loadWorkspace(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const [projectResult, planResult] = await Promise.all([
      getProject(projectId.value),
      getProjectPlan(projectId.value),
    ])
    project.value = projectResult
    plan.value = planResult
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '项目加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(loadWorkspace)
</script>

<template>
  <section class="workspace">
    <RouterLink to="/" class="back-link">← 返回项目</RouterLink>

    <p v-if="loading" class="muted">正在加载项目…</p>
    <p v-else-if="errorMessage" class="error-message">{{ errorMessage }}</p>

    <template v-else-if="project && plan">
      <header class="workspace-header">
        <div>
          <span class="project-type">{{ projectTypeLabel(project.project_type) }}</span>
          <h1>{{ project.name }}</h1>
          <p>{{ project.target_language }} · {{ project.target_region }}</p>
        </div>
        <div class="skill-card">
          <small>当前根技能</small>
          <strong>{{ plan.skill_title }}</strong>
          <span>{{ plan.skill_id }}</span>
        </div>
      </header>

      <section class="plan-section">
        <div class="section-heading">
          <div>
            <p class="eyebrow">执行计划</p>
            <h2>系统根据 Skill 和现有资产实时编译</h2>
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
.plan-section { display: grid; gap: 16px; }
.section-heading { display: flex; justify-content: space-between; align-items: end; gap: 16px; }
.section-heading h2 { margin: 3px 0 0; font-size: 22px; }
.eyebrow { margin: 0; color: #6d5dfc; font-size: 12px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.revision { color: #667085; font-size: 13px; }
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
.status.blocked_dependency { background: #f2f4f7; color: #667085; }
.dependency-note { font-size: 12px; }
.error-message { color: #b42318; }
.muted { color: #667085; }
@media (max-width: 720px) { .workspace-header, .section-heading { display: grid; } .skill-card { min-width: 0; } .plan-step { grid-template-columns: 1fr; } .step-heading { align-items: flex-start; } }
</style>
