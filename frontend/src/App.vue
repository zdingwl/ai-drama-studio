<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import SourceConfirmOverlayV1 from './components/SourceConfirmOverlayV1.vue'
import './styles/character-confirm-flow-v1.css'
import './styles/character-confirm-image-fix-v1.css'
import './styles/character-confirm-locator-image-fix-v1.css'

const route = useRoute()
const workspaceKey = ref(0)

const sourceConfirmProjectId = computed(() => {
  if (route.name !== 'breakdown' || String(route.query.mode || '') !== 'confirm') return ''
  return String(route.params.projectId || '')
})

function handleTaskFinished() {
  // 统一让当前工作区重新读取 Project / Shot / Asset 最新状态。
  workspaceKey.value += 1
}

onMounted(() => window.addEventListener('studio-task-finished', handleTaskFinished))
onUnmounted(() => window.removeEventListener('studio-task-finished', handleTaskFinished))
</script>

<template>
  <RouterView :key="workspaceKey" />
  <SourceConfirmOverlayV1 v-if="sourceConfirmProjectId" :project-id="sourceConfirmProjectId" />
</template>
