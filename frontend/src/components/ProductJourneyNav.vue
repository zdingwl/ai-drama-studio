<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getProject } from '@/features/projects/api'
import type { ProjectType } from '@/features/projects/types'

type WorkspaceId = 'overview' | 'episodes' | 'source' | 'localize' | 'assets' | 'prompts' | 'generation' | 'script' | 'storyboard' | 'final'

const route = useRoute()
const router = useRouter()
const projectType = ref<ProjectType | null>(null)
const replicaSteps: { id: WorkspaceId; label: string; hint: string }[] = [
  { id: 'source', label: '原片分镜', hint: '分析视频 · 获取分镜' },
  { id: 'localize', label: '本土化分镜', hint: '中文描述 · 本土对白' },
  { id: 'assets', label: '视觉资产', hint: '人物 · 场景 · 道具' },
  { id: 'prompts', label: 'H3 提示词', hint: '多参考 · 音画提示词' },
  { id: 'generation', label: '视频生成', hint: '生成 · 审核 · 重做' },
]
const scriptSteps: { id: WorkspaceId; label: string; hint: string }[] = [
  { id: 'source', label: '原剧本', hint: '上传与粘贴' },
  { id: 'script', label: '本土化剧本', hint: '分析与改写' },
]
const legacySteps: { id: WorkspaceId; label: string; hint: string }[] = [
  { id: 'source', label: '原作', hint: '上传与解析' },
  { id: 'script', label: '剧本', hint: '故事、剧集、对白' },
  { id: 'assets', label: '资产', hint: '人物、场景、道具' },
  { id: 'storyboard', label: '分镜', hint: '镜头生成计划' },
  { id: 'generation', label: '生成', hint: '生成结果' },
  { id: 'final', label: '成片', hint: '检查与导出' },
]

const activeId = computed<WorkspaceId>(() => (route.params.workspace as WorkspaceId | undefined) ?? 'source')
const visibleSteps = computed(() => projectType.value === 'REPLICA' ? replicaSteps : projectType.value === 'SCRIPT_LOCALIZATION' ? scriptSteps : legacySteps)

function openWorkspace(id: WorkspaceId) {
  void router.push({ path: `/projects/${String(route.params.id)}/${id}`, query: route.query })
}

function workspaceHref(id: WorkspaceId) { return `/projects/${String(route.params.id)}/${id}` }

async function loadProject() {
  try {
    const id = String(route.params.id)
    const type = (await getProject(id)).project_type
    if (id !== String(route.params.id)) return
    projectType.value = type
    if (type === 'REPLICA') {
      const legacyRedirect: Partial<Record<WorkspaceId, WorkspaceId>> = { script: 'localize', storyboard: 'prompts', final: 'generation' }
      const target = legacyRedirect[activeId.value]
      if (target) await router.replace(`/projects/${id}/${target}`)
    } else if (type === 'SCRIPT_LOCALIZATION' && !['source', 'script', 'overview'].includes(activeId.value)) {
      await router.replace(`/projects/${id}/source`)
    }
  } catch { projectType.value = null }
}
onMounted(() => { void loadProject() })
watch(() => route.params.id, () => { projectType.value = null; void loadProject() })
</script>

<template>
  <nav class="journey-nav" :class="{ replica: projectType === 'REPLICA' }" aria-label="项目制作流程">
    <section class="nav-group">
      <span class="group-title">项目</span>
      <a class="utility-link" :class="{ active: activeId === 'overview' }" :href="workspaceHref('overview')" @click.prevent="openWorkspace('overview')"><span aria-hidden="true">▦</span><strong>项目概览</strong></a>
      <a v-if="projectType !== 'SCRIPT_LOCALIZATION'" class="utility-link" :class="{ active: activeId === 'episodes' }" :href="workspaceHref('episodes')" @click.prevent="openWorkspace('episodes')"><span aria-hidden="true">▣</span><strong>剧集管理</strong></a>
    </section>
    <section class="nav-group flow-group">
      <span class="group-title">制作流程</span>
      <div class="journey-steps">
        <button v-for="(step, index) in visibleSteps" :key="step.id" type="button" :class="{ active: activeId === step.id }" :aria-current="activeId === step.id ? 'page' : undefined" @click="openWorkspace(step.id)">
          <span class="journey-number">{{ index + 1 }}</span>
          <span class="journey-copy"><strong>{{ step.label }}</strong></span>
        </button>
      </div>
    </section>
    <section class="nav-group system-group">
      <span class="group-title">系统</span>
      <span class="utility-link passive"><span aria-hidden="true">⚙</span><strong>项目设置</strong></span>
      <span class="utility-link passive"><span aria-hidden="true">?</span><strong>使用帮助</strong></span>
    </section>
  </nav>
</template>

<style scoped>
.journey-nav{position:sticky;top:56px;display:flex;flex-direction:column;height:calc(100vh - 56px);padding:14px 10px 12px;border-right:1px solid #e8eaf1;background:#fbfcff;color:#263653}.nav-group{display:grid;gap:6px;padding:0 0 14px}.nav-group+.nav-group{padding-top:14px;border-top:1px solid #ececf3}.group-title{padding:0 10px 4px;color:#939db0;font-size:12px;font-weight:800;letter-spacing:.06em}.utility-link{display:flex;align-items:center;gap:10px;min-height:38px;padding:0 10px;border-radius:9px;color:#425273;text-decoration:none}.utility-link>span{display:grid;place-items:center;width:24px;color:#556886;font-size:14px}.utility-link strong{font-size:14px;font-weight:700}.utility-link:hover,.utility-link.active{background:#f1efff;color:#5345dc}.passive{cursor:default}.journey-steps{display:grid;gap:5px}.journey-nav button{display:flex;align-items:center;gap:10px;width:100%;min-height:44px;padding:6px 10px;border:0;border-radius:10px;background:transparent;color:#475778;text-align:left;cursor:pointer}.journey-nav button:hover{background:#f5f4ff;color:#5142dd}.journey-nav button.active{background:linear-gradient(90deg,#ebe8ff,#f5f3ff);color:#4c3cdb}.journey-number{display:grid;place-items:center;flex:0 0 30px;width:30px;height:30px;border-radius:50%;background:#eef0f5;color:#60708d;font-size:12px;font-weight:850}.active .journey-number{background:#654cf1;color:#fff;box-shadow:0 5px 13px rgba(101,76,241,.24)}.journey-copy{display:grid;min-width:0}.journey-copy strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px}.system-group{margin-top:auto}@media(max-width:980px){.journey-nav{position:static;height:auto;min-height:0;border-right:0;border-bottom:1px solid #e8e9f0;padding:8px}.nav-group:not(.flow-group){display:none}.nav-group+.nav-group{padding-top:0;border-top:0}.flow-group{padding:0}.group-title{display:none}.journey-steps{display:flex;overflow-x:auto}.journey-nav button{flex:0 0 148px}.journey-copy small{display:none}}
</style>
