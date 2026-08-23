<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjectStore } from '../stores/project'

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

onMounted(async () => {
  const projectId = String(route.params.projectId || '')
  try {
    await store.openProject(projectId)
  } catch {
    // 打不开时保留错误信息，由页面展示，并允许返回项目首页。
  }
})
</script>

<template>
  <main class="page">
    <button class="back" @click="router.push('/')">← 返回项目列表</button>
    <p v-if="store.opening">正在打开项目…</p>
    <div v-else-if="store.errorMessage" class="error-panel">
      <h2>项目无法打开</h2>
      <p>{{ store.errorMessage }}</p>
    </div>
    <section v-else-if="store.currentProject" class="workspace-card">
      <h1>{{ store.currentProject.name }}</h1>
      <dl>
        <dt>Project ID</dt><dd>{{ store.currentProject.id }}</dd>
        <dt>目标语言 / 地区</dt><dd>{{ store.currentProject.target_language }} / {{ store.currentProject.target_region }}</dd>
        <dt>Workspace</dt><dd>{{ store.currentProject.workspace_path }}</dd>
      </dl>
      <p class="ready">项目已创建。</p>
    </section>
  </main>
</template>
