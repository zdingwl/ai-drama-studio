<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import CreateProjectDialog from '../components/CreateProjectDialog.vue'
import ProjectCard from '../components/ProjectCard.vue'
import { useProjectStore } from '../stores/project'
import type { CreateProjectPayload } from '../types/project'

const store = useProjectStore()
const router = useRouter()
const dialogOpen = ref(false)

onMounted(() => store.loadProjects())

async function handleCreate(payload: CreateProjectPayload): Promise<void> {
  try {
    const project = await store.submitCreateProject(payload)
    dialogOpen.value = false
    await router.push(`/projects/${project.id}`)
  } catch {
    // 错误文案已经由 Store 写入 errorMessage，Dialog 直接展示。
  }
}

async function handleOpen(projectId: string): Promise<void> {
  // 首页只负责导航。真正的“打开项目”由 ProjectWorkspace 统一调用 openProject()。
  // 这样卡片点击、页面刷新和直接输入 URL 都只走一次后端 /open，不会重复更新时间。
  await router.push(`/projects/${projectId}`)
}
</script>

<template>
  <main class="page">
    <header class="page-header">
      <div><h1>AI Drama Studio</h1><p>本地 AI 短剧重制工作台</p></div>
      <button @click="dialogOpen = true">+ 新建项目</button>
    </header>

    <p v-if="store.errorMessage" class="error">{{ store.errorMessage }}</p>
    <p v-if="store.loading">正在加载项目…</p>
    <section v-else>
      <h2>最近项目</h2>
      <p v-if="store.projects.length === 0" class="empty">还没有项目，先创建第一个项目。</p>
      <div class="project-grid">
        <ProjectCard
          v-for="project in store.projects"
          :key="project.id"
          :project="project"
          :disabled="store.opening"
          @open="handleOpen"
        />
      </div>
    </section>

    <CreateProjectDialog
      :open="dialogOpen"
      :submitting="store.creating"
      :error-message="store.errorMessage"
      @close="dialogOpen = false"
      @submit="handleCreate"
    />
  </main>
</template>
