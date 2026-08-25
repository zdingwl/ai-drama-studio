<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AssetStageV4 from '../components/AssetStageV4.vue'
import EpisodeManagerV3 from '../components/EpisodeManagerV3.vue'
import ShotWorkbenchV4 from '../components/ShotWorkbenchV4.vue'
import { api } from '../api/client'
import type { BackgroundTask, Project } from '../types/studio'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))
const project = ref<Project | null>(null)
const activeStage = ref(1)
const loading = ref(true)
const error = ref('')
const shotRefreshToken = ref(0)

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

/**
 * 职责：后台拉片完成后强制让 ShotWorkbench 重新读取 Shot / Revision。
 * 输入：Task Dock 派发的 studio-task-finished；输出：刷新 Project，并重建拉片工作台。
 * 为什么：第一次拉片会改变 shot_count；重新自动拉片可能 shot_count 不变，单靠 props watch 无法保证刷新。
 */
function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  void refreshProject()
  if (task.task_type === 'EPISODE_SHOTS' || task.task_type === 'BATCH_SHOTS') {
    shotRefreshToken.value += 1
  }
}

function selectStage(stageId: number): void {
  activeStage.value = stageId
}

onMounted(() => {
  window.addEventListener('studio-task-finished', onTaskFinished)
  void refreshProject()
})

onUnmounted(() => {
  window.removeEventListener('studio-task-finished', onTaskFinished)
})
</script>

<template>
  <div v-if="project" class="studio-shell">
    <aside class="studio-sidebar">
      <button class="back-link" @click="router.push('/')">← 返回项目</button>
      <div class="studio-brand"><span>AI DRAMA STUDIO</span><strong>{{ project.name }}</strong><small>{{ project.source_language }} → {{ project.target_language }} · {{ project.target_region }}</small></div>
      <nav class="stage-nav">
        <button v-for="stage in stages" :key="stage.id" :class="['stage-item', { active: activeStage === stage.id }]" @click="selectStage(stage.id)">
          <span class="stage-code">{{ String(stage.id).padStart(2, '0') }}</span>
          <span class="stage-copy"><strong>{{ stage.title }}</strong><small>{{ stage.subtitle }}</small></span>
          <i :class="['stage-dot', { ready: stage.id <= 3 && project.episodes.length > 0 }]"></i>
        </button>
      </nav>
      <div class="sidebar-footer">
        <span>REFERENCE VIDEO V2.5</span>
        <small>{{ project.episodes.length }} 集 · 本地工作流</small>
      </div>
    </aside>

    <main :class="['studio-main', { 'shot-stage-main': activeStage === 2, 'asset-stage-main': activeStage === 3 }]">
      <EpisodeManagerV3 v-if="activeStage === 1" :project="project" @refresh="refreshProject" />
      <ShotWorkbenchV4 :key="shotRefreshToken" v-else-if="activeStage === 2" :project-id="project.id" :episodes="project.episodes" @refresh-project="refreshProject" />
      <AssetStageV4 v-else-if="activeStage === 3" :project-id="project.id" :episodes="project.episodes" />

      <section v-else class="workspace-panel planned-panel">
        <div class="planned-icon">{{ String(activeStage).padStart(2, '0') }}</div>
        <h2>{{ stages.find((item) => item.id === activeStage)?.title }}</h2>
        <p>{{ stages.find((item) => item.id === activeStage)?.subtitle }}</p>
        <div class="architecture-note">
          <strong>只在真正需要判断和修改时才做工作区</strong>
          <p>不可修改的模型中间结果继续留在后台；后续页面会直接围绕对白、剧本、重制决策和异常生成结果展开。</p>
        </div>
      </section>
    </main>
  </div>

  <div v-else-if="loading" class="screen-loading">正在读取项目…</div>
  <div v-else class="screen-loading"><strong>项目无法打开</strong><span>{{ error }}</span><button class="ghost-button" @click="router.push('/')">返回项目列表</button></div>
</template>
