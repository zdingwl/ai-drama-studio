<script setup lang="ts">
import { onMounted } from 'vue'

import { useAppStore } from '@/stores/app'

const appStore = useAppStore()

onMounted(() => {
  appStore.markReady()
})
</script>

<template>
  <section class="hero">
    <p class="eyebrow">V3 重建基线</p>
    <h1>AI 短剧生产工作台</h1>
    <p class="description">新的业务能力将从六类项目入口开始逐阶段建设。</p>
    <p class="status">{{ appStore.ready ? '前端骨架已就绪' : '正在初始化' }}</p>
  </section>
</template>
