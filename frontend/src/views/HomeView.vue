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

interface SourceAsset {
  id: string
  original_filename: string
  mime_type: string
  size_bytes: number
}

interface Episode {
  id: string
  source_asset: SourceAsset
  episode_order: number
  duration_us: number
  width: number
  height: number
  has_audio: boolean
}

interface SourceDocument {
  id: string
  source_asset: SourceAsset
  revision: number
  document_format: 'TXT' | 'MARKDOWN'
  char_count: number
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

const videoProjectTypes: ProjectType[] = ['REPLICA', 'REDRAW', 'TRANSLATION']

const skills = ref<RootSkill[]>([])
const projects = ref<Project[]>([])
const selectedProjectId = ref<string | null>(null)
const plan = ref<ProjectPlan | null>(null)
const episodes = ref<Episode[]>([])
const sourceDocument = ref<SourceDocument | null>(null)
const loading = ref(true)
const sourceLoading = ref(false)
const saving = ref(false)
const uploading = ref(false)
const reordering = ref(false)
const draggedEpisodeId = ref<string | null>(null)
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

const isVideoProject = computed(() => videoProjectTypes.includes(form.project_type))
const selectedProject = computed(() =>
  projects.value.find((item) => item.id === selectedProjectId.value) ?? null,
)
const selectedIsVideoProject = computed(() =>
  selectedProject.value ? videoProjectTypes.includes(selectedProject.value.project_type) : false,
)
const sourceTitle = computed(() => {
  if (!selectedProject.value) return '原始素材'
  if (selectedIsVideoProject.value) return '原片剧集'
  return selectedProject.value.project_type === 'NOVEL_TO_DRAMA' ? '原始小说' : '原始剧本'
})

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

function humanDuration(durationUs: number) {
  const seconds = durationUs / 1_000_000
  if (seconds < 60) return `${seconds.toFixed(1)} 秒`
  const minutes = Math.floor(seconds / 60)
  const remaining = Math.round(seconds % 60)
  return `${minutes}分${remaining}秒`
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

async function loadSources(project: Project) {
  sourceLoading.value = true
  episodes.value = []
  sourceDocument.value = null
  try {
    if (videoProjectTypes.includes(project.project_type)) {
      episodes.value = await apiRequest<Episode[]>(`/projects/${project.id}/sources/episodes`)
      return
    }
    try {
      sourceDocument.value = await apiRequest<SourceDocument>(`/projects/${project.id}/sources/document`)
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return
      throw error
    }
  } finally {
    sourceLoading.value = false
  }
}

async function selectProject(projectId: string) {
  selectedProjectId.value = projectId
  message.value = ''
  const project = projects.value.find((item) => item.id === projectId)
  await Promise.all([loadPlan(projectId), project ? loadSources(project) : Promise.resolve()])
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
  if (project) project.current_plan_id = plan.value.id
  message.value = '执行计划已根据当前素材重新生成。'
}

function markSourceChanged() {
  plan.value = null
  if (selectedProject.value) selectedProject.value.current_plan_id = null
  message.value = '原始素材已更新，请重新生成执行计划。'
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
    episodes.value = []
    sourceDocument.value = null
    await compilePlan(project.id)
    form.name = ''
    message.value = '项目已创建。现在可以导入原始素材。'
  } catch (error) {
    message.value = error instanceof Error ? error.message : '项目创建失败'
  } finally {
    saving.value = false
  }
}

async function uploadVideos(event: Event) {
  const input = event.target as HTMLInputElement
  if (!selectedProject.value || !input.files?.length) return
  uploading.value = true
  message.value = ''
  try {
    const data = new FormData()
    Array.from(input.files).forEach((file) => data.append('files', file))
    await apiRequest<Episode[]>(`/projects/${selectedProject.value.id}/sources/videos`, {
      method: 'POST',
      body: data,
    })
    episodes.value = await apiRequest<Episode[]>(`/projects/${selectedProject.value.id}/sources/episodes`)
    markSourceChanged()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '原片上传失败'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

async function uploadDocument(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!selectedProject.value || !file) return
  uploading.value = true
  message.value = ''
  try {
    const data = new FormData()
    data.append('file', file)
    sourceDocument.value = await apiRequest<SourceDocument>(
      `/projects/${selectedProject.value.id}/sources/document`,
      { method: 'POST', body: data },
    )
    markSourceChanged()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '文本上传失败'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

function startEpisodeDrag(episodeId: string) {
  draggedEpisodeId.value = episodeId
}

async function dropEpisode(targetEpisodeId: string) {
  if (!selectedProject.value || !draggedEpisodeId.value || reordering.value) return
  const sourceId = draggedEpisodeId.value
  draggedEpisodeId.value = null
  if (sourceId === targetEpisodeId) return

  const ids = episodes.value.map((item) => item.id)
  const sourceIndex = ids.indexOf(sourceId)
  const targetIndex = ids.indexOf(targetEpisodeId)
  if (sourceIndex < 0 || targetIndex < 0) return
  const [moved] = ids.splice(sourceIndex, 1)
  ids.splice(targetIndex, 0, moved)

  reordering.value = true
  try {
    episodes.value = await apiRequest<Episode[]>(
      `/projects/${selectedProject.value.id}/sources/episodes/reorder`,
      { method: 'POST', body: JSON.stringify({ episode_ids: ids }) },
    )
    markSourceChanged()
  } catch (error) {
    message.value = error instanceof Error ? error.message : '剧集排序失败'
  } finally {
    reordering.value = false
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
          <small>流程 r{{ project.workflow_revision }}</small>
        </button>
      </div>

      <div class="panel source-panel">
        <div class="section-heading source-heading">
          <div>
            <p class="eyebrow">原始素材</p>
            <h2>{{ selectedProject ? sourceTitle : '选择一个项目' }}</h2>
          </div>
          <label v-if="selectedProject && selectedIsVideoProject" class="upload-button">
            <span>{{ uploading ? '正在导入…' : '上传原片' }}</span>
            <input
              class="visually-hidden"
              type="file"
              multiple
              accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm,.avi,.m4v"
              :disabled="uploading"
              @change="uploadVideos"
            />
          </label>
          <label v-else-if="selectedProject" class="upload-button">
            <span>{{ uploading ? '正在导入…' : sourceDocument ? '替换文本' : '上传文本' }}</span>
            <input
              class="visually-hidden"
              type="file"
              accept=".txt,.md,.markdown,text/plain,text/markdown"
              :disabled="uploading"
              @change="uploadDocument"
            />
          </label>
        </div>

        <p v-if="!selectedProject" class="empty">从左侧选择项目后导入素材。</p>
        <p v-else-if="sourceLoading" class="muted">正在读取原始素材…</p>

        <template v-else-if="selectedProject && selectedIsVideoProject">
          <p v-if="episodes.length === 0" class="empty">还没有原片。可以一次选择多集，上传顺序就是初始剧集顺序。</p>
          <p v-else class="source-help">拖动剧集可以调整顺序。这里只展示你真正需要确认的集数、文件和时长。</p>
          <ol v-if="episodes.length" class="episode-list">
            <li
              v-for="episode in episodes"
              :key="episode.id"
              class="episode-row"
              draggable="true"
              @dragstart="startEpisodeDrag(episode.id)"
              @dragover.prevent
              @drop.prevent="dropEpisode(episode.id)"
            >
              <span class="drag-handle" title="拖动排序">⋮⋮</span>
              <span class="episode-number">第 {{ episode.episode_order }} 集</span>
              <span class="episode-file">{{ episode.source_asset.original_filename }}</span>
              <span class="episode-duration">{{ humanDuration(episode.duration_us) }}</span>
            </li>
          </ol>
          <p v-if="reordering" class="muted">正在保存剧集顺序…</p>
        </template>

        <template v-else-if="selectedProject">
          <div v-if="sourceDocument" class="document-card">
            <div>
              <strong>{{ sourceDocument.source_asset.original_filename }}</strong>
              <p>当前版本 r{{ sourceDocument.revision }} · {{ sourceDocument.char_count.toLocaleString() }} 字符</p>
            </div>
            <span>{{ sourceDocument.document_format === 'MARKDOWN' ? 'Markdown' : 'TXT' }}</span>
          </div>
          <p v-else class="empty">还没有{{ selectedProject.project_type === 'NOVEL_TO_DRAMA' ? '小说' : '剧本' }}文本。当前支持 TXT 和 Markdown。</p>
        </template>
      </div>
    </section>

    <section class="panel">
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
          重新生成执行计划
        </button>
      </div>

      <p v-if="selectedProject && !plan" class="empty">当前没有可用计划。项目配置或原始素材变化后，需要显式重新生成。</p>
      <p v-else-if="!selectedProject" class="empty">选择项目后查看执行计划。</p>

      <ol v-if="plan" class="plan-list">
        <li v-for="(step, index) in plan.steps" :key="step.id" class="plan-step">
          <div class="step-index">{{ String(index + 1).padStart(2, '0') }}</div>
          <div class="step-body">
            <div class="step-title-row">
              <strong>{{ step.title }}</strong>
              <span class="status-pill" :data-status="step.status">{{ statusLabels[step.status] }}</span>
            </div>
            <p>{{ step.description }}</p>
          </div>
        </li>
      </ol>
    </section>
  </div>
</template>
