<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import CreateProjectDialog from '../components/CreateProjectDialog.vue'
import ProjectCard from '../components/ProjectCard.vue'
import StudioShell from '../components/StudioShell.vue'
import { useProjectStore } from '../stores/project'
import type { CreateProjectPayload } from '../types/project'

const store = useProjectStore()
const router = useRouter()
const dialogOpen = ref(false)
const searchQuery = ref('')

const filteredProjects = computed(() => {
  const keyword = searchQuery.value.trim().toLowerCase()
  if (!keyword) return store.projects
  return store.projects.filter((project) => {
    return [
      project.name,
      project.id,
      project.source_language || '',
      project.target_language,
      project.target_region,
    ].some((value) => value.toLowerCase().includes(keyword))
  })
})

const openedCount = computed(() => store.projects.filter((project) => project.last_opened_at).length)
const targetCount = computed(
  () => new Set(store.projects.map((project) => `${project.target_language}-${project.target_region}`)).size,
)

onMounted(() => store.loadProjects())

function openCreateDialog(): void {
  store.resetImportWorkflowState()
  dialogOpen.value = true
}

async function handleCreate(payload: CreateProjectPayload, file: File): Promise<void> {
  try {
    const project = await store.submitCreateAndImport(payload, file)
    dialogOpen.value = false
    await router.push(`/projects/${project.id}`)
  } catch {
    // 错误和当前 Workflow 阶段已经由 Store 保存，Dialog 直接展示。
  }
}

async function handleOpen(projectId: string): Promise<void> {
  // 首页只负责导航。真正的“打开项目”由 ProjectWorkspace 统一调用 openProject()。
  await router.push(`/projects/${projectId}`)
}
</script>

<template>
  <StudioShell title="工作台" subtitle="管理本地短剧重制项目">
    <template #topbar>
      <label class="top-search">
        <span aria-hidden="true">⌕</span>
        <input v-model="searchQuery" type="search" placeholder="搜索项目名称或 Project ID" />
      </label>
      <button type="button" class="primary-button top-create-button" @click="openCreateDialog">
        <span class="button-plus">＋</span>
        导入原片
      </button>
    </template>

    <section class="dashboard-stats" aria-label="项目统计">
      <article class="stat-card stat-purple">
        <div class="stat-icon">▣</div>
        <div class="stat-copy">
          <span>项目总数</span>
          <strong>{{ store.projects.length }}</strong>
          <small>本机已保存项目</small>
        </div>
      </article>
      <article class="stat-card stat-blue">
        <div class="stat-icon">✓</div>
        <div class="stat-copy">
          <span>可打开项目</span>
          <strong>{{ store.projects.length }}</strong>
          <small>状态正常 · ready</small>
        </div>
      </article>
      <article class="stat-card stat-green">
        <div class="stat-icon">↗</div>
        <div class="stat-copy">
          <span>已打开过</span>
          <strong>{{ openedCount }}</strong>
          <small>已有工作记录</small>
        </div>
      </article>
      <article class="stat-card stat-orange">
        <div class="stat-icon">◎</div>
        <div class="stat-copy">
          <span>本土化目标</span>
          <strong>{{ targetCount }}</strong>
          <small>语言 / 地区组合</small>
        </div>
      </article>
    </section>

    <section class="content-panel projects-panel">
      <div class="section-heading">
        <div>
          <h2>最近项目</h2>
          <p>继续上次的本地短剧重制工作</p>
        </div>
        <span class="section-count">{{ filteredProjects.length }} 个项目</span>
      </div>

      <div v-if="store.errorMessage && !dialogOpen" class="inline-alert error-alert">
        <span>!</span>
        <div>
          <strong>项目列表加载失败</strong>
          <p>{{ store.errorMessage }}</p>
        </div>
        <button type="button" class="ghost-button" @click="store.loadProjects()">重试</button>
      </div>

      <div v-if="store.loading" class="project-skeleton-grid" aria-label="正在加载项目">
        <div v-for="index in 4" :key="index" class="project-skeleton"></div>
      </div>

      <div v-else-if="store.projects.length === 0" class="empty-workbench">
        <div class="empty-visual">
          <span class="empty-film">▶</span>
        </div>
        <h3>导入你的第一部短剧原片</h3>
        <p>选择原片后，系统会一次完成项目创建、视频导入、Proxy、分析音频和缩略图初始化。</p>
        <button type="button" class="primary-button" @click="openCreateDialog">＋ 导入原片</button>
      </div>

      <div v-else-if="filteredProjects.length === 0" class="empty-search">
        <strong>没有找到匹配项目</strong>
        <p>尝试搜索项目名称、Project ID、语言或地区。</p>
      </div>

      <div v-else class="project-grid">
        <ProjectCard
          v-for="project in filteredProjects"
          :key="project.id"
          :project="project"
          :disabled="store.opening"
          @open="handleOpen"
        />
      </div>
    </section>

    <section class="dashboard-bottom-grid">
      <article class="content-panel local-panel">
        <div class="section-heading compact">
          <div>
            <h2>本地工作流</h2>
            <p>用户只操作 Workflow，内部 Feature 自动编排</p>
          </div>
          <span class="online-chip"><i></i> 本地可用</span>
        </div>
        <div class="local-feature-list">
          <div><span>01</span><div><strong>导入原片</strong><p>创建项目、导入视频和初始化分析资产一次完成。</p></div></div>
          <div><span>02</span><div><strong>拉片</strong><p>自动切镜后直接进入人工镜头工作台。</p></div></div>
          <div><span>03</span><div><strong>人物对白</strong><p>演员、对白和说话人绑定在一个连续工作区处理。</p></div></div>
        </div>
      </article>

      <article class="content-panel quick-panel">
        <div class="section-heading compact">
          <div>
            <h2>快速开始</h2>
            <p>从一部原片直接开始完整生产流程</p>
          </div>
        </div>
        <button type="button" class="quick-action" @click="openCreateDialog">
          <span class="quick-icon">＋</span>
          <span><strong>导入原片</strong><small>创建项目并自动完成分析资产初始化</small></span>
          <b>→</b>
        </button>
      </article>
    </section>

    <CreateProjectDialog
      :open="dialogOpen"
      :submitting="store.creating"
      :error-message="dialogOpen ? store.errorMessage : ''"
      :stage="store.importStage"
      :upload-progress="store.importProgress"
      @close="dialogOpen = false"
      @submit="handleCreate"
    />
  </StudioShell>
</template>
