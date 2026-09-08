<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { createProject, listProjects } from '@/features/projects/api'
import {
  LANGUAGE_OPTIONS,
  PROJECT_TYPE_OPTIONS,
  REGION_OPTIONS,
  VIDEO_PROJECT_TYPES,
  projectTypeLabel,
  type AudioPolicy,
  type ProjectCreatePayload,
  type ProjectRead,
  type SceneStrategy,
} from '@/features/projects/types'

const projects = ref<ProjectRead[]>([])
const loading = ref(true)
const creating = ref(false)
const errorMessage = ref('')

const form = reactive<ProjectCreatePayload>({
  name: '',
  project_type: 'REPLICA',
  source_language: 'zh-CN',
  target_language: 'en-US',
  target_region: 'US',
  scene_strategy: 'MIXED',
  audio_policy: 'REGENERATE_AUDIO',
})

const isVideoProject = computed(() => VIDEO_PROJECT_TYPES.has(form.project_type))

function applyTypeDefaults(): void {
  if (!isVideoProject.value) {
    form.source_language = null
    form.scene_strategy = 'LOCALIZE'
    form.audio_policy = 'REGENERATE_AUDIO'
    return
  }
  if (!form.source_language) form.source_language = 'zh-CN'
  if (form.project_type === 'TRANSLATION') {
    form.scene_strategy = 'KEEP'
    form.audio_policy = 'REGENERATE_AUDIO'
  } else if (form.project_type === 'REDRAW') {
    form.scene_strategy = 'LOCALIZE'
    form.audio_policy = 'KEEP_SOURCE_AUDIO'
  } else {
    form.scene_strategy = 'MIXED'
    form.audio_policy = 'REGENERATE_AUDIO'
  }
}

watch(() => form.project_type, applyTypeDefaults)

async function refreshProjects(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    projects.value = await listProjects()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '项目列表加载失败'
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  if (!form.name.trim()) {
    errorMessage.value = '请填写项目名称'
    return
  }
  creating.value = true
  errorMessage.value = ''
  try {
    const payload: ProjectCreatePayload = {
      ...form,
      name: form.name.trim(),
      source_language: isVideoProject.value ? form.source_language : null,
    }
    const project = await createProject(payload)
    projects.value = [project, ...projects.value]
    form.name = ''
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '创建项目失败'
  } finally {
    creating.value = false
  }
}

onMounted(refreshProjects)

const sceneStrategyOptions: { value: SceneStrategy; label: string }[] = [
  { value: 'KEEP', label: '保持原场景' },
  { value: 'LOCALIZE', label: '本土化场景' },
  { value: 'MIXED', label: '按剧情自动决定' },
]

const audioPolicyOptions: { value: AudioPolicy; label: string }[] = [
  { value: 'KEEP_SOURCE_AUDIO', label: '保留原音频' },
  { value: 'REGENERATE_AUDIO', label: '重建目标音频' },
]
</script>

<template>
  <section class="page-stack">
    <div class="page-heading">
      <div>
        <p class="eyebrow">创建项目</p>
        <h1>你这次想做什么？</h1>
        <p>先选择项目类型。系统会加载对应技能手册，再根据当前素材生成真正需要的执行计划。</p>
      </div>
    </div>

    <form class="create-panel" @submit.prevent="submit">
      <div class="type-grid" aria-label="项目类型">
        <button
          v-for="option in PROJECT_TYPE_OPTIONS"
          :key="option.value"
          type="button"
          class="type-card"
          :class="{ selected: form.project_type === option.value }"
          @click="form.project_type = option.value"
        >
          <span class="type-icon">{{ option.icon }}</span>
          <strong>{{ option.label }}</strong>
          <span>{{ option.description }}</span>
        </button>
      </div>

      <div class="form-grid">
        <label>
          <span>项目名称</span>
          <input v-model="form.name" maxlength="120" placeholder="例如：总裁短剧美国版" />
        </label>

        <label v-if="isVideoProject">
          <span>原始语言</span>
          <select v-model="form.source_language">
            <option v-for="option in LANGUAGE_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>

        <label>
          <span>目标语言</span>
          <select v-model="form.target_language">
            <option v-for="option in LANGUAGE_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>

        <label>
          <span>目标地区</span>
          <select v-model="form.target_region">
            <option v-for="option in REGION_OPTIONS" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>

        <label v-if="isVideoProject">
          <span>场景策略</span>
          <select v-model="form.scene_strategy">
            <option v-for="option in sceneStrategyOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>

        <label v-if="isVideoProject">
          <span>音频策略</span>
          <select v-model="form.audio_policy">
            <option v-for="option in audioPolicyOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
      </div>

      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      <button class="primary-button" type="submit" :disabled="creating">
        {{ creating ? '创建中…' : `创建${projectTypeLabel(form.project_type)}项目` }}
      </button>
    </form>

    <div class="projects-section">
      <div class="section-heading">
        <h2>项目</h2>
        <button type="button" class="text-button" @click="refreshProjects">刷新</button>
      </div>
      <p v-if="loading" class="muted">正在加载项目…</p>
      <p v-else-if="projects.length === 0" class="empty-state">还没有项目，先从上面选择一种类型开始。</p>
      <div v-else class="project-grid">
        <RouterLink v-for="project in projects" :key="project.id" :to="`/projects/${project.id}`" class="project-card">
          <span class="project-type">{{ projectTypeLabel(project.project_type) }}</span>
          <strong>{{ project.name }}</strong>
          <span>{{ project.target_language }} · {{ project.target_region }}</span>
          <small>执行计划版本 {{ project.workflow_revision }}</small>
        </RouterLink>
      </div>
    </div>
  </section>
</template>

<style scoped>
.page-stack { display: grid; gap: 28px; }
.page-heading h1 { margin: 4px 0 8px; font-size: clamp(28px, 4vw, 44px); }
.page-heading p { max-width: 760px; margin: 0; color: #667085; line-height: 1.7; }
.eyebrow { color: #6d5dfc !important; font-size: 13px; font-weight: 800; letter-spacing: .12em; text-transform: uppercase; }
.create-panel { display: grid; gap: 24px; padding: 24px; border: 1px solid #e7e7ef; border-radius: 20px; background: #fff; box-shadow: 0 12px 40px rgba(23, 24, 35, .06); }
.type-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.type-card { display: grid; gap: 7px; min-height: 138px; padding: 18px; border: 1px solid #e5e6ec; border-radius: 16px; background: #fafafa; text-align: left; cursor: pointer; color: inherit; }
.type-card:hover { border-color: #b8b2ff; }
.type-card.selected { border-color: #6d5dfc; background: #f3f1ff; box-shadow: inset 0 0 0 1px #6d5dfc; }
.type-card strong { font-size: 16px; }
.type-card span:last-child { color: #667085; line-height: 1.45; font-size: 13px; }
.type-icon { font-size: 24px; }
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
label { display: grid; gap: 7px; font-size: 13px; font-weight: 700; color: #344054; }
input, select { width: 100%; min-height: 42px; padding: 9px 11px; border: 1px solid #d9dce5; border-radius: 10px; background: #fff; color: #1d2939; font: inherit; }
.primary-button { justify-self: start; min-height: 42px; padding: 0 18px; border: 0; border-radius: 10px; background: #111827; color: #fff; font-weight: 700; cursor: pointer; }
.primary-button:disabled { opacity: .55; cursor: default; }
.error-message { margin: 0; color: #b42318; }
.projects-section { display: grid; gap: 14px; }
.section-heading { display: flex; align-items: center; justify-content: space-between; }
.section-heading h2 { margin: 0; }
.text-button { border: 0; background: transparent; color: #5b4ee8; cursor: pointer; }
.project-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.project-card { display: grid; gap: 7px; padding: 18px; border: 1px solid #e7e7ef; border-radius: 14px; background: #fff; color: inherit; text-decoration: none; }
.project-card:hover { border-color: #a8a2f5; }
.project-card > span:not(.project-type), .project-card small, .muted, .empty-state { color: #667085; }
.project-type { justify-self: start; padding: 4px 8px; border-radius: 999px; background: #f1f0ff; color: #5b4ee8; font-size: 12px; font-weight: 800; }
.empty-state { padding: 28px; border: 1px dashed #d5d7df; border-radius: 14px; text-align: center; }
@media (max-width: 900px) { .type-grid, .form-grid, .project-grid { grid-template-columns: 1fr 1fr; } }
@media (max-width: 640px) { .type-grid, .form-grid, .project-grid { grid-template-columns: 1fr; } .create-panel { padding: 16px; } }
</style>
