<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { remakeApi } from '../api/remake'
import type { ScenePolicy } from '../types/remake'
import type { BackgroundTask, Project } from '../types/studio'

interface ProjectSummary {
  reviewCount: number
  activeTask: BackgroundTask | null
}

const router = useRouter()
const projects = ref<Project[]>([])
const summaries = reactive<Record<string, ProjectSummary>>({})
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const form = reactive({
  name: '',
  source_language: 'zh-CN',
  target_language: 'en-US',
  target_region: 'US',
  scene_policy: 'AUTO' as ScenePolicy,
})

const languageOptions = [
  ['zh-CN', '中文（简体）'], ['en-US', '英语'], ['ja-JP', '日语'], ['ko-KR', '韩语'],
  ['es-ES', '西班牙语'], ['pt-BR', '葡萄牙语'], ['fr-FR', '法语'], ['de-DE', '德语'],
]
const regionOptions = [
  ['US', '美国'], ['GB', '英国'], ['CA', '加拿大'], ['AU', '澳大利亚'],
  ['JP', '日本'], ['KR', '韩国'], ['SG', '新加坡'], ['BR', '巴西'],
]
const scenePolicies: Array<[ScenePolicy, string, string]> = [
  ['AUTO', '智能判断（推荐）', '普通环境尽量保留；明显地域化场景自动替换'],
  ['KEEP', '尽量保留原场景', '主要替换人物、语言和声音，降低生成成本'],
  ['LOCALIZE', '场景全部本土化', '人物和环境都按目标地区重新设计'],
]

async function loadSummary(project: Project): Promise<void> {
  const [reviewResult, taskResult] = await Promise.allSettled([
    remakeApi.listReviewIssues(project.id, 'OPEN'),
    api.listProjectTasks(project.id, 20),
  ])
  const tasks = taskResult.status === 'fulfilled' ? taskResult.value : []
  summaries[project.id] = {
    reviewCount: reviewResult.status === 'fulfilled' ? reviewResult.value.length : 0,
    activeTask: tasks.find((task) => task.status === 'QUEUED' || task.status === 'PROCESSING') ?? null,
  }
}

async function loadProjects(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    projects.value = await api.listProjects()
    await Promise.allSettled(projects.value.map(loadSummary))
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目读取失败'
  } finally {
    loading.value = false
  }
}

async function submit(): Promise<void> {
  if (!form.name.trim() || saving.value) return
  saving.value = true
  error.value = ''
  try {
    const project = await api.createProject({
      name: form.name.trim(),
      source_language: form.source_language,
      target_language: form.target_language,
      target_region: form.target_region,
    })
    await remakeApi.updatePolicy(project.id, form.scene_policy)
    await router.push(`/projects/${project.id}?view=project`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建项目失败'
  } finally {
    saving.value = false
  }
}

function openProject(project: Project): void {
  const summary = summaries[project.id]
  const view = summary?.reviewCount ? 'review' : 'project'
  void router.push(`/projects/${project.id}?view=${view}`)
}

function episodeSummary(project: Project): string {
  const shots = project.episodes.reduce((sum, item) => sum + item.shot_count, 0)
  return `${project.episodes.length} 集 · ${shots} 个镜头`
}

onMounted(loadProjects)
</script>

<template>
  <main class="project-home-v4">
    <header class="hero">
      <div>
        <small>AI Drama Studio</small>
        <h1>短剧本土化重拍</h1>
        <p>导入原短剧，系统自动理解剧情、镜头、人物和对白；只把真正不确定的内容交给你确认，最终使用本地 MiniMax H3 重拍。</p>
      </div>
      <div class="engine-pill"><span>生成引擎</span><strong>MiniMax H3 · Local</strong></div>
    </header>

    <section class="home-grid">
      <form class="create-card" @submit.prevent="submit">
        <header><div><small>新项目</small><h2>确定出海目标</h2></div><span>人物默认本土化</span></header>
        <label><span>项目名称</span><input v-model="form.name" maxlength="200" placeholder="例如：豪门短剧 · 美国版" /></label>
        <div class="two-columns">
          <label><span>原项目语言</span><select v-model="form.source_language"><option v-for="item in languageOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <label><span>目标语言</span><select v-model="form.target_language"><option v-for="item in languageOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
        </div>
        <label><span>目标地区</span><select v-model="form.target_region"><option v-for="item in regionOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>

        <fieldset class="scene-policy">
          <legend>场景处理</legend>
          <label v-for="item in scenePolicies" :key="item[0]" :class="{ active: form.scene_policy === item[0] }">
            <input v-model="form.scene_policy" type="radio" :value="item[0]" />
            <span><strong>{{ item[1] }}</strong><small>{{ item[2] }}</small></span>
          </label>
        </fieldset>

        <div class="fixed-rules"><span>固定规则</span><strong>人物替换为目标地区角色 · 语言翻译并重新对口型 · 对白时长自动重排镜头</strong></div>
        <button class="primary" :disabled="saving || !form.name.trim()">{{ saving ? '正在创建…' : '创建项目' }}</button>
        <p v-if="error" class="error">{{ error }}</p>
      </form>

      <section class="projects-card">
        <header><div><small>已有项目</small><h2>继续工作</h2></div><button @click="loadProjects">刷新</button></header>
        <div v-if="loading" class="empty">正在读取项目…</div>
        <div v-else-if="!projects.length" class="empty"><strong>还没有项目</strong><span>创建项目后导入短剧即可开始自动处理。</span></div>
        <div v-else class="project-list">
          <button v-for="project in projects" :key="project.id" class="project-row" @click="openProject(project)">
            <div class="project-main"><strong>{{ project.name }}</strong><span>{{ project.source_language }} → {{ project.target_language }} · {{ project.target_region }}</span></div>
            <div><small>素材</small><strong>{{ episodeSummary(project) }}</strong></div>
            <div v-if="summaries[project.id]?.activeTask" class="state processing"><small>状态</small><strong>{{ summaries[project.id].activeTask?.title }}</strong></div>
            <div v-else-if="summaries[project.id]?.reviewCount" class="state review"><small>待确认</small><strong>{{ summaries[project.id].reviewCount }} 项</strong></div>
            <div v-else class="state"><small>状态</small><strong>{{ project.episodes.length ? '可继续处理' : '等待导入' }}</strong></div>
            <b>打开 →</b>
          </button>
        </div>
      </section>
    </section>
  </main>
</template>

<style scoped>
.project-home-v4 { min-height: 100vh; padding: 28px; background: #f4f6f9; color: #2d3d55; }
.hero { max-width: 1500px; margin: 0 auto 18px; display: flex; justify-content: space-between; gap: 24px; align-items: end; padding: 24px 26px; border: 1px solid #dfe5ed; border-radius: 18px; background: #fff; }
.hero small, .create-card header small, .projects-card header small { color: #7188ad; font-size: 10px; font-weight: 850; letter-spacing: .06em; }
.hero h1 { margin: 4px 0 6px; font-size: 30px; }
.hero p { max-width: 900px; margin: 0; color: #718096; font-size: 13px; line-height: 1.65; }
.engine-pill { display: grid; gap: 2px; min-width: 210px; padding: 12px 14px; border-radius: 12px; background: #eef4ff; }
.engine-pill span { color: #7485a3; font-size: 10px; }.engine-pill strong { color: #315cad; font-size: 13px; }
.home-grid { max-width: 1500px; margin: 0 auto; display: grid; grid-template-columns: minmax(380px, 520px) minmax(0, 1fr); gap: 16px; align-items: start; }
.create-card, .projects-card { display: grid; gap: 13px; padding: 20px; border: 1px solid #dfe5ed; border-radius: 16px; background: #fff; }
.create-card header, .projects-card > header { display: flex; justify-content: space-between; gap: 16px; align-items: center; }
h2 { margin: 2px 0 0; font-size: 20px; }.create-card header > span { padding: 5px 8px; border-radius: 999px; background: #edf8f2; color: #287653; font-size: 10px; font-weight: 800; }
.create-card label { display: grid; gap: 5px; }.create-card label > span, legend { color: #66758a; font-size: 11px; font-weight: 800; }
input, select { height: 40px; border: 1px solid #d6dfe9; border-radius: 9px; padding: 0 10px; background: #fbfcfe; color: #35465e; outline: none; }
.two-columns { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }.scene-policy { display: grid; gap: 7px; margin: 0; padding: 10px; border: 1px solid #e0e5ec; border-radius: 11px; }
.scene-policy label { grid-template-columns: auto 1fr; align-items: center; gap: 9px; padding: 9px; border: 1px solid #e5e9ef; border-radius: 9px; cursor: pointer; }.scene-policy label.active { border-color: #9db6e8; background: #f4f7ff; }.scene-policy input { width: 15px; height: 15px; }.scene-policy label span { display: grid; gap: 2px; }.scene-policy label strong { color: #42536a; font-size: 11px; }.scene-policy label small { color: #8793a4; font-size: 9px; font-weight: 500; }
.fixed-rules { display: grid; gap: 2px; padding: 10px 11px; border-radius: 9px; background: #f5f7fa; }.fixed-rules span { color: #8a95a5; font-size: 9px; }.fixed-rules strong { color: #5b697d; font-size: 10px; line-height: 1.5; }
.primary { min-height: 42px; border: 0; border-radius: 10px; background: #3566d6; color: #fff; font-weight: 850; cursor: pointer; }.primary:disabled { opacity: .5; }.error { margin: 0; color: #b44949; font-size: 11px; }
.projects-card > header button { border: 1px solid #d9e1eb; border-radius: 8px; padding: 7px 10px; background: #fff; color: #62738c; cursor: pointer; }.project-list { display: grid; gap: 8px; }.project-row { display: grid; grid-template-columns: minmax(260px, 1fr) 130px 150px 70px; gap: 12px; align-items: center; width: 100%; padding: 13px; border: 1px solid #e2e7ee; border-radius: 11px; background: #fbfcfe; text-align: left; cursor: pointer; }.project-row:hover { border-color: #bdcbe0; background: #fff; }.project-main { min-width: 0; display: grid; gap: 3px; }.project-main strong { overflow: hidden; color: #33475f; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.project-main span { color: #8995a6; font-size: 10px; }.project-row > div:not(.project-main) { display: grid; gap: 2px; }.project-row small { color: #8a96a7; font-size: 9px; }.project-row > div > strong { color: #56667c; font-size: 10px; }.project-row .state.review strong { color: #98660f; }.project-row .state.processing strong { color: #3d65b2; }.project-row b { color: #4c70b9; font-size: 10px; text-align: right; }.empty { min-height: 190px; display: grid; place-items: center; align-content: center; gap: 5px; color: #8995a5; font-size: 12px; }.empty strong { color: #5a6a7d; }
@media (max-width: 1050px) { .home-grid { grid-template-columns: 1fr; }.project-row { grid-template-columns: minmax(220px, 1fr) 120px 140px 60px; } }
</style>
