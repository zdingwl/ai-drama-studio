<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssetWorkbenchV3 from '../components/AssetWorkbenchV3.vue'
import EpisodeManagerV3 from '../components/EpisodeManagerV3.vue'
import ShotWorkbenchV3 from '../components/ShotWorkbenchV3.vue'
import { api } from '../api/client'
import type { Project } from '../types/studio'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))
const project = ref<Project | null>(null)
const activeStage = ref(1)
const loading = ref(true)
const error = ref('')

const stages = [
  { id: 1, title: '剧集管理', subtitle: '批量导入 / 排序 / 替换' },
  { id: 2, title: '拉片', subtitle: '自动切镜 / 必要时人工修正' },
  { id: 3, title: '资产', subtitle: '人物 / 场景 / 道具 + Shot 绑定' },
  { id: 4, title: '内容剧本', subtitle: '对白 / Speaker / 动作 / 结构化剧本' },
  { id: 5, title: '重制设计', subtitle: '角色 / 场景 / 本土化 / Shot Spec' },
  { id: 6, title: '生成 / 导出', subtitle: 'Video / Voice / LipSync / QC / Export' },
]

/**
 * 职责：从后端重新读取整个 Project。
 * 输入：路由 Project ID；输出：Project + Episode 最新状态。
 * 为什么：剧集导入、拉片任务完成后左侧状态和下游工作区必须共享同一份最新数据。
 */
async function refreshProject(): Promise<void> {
  if (!projectId.value) return
  try {
    project.value = await api.getProject(projectId.value)
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目读取失败'
  } finally {
    loading.value = false
  }
}

function selectStage(stageId: number): void {
  activeStage.value = stageId
}

onMounted(refreshProject)
</script>

<template>
  <div v-if="project" class="studio-shell">
    <aside class="studio-sidebar">
      <button class="back-link" @click="router.push('/')">← 返回项目</button>
      <div class="sidebar-brand"><span>AI DRAMA STUDIO</span><strong>{{ project.name }}</strong><small>{{ project.source_language }} → {{ project.target_language }} · {{ project.target_region }}</small></div>
      <nav class="stage-nav">
        <button v-for="stage in stages" :key="stage.id" :class="{ active: activeStage === stage.id }" @click="selectStage(stage.id)">
          <span class="stage-number">{{ String(stage.id).padStart(2, '0') }}</span>
          <span class="stage-copy"><strong>{{ stage.title }}</strong><small>{{ stage.subtitle }}</small></span>
          <i :class="{ ready: stage.id <= 3 && project.episodes.length > 0 }"></i>
        </button>
      </nav>
      <div class="sidebar-footer">
        <span>REFERENCE VIDEO V2.4</span>
        <small>{{ project.episodes.length }} 集 · 本地工作流</small>
      </div>
    </aside>

    <main :class="['studio-main', { 'full-workbench': activeStage === 2 || activeStage === 3 }]">
      <EpisodeManagerV3 v-if="activeStage === 1" :project="project" @refresh="refreshProject" />
      <ShotWorkbenchV3 v-else-if="activeStage === 2" :project-id="project.id" :episodes="project.episodes" @refresh-project="refreshProject" />
      <AssetWorkbenchV3 v-else-if="activeStage === 3" :project-id="project.id" :episodes="project.episodes" />

      <section v-else class="workspace-panel future-workspace">
        <div class="section-title"><div><span>{{ String(activeStage).padStart(2, '0') }}</span><h2>{{ stages.find((item) => item.id === activeStage)?.title }}</h2></div></div>
        <div class="empty-state large">
          <strong>{{ stages.find((item) => item.id === activeStage)?.title }}将在前置数据稳定后接入</strong>
          <span>这里不会为了“多一个阶段”提前堆不可修改的技术结果。只有需要判断或修改的生产结果才会进入正式页面。</span>
        </div>
      </section>
    </main>
  </div>

  <div v-else-if="loading" class="page-loading">正在读取项目…</div>
  <div v-else class="page-loading error-page"><strong>项目无法打开</strong><span>{{ error }}</span><button @click="router.push('/')">返回项目列表</button></div>
</template>