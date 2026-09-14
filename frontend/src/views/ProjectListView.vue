<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

import { createProject, listProjects } from '@/features/projects/api'
import {
  LANGUAGE_OPTIONS, PROJECT_TYPE_OPTIONS, REGION_OPTIONS, VIDEO_PROJECT_TYPES, projectTypeLabel,
  type AudioPolicy, type ProjectCreatePayload, type ProjectRead, type ProjectType, type SceneStrategy,
} from '@/features/projects/types'

type ProjectFilter = 'ALL' | 'ACTIVE' | 'ARCHIVED'
type ViewMode = 'GRID' | 'LIST'
type SortMode = 'UPDATED_DESC' | 'CREATED_DESC' | 'NAME_ASC'

const projects = ref<ProjectRead[]>([])
const loading = ref(true)
const creating = ref(false)
const createOpen = ref(false)
const errorMessage = ref('')
const searchQuery = ref('')
const activeFilter = ref<ProjectFilter>('ALL')
const viewMode = ref<ViewMode>('GRID')
const sortMode = ref<SortMode>('UPDATED_DESC')

const form = reactive<ProjectCreatePayload>({
  name: '', project_type: 'REPLICA', source_language: 'zh-CN', target_language: 'en-US',
  target_region: 'US', scene_strategy: 'MIXED', audio_policy: 'REGENERATE_AUDIO',
})

const isVideoProject = computed(() => VIDEO_PROJECT_TYPES.has(form.project_type))
const filteredProjects = computed(() => {
  const query = searchQuery.value.trim().toLocaleLowerCase()
  const rows = projects.value.filter((project) => {
    const statusMatches = activeFilter.value === 'ALL' || project.status === activeFilter.value
    const queryMatches = !query || [project.name, projectTypeLabel(project.project_type), project.target_language, project.target_region]
      .some((value) => value.toLocaleLowerCase().includes(query))
    return statusMatches && queryMatches
  })
  return [...rows].sort((left, right) => {
    if (sortMode.value === 'NAME_ASC') return left.name.localeCompare(right.name, 'zh-CN')
    const key = sortMode.value === 'CREATED_DESC' ? 'created_at' : 'updated_at'
    return new Date(right[key]).getTime() - new Date(left[key]).getTime()
  })
})

const sceneStrategyOptions: { value: SceneStrategy; label: string }[] = [
  { value: 'KEEP', label: '保持原场景' }, { value: 'LOCALIZE', label: '本土化场景' }, { value: 'MIXED', label: '按剧情自动决定' },
]
const audioPolicyOptions: { value: AudioPolicy; label: string }[] = [
  { value: 'KEEP_SOURCE_AUDIO', label: '保留原音频' }, { value: 'REGENERATE_AUDIO', label: '重建目标音频' },
]

function countByStatus(status: ProjectFilter): number {
  return status === 'ALL' ? projects.value.length : projects.value.filter((project) => project.status === status).length
}

function applyTypeDefaults(): void {
  if (!isVideoProject.value) {
    form.source_language = null
    form.scene_strategy = 'LOCALIZE'
    form.audio_policy = 'REGENERATE_AUDIO'
  } else {
    if (!form.source_language) form.source_language = 'zh-CN'
    form.scene_strategy = form.project_type === 'TRANSLATION' ? 'KEEP' : form.project_type === 'REDRAW' ? 'LOCALIZE' : 'MIXED'
    form.audio_policy = form.project_type === 'REDRAW' ? 'KEEP_SOURCE_AUDIO' : 'REGENERATE_AUDIO'
  }
}
watch(() => form.project_type, applyTypeDefaults)

async function refreshProjects(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try { projects.value = await listProjects() }
  catch (error) { errorMessage.value = error instanceof Error ? error.message : '项目列表加载失败' }
  finally { loading.value = false }
}

async function submit(): Promise<void> {
  if (!form.name.trim()) { errorMessage.value = '请填写项目名称'; return }
  creating.value = true
  errorMessage.value = ''
  try {
    const project = await createProject({ ...form, name: form.name.trim(), source_language: isVideoProject.value ? form.source_language : null })
    projects.value = [project, ...projects.value]
    form.name = ''
    createOpen.value = false
    activeFilter.value = 'ALL'
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : '创建项目失败' }
  finally { creating.value = false }
}

function relativeDate(value: string): string {
  const time = new Date(value).getTime()
  if (Number.isNaN(time)) return '最近更新'
  const seconds = Math.max(0, Math.floor((Date.now() - time) / 1000))
  if (seconds < 60) return '刚刚更新'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分钟前更新`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小时前更新`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)} 天前更新`
  const date = new Date(time)
  return `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()} 更新`
}

function typeTone(type: ProjectType): string { return `tone-${type.toLowerCase().replaceAll('_', '-')}` }
onMounted(refreshProjects)
</script>

<template>
  <section class="projects-page">
    <header class="projects-hero">
      <div><h1>我的项目</h1><p>管理你的短剧项目，继续创作或开启一段新故事。</p></div>
      <button class="primary-action" type="button" @click="createOpen = true">＋ 新建项目</button>
    </header>

    <div class="project-toolbar">
      <div class="filter-tabs" role="tablist" aria-label="项目状态筛选">
        <button v-for="filter in (['ALL','ACTIVE','ARCHIVED'] as ProjectFilter[])" :key="filter" type="button" role="tab"
          :aria-selected="activeFilter === filter" :class="{ active: activeFilter === filter }" @click="activeFilter = filter">
          {{ filter === 'ALL' ? '全部' : filter === 'ACTIVE' ? '进行中' : '已归档' }} <span>{{ countByStatus(filter) }}</span>
        </button>
      </div>
      <div class="toolbar-actions">
        <label class="search-field">
          <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m16.5 16.5 4 4"/></svg>
          <span class="visually-hidden">搜索项目</span><input v-model="searchQuery" type="search" placeholder="搜索项目名称、类型或地区…" />
        </label>
        <label class="sort-field"><span class="visually-hidden">项目排序</span><select v-model="sortMode"><option value="UPDATED_DESC">最近更新</option><option value="CREATED_DESC">最近创建</option><option value="NAME_ASC">按名称</option></select></label>
        <div class="view-switch" aria-label="视图切换">
          <button type="button" :class="{ active: viewMode === 'GRID' }" aria-label="网格视图" @click="viewMode = 'GRID'"><svg viewBox="0 0 24 24"><rect x="4" y="4" width="6" height="6"/><rect x="14" y="4" width="6" height="6"/><rect x="4" y="14" width="6" height="6"/><rect x="14" y="14" width="6" height="6"/></svg></button>
          <button type="button" :class="{ active: viewMode === 'LIST' }" aria-label="列表视图" @click="viewMode = 'LIST'"><svg viewBox="0 0 24 24"><path d="M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01"/></svg></button>
        </div>
      </div>
    </div>

    <p v-if="errorMessage && !createOpen" class="error-banner" role="alert">{{ errorMessage }}<button type="button" @click="refreshProjects">重试</button></p>
    <div v-if="loading" class="project-collection"><div v-for="index in 8" :key="index" class="project-skeleton" /></div>
    <div v-else-if="filteredProjects.length" class="project-collection" :class="{ 'is-list': viewMode === 'LIST' }">
      <article v-for="project in filteredProjects" :key="project.id" class="project-card">
        <RouterLink :to="`/projects/${project.id}`" class="project-cover" :class="typeTone(project.project_type)" :aria-label="`打开项目：${project.name}`">
          <span class="cover-orb one"/><span class="cover-orb two"/>
          <span class="cover-mark" aria-hidden="true">{{ PROJECT_TYPE_OPTIONS.find((item) => item.value === project.project_type)?.icon }}</span>
          <span class="status-chip" :class="{ archived: project.status === 'ARCHIVED' }"><i/>{{ project.status === 'ARCHIVED' ? '已归档' : '进行中' }}</span>
        </RouterLink>
        <div class="project-card-body">
          <div class="project-title-row"><RouterLink :to="`/projects/${project.id}`">{{ project.name }}</RouterLink><span aria-hidden="true">•••</span></div>
          <div class="project-kind">◆ {{ projectTypeLabel(project.project_type) }}</div>
          <p>{{ project.target_language }} · {{ project.target_region }} · 工作流版本 {{ project.workflow_revision }}</p>
          <time :datetime="project.updated_at">{{ relativeDate(project.updated_at) }}</time>
        </div>
      </article>
    </div>
    <div v-else class="empty-projects">
      <div class="empty-illustration" aria-hidden="true">＋</div>
      <h2>{{ searchQuery ? '没有找到匹配的项目' : '这里还没有项目' }}</h2>
      <p>{{ searchQuery ? '换个关键词，或清除搜索后再试试。' : '创建你的第一个短剧项目，从素材到成片都在这里完成。' }}</p>
      <button v-if="!searchQuery" class="primary-action" type="button" @click="createOpen = true">＋ 新建项目</button>
      <button v-else class="link-action" type="button" @click="searchQuery = ''">清除搜索</button>
    </div>

    <Teleport to="body">
      <div v-if="createOpen" class="dialog-backdrop" @click.self="!creating && (createOpen = false)">
        <section class="create-dialog" role="dialog" aria-modal="true" aria-labelledby="create-title">
          <header><div><p>开始创作</p><h2 id="create-title">新建项目</h2></div><button type="button" aria-label="关闭" @click="createOpen = false">×</button></header>
          <form @submit.prevent="submit">
            <label class="field-wide"><span>项目名称</span><input v-model="form.name" autofocus maxlength="120" placeholder="给项目起个容易识别的名字" /></label>
            <fieldset class="field-wide"><legend>项目类型</legend><div class="type-options">
              <button v-for="option in PROJECT_TYPE_OPTIONS" :key="option.value" type="button" :class="{ selected: form.project_type === option.value }" @click="form.project_type = option.value"><span>{{ option.icon }}</span><strong>{{ option.label }}</strong></button>
            </div></fieldset>
            <div class="dialog-fields">
              <label><span>目标语言</span><select v-model="form.target_language"><option v-for="option in LANGUAGE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label><span>目标地区</span><select v-model="form.target_region"><option v-for="option in REGION_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            </div>
            <details class="advanced-settings"><summary>高级设置</summary><div class="dialog-fields">
              <label v-if="isVideoProject"><span>原始语言</span><select v-model="form.source_language"><option v-for="option in LANGUAGE_OPTIONS" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label v-if="isVideoProject"><span>场景策略</span><select v-model="form.scene_strategy"><option v-for="option in sceneStrategyOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
              <label v-if="isVideoProject"><span>声音策略</span><select v-model="form.audio_policy"><option v-for="option in audioPolicyOptions" :key="option.value" :value="option.value">{{ option.label }}</option></select></label>
            </div></details>
            <p v-if="errorMessage" class="dialog-error" role="alert">{{ errorMessage }}</p>
            <footer><button class="cancel-action" type="button" @click="createOpen = false">取消</button><button class="primary-action" type="submit" :disabled="creating">{{ creating ? '创建中…' : '创建项目' }}</button></footer>
          </form>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.projects-page{display:grid;gap:24px;color:#172036}.projects-hero{display:flex;align-items:flex-end;justify-content:space-between;gap:24px}.projects-hero h1{margin:0;font-size:clamp(30px,4vw,42px);line-height:1.15;letter-spacing:-.035em}.projects-hero p{margin:9px 0 0;color:#778198;font-size:14px}.primary-action{display:inline-flex;align-items:center;justify-content:center;min-height:42px;padding:0 17px;border:0;border-radius:8px;background:#2878ff;color:#fff;font-weight:700;box-shadow:0 8px 20px rgba(40,120,255,.2);cursor:pointer}.primary-action:hover{background:#1768ec;transform:translateY(-1px)}.primary-action:disabled{opacity:.6;cursor:progress;transform:none}.project-toolbar{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;border-bottom:1px solid #e8ebf2}.filter-tabs{display:flex;align-items:center;gap:26px}.filter-tabs button{position:relative;padding:0 0 13px;border:0;background:transparent;color:#788297;font-size:13px;cursor:pointer}.filter-tabs span{color:#a3aabb}.filter-tabs button.active{color:#2878ff;font-weight:700}.filter-tabs button.active:after{content:'';position:absolute;right:0;bottom:-1px;left:0;height:3px;border-radius:3px 3px 0 0;background:#2878ff}.toolbar-actions{display:flex;align-items:center;gap:9px;padding-bottom:10px}.search-field{display:flex;align-items:center;width:min(320px,29vw);height:36px;padding:0 11px;border:1px solid #e1e5ed;border-radius:8px;background:#fff}.search-field:focus-within{border-color:#78a7ff;box-shadow:0 0 0 3px rgba(40,120,255,.1)}.search-field svg{width:17px;fill:none;stroke:#98a1b3;stroke-width:1.8}.search-field input{width:100%;height:100%;padding:0 0 0 8px;border:0;outline:0;background:transparent;font-size:12px}.sort-field select{height:36px;padding:0 30px 0 11px;border:1px solid #e1e5ed;border-radius:8px;background:#fff;color:#667188;font-size:12px}.view-switch{display:flex;padding:3px;border:1px solid #e1e5ed;border-radius:8px;background:#fff}.view-switch button{display:grid;place-items:center;width:30px;height:28px;border:0;border-radius:5px;background:transparent;cursor:pointer}.view-switch button.active{background:#edf4ff;color:#2878ff}.view-switch svg{width:16px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round}.view-switch rect{fill:currentColor;stroke:none}.project-collection{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:18px}.project-card{min-width:0;overflow:hidden;border:1px solid #e7eaf0;border-radius:10px;background:#fff;box-shadow:0 3px 14px rgba(40,54,85,.05);transition:.18s}.project-card:hover{transform:translateY(-3px);border-color:#cad8ee;box-shadow:0 10px 26px rgba(34,63,112,.12)}.project-cover{position:relative;display:block;height:138px;overflow:hidden;background:linear-gradient(135deg,#dce9ff,#f5d7cf);text-decoration:none}.project-cover:after{content:'';position:absolute;inset:auto 12% -36% 12%;height:90%;border-radius:50% 50% 20% 20%;background:linear-gradient(140deg,rgba(255,255,255,.9),rgba(255,255,255,.15));transform:rotate(-8deg)}.tone-redraw{background:linear-gradient(135deg,#d9f0df,#b6c99d 48%,#ead7b3)}.tone-translation{background:linear-gradient(135deg,#b9c6eb,#edd2d9 56%,#d8a991)}.tone-novel-to-drama{background:linear-gradient(135deg,#cbd7e8,#aec1cf 50%,#5c7c96)}.tone-script-to-drama{background:linear-gradient(135deg,#f1d9ae,#d99972 50%,#77574b)}.tone-script-localization{background:linear-gradient(135deg,#cac7f4,#9aa8dd 52%,#6276ac)}.cover-orb{position:absolute;z-index:1;border-radius:50%;background:rgba(255,255,255,.45)}.cover-orb.one{width:88px;height:88px;top:-20px;right:-10px}.cover-orb.two{width:54px;height:54px;bottom:-10px;left:15%;background:rgba(32,55,99,.12)}.cover-mark{position:absolute;z-index:2;top:50%;left:50%;font-size:42px;filter:drop-shadow(0 7px 10px rgba(26,39,67,.2));transform:translate(-50%,-50%)}.status-chip{position:absolute;z-index:3;top:10px;left:10px;display:inline-flex;align-items:center;gap:5px;padding:4px 8px;border-radius:999px;background:rgba(232,253,244,.94);color:#159664;font-size:10px;font-weight:750}.status-chip i{width:5px;height:5px;border-radius:50%;background:currentColor}.status-chip.archived{background:rgba(242,244,248,.94);color:#6e788a}.project-card-body{display:grid;gap:7px;padding:13px 14px 14px}.project-title-row{display:flex;align-items:center;justify-content:space-between;gap:10px}.project-title-row a{min-width:0;overflow:hidden;color:#192238;font-size:14px;font-weight:750;text-decoration:none;text-overflow:ellipsis;white-space:nowrap}.project-title-row a:hover{color:#2878ff}.project-title-row span{color:#9ba3b3;font-size:11px;letter-spacing:1px}.project-kind{color:#2878ff;font-size:11px;font-weight:700}.project-card-body p{overflow:hidden;margin:0;color:#7c8598;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.project-card-body time{color:#a0a7b6;font-size:10px}.project-collection.is-list{grid-template-columns:1fr;gap:10px}.is-list .project-card{display:grid;grid-template-columns:190px 1fr}.is-list .project-cover{height:112px}.is-list .project-card-body{align-content:center}.project-skeleton{height:242px;border-radius:10px;background:linear-gradient(100deg,#edf0f5 25%,#f8f9fb 40%,#edf0f5 55%);background-size:220% 100%;animation:shimmer 1.3s infinite linear}@keyframes shimmer{to{background-position-x:-220%}}.error-banner{display:flex;justify-content:space-between;margin:0;padding:12px 14px;border:1px solid #ffd3d0;border-radius:9px;background:#fff3f2;color:#a83932;font-size:13px}.error-banner button,.link-action{border:0;background:transparent;color:#2878ff;font-weight:700;cursor:pointer}.empty-projects{display:grid;justify-items:center;padding:76px 20px;border:1px dashed #d9deea;border-radius:12px;background:rgba(255,255,255,.55);text-align:center}.empty-illustration{display:grid;place-items:center;width:84px;height:66px;border:1px solid #cfd9ec;border-radius:12px;background:linear-gradient(145deg,#eef4ff,#fff);box-shadow:12px -8px 0 -2px #e5edfb;color:#2878ff;font-size:27px}.empty-projects h2{margin:22px 0 7px;font-size:18px}.empty-projects p{margin:0 0 20px;color:#7c8699;font-size:13px}.visually-hidden{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.dialog-backdrop{position:fixed;z-index:100;inset:0;display:grid;place-items:center;padding:24px;background:rgba(19,28,48,.48);backdrop-filter:blur(3px)}.create-dialog{width:min(720px,100%);max-height:calc(100vh - 48px);overflow:auto;border-radius:16px;background:#fff;box-shadow:0 28px 80px rgba(13,25,50,.26)}.create-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:23px 24px 18px;border-bottom:1px solid #eceef3}.create-dialog header p{margin:0 0 4px;color:#2878ff;font-size:11px;font-weight:800;letter-spacing:.12em;text-transform:uppercase}.create-dialog h2{margin:0;font-size:24px}.create-dialog header button{width:34px;height:34px;border:0;border-radius:7px;background:#f4f6f9;color:#687287;font-size:22px;cursor:pointer}.create-dialog form{display:grid;gap:20px;padding:22px 24px 24px}.create-dialog label,.create-dialog fieldset{display:grid;gap:7px;min-width:0;margin:0;padding:0;border:0;color:#39445a;font-size:12px;font-weight:700}.create-dialog legend{margin-bottom:9px}.create-dialog input,.create-dialog select{width:100%;height:41px;padding:0 11px;border:1px solid #dce1ea;border-radius:8px;background:#fff;outline:0}.type-options{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.type-options button{display:flex;align-items:center;gap:8px;min-height:48px;padding:8px 10px;border:1px solid #e1e5ed;border-radius:8px;background:#fff;font-size:12px;text-align:left;cursor:pointer}.type-options button.selected{border-color:#2878ff;background:#eff5ff;color:#1d67dc;box-shadow:inset 0 0 0 1px #2878ff}.type-options button span{font-size:18px}.dialog-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.dialog-error{margin:0;color:#bb3e36;font-size:13px}.create-dialog footer{display:flex;justify-content:flex-end;gap:10px}.cancel-action{min-height:42px;padding:0 18px;border:1px solid #dfe3eb;border-radius:8px;background:#fff;color:#5f697d;font-weight:700;cursor:pointer}@media(max-width:1100px){.project-collection{grid-template-columns:repeat(3,minmax(0,1fr))}.project-toolbar{align-items:stretch;flex-direction:column}.toolbar-actions{align-self:flex-end}}@media(max-width:760px){.projects-hero{align-items:flex-start;flex-direction:column}.project-collection{grid-template-columns:repeat(2,minmax(0,1fr))}.toolbar-actions{width:100%;flex-wrap:wrap}.search-field{width:100%}.dialog-fields,.type-options{grid-template-columns:1fr 1fr}}@media(max-width:520px){.project-collection{grid-template-columns:1fr}.is-list .project-card{grid-template-columns:112px 1fr}.is-list .project-cover{height:122px}.dialog-fields,.type-options{grid-template-columns:1fr}}
.project-card{display:block;width:auto;margin-top:0;text-align:left;cursor:default}.project-cover{width:100%}
</style>
