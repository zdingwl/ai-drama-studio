<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { usePreprocessStore } from '../stores/preprocess'
import { useProjectStore } from '../stores/project'
import { useShotDetectionStore } from '../stores/shot-detection'
import { useSourceVideoStore } from '../stores/source-video'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const sourceStore = useSourceVideoStore()
const preprocessStore = usePreprocessStore()
const shotStore = useShotDetectionStore()

const project = computed(() => projectStore.currentProject)
const sourceVideo = computed(() => sourceStore.currentSourceVideo)
const preprocess = computed(() => preprocessStore.currentPreprocess)
const shotDetection = computed(() => shotStore.currentDetection)

const steps = computed(() => [
  { number: '01', label: '项目创建', state: 'done' },
  { number: '02', label: '视频导入', state: sourceVideo.value ? 'done' : 'current' },
  { number: '03', label: '视频预处理', state: preprocess.value ? 'done' : sourceVideo.value ? 'current' : 'future' },
  { number: '04', label: '自动拉片', state: shotDetection.value?.status === 'ready' ? 'done' : preprocess.value ? 'current' : 'future' },
  { number: '05', label: '镜头修正', state: shotDetection.value?.status === 'ready' ? 'current' : 'future' },
  { number: '06', label: '人物对白', state: 'future' },
  { number: '07', label: '生成制作', state: 'future' },
  { number: '08', label: '最终合成', state: 'future' },
])

const currentFeatureLabel = computed(() => {
  if (shotDetection.value?.status === 'ready') return 'F05'
  if (preprocess.value) return 'F04'
  if (sourceVideo.value) return 'F03'
  return 'F02'
})

onMounted(async () => {
  const projectId = String(route.params.projectId || '')
  try {
    await projectStore.openProject(projectId)
    await sourceStore.loadSourceVideo(projectId)
    if (sourceStore.currentSourceVideo) {
      await preprocessStore.loadPreprocess(projectId)
    } else {
      preprocessStore.resetPreprocessState()
    }
    if (preprocessStore.currentPreprocess) {
      await shotStore.loadShotDetection(projectId)
    } else {
      shotStore.resetShotDetectionState()
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

    <div v-if="projectStore.opening || sourceStore.loading || preprocessStore.loading || shotStore.loading" class="workspace-loading">
      <div class="loading-ring"></div>
      <strong>正在打开项目</strong>
      <p>校验 Project、Source Video、预处理和自动拉片状态…</p>
    </div>

    <div v-else-if="projectStore.errorMessage" class="workspace-error-panel">
      <div class="error-visual">!</div>
      <div>
        <span class="panel-eyebrow">PROJECT ERROR</span>
        <h2>项目无法打开</h2>
        <p>{{ projectStore.errorMessage }}</p>
        <button type="button" class="secondary-button" @click="router.push('/')">返回项目列表</button>
      </div>
    </div>

    <template v-else-if="project">
      <div v-if="sourceStore.errorMessage || preprocessStore.errorMessage || shotStore.errorMessage" class="inline-alert error-alert">
        <span>!</span>
        <div><strong>项目媒体状态异常</strong><p>{{ sourceStore.errorMessage || preprocessStore.errorMessage || shotStore.errorMessage }}</p></div>
      </div>

      <section class="project-hero content-panel">
        <div class="project-hero-cover project-cover-hero">
          <div class="cover-grid"></div>
          <div class="hero-logo">AI</div>
          <span class="hero-ready"><i></i> READY</span>
        </div>
        <div class="project-hero-main">
          <div class="project-hero-title">
            <div>
              <span class="panel-eyebrow">LOCAL REMAKE PROJECT</span>
              <h2>{{ project.name }}</h2>
            </div>
            <span class="locale-chip large">{{ project.target_language.toUpperCase() }} · {{ project.target_region }}</span>
          </div>
          <div class="hero-info-grid">
            <div><span>Project ID</span><strong class="mono-value">{{ project.id }}</strong></div>
            <div><span>原片语言</span><strong>{{ project.source_language ? project.source_language.toUpperCase() : '待识别' }}</strong></div>
            <div><span>目标市场</span><strong>{{ project.target_language.toUpperCase() }} / {{ project.target_region }}</strong></div>
            <div><span>项目格式</span><strong>Format v{{ project.project_format_version }}</strong></div>
          </div>
        </div>
      </section>

      <section class="content-panel process-panel">
        <div class="section-heading">
          <div>
            <h2>生产流程</h2>
            <p>页面根据当前项目真实数据判断已经完成和当前可进入的 Feature。</p>
          </div>
          <span class="progress-summary">{{ currentFeatureLabel }}</span>
        </div>
        <div class="process-rail">
          <div v-for="(step, index) in steps" :key="step.number" class="process-step" :class="step.state">
            <div class="step-node"><span>{{ step.state === 'done' ? '✓' : step.number }}</span></div>
            <strong>{{ step.label }}</strong>
            <small>{{ step.state === 'done' ? '已完成' : step.state === 'current' ? '当前阶段' : '待开放' }}</small>
            <div v-if="index < steps.length - 1" class="step-line"></div>
          </div>
        </div>
      </section>

      <section class="workspace-overview-grid">
        <article class="content-panel workspace-info-panel">
          <div class="section-heading compact">
            <div><h2>项目存储</h2><p>本地 Workspace 状态</p></div>
            <span class="online-chip"><i></i> 正常</span>
          </div>
          <div class="workspace-path-card">
            <span class="path-icon">▱</span>
            <div><span>Workspace</span><strong>{{ project.workspace_path }}</strong></div>
          </div>
          <div class="manifest-row">
            <div><span>project.json</span><strong>已创建</strong></div>
            <div><span>Source Video</span><strong>{{ sourceVideo ? 'ready' : '未导入' }}</strong></div>
            <div><span>视频预处理</span><strong>{{ preprocess ? 'ready' : '未完成' }}</strong></div>
            <div><span>自动拉片</span><strong>{{ shotDetection?.status === 'ready' ? 'ready' : '未完成' }}</strong></div>
          </div>
        </article>

        <article v-if="!sourceVideo" class="content-panel next-step-panel">
          <div class="next-step-icon">02</div>
          <span class="panel-eyebrow">CURRENT FEATURE</span>
          <h2>导入原视频</h2>
          <p>先把真实短剧原片复制进 Workspace，并完成 SHA-256 与 FFprobe 校验。</p>
          <button type="button" class="primary-button" @click="router.push(`/projects/${project.id}/source-video`)">进入视频导入</button>
        </article>

        <article v-else-if="!preprocess" class="content-panel next-step-panel">
          <div class="next-step-icon">03</div>
          <span class="panel-eyebrow">CURRENT FEATURE</span>
          <h2>视频预处理</h2>
          <p>原片已经锁定，可以生成 Proxy、分析 WAV、Thumbnail 和 Source Timeline Mapping。</p>
          <button type="button" class="primary-button" @click="router.push(`/projects/${project.id}/preprocess`)">进入视频预处理</button>
        </article>

        <article v-else-if="shotDetection?.status !== 'ready'" class="content-panel next-step-panel">
          <div class="next-step-icon">04</div>
          <span class="panel-eyebrow">CURRENT FEATURE</span>
          <h2>开始自动拉片</h2>
          <p>F03 分析 Proxy 已经就绪。现在用本地 TransNetV2 检测镜头边界，并以真实 PTS 生成连续 Shot Candidate。</p>
          <button type="button" class="primary-button" @click="router.push(`/projects/${project.id}/shot-detection`)">进入自动拉片</button>
        </article>

        <article v-else class="content-panel next-step-panel">
          <div class="next-step-icon">05</div>
          <span class="panel-eyebrow">NEXT FEATURE</span>
          <h2>自动拉片已经完成</h2>
          <p>F04 已保存 {{ shotDetection.shot_count || shotDetection.candidates.length }} 个自动 Shot Candidate。下一步由 F05 做人工边界修正，不覆盖自动证据。</p>
          <div class="next-step-note"><span>✓</span><div><strong>F04 ready</strong><small>可以安全关闭并在下次启动后继续。</small></div></div>
          <button type="button" class="secondary-button" @click="router.push(`/projects/${project.id}/shot-detection`)">查看自动拉片结果</button>
        </article>
      </section>
    </template>
  </StudioShell>
</template>
