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

const route = useRoute()
const isProjectWorkspace = computed(() => route.name === 'project-workspace')
const debugMode = computed(() => route.query.debug === '1')
</script>

<template>
  <AppShell>
    <RouterView />
    <SourceScriptStoryboardWorkspace v-if="isProjectWorkspace" />

    <template v-if="isProjectWorkspace && debugMode">
      <P6AcceptancePanel />
      <P7SourceUnderstandingWorkspace />
      <P8ShotBreakdownPanel />
      <P9SourceResolutionPanel />
      <SourceResultApprovalBar />
    </template>
  </AppShell>
</template>
