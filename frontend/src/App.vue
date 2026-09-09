<script setup lang="ts">
import { useRoute } from 'vue-router'

import AppShell from '@/components/AppShell.vue'
import P6AcceptancePanel from '@/components/P6AcceptancePanel.vue'
import P7SourceBiblePanel from '@/components/P7SourceBiblePanel.vue'

const route = useRoute()
</script>

<template>
  <AppShell>
    <RouterView />
    <P6AcceptancePanel v-if="route.name === 'project-workspace'" />
    <P7SourceBiblePanel v-if="route.name === 'project-workspace'" />
  </AppShell>
</template>
