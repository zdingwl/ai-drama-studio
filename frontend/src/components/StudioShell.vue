<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    projectMode?: boolean
    projectName?: string
  }>(),
  {
    subtitle: '',
    projectMode: false,
    projectName: '',
  },
)

const route = useRoute()
const router = useRouter()

const isHome = computed(() => route.path === '/')
const projectId = computed(() => String(route.params.projectId || ''))
const globalNav = computed(() => [
  { label: '工作台', icon: 'home', enabled: true, active: isHome.value },
  { label: '项目管理', icon: 'projects', enabled: true, active: !isHome.value },
  { label: '任务中心', icon: 'tasks', enabled: false, active: false },
  { label: '资产中心', icon: 'assets', enabled: false, active: false },
])

// 侧栏仍用 8 个大工作区概括完整 35 Feature；第 06 大区从 F06 自动人物识别开始开放。
// F06 当前只实现人物 Candidate，ASR / Speaker / 人工对白仍按 F08–F10 后续 Feature 进入该大区。
const projectNav = computed(() => [
  { label: '项目总览', step: '01', enabled: true, active: route.name === 'workspace', routeName: 'workspace' },
  { label: '视频导入', step: '02', enabled: true, active: route.name === 'source-video', routeName: 'source-video' },
  { label: '视频预处理', step: '03', enabled: true, active: route.name === 'preprocess', routeName: 'preprocess' },
  { label: '自动拉片', step: '04', enabled: true, active: route.name === 'shot-detection', routeName: 'shot-detection' },
  { label: '镜头修正', step: '05', enabled: true, active: route.name === 'shot-workbench', routeName: 'shot-workbench' },
  { label: '人物对白', step: '06', enabled: true, active: route.name === 'character-detection', routeName: 'character-detection' },
  { label: '生成制作', step: '07', enabled: false, active: false, routeName: '' },
  { label: '最终合成', step: '08', enabled: false, active: false, routeName: '' },
])

function goGlobal(label: string): void {
  if (label === '工作台' || label === '项目管理') void router.push('/')
}

function goProject(routeName: string): void {
  if (!routeName || !projectId.value) return
  void router.push({ name: routeName, params: { projectId: projectId.value } })
}
</script>

<template>
  <div class="studio-shell">
    <aside class="studio-sidebar">
      <div class="brand-block" @click="router.push('/')">
        <div class="brand-mark" aria-hidden="true"><span class="brand-mark-core">AI</span></div>
        <div class="brand-copy"><strong>AI短剧工厂</strong><span>Drama Studio</span></div>
      </div>

      <nav class="side-nav" aria-label="主导航">
        <button
          v-for="item in globalNav"
          :key="item.label"
          type="button"
          class="nav-item"
          :class="{ active: item.active, disabled: !item.enabled }"
          :disabled="!item.enabled"
          @click="goGlobal(item.label)"
        >
          <span class="nav-icon" :data-icon="item.icon" aria-hidden="true"></span>
          <span>{{ item.label }}</span>
          <span v-if="!item.enabled" class="nav-soon">后续</span>
        </button>
      </nav>

      <div v-if="projectMode" class="project-nav-section">
        <div class="project-nav-title"><span>当前项目</span><strong :title="projectName">{{ projectName || '项目工作区' }}</strong></div>
        <div class="project-flow-nav">
          <button
            v-for="item in projectNav"
            :key="item.label"
            type="button"
            class="project-flow-item"
            :class="{ active: item.active, disabled: !item.enabled }"
            :disabled="!item.enabled"
            @click="goProject(item.routeName)"
          >
            <span class="flow-number">{{ item.step }}</span>
            <span class="flow-label">{{ item.label }}</span>
            <span v-if="!item.enabled" class="flow-lock">·</span>
          </button>
        </div>
      </div>

      <div class="sidebar-footer">
        <div class="local-badge"><span class="status-dot"></span><div><strong>本地模式</strong><span>数据保存在当前电脑</span></div></div>
        <button type="button" class="nav-item disabled" disabled>
          <span class="nav-icon" data-icon="settings" aria-hidden="true"></span><span>系统设置</span><span class="nav-soon">后续</span>
        </button>
      </div>
    </aside>

    <div class="studio-main">
      <header class="topbar">
        <div class="page-heading">
          <button v-if="projectMode" type="button" class="back-button" @click="router.push('/')">←</button>
          <div><h1>{{ title }}</h1><p v-if="subtitle">{{ subtitle }}</p></div>
        </div>
        <div class="topbar-actions">
          <slot name="topbar" />
          <button type="button" class="icon-button" title="通知（后续功能）" disabled><span aria-hidden="true">◌</span></button>
          <div class="avatar-button" title="本地用户">本</div>
        </div>
      </header>

      <main class="studio-content"><slot /></main>
    </div>
  </div>
</template>
