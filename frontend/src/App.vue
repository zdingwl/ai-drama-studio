<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import SourceConfirmOverlayV4 from './components/SourceConfirmOverlayV4.vue'
import './styles/character-confirm-flow-v1.css'
import './styles/character-confirm-image-fix-v1.css'
import './styles/character-confirm-locator-image-fix-v1.css'
import { installCharacterLocatorViewportV1 } from './utils/characterLocatorViewportV1'

const route = useRoute()
const workspaceKey = ref(0)
let cleanupLocatorViewport: (() => void) | null = null

const projectId = computed(() => String(route.params.projectId || ''))
const showScreenplayEntry = computed(() => Boolean(projectId.value) && route.name !== 'source-screenplay')
const sourceConfirmProjectId = computed(() => {
  if (route.name !== 'breakdown' || String(route.query.mode || '') !== 'confirm') return ''
  return projectId.value
})

function handleTaskFinished() {
  // 统一让当前工作区重新读取 Project / Shot / Asset 最新状态。
  workspaceKey.value += 1
}

onMounted(() => {
  window.addEventListener('studio-task-finished', handleTaskFinished)
  cleanupLocatorViewport = installCharacterLocatorViewportV1()
})

onUnmounted(() => {
  window.removeEventListener('studio-task-finished', handleTaskFinished)
  cleanupLocatorViewport?.()
  cleanupLocatorViewport = null
})
</script>

<template>
  <RouterView :key="workspaceKey" />
  <RouterLink
    v-if="showScreenplayEntry"
    class="screenplay-entry"
    :to="{ name: 'source-screenplay', params: { projectId } }"
  >
    剧本母版
  </RouterLink>
  <SourceConfirmOverlayV4 v-if="sourceConfirmProjectId" :project-id="sourceConfirmProjectId" />
</template>

<style scoped>
.screenplay-entry {
  position: fixed;
  right: 22px;
  bottom: 22px;
  z-index: 40;
  display: inline-flex;
  align-items: center;
  min-height: 42px;
  padding: 0 16px;
  border: 1px solid rgba(22, 25, 29, .1);
  border-radius: 999px;
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 8px 26px rgba(26, 32, 39, .12);
  color: #20242a;
  font-size: 14px;
  font-weight: 700;
  text-decoration: none;
  backdrop-filter: blur(10px);
}
.screenplay-entry:hover { transform: translateY(-1px); }
</style>
