<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const workspaceKey = ref(0)

function handleTaskFinished() {
  // 统一让当前工作区重新读取 Project / Shot / Asset 最新状态。
  workspaceKey.value += 1
}

onMounted(() => window.addEventListener('studio-task-finished', handleTaskFinished))
onUnmounted(() => window.removeEventListener('studio-task-finished', handleTaskFinished))
</script>

<template>
  <RouterView :key="workspaceKey" />
</template>
