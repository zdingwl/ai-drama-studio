<script setup lang="ts">
import type { Project } from '../types/project'

defineProps<{ project: Project; disabled?: boolean }>()
const emit = defineEmits<{ open: [projectId: string] }>()

function displayDate(value: string | null): string {
  return value ? new Date(value).toLocaleString('zh-CN') : '尚未打开'
}
</script>

<template>
  <button class="project-card" :disabled="disabled" @click="emit('open', project.id)">
    <strong>{{ project.name }}</strong>
    <span>{{ project.source_language || '待识别' }} → {{ project.target_language }} / {{ project.target_region }}</span>
    <span class="path">{{ project.workspace_path }}</span>
    <span>最近打开：{{ displayDate(project.last_opened_at) }}</span>
  </button>
</template>
