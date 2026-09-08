<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { ApiError, apiRequest } from '@/lib/api'

type ProjectType =
  | 'REPLICA'
  | 'REDRAW'
  | 'TRANSLATION'
  | 'NOVEL_TO_DRAMA'
  | 'SCRIPT_TO_DRAMA'
  | 'SCRIPT_LOCALIZATION'

type PlanStatus = 'COMPLETED' | 'READY' | 'BLOCKED_DEPENDENCY' | 'WAITING_CAPABILITY'

interface RootSkill {
  id: string
  name: string
  version: string
  description: string
  project_type: ProjectType
}

interface Project {
  id: string
  name: string
  project_type: ProjectType
  source_language: string | null
  target_language: string
  target_region: string
  scene_strategy: 'KEEP' | 'LOCALIZE' | 'MIXED'
  audio_policy: 'KEEP_SOURCE_AUDIO' | 'REGENERATE_AUDIO'
  visual_style: string | null
  root_skill_id: string
  root_skill_version: string
  current_plan_id: string | null
  workflow_revision: number
}

interface PlanStep {
  id: string
  phase: string
  title: string
  description: string
  status: PlanStatus
  missing_artifacts: string[]
  unavailable_capabilities: string[]
}

interface ProjectPlan {
  id: string
  project_id: string
  skill_id: string
  skill_title: string
  skill_version: string
  revision: number
  input_fingerprint: string
  steps: PlanStep[]
}

const projectLabels: Record<ProjectType, string> = {
  REPLICA: '复刻',
  REDRAW: '重绘',
  TRANSLATION: '翻译',
  NOVEL_TO_DRAMA: '小说生成短剧',
  SCRIPT_TO_DRAMA: '剧本生成短剧',
  SCRIPT_LOCALIZATION: '剧本本土化',
}

const statusLabels: Record<PlanStatus, string> = {
  COMPLETED: '已完成',
  READY: '可执行',
  BLOCKED_DEPENDENCY: '等待前置结果',
  WAITING_CAPABILITY: '等待后续能力接入',
}

const skills = ref<RootSkill[]>([])
const projects = ref<Project[]>([])
const selectedProjectId = ref<string | null>(null)
const plan = ref<ProjectPlan | null>(null)
const loading = ref(true)
const saving = ref(false)
const message = ref('')

const form = reactive({
  name: '',
  project_type: 'REPLICA' as ProjectType,
  source_language: 'zh-CN',
  target_language: 'en-US',
  target_region: 'US',
  scene_strategy: 'MIXED' as 'KEEP' | 'LOCALIZE' | 'MIXED',
  audio_policy: 'REGENERATE_AUDIO' as 'KEEP_SOURCE_AUDIO' | 'REGENERATE_AUDIO',
  visual_style: 'SOURCE_LIKE',
})

const isVideoProject = computed(() =>
  ['REPLICA', 'REDRAW', 'TRANSLATION'].includes(form.project_type),
)

const selectedProject = computed(() =>
  projects.value.find((item) => item.id === selectedProjectId.value) ?? null,
)

function chooseProjectType(projectType: ProjectType) {
  form.project_type = projectType
  if (projectType === 'TRANSLATION') {
    form.scene_strategy = 'KEEP'
  } else if (projectType === 'REPLICA') {
    form.scene_strategy = 'MIXED'
  } else {
    form.scene_strategy = 'LOCALIZE'
  }
  form.audio_policy = projectType === 'REDRAW' ? 'KEEP_SOURCE_AUDIO' : 'REGENERATE_AUDIO'
}

async function loadPlan(projectId: string) {
  try {
    plan.value = await apiRequest<ProjectPlan>(`/projects/${projectId}/plan`)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      plan.value = null
      return
    }
    throw error
  }
}

async function selectProject(projectId: string) {
  selectedProjectId.value = projectId
  message.value = ''
  await loadPlan(projectId)
}

async function loadWorkspace() {
  loading.value = true
  try {
    const [skillRows, projectRows] = await Promise.all([
      apiRequest<RootSkill[]>('/skills'),
      apiRequest<Project[]>('/projects'),
    ])
    skills.value = skillRows
    projects.value = projectRows
    if (projectRows.length > 0) {
      await selectProject(projectRows[0].id)
    }
  } catch (error) {
    message.value = error instanceof Error ? error.message : '工作台加载失败'
  } finally {
    loading.value = false
  }
}

async function compilePlan(projectId: string) {
  plan.value = await apiRequest<ProjectPlan>(`/projects/${projectId}/commands/compile-plan`, {
    method: 'POST',
  })
  const project = projects.value.find((item) => item.id === projectId)
  if (project) {
    project.current_plan_id = plan.value.id
  }
}

async function createProject() {
  if (!form.name.trim()) {
    message.value = '请填写项目名称'
    return
  }
  saving.value = true
  message.value = ''
  try {
    const payload = {
      name: form.name.trim(),
      project_type: form.project_type,
      source_language: isVideoProject.value ? form.source_language : undefined,
      target_language: form.target_language,
      target_region: form.target_region,
      scene_strategy: form.scene_strategy,
      audio_policy: form.audio_policy,
      visual_style: form.visual_style,
    }
    const project = await apiRequest<Project>('/projects', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    projects.value = [project, ...projects.value]
    selectedProjectId.value = project.id
    await compilePlan(project.id)
    form.name = ''
    message.value = '项目已创建，执行计划已生成。'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '项目创建失败'
  } finally {
    saving.value = false
  }
}

onMounted(loadWorkspace)
</script>

<template>
  <div class="workspace">
    <section class="intro">
      <p class="eyebrow">AI Drama Studio V3</p>
      <h1>你想创建什么？</h1>
      <p>先选项目类型。系统会绑定对应专业 Skill，再根据项目已有正式资产生成执行计划。</p>
    </section>

    <p v-if="message" class="notice">{{ message }}</p>
    <p v-if="loading" class="muted">正在读取项目与 Skill…</p>

    <section v-else class="panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">创建项目</p>
          <h2>六种项目，六套专业方法</h2>
        </div>
      </div>

      <div class="type-grid">
        <button
          v-for="skill in skills"
          :key="skill.id"
          class="type-card"
          :class="{ selected: form.project_type === skill.project_type }"
          type="button"
          @click="chooseProjectType(skill.project_type)"
        >
          <strong>{{ projectLabels[skill.project_type] }}</strong>
          <span>{{ skill.description }}</span>
        </button>
      </div>

      <form class="project-form" @submit.prevent="createProject">
        <label>
          <span>项目名称</span>
          <input v-model="form.name" maxlength="120" placeholder="例如：复刻版 EP01" />
        </label>

        <label v-if="isVideoProject">
          <span>原始语言</span>
          <select v-model="form.source_language">
            <option value="zh-CN">中文</option>
            <option value="en-US">英语</option>
            <option value="es-ES">西班牙语</option>
            <option value="pt-BR">葡萄牙语</option>
            <option value="ja-JP">日语</option>
            <option value="ko-KR">韩语</option>
          </select>
        </label>

        <label>
          <span>目标语言</span>
          <select v-model="form.target_language">
            <option value="en-US">英语（美国）</option>
            <option value="en-GB">英语（英国）</option>
            <option value="es-ES">西班牙语</option>
            <option value="pt-BR">葡萄牙语（巴西）</option>
            <option value="ja-JP">日语</option>
            <option value="ko-KR">韩语</option>
          </select>
        </label>

        <label>
          <span>目标地区</span>
          <select v-model="form.target_region">
            <option value="US">美国</option>
            <option value="GB">英国</option>
            <option value="CA">加拿大</option>
            <option value="AU">澳大利亚</option>
            <option value="MX">墨西哥</option>
            <option value="BR">巴西</option>
            <option value="JP">日本</option>
            <option value="KR">韩国</option>
          </select>
        </label>

        <label>
          <span>场景策略</span>
          <select v-model="form.scene_strategy">
            <option value="KEEP">尽量保留</option>
            <option value="LOCALIZE">本土化替换</option>
            <option value="MIXED">按镜头判断</option>
          </select>
        </label>

        <label>
          <span>音频策略</span>
          <select v-model="form.audio_policy">
            <option value="REGENERATE_AUDIO">重建目标音频</option>
            <option value="KEEP_SOURCE_AUDIO">保留原音频</option>
          </select>
        </label>

        <label>
          <span>视觉方向</span>
          <select v-model="form.visual_style">
            <option value="SOURCE_LIKE">跟随原片</option>
            <option value="CINEMATIC_REALISM">电影写实</option>
            <option value="STYLIZED">风格化</option>
          </select>
        </label>

        <button class="primary" type="submit" :disabled="saving">
          {{ saving ? '正在创建…' : `创建${projectLabels[form.project_type]}项目` }}
        </button>
      </form>
    </section>

    <section class="two-column">
      <div class="panel">
        <div class="section-heading">
          <div>
            <p class="eyebrow">已有项目</p>
            <h2>项目列表</h2>
          </div>
        </div>
        <p v-if="projects.length === 0" class="empty">还没有项目。</p>
        <button
          v-for="project in projects"
          :key="project.id"
          class="project-card"
          :class="{ selected: selectedProjectId === project.id }"
          type="button"
          @click="selectProject(project.id)"
        >
          <span>
            <strong>{{ project.name }}</strong>
            <small>{{ projectLabels[project.project_type] }} · {{ project.target_language }} / {{ project.target_region }}</small>
          </span>
          <small>计划 r{{ project.workflow_revision }}</small>
        </button>
      </div>

      <div class="panel">
        <div class="section-heading plan-heading">
          <div>
            <p class="eyebrow">当前执行计划</p>
            <h2>{{ selectedProject?.name ?? '选择一个项目' }}</h2>
          </div>
          <button
            v-if="selectedProject && !plan"
            class="secondary"
            type="button"
            @click="compilePlan(selectedProject.id)"
          >
            生成执行计划
          </button>
        </div>

        <p v-if="selectedProject && !plan" class="empty">当前没有可用计划。项目配置或正式资产变化后，需要显式重新生成。</p>
        <p v-else-if="!selectedProject" class="empty">从左侧选择项目查看计划。</p>

        <ol v-if="plan" class="plan-list">
          <li v-for="step in plan.steps" :key="step.id" class="plan-step">
            <div class="step-index">{{ String(plan.steps.indexOf(step) + 1).padStart(2, '0') }}</div>
            <div class="step-body">
              <div class="step-title-row">
                <strong>{{ step.title }}</strong>
                <span class="status-pill" :data-status="step.status">{{ statusLabels[step.status] }}</span>
              </div>
              <p>{{ step.description }}</p>
            </div>
          </li>
        </ol>
      </div>
    </section>
  </div>
</template>
