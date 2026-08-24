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

// 用户侧栏只展示 Workflow，不再把内部 F01/F02/F03/F04/F05 直接当成用户步骤。
// Workflow 01 在首页“导入原片”一次完成；进入项目后点击 01 可回到项目总览查看导入结果。
const projectNav = computed(() => [
  {
    label: '导入原片',
    step: '01',
    enabled: true,
    active: ['workspace', 'source-video', 'preprocess'].includes(String(route.name || '')),
    routeName: 'workspace',
  },
  {
    label: '拉片',
    step: '02',
    enabled: true,
    active: ['shot-detection', 'shot-workbench'].includes(String(route.name || '')),
    routeName: 'shot-detection',
  },
  {
    label: '人物对白',
    step: '03',
    enabled: true,
    active: route.name === 'character-detection',
    routeName: 'character-detection',
  },
  { label: '剧本 / 重制设计', step: '04', enabled: false, active: false, routeName: '' },
  { label: '生成制作', step: '05', enabled: false, active: false, routeName: '' },
  { label: '最终合成 / 导出', step: '06', enabled: false, active: false, routeName: '' },
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
        <div class="project-nav-title"><span>生产工作流</span><strong :title="projectName">{{ projectName || '项目工作区' }}</strong></div>
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
