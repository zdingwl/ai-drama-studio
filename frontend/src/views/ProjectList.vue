<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import type { Project } from '../types/studio'

const router = useRouter()
const projects = ref<Project[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const form = reactive({ name: '', source_language: 'zh-CN', target_language: 'en-US', target_region: 'US' })

const languageOptions = [
  ['zh-CN', '中文（简体）'], ['en-US', '英语'], ['ja-JP', '日语'], ['ko-KR', '韩语'], ['es-ES', '西班牙语'], ['pt-BR', '葡萄牙语'],
]
const regionOptions = [
  ['US', '美国'], ['GB', '英国'], ['CA', '加拿大'], ['AU', '澳大利亚'], ['JP', '日本'], ['KR', '韩国'], ['SG', '新加坡'], ['BR', '巴西'],
]

async function loadProjects() {
  loading.value = true
  error.value = ''
  try { projects.value = await api.listProjects() }
  catch (err) { error.value = err instanceof Error ? err.message : '项目列表读取失败' }
  finally { loading.value = false }
}

async function submit() {
  if (!form.name.trim()) return
  saving.value = true
  error.value = ''
  try {
    const project = await api.createProject({ ...form, name: form.name.trim() })
    await router.push(`/projects/${project.id}`)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目创建失败'
  } finally { saving.value = false }
}

function episodeSummary(project: Project) {
  const shots = project.episodes.reduce((sum, item) => sum + item.shot_count, 0)
  return `${project.episodes.length} 集 · ${shots} 个镜头`
}

onMounted(loadProjects)
</script>

<template>
  <main class="home-shell">
    <section class="home-hero">
      <div>
        <div class="eyebrow">AI DRAMA STUDIO · REFERENCE VIDEO V2</div>
        <h1>短剧本地化重制工作台</h1>
        <p>先把原片拆成可控制的镜头，再基于 Reference Video 替换人物、语言、声音、场景和关键道具。</p>
      </div>
      <div class="hero-badge"><strong>13</strong><span>阶段生产链</span></div>
    </section>

    <section class="home-grid">
      <div class="panel create-panel">
        <div class="panel-heading">
          <div><div class="panel-kicker">F01</div><h2>新建项目</h2></div>
          <span class="status-pill ready">可用</span>
        </div>
        <form class="project-form" @submit.prevent="submit">
          <label><span>项目名称</span><input v-model="form.name" placeholder="例如：霸总短剧 · 美国版" maxlength="200" /></label>
          <label><span>原项目语言</span><select v-model="form.source_language"><option v-for="item in languageOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <label><span>目标语言</span><select v-model="form.target_language"><option v-for="item in languageOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <label><span>目标地区</span><select v-model="form.target_region"><option v-for="item in regionOptions" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label>
          <button class="primary-button" :disabled="saving || !form.name.trim()">{{ saving ? '正在创建…' : '创建并进入工作台' }}</button>
        </form>
        <p v-if="error" class="error-banner">{{ error }}</p>
      </div>

      <div class="panel projects-panel">
        <div class="panel-heading"><div><div class="panel-kicker">PROJECTS</div><h2>已有项目</h2></div><button class="ghost-button" @click="loadProjects">刷新</button></div>
        <div v-if="loading" class="empty-state">正在读取项目…</div>
        <div v-else-if="projects.length === 0" class="empty-state"><strong>还没有项目</strong><span>从左侧创建第一个本地化重制项目。</span></div>
        <div v-else class="project-list">
          <button v-for="project in projects" :key="project.id" class="project-card" @click="router.push(`/projects/${project.id}`)">
            <div class="project-card-top"><strong>{{ project.name }}</strong><span>V{{ project.project_format_version }}</span></div>
            <div class="project-locale">{{ project.source_language }} <span>→</span> {{ project.target_language }} · {{ project.target_region }}</div>
            <div class="project-stats">{{ episodeSummary(project) }}</div>
          </button>
        </div>
      </div>
    </section>
  </main>
</template>
