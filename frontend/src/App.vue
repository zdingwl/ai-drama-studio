<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import AppShell from '@/components/AppShell.vue'
import ProductJourneyNav from '@/components/ProductJourneyNav.vue'
import P14AcceptanceReadinessPanel from '@/components/P14AcceptanceReadinessPanel.vue'
import P14TimingOverflowTriage from '@/components/P14TimingOverflowTriage.vue'
import ReplicaProductionWorkspace from '@/components/ReplicaProductionWorkspace.vue'
import P6AcceptancePanel from '@/components/P6AcceptancePanel.vue'
import P7SourceUnderstandingWorkspace from '@/components/P7SourceUnderstandingWorkspace.vue'
import P8ShotBreakdownPanel from '@/components/P8ShotBreakdownPanel.vue'
import P9SourceResolutionPanel from '@/components/P9SourceResolutionPanel.vue'
import SourceResultApprovalBar from '@/components/SourceResultApprovalBar.vue'
import SourceScriptStoryboardWorkspace from '@/components/SourceScriptStoryboardWorkspace.vue'
import TargetAssetsWorkspace from '@/components/TargetAssetsWorkspace.vue'
import TargetAudioRetakeWorkspace from '@/components/TargetAudioRetakeWorkspace.vue'
import TargetAudioTimingWorkspace from '@/components/TargetAudioTimingWorkspace.vue'
import TargetBibleWorkspace from '@/components/TargetBibleWorkspace.vue'
import TargetScriptWorkspace from '@/components/TargetScriptWorkspace.vue'

const route = useRoute()
const isProjectWorkspace = computed(() => route.name === 'project-workspace')
const debugMode = computed(() => route.query.debug === '1')
const activeWorkspace = computed(() => String(route.params.workspace ?? 'source'))
</script>

<template>
  <AppShell>
    <div :class="[{ 'product-mode': isProjectWorkspace && !debugMode }, `workspace-${activeWorkspace}`]">
      <ProductJourneyNav v-if="isProjectWorkspace && !debugMode" />
      <RouterView />
      <section v-if="isProjectWorkspace && activeWorkspace === 'script'" class="product-page"><SourceScriptStoryboardWorkspace /><TargetBibleWorkspace /><TargetScriptWorkspace /></section>
      <section v-if="isProjectWorkspace && activeWorkspace === 'assets'" class="product-page"><TargetAssetsWorkspace /></section>
      <section v-if="isProjectWorkspace && activeWorkspace === 'storyboard'" class="product-page"><ReplicaProductionWorkspace workspace="storyboard" /></section>
      <section v-if="isProjectWorkspace && activeWorkspace === 'generation'" class="product-page">
        <ReplicaProductionWorkspace workspace="generation" />
        <details class="advanced-audio"><summary>高级声音设置</summary><p>默认使用 H3 音画联合生成。只有指定声线、独立配音或兼容旧项目时才需要这里。</p><TargetAudioTimingWorkspace /><P14TimingOverflowTriage /><TargetAudioRetakeWorkspace /><P14AcceptanceReadinessPanel /></details>
      </section>
      <section v-if="isProjectWorkspace && activeWorkspace === 'final'" class="product-page"><ReplicaProductionWorkspace workspace="final" /></section>

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
 * followed by business-facing Target Bible, Target Script, Target Assets, audio/timing, storyboard, generation and final-output workspaces for Replica projects.
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
.product-mode:not(.workspace-source) #source-input>.understanding-section{display:none}.product-mode .product-page{display:grid;gap:18px;max-width:1360px;margin:0 auto}.product-mode .product-page>*{width:100%;margin-top:0;margin-bottom:0}.advanced-audio{padding:16px 18px;border:1px solid #deded8;border-radius:14px;background:#fff}.advanced-audio>summary{cursor:pointer;font-weight:800}.advanced-audio>p{color:#74706a;font-size:13px}.advanced-audio>*:not(summary):not(p){margin-top:18px!important}
</style>
