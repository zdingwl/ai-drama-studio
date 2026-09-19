<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '@/components/AppShell.vue'
import AssetImagesWorkspace from '@/components/AssetImagesWorkspace.vue'
import EpisodeManagementWorkspace from '@/components/EpisodeManagementWorkspace.vue'
import EpisodeWorkspaceNav from '@/components/EpisodeWorkspaceNav.vue'
import H3GenerationWorkspace from '@/components/H3GenerationWorkspace.vue'
import H3PromptWorkspace from '@/components/H3PromptWorkspace.vue'
import LocalizedStoryboardWorkspace from '@/components/LocalizedStoryboardWorkspace.vue'
import P6AcceptancePanel from '@/components/P6AcceptancePanel.vue'
import P7SourceUnderstandingWorkspace from '@/components/P7SourceUnderstandingWorkspace.vue'
import P8ShotBreakdownPanel from '@/components/P8ShotBreakdownPanel.vue'
import P9SourceResolutionPanel from '@/components/P9SourceResolutionPanel.vue'
import ProjectOverviewWorkspace from '@/components/ProjectOverviewWorkspace.vue'
import ProductJourneyNav from '@/components/ProductJourneyNav.vue'
import ReplicaProductionWorkspace from '@/components/ReplicaProductionWorkspace.vue'
import ScriptLocalizationWorkspace from '@/components/ScriptLocalizationWorkspace.vue'
import SourceResultApprovalBar from '@/components/SourceResultApprovalBar.vue'
import SourceScriptStoryboardWorkspace from '@/components/SourceScriptStoryboardWorkspace.vue'
import SourceStoryboardWorkspace from '@/components/SourceStoryboardWorkspace.vue'
import TargetBibleWorkspace from '@/components/TargetBibleWorkspace.vue'
import TargetScriptWorkspace from '@/components/TargetScriptWorkspace.vue'
import { getProject } from '@/features/projects/api'
import type { ProjectType } from '@/features/projects/types'

const route = useRoute()
const isProjectWorkspace = computed(() => route.name === 'project-workspace')
const debugMode = computed(() => route.query.debug === '1')
const activeWorkspace = computed(() => String(route.params.workspace ?? 'source'))
const projectType = ref<ProjectType | null>(null)
const projectError = ref('')
const scriptLocalization = computed(() => projectType.value === 'SCRIPT_LOCALIZATION')
const hideEpisodeNav = computed(() => scriptLocalization.value || activeWorkspace.value === 'overview' || activeWorkspace.value === 'episodes')
const showRoutedView = computed(() => !isProjectWorkspace.value || debugMode.value)

watch(() => String(route.params.id ?? ''), async id => {
  projectType.value = null
  projectError.value = ''
  if (!id || !isProjectWorkspace.value || debugMode.value) return
  try {
    const project = await getProject(id)
    if (id === String(route.params.id ?? '')) projectType.value = project.project_type
  } catch (exc) {
    if (id === String(route.params.id ?? '')) projectError.value = exc instanceof Error ? exc.message : '读取项目失败'
  }
}, { immediate: true })
</script>

<template>
  <AppShell :wide="isProjectWorkspace && !debugMode">
    <RouterView v-if="showRoutedView" />

    <p v-if="isProjectWorkspace && !debugMode && projectError" class="product-load-state" role="alert">{{ projectError }}</p>
    <p v-else-if="isProjectWorkspace && !debugMode && !projectType" class="product-load-state">正在读取项目类型…</p>
    <div v-else-if="isProjectWorkspace && !debugMode" :class="['product-mode', `workspace-${activeWorkspace}`]">
      <aside class="product-sidebar"><ProductJourneyNav /></aside>
      <div class="product-content" :class="{ 'without-episode-nav': hideEpisodeNav }">
        <EpisodeWorkspaceNav v-if="!hideEpisodeNav" />
        <main id="project-workspace-main" class="product-stage-host">
          <template v-if="scriptLocalization">
            <section v-if="activeWorkspace === 'source' || activeWorkspace === 'overview'" class="product-page"><ScriptLocalizationWorkspace mode="source" /></section>
            <section v-else class="product-page"><ScriptLocalizationWorkspace mode="script" /></section>
          </template>
          <template v-else>
            <section v-if="activeWorkspace === 'overview'" class="product-page"><ProjectOverviewWorkspace /></section>
            <section v-if="activeWorkspace === 'episodes'" class="product-page"><EpisodeManagementWorkspace /></section>
            <section v-if="activeWorkspace === 'source'" class="product-page"><SourceStoryboardWorkspace /></section>
            <section v-if="activeWorkspace === 'localize'" class="product-page"><LocalizedStoryboardWorkspace /></section>
            <section v-if="activeWorkspace === 'assets'" class="product-page"><AssetImagesWorkspace /></section>
            <section v-if="activeWorkspace === 'prompts'" class="product-page"><H3PromptWorkspace /></section>
            <section v-if="activeWorkspace === 'generation'" class="product-page"><H3GenerationWorkspace /></section>
            <section v-if="activeWorkspace === 'script'" class="product-page legacy-product-page"><SourceScriptStoryboardWorkspace /><TargetBibleWorkspace /><TargetScriptWorkspace /></section>
            <section v-if="activeWorkspace === 'storyboard'" class="product-page legacy-product-page"><ReplicaProductionWorkspace workspace="storyboard" /></section>
            <section v-if="activeWorkspace === 'final'" class="product-page legacy-product-page"><ReplicaProductionWorkspace workspace="final" /></section>
          </template>
        </main>
      </div>
    </div>

    <div v-if="isProjectWorkspace && debugMode" :class="`workspace-${activeWorkspace}`">
      <P6AcceptancePanel />
      <P7SourceUnderstandingWorkspace />
      <P8ShotBreakdownPanel />
      <P9SourceResolutionPanel />
      <SourceResultApprovalBar />
    </div>
  </AppShell>
</template>

<style>
/* Preserve the validated Replica five-step surface; text projects use an isolated workspace. */
.product-mode .analysis-principle,
.product-mode .evidence-grid,
.product-mode .technical-details,
.product-mode .task-section,
.product-mode .acceptance-section,
.product-mode .plan-section,
.product-mode .plan-empty,
.product-mode .project-stage { display: none !important; }
.product-mode .project-meta span:nth-child(n + 2),.product-mode .understanding-section .section-note{display:none}
.product-mode .understanding-section{margin-bottom:0}
.product-mode .product-page{display:grid;gap:14px;min-width:0;min-height:0;margin:0}
.product-mode .product-page>*{width:100%;margin-top:0;margin-bottom:0}
.product-load-state{padding:25px;color:#63748b}
.product-mode{display:grid;grid-template-columns:196px minmax(0,1fr);height:calc(100dvh - 56px);min-height:0;overflow:hidden;border-top:0;background:#fff}
.product-sidebar{min-width:0;min-height:0;background:#fbfcff}
.product-content{display:grid;grid-template-rows:auto minmax(0,1fr);min-width:0;min-height:0;overflow:hidden}
.product-content.without-episode-nav{grid-template-rows:minmax(0,1fr)}
.product-stage-host{min-width:0;min-height:0;overflow:auto;padding:10px 14px 12px;background:#f7f8fb}
.product-mode.workspace-source .product-stage-host{overflow:hidden}
.product-mode.workspace-source .product-page{height:100%;min-height:0}
.product-mode.workspace-source .script-workspace{height:100%;overflow:auto}
@media(max-width:980px){.product-mode{grid-template-columns:1fr;height:auto;min-height:calc(100dvh - 56px);overflow:visible}.product-sidebar{position:sticky;top:56px;z-index:50}.product-content,.product-stage-host{overflow:visible}.product-stage-host{padding:10px}.product-mode.workspace-source .product-page{height:auto}}
</style>
