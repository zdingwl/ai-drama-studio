<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api/client'
import type { Episode, Project } from '../types/studio'

const props = defineProps<{
  project: Project
}>()

const emit = defineEmits<{
  refresh: []
}>()

const busy = ref('')
const error = ref('')
const draggedId = ref<string | null>(null)

function seconds(us: number | null): string {
  return us === null ? '—' : `${(us / 1_000_000).toFixed(2)}s`
}

/**
 * 职责：统一执行剧集管理写操作。
 * 输入：用户动作名称 + API；输出：成功后通知父工作台重新读取项目。
 * 为什么：导入、排序、删除都属于 Project/Episode 管理，不应该和拉片/资产状态混在一起。
 */
async function run(label: string, action: () => Promise<unknown>): Promise<void> {
  busy.value = label
  error.value = ''
  try {
    await action()
    emit('refresh')
  } catch (err) {
    error.value = err instanceof Error ? err.message : `${label}失败`
  } finally {
    busy.value = ''
  }
}

async function uploadFiles(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  if (!files.length) return
  await run('正在导入视频', () => api.uploadEpisodes(props.project.id, files))
  input.value = ''
}

function dragStart(episodeId: string): void {
  draggedId.value = episodeId
}

async function dropOn(targetId: string): Promise<void> {
  const sourceId = draggedId.value
  draggedId.value = null
  if (!sourceId || sourceId === targetId) return
  const reordered = [...props.project.episodes]
  const sourceIndex = reordered.findIndex((item) => item.id === sourceId)
  const targetIndex = reordered.findIndex((item) => item.id === targetId)
  if (sourceIndex < 0 || targetIndex < 0) return
  const [moved] = reordered.splice(sourceIndex, 1)
  reordered.splice(targetIndex, 0, moved)
  await run('正在保存剧集顺序', () => api.reorderEpisodes(props.project.id, reordered.map((item) => item.id)))
}

async function removeEpisode(episode: Episode): Promise<void> {
  if (!window.confirm(`删除「${episode.title}」及其当前分析结果？`)) return
  await run('正在删除剧集', () => api.deleteEpisode(episode.id))
}
</script>

<template>
  <section class="workspace-panel">
    <div class="section-title">
      <div><span>01</span><h2>剧集管理</h2></div>
      <label class="primary-button file-button">导入多个视频<input type="file" multiple accept="video/*" @change="uploadFiles" /></label>
    </div>
    <p class="section-help">一个项目代表一部短剧。批量导入后可拖动调整剧集顺序；批量拉片严格按照这里的顺序逐集处理。</p>
    <p v-if="error" class="error-banner">{{ error }}</p>
    <div v-if="busy" class="busy-banner"><span class="spinner"></span>{{ busy }}…</div>

    <div v-if="project.episodes.length === 0" class="empty-state large">
      <strong>还没有剧集</strong>
      <span>一次选择多个视频导入即可。Proxy / Audio 等技术准备会在拉片时自动执行。</span>
    </div>
    <div v-else class="episode-list">
      <div
        v-for="episode in project.episodes"
        :key="episode.id"
        class="episode-row"
        draggable="true"
        @dragstart="dragStart(episode.id)"
        @dragover.prevent
        @drop="dropOn(episode.id)"
      >
        <div class="drag-handle">⋮⋮</div>
        <div class="episode-index">{{ String(episode.sort_order).padStart(2, '0') }}</div>
        <div class="episode-main"><strong>{{ episode.title }}</strong><small>{{ episode.original_filename }}</small></div>
        <div class="episode-meta">
          <span>{{ seconds(episode.duration_us) }}</span>
          <span>{{ episode.preprocess_status === 'READY' ? '分析素材已准备' : '拉片时自动准备' }}</span>
          <span>{{ episode.shot_count }} Shots</span>
        </div>
        <button class="danger-text" :disabled="!!busy" @click="removeEpisode(episode)">删除</button>
      </div>
    </div>

    <div class="architecture-note">
      <strong>项目设置</strong>
      <p>{{ project.name }} · {{ project.source_language }} → {{ project.target_language }} · {{ project.target_region }}。语言与目标地区属于项目属性，不占生产阶段。</p>
    </div>
  </section>
</template>