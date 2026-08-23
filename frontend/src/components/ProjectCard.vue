<script setup lang="ts">
import { computed } from 'vue'
import type { Project } from '../types/project'

const props = defineProps<{ project: Project; disabled?: boolean }>()
const emit = defineEmits<{ open: [projectId: string] }>()

const coverVariant = computed(() => {
  const tail = props.project.id.slice(-1)
  const parsed = Number.parseInt(tail, 16)
  return Number.isNaN(parsed) ? 0 : parsed % 4
})

function displayDate(value: string | null): string {
  if (!value) return '尚未打开'
  const date = new Date(value)
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
</script>

<template>
  <button
    type="button"
    class="project-card"
    :class="`project-cover-${coverVariant}`"
    :disabled="disabled"
    @click="emit('open', project.id)"
  >
    <div class="project-cover">
      <div class="cover-grid"></div>
      <div class="cover-orb cover-orb-a"></div>
      <div class="cover-orb cover-orb-b"></div>
      <div class="cover-clapper">
        <span></span><span></span><span></span>
      </div>
      <span class="project-status"><i></i> {{ project.status === 'ready' ? '可打开' : '创建中' }}</span>
      <span class="project-arrow">↗</span>
    </div>

    <div class="project-card-body">
      <div class="project-title-row">
        <strong>{{ project.name }}</strong>
        <span class="locale-chip">{{ project.target_language.toUpperCase() }} · {{ project.target_region }}</span>
      </div>
      <div class="project-meta-row">
        <span>{{ project.source_language ? project.source_language.toUpperCase() : '待识别' }}</span>
        <b>→</b>
        <span>{{ project.target_language.toUpperCase() }}</span>
        <span class="meta-divider"></span>
        <span>Format v{{ project.project_format_version }}</span>
      </div>
      <p class="project-id">{{ project.id }}</p>
      <div class="project-card-footer">
        <span>最近打开 {{ displayDate(project.last_opened_at) }}</span>
        <span class="open-label">进入项目 →</span>
      </div>
    </div>
  </button>
</template>
