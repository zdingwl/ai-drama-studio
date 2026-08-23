<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { useProjectStore } from '../stores/project'

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

const project = computed(() => store.currentProject)

const steps = [
  { number: '01', label: '项目创建', state: 'done' },
  { number: '02', label: '视频导入', state: 'future' },
  { number: '03', label: '自动拉片', state: 'future' },
  { number: '04', label: '人物对白', state: 'future' },
  { number: '05', label: '本土选角', state: 'future' },
  { number: '06', label: '生成制作', state: 'future' },
  { number: '07', label: '最终合成', state: 'future' },
]

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

    <div v-if="store.opening" class="workspace-loading">
      <div class="loading-ring"></div>
      <strong>正在打开项目</strong>
      <p>校验数据库、Workspace 和 project.json…</p>
    </div>

    <div v-else-if="store.errorMessage" class="workspace-error-panel">
      <div class="error-visual">!</div>
      <div>
        <span class="panel-eyebrow">PROJECT ERROR</span>
        <h2>项目无法打开</h2>
        <p>{{ store.errorMessage }}</p>
        <button type="button" class="secondary-button" @click="router.push('/')">返回项目列表</button>
      </div>
    </div>

    <template v-else-if="project">
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
            <p>当前 F01 已完成项目容器创建，后续 Feature 将沿此流程逐步开放。</p>
          </div>
          <span class="progress-summary">1 / 7</span>
        </div>
        <div class="process-rail">
          <div
            v-for="(step, index) in steps"
            :key="step.number"
            class="process-step"
            :class="step.state"
          >
            <div class="step-node">
              <span>{{ step.state === 'done' ? '✓' : step.number }}</span>
            </div>
            <strong>{{ step.label }}</strong>
            <small>{{ step.state === 'done' ? '已完成' : '待开放' }}</small>
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
            <div>
              <span>Workspace</span>
              <strong>{{ project.workspace_path }}</strong>
            </div>
          </div>
          <div class="manifest-row">
            <div><span>project.json</span><strong>已创建</strong></div>
            <div><span>数据库状态</span><strong>{{ project.status }}</strong></div>
            <div><span>最近打开</span><strong>{{ project.last_opened_at ? new Date(project.last_opened_at).toLocaleString('zh-CN') : '首次创建' }}</strong></div>
          </div>
        </article>

        <article class="content-panel next-step-panel">
          <div class="next-step-icon">02</div>
          <span class="panel-eyebrow">NEXT FEATURE</span>
          <h2>项目已经准备好</h2>
          <p>F01 只负责创建和重新打开项目。上传原视频将在 F02 完成，因此这里不会提前放一个不可用的上传按钮。</p>
          <div class="next-step-note">
            <span>✓</span>
            <div><strong>当前项目容器已就绪</strong><small>可以安全关闭应用并在下次启动后重新打开。</small></div>
          </div>
        </article>
      </section>
    </template>
  </StudioShell>
</template>
