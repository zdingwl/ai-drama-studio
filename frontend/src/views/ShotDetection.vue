<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { usePreprocessStore } from '../stores/preprocess'
import { useProjectStore } from '../stores/project'
import { useShotDetectionStore } from '../stores/shot-detection'
import { useShotWorkbenchStore } from '../stores/shot-workbench'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const preprocessStore = usePreprocessStore()
const shotStore = useShotDetectionStore()
const workbenchStore = useShotWorkbenchStore()
const enteringWorkbench = ref(false)

const projectId = computed(() => String(route.params.projectId || ''))
const project = computed(() => projectStore.currentProject)
const preprocess = computed(() => preprocessStore.currentPreprocess)
const detection = computed(() => shotStore.currentDetection)
const workflowBusy = computed(() => shotStore.processing || workbenchStore.loading || enteringWorkbench.value)
const workflowError = computed(() => shotStore.errorMessage || workbenchStore.errorMessage || preprocessStore.errorMessage)

/**
 * 职责：把已经 ready 的自动 Shot Detection 接成生产级 Final Shot Draft，并进入镜头工作台。
 * 输入：当前 projectId；输出：导航到 /shot-workbench。
 * 为什么：用户的“拉片”是一个连续 Workflow，不应该停在 F04 技术结果页再手动初始化 F05。
 */
async function enterShotWorkbench(): Promise<void> {
  if (enteringWorkbench.value) return
  enteringWorkbench.value = true
  try {
    await workbenchStore.loadOrInitialize(projectId.value)
    await router.replace(`/projects/${projectId.value}/shot-workbench`)
  } catch {
    // Workbench Store 已保存具体错误；页面保留当前状态供用户重试。
  } finally {
    enteringWorkbench.value = false
  }
}

onMounted(async () => {
  shotStore.resetShotDetectionState()
  workbenchStore.reset()
  try {
    if (projectStore.currentProject?.id !== projectId.value) {
      await projectStore.openProject(projectId.value)
    }
    if (preprocessStore.currentPreprocess?.project_id !== projectId.value) {
      await preprocessStore.loadPreprocess(projectId.value)
    }
    if (!preprocessStore.currentPreprocess) return

    await shotStore.loadShotDetection(projectId.value)

    // 历史项目已经完成 F04 时，不再让用户停留在旧的“自动检测结果页”。
    // 直接恢复/创建 Final Shot Draft 并进入统一拉片工作台。
    if (shotStore.currentDetection?.status === 'ready') {
      await enterShotWorkbench()
    }
  } catch {
    // 对应 Store 已保存具体错误。
  }
})

/**
 * 职责：执行 Workflow 02 的自动分析阶段，并在成功后立即进入人工拉片工作台。
 * 输入：confirmed F03 Preprocess；输出：F04 Auto Evidence + F05 Final Shot Draft。
 * 为什么：用户只需要一次“开始拉片”，不需要理解 F04/F05 初始化边界。
 */
async function startShotWorkflow(): Promise<void> {
  if (!preprocess.value || workflowBusy.value) return
  try {
    if (detection.value?.status !== 'ready') {
      await shotStore.runShotDetection(projectId.value)
    }
    await enterShotWorkbench()
  } catch {
    // Store 已保存具体错误。
  }
}
</script>

<template>
  <StudioShell
    title="拉片"
    :subtitle="project ? `${project.name} · 自动检测 + 镜头人工修正` : '正在读取项目'"
    project-mode
    :project-name="project?.name || ''"
  >
    <template #topbar>
      <span v-if="project" class="workspace-status-chip"><i></i> WORKFLOW 02 · LOCAL</span>
      <button type="button" class="secondary-button compact-button" @click="router.push(`/projects/${projectId}`)">
        返回项目总览
      </button>
    </template>

    <div v-if="projectStore.opening || preprocessStore.loading || shotStore.loading" class="workspace-loading">
      <div class="loading-ring"></div>
      <strong>正在恢复拉片状态</strong>
      <p>检查分析视频、已有自动切镜结果和 Final Shot Draft…</p>
    </div>

    <div v-else-if="projectStore.errorMessage" class="workspace-error-panel">
      <div class="error-visual">!</div>
      <div>
        <span class="panel-eyebrow">PROJECT ERROR</span>
        <h2>项目无法打开</h2>
        <p>{{ projectStore.errorMessage }}</p>
        <button type="button" class="secondary-button" @click="router.push('/')">返回工作台</button>
      </div>
    </div>

    <template v-else-if="project">
      <div v-if="workflowError" class="inline-alert error-alert shot-alert">
        <span>!</span>
        <div>
          <strong>拉片流程未完成</strong>
          <p>{{ workflowError }}</p>
        </div>
      </div>

      <section v-if="!preprocess" class="content-panel shot-blocked-panel">
        <div class="shot-blocked-icon">01</div>
        <span class="panel-eyebrow">SOURCE REQUIRED</span>
        <h2>当前项目还没有完成原片初始化</h2>
        <p>新的正常流程会在“导入原片”时一次完成 Proxy、分析音频和时间映射。历史项目请先完成原片恢复。</p>
        <button type="button" class="secondary-button" @click="router.push(`/projects/${projectId}`)">返回项目总览</button>
      </section>

      <section v-else class="content-panel shot-run-panel">
        <div v-if="workflowBusy" class="shot-processing-state">
          <div class="loading-ring"></div>
          <div>
            <strong>{{ detection?.status === 'ready' ? '正在进入镜头工作台…' : '正在自动拉片…' }}</strong>
            <p v-if="detection?.status === 'ready'">自动切镜结果已经完成，正在恢复或创建 Final Shot Draft。</p>
            <p v-else>本地 TransNetV2 正在检测切镜点；完成后会自动创建 Final Shot Draft，并直接进入镜头工作台。</p>
          </div>
        </div>

        <template v-else>
          <div>
            <span class="panel-eyebrow">WORKFLOW 02 · SHOT ANALYSIS</span>
            <h2>{{ detection?.status === 'ready' ? '自动切镜已经完成' : '开始拉片' }}</h2>
            <p v-if="detection?.status === 'ready'">不需要停留查看内部 F04 表格。继续后会直接进入 Final Shot 人工修正工作台。</p>
            <p v-else>系统会自动完成镜头边界检测并建立 Final Shot Draft。你只需要在随后打开的工作台里检查、拆分、合并和确认。</p>
          </div>
          <button type="button" class="primary-button shot-start-button" @click="startShotWorkflow">
            {{ detection?.status === 'ready' ? '进入镜头工作台' : '开始拉片' }}
          </button>
        </template>
      </section>

      <section class="shot-profile-grid">
        <article class="content-panel shot-profile-card">
          <span>01</span><div><strong>自动检测</strong><p>本地模型识别镜头转场，自动证据保持只读。</p></div>
        </article>
        <article class="content-panel shot-profile-card">
          <span>02</span><div><strong>建立 Final Shot</strong><p>自动结果完成后系统自动建立独立 Draft，不要求用户点击“初始化”。</p></div>
        </article>
        <article class="content-panel shot-profile-card">
          <span>03</span><div><strong>人工确认</strong><p>直接进入三栏镜头工作台，完成边界修正、拆分、合并和最终确认。</p></div>
        </article>
      </section>
    </template>
  </StudioShell>
</template>
