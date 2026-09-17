<script setup lang="ts">
import { RouterLink } from 'vue-router'

defineProps<{ wide?: boolean }>()
</script>

<template>
  <div class="app-shell" :class="{ wide }">
    <header class="app-header">
      <RouterLink to="/" class="brand-lockup">
        <span class="brand-mark" aria-hidden="true">剧</span>
        <div>
          <strong>AI 短剧工坊</strong>
          <small>用 AI 让好故事走向全世界</small>
        </div>
      </RouterLink>
      <div class="header-actions">
        <span class="save-state"><i/> 自动保存</span>
        <span class="header-icon" aria-hidden="true">?</span>
        <span class="header-icon" aria-hidden="true">⚙</span>
        <span class="account-chip">创作者</span>
      </div>
    </header>
    <main class="app-main">
      <slot />
    </main>
  </div>
</template>

<style scoped>
.brand-lockup {
  text-decoration: none;
  color: inherit;
  cursor: pointer;
}
</style>
