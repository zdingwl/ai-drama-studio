<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '@/components/AppShell.vue'
import P6AcceptancePanel from '@/components/P6AcceptancePanel.vue'
import P7SourceUnderstandingWorkspace from '@/components/P7SourceUnderstandingWorkspace.vue'
import P8ShotBreakdownPanel from '@/components/P8ShotBreakdownPanel.vue'
import P9SourceResolutionPanel from '@/components/P9SourceResolutionPanel.vue'
import SourceResultApprovalBar from '@/components/SourceResultApprovalBar.vue'
import SourceScriptStoryboardWorkspace from '@/components/SourceScriptStoryboardWorkspace.vue'
import TargetBibleWorkspace from '@/components/TargetBibleWorkspace.vue'

const route = useRoute()
const isProjectWorkspace = computed(() => route.name === 'project-workspace')
const debugMode = computed(() => route.query.debug === '1')
</script>

<template>
  <AppShell>
    <div :class="{ 'product-mode': isProjectWorkspace && !debugMode }">
      <RouterView />
      <SourceScriptStoryboardWorkspace v-if="isProjectWorkspace" />
      <TargetBibleWorkspace v-if="isProjectWorkspace" />

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
 * Product mode exposes one source-analysis action and the resulting script / storyboard,
 * followed by the business-facing Target Bible workspace for Replica projects.
 * The existing P5-P10 engineering surfaces stay available at ?debug=1 for acceptance
 * and diagnostics without making ordinary users operate the internal pipeline.
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
</style>
