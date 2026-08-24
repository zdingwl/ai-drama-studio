<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { useCharacterDetectionStore } from '../stores/character-detection'
import { usePreprocessStore } from '../stores/preprocess'
import { useProjectStore } from '../stores/project'
import { useShotDetectionStore } from '../stores/shot-detection'
import { useShotWorkbenchStore } from '../stores/shot-workbench'
import { useSourceVideoStore } from '../stores/source-video'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const sourceStore = useSourceVideoStore()
const preprocessStore = usePreprocessStore()
const shotStore = useShotDetectionStore()
const workbenchStore = useShotWorkbenchStore()
const characterStore = useCharacterDetectionStore()

const project = computed(() => projectStore.currentProject)
const sourceVideo = computed(() => sourceStore.currentSourceVideo)
const preprocess = computed(() => preprocessStore.currentPreprocess)
const shotDetection = computed(() => shotStore.currentDetection)
const workbench = computed(() => workbenchStore.currentWorkbench)
const characterDetection = computed(() => characterStore.currentDetection)

const importReady = computed(() => Boolean(sourceVideo.value && preprocess.value))
const shotsConfirmed = computed(() => workbench.value?.status === 'confirmed')

const steps = computed(() => [
  { number: '01', label: '导入原片', state: importReady.value ? 'done' : 'current' },
  {
    number: '02',
    label: '拉片',
    state: shotsConfirmed.value ? 'done' : importReady.value ? 'current' : 'future',
  },
  {
    number: '03',
    label: '人物对白',
    state: shotsConfirmed.value ? 'current' : 'future',
  },
  { number: '04', label: '剧本 / 重制设计', state: 'future' },
  { number: '05', label: '生成制作', state: 'future' },
  { number: '06', label: '最终合成 / 导出', state: 'future' },
])

const currentWorkflowLabel = computed(() => {
  if (shotsConfirmed.value) return 'Workflow 03 · 人物对白'
  if (importReady.value) return 'Workflow 02 · 拉片'
  return 'Workflow 01 · 导入原片'
})

onMounted(async () => {
  const projectId = String(route.params.projectId || '')
  workbenchStore.reset()
  characterStore.resetCharacterDetectionState()
  try {
    await projectStore.openProject(projectId)
    await sourceStore.loadSourceVideo(projectId)
    if (sourceStore.currentSourceVideo) await preprocessStore.loadPreprocess(projectId)
    else preprocessStore.resetPreprocessState()

    if (preprocessStore.currentPreprocess) await shotStore.loadShotDetection(projectId)
    else shotStore.resetShotDetectionState()

    if (shotStore.currentDetection?.status === 'ready') {
      // 总览只读取现有 Final Shot，不在后台偷偷初始化拉片 Draft。
      const { fetchShotWorkbench } = await import('../api/shot-workbench')
      workbenchStore.currentWorkbench = await fetchShotWorkbench(projectId)
    }

    if (workbenchStore.currentWorkbench?.status === 'confirmed') {
      // 人物对白 Workflow 当前只读取已有演员视觉 Evidence，不在总览触发模型推理。
      await characterStore.loadCharacterDetection(projectId)
    }
  } catch {
    // 对应 Store 已保存具体错误；页面按当前能确认的状态展示。
  }
})
</script>

<template>
  <StudioShell
    title="项目总览"
    :subtitle="project ? `${project.name} · ${project.id}` : '正在读取本地项目'"
    project-mode
    :project-name="project?.name || ''"
  >
    <template #topbar>
      <span v-if="project" class="workspace-status-chip"><i></i> Workspace 正常</span>
      <button type="button" class="secondary-button compact-button" @click="router.push('/')">返回工作台</button>
    </template>

    <div v-if="projectStore.opening || sourceStore.loading || preprocessStore.loading || shotStore.loading || workbenchStore.loading || characterStore.loading" class="workspace-loading">
      <div class="loading-ring"></div>
      <strong>正在打开项目</strong>
      <p>读取导入原片、拉片和人物对白工作流状态…</p>
    </div>

    <div v-else-if="projectStore.errorMessage" class="workspace-error-panel">
      <div class="error-visual">!</div>
      <div><span class="panel-eyebrow">PROJECT ERROR</span><h2>项目无法打开</h2><p>{{ projectStore.errorMessage }}</p><button type="button" class="secondary-button" @click="router.push('/')">返回项目列表</button></div>
    </div>

    <template v-else-if="project">
      <div v-if="sourceStore.errorMessage || preprocessStore.errorMessage || shotStore.errorMessage || workbenchStore.errorMessage || characterStore.errorMessage" class="inline-alert error-alert">
        <span>!</span><div><strong>项目状态异常</strong><p>{{ sourceStore.errorMessage || preprocessStore.errorMessage || shotStore.errorMessage || workbenchStore.errorMessage || characterStore.errorMessage }}</p></div>
      </div>

      <section class="project-hero content-panel">
        <div class="project-hero-cover project-cover-hero"><div class="cover-grid"></div><div class="hero-logo">AI</div><span class="hero-ready"><i></i> READY</span></div>
        <div class="project-hero-main">
          <div class="project-hero-title"><div><span class="panel-eyebrow">LOCAL REMAKE PROJECT</span><h2>{{ project.name }}</h2></div><span class="locale-chip large">{{ project.target_language.toUpperCase() }} · {{ project.target_region }}</span></div>
          <div class="hero-info-grid">
            <div><span>Project ID</span><strong class="mono-value">{{ project.id }}</strong></div>
            <div><span>原片语言</span><strong>{{ project.source_language ? project.source_language.toUpperCase() : '待识别' }}</strong></div>
            <div><span>目标市场</span><strong>{{ project.target_language.toUpperCase() }} / {{ project.target_region }}</strong></div>
            <div><span>项目格式</span><strong>Format v{{ project.project_format_version }}</strong></div>
          </div>
        </div>
      </section>

      <section class="content-panel process-panel">
        <div class="section-heading"><div><h2>生产工作流</h2><p>用户只处理连续 Workflow；Project、Source、Preprocess、Detection 等内部模块自动编排。</p></div><span class="progress-summary">{{ currentWorkflowLabel }}</span></div>
        <div class="process-rail">
          <div v-for="(step, index) in steps" :key="step.number" class="process-step" :class="step.state">
            <div class="step-node"><span>{{ step.state === 'done' ? '✓' : step.number }}</span></div><strong>{{ step.label }}</strong><small>{{ step.state === 'done' ? '已完成' : step.state === 'current' ? '当前阶段' : '待开放' }}</small><div v-if="index < steps.length - 1" class="step-line"></div>
          </div>
        </div>
      </section>

      <section class="workspace-overview-grid">
        <article class="content-panel workspace-info-panel">
          <div class="section-heading compact"><div><h2>项目资产</h2><p>内部数据状态，仅用于确认工作流是否完整</p></div><span class="online-chip"><i></i> 本地</span></div>
          <div class="workspace-path-card"><span class="path-icon">▱</span><div><span>Workspace</span><strong>{{ project.workspace_path }}</strong></div></div>
          <div class="manifest-row">
            <div><span>原片</span><strong>{{ sourceVideo ? 'ready' : '未完成' }}</strong></div>
            <div><span>Proxy / WAV / Thumbnail</span><strong>{{ preprocess ? 'ready' : '未完成' }}</strong></div>
            <div><span>自动切镜 Evidence</span><strong>{{ shotDetection?.status === 'ready' ? 'ready' : '未完成' }}</strong></div>
            <div><span>Final Shots</span><strong>{{ workbench ? workbench.status : '未开始' }}</strong></div>
            <div><span>演员视觉 Evidence</span><strong>{{ characterDetection ? characterDetection.status : '未开始' }}</strong></div>
          </div>
        </article>

        <article v-if="!sourceVideo" class="content-panel next-step-panel">
          <div class="next-step-icon">01</div><span class="panel-eyebrow">WORKFLOW RECOVERY</span><h2>导入原片未完成</h2><p>这是旧项目或中断后的恢复状态。新项目正常情况下会在首页一次完成创建、原片导入和初始化。</p><button type="button" class="primary-button" @click="router.push(`/projects/${project.id}/source-video`)">恢复原片导入</button>
        </article>

        <article v-else-if="!preprocess" class="content-panel next-step-panel">
          <div class="next-step-icon">01</div><span class="panel-eyebrow">WORKFLOW RECOVERY</span><h2>原片已保存，初始化未完成</h2><p>Source 已安全落盘。继续生成 Proxy、分析 WAV、Thumbnail 和时间映射即可恢复 Workflow 01。</p><button type="button" class="primary-button" @click="router.push(`/projects/${project.id}/preprocess`)">继续初始化</button>
        </article>

        <article v-else-if="shotDetection?.status !== 'ready'" class="content-panel next-step-panel">
          <div class="next-step-icon">02</div><span class="panel-eyebrow">CURRENT WORKFLOW</span><h2>开始拉片</h2><p>原片和分析资产已经完整初始化。下一步自动检测切镜，并继续进入 Final Shot 工作台。</p><button type="button" class="primary-button" @click="router.push(`/projects/${project.id}/shot-detection`)">开始拉片</button>
        </article>

        <article v-else-if="workbench?.status !== 'confirmed'" class="content-panel next-step-panel">
          <div class="next-step-icon">02</div><span class="panel-eyebrow">CURRENT WORKFLOW</span><h2>继续拉片</h2><p>自动切镜已经完成，现在继续在同一拉片 Workflow 中检查并确认 Final Shots。</p>
          <div class="next-step-note"><span>✓</span><div><strong>{{ shotDetection.shot_count || shotDetection.candidates.length }} 个自动镜头</strong><small>自动 Evidence 保持只读，人工结果写入 Final Shot。</small></div></div>
          <button type="button" class="primary-button" @click="router.push(`/projects/${project.id}/shot-workbench`)">进入镜头工作台</button>
        </article>

        <article v-else class="content-panel next-step-panel">
          <div class="next-step-icon">03</div><span class="panel-eyebrow">CURRENT WORKFLOW</span><h2>人物对白</h2><p>Final Shots 已确认。这个 Workflow 的最终目标是“演员是谁、每个演员说了哪些对白”，演员视觉识别只是其中第一步。</p>
          <div class="next-step-note"><span>✓</span><div><strong>{{ workbench.shots.length }} 个 Final Shots 已锁定</strong><small>{{ characterDetection?.status === 'ready' ? `已有 ${characterDetection.candidate_count} 个演员视觉 Candidate Evidence` : '演员视觉 Evidence 尚未运行' }}</small></div></div>
          <button type="button" class="primary-button" @click="router.push(`/projects/${project.id}/character-detection`)">进入人物对白</button>
          <button type="button" class="secondary-button" @click="router.push(`/projects/${project.id}/shot-workbench`)">查看 Final Shots</button>
        </article>
      </section>
    </template>
  </StudioShell>
</template>
