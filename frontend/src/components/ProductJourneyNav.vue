<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getProject } from '@/features/projects/api'
import type { ProjectType } from '@/features/projects/types'

type WorkspaceId = 'source' | 'script' | 'assets' | 'storyboard' | 'generation' | 'final'

const route = useRoute()
const router = useRouter()
const projectType = ref<ProjectType | null>(null)
const allSteps: { id: WorkspaceId; label: string; hint: string }[] = [
  { id: 'source', label: '原作', hint: '上传与解析' },
  { id: 'script', label: '剧本', hint: '故事、剧集、对白' },
  { id: 'assets', label: '资产', hint: '人物、场景、道具' },
  { id: 'storyboard', label: '分镜', hint: '镜头生成计划' },
  { id: 'generation', label: '生成', hint: '音画联合生成' },
  { id: 'final', label: '成片', hint: '检查与导出' },
]

const activeId = computed<WorkspaceId>(() => (route.params.workspace as WorkspaceId | undefined) ?? 'source')
const visibleSteps = computed(() => projectType.value === 'SCRIPT_LOCALIZATION' ? allSteps.slice(0, 2) : allSteps)

function openWorkspace(id: WorkspaceId) {
  void router.push(`/projects/${String(route.params.id)}/${id}`)
}

onMounted(async () => {
  try {
    projectType.value = (await getProject(String(route.params.id))).project_type
    if (projectType.value === 'SCRIPT_LOCALIZATION' && !['source', 'script'].includes(activeId.value)) {
      await router.replace(`/projects/${String(route.params.id)}/script`)
    }
  }
  catch { projectType.value = null }
})
</script>

<template>
  <nav class="journey-nav" aria-label="项目制作流程">
    <button v-for="(step, index) in visibleSteps" :key="step.id" type="button" :class="{ active: activeId === step.id }" :aria-current="activeId === step.id ? 'page' : undefined" @click="openWorkspace(step.id)">
      <span class="journey-number">{{ index + 1 }}</span>
      <span><strong>{{ step.label }}</strong><small>{{ step.hint }}</small></span>
    </button>
  </nav>
</template>

<style scoped>
.journey-nav{position:sticky;top:76px;z-index:45;display:grid;grid-template-columns:repeat(6,minmax(0,1fr));max-width:1360px;margin:0 auto 18px;padding:7px;border:1px solid #e3e1dc;border-radius:16px;background:rgba(255,255,255,.95);box-shadow:0 10px 32px rgba(35,31,26,.08);backdrop-filter:blur(14px)}
.journey-nav button{position:relative;display:flex;align-items:center;gap:9px;min-width:0;padding:10px 12px;border:0;border-radius:11px;background:transparent;color:#77736d;text-align:left;cursor:pointer;transition:.18s ease}
.journey-nav button:not(:last-child)::after{content:'';position:absolute;right:-4px;width:8px;height:1px;background:#d9d6d0}.journey-nav button:hover{background:#f7f5ff;color:#5b4ee8}.journey-nav button.active{background:#f0edff;color:#5143df;box-shadow:inset 0 0 0 1px #ddd7ff}
.journey-number{display:grid;place-items:center;flex:0 0 28px;width:28px;height:28px;border-radius:9px;background:#efeee9;color:#68645f;font-size:12px;font-weight:850}.active .journey-number{background:#6152e8;color:#fff}.journey-nav button>span:last-child{display:grid;min-width:0;gap:2px}.journey-nav strong,.journey-nav small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.journey-nav strong{font-size:13px}.journey-nav small{font-size:10px;font-weight:500;opacity:.72}
@media(max-width:980px){.journey-nav{top:68px;display:flex;overflow-x:auto}.journey-nav button{flex:0 0 132px}.journey-nav button:not(:last-child)::after{display:none}}
</style>
