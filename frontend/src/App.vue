<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '@/components/AppShell.vue'
import AssetImagesWorkspace from '@/components/AssetImagesWorkspace.vue'
import H3GenerationWorkspace from '@/components/H3GenerationWorkspace.vue'
import H3PromptWorkspace from '@/components/H3PromptWorkspace.vue'
import LocalizedStoryboardWorkspace from '@/components/LocalizedStoryboardWorkspace.vue'
import P6AcceptancePanel from '@/components/P6AcceptancePanel.vue'
import P7SourceUnderstandingWorkspace from '@/components/P7SourceUnderstandingWorkspace.vue'
import P8ShotBreakdownPanel from '@/components/P8ShotBreakdownPanel.vue'
import P9SourceResolutionPanel from '@/components/P9SourceResolutionPanel.vue'
import ProductJourneyNav from '@/components/ProductJourneyNav.vue'
import ReplicaProductionWorkspace from '@/components/ReplicaProductionWorkspace.vue'
import SourceResultApprovalBar from '@/components/SourceResultApprovalBar.vue'
import SourceScriptStoryboardWorkspace from '@/components/SourceScriptStoryboardWorkspace.vue'
import SourceStoryboardWorkspace from '@/components/SourceStoryboardWorkspace.vue'
import TargetBibleWorkspace from '@/components/TargetBibleWorkspace.vue'
import TargetScriptWorkspace from '@/components/TargetScriptWorkspace.vue'

const route = useRoute()
const isProjectWorkspace = computed(() => route.name === 'project-workspace')
const debugMode = computed(() => route.query.debug === '1')
const activeWorkspace = computed(() => String(route.params.workspace ?? 'source'))
const showRoutedView = computed(() => (
  !isProjectWorkspace.value
  || debugMode.value
  || activeWorkspace.value === 'source'
))
</script>

<template>
  <AppShell>
    <div :class="[{ 'product-mode': isProjectWorkspace && !debugMode }, `workspace-${activeWorkspace}`]">
      <ProductJourneyNav v-if="isProjectWorkspace && !debugMode" />

      <!--
        ProjectWorkspaceView is the source ingest/preflight host only. Mounting it on localize/assets/
        prompts/generation would execute the historical plan/task UI and visually mix old P11-P17
        concepts into the Replica v2 five-step path. Non-project routes and explicit debug mode still
        use the router view normally.
      -->
      <RouterView v-if="showRoutedView" />

      <!-- Replica v2 ordinary product path: docs/55 is the highest-priority contract. -->
      <section v-if="isProjectWorkspace && !debugMode && activeWorkspace === 'source'" class="product-page">
        <SourceStoryboardWorkspace />
      </section>
      <section v-if="isProjectWorkspace && !debugMode && activeWorkspace === 'localize'" class="product-page">
        <LocalizedStoryboardWorkspace />
      </section>
      <section v-if="isProjectWorkspace && !debugMode && activeWorkspace === 'assets'" class="product-page">
        <AssetImagesWorkspace />
      </section>
      <section v-if="isProjectWorkspace && !debugMode && activeWorkspace === 'prompts'" class="product-page">
        <H3PromptWorkspace />
      </section>
      <section v-if="isProjectWorkspace && !debugMode && activeWorkspace === 'generation'" class="product-page">
        <H3GenerationWorkspace />
      </section>

      <!-- Historical routes remain readable for old projects / bookmarked URLs, but are not Replica v2 main-flow prerequisites. -->
      <section v-if="isProjectWorkspace && !debugMode && activeWorkspace === 'script'" class="product-page legacy-product-page">
        <SourceScriptStoryboardWorkspace />
        <TargetBibleWorkspace />
        <TargetScriptWorkspace />
      </section>
      <section v-if="isProjectWorkspace && !debugMode && activeWorkspace === 'storyboard'" class="product-page legacy-product-page">
        <ReplicaProductionWorkspace workspace="storyboard" />
      </section>
      <section v-if="isProjectWorkspace && !debugMode && activeWorkspace === 'final'" class="product-page legacy-product-page">
        <ReplicaProductionWorkspace workspace="final" />
      </section>

      <template v-if="isProjectWorkspace && debugMode">
        <P6AcceptancePanel />
        <P7SourceUnderstandingWorkspace />
        <P8ShotBreakdownPanel />
        <P9SourceResolutionPanel />
        <SourceResultApprovalBar />
      </template>
    </div>
  </AppShell>
</template>

<style>
/*
 * Replica ordinary product mode follows exactly five user-visible stages:
 * source storyboard -> localized storyboard -> real asset images -> model Prompt Skill -> H3 video.
 * P5-P10 engineering surfaces and the historical P11/P12/P14/P15/P17 chain stay outside that path.
 */
.product-mode .analysis-principle,
.product-mode .evidence-grid,
.product-mode .technical-details,
.product-mode .task-section,
.product-mode .acceptance-section,
.product-mode .plan-section,
.product-mode .plan-empty,
.product-mode .project-stage {
  display: none !important;
}

.product-mode .project-meta span:nth-child(n + 2),
.product-mode .understanding-section .section-note {
  display: none;
}

.product-mode .understanding-section {
  margin-bottom: 0;
}

.product-mode .product-page {
  display: grid;
  gap: 18px;
  max-width: 1360px;
  margin: 0 auto;
}

.product-mode .product-page > * {
  width: 100%;
  margin-top: 0;
  margin-bottom: 0;
}
</style>
