<script setup lang="ts">
import { useRoute } from 'vue-router'

import AppShell from '@/components/AppShell.vue'
import P6AcceptancePanel from '@/components/P6AcceptancePanel.vue'
import P7SourceUnderstandingWorkspace from '@/components/P7SourceUnderstandingWorkspace.vue'
import P8ShotBreakdownPanel from '@/components/P8ShotBreakdownPanel.vue'
import P9SourceResolutionPanel from '@/components/P9SourceResolutionPanel.vue'
import SourceResultApprovalBar from '@/components/SourceResultApprovalBar.vue'

const route = useRoute()
</script>

<template>
  <AppShell>
    <RouterView />
    <P6AcceptancePanel v-if="route.name === 'project-workspace'" />
    <P7SourceUnderstandingWorkspace v-if="route.name === 'project-workspace'" />
    <P8ShotBreakdownPanel v-if="route.name === 'project-workspace'" />
    <P9SourceResolutionPanel v-if="route.name === 'project-workspace'" />
    <SourceResultApprovalBar v-if="route.name === 'project-workspace'" />
  </AppShell>
</template>
