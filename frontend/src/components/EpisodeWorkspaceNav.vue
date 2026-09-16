<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getEpisodeShotBoundary, getProject, listProjectEpisodes } from '@/features/projects/api'
import type { EpisodeRead, EpisodeShotBoundaryRead, ProjectRead } from '@/features/projects/types'
import { apiRequest } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const episodes = ref<EpisodeRead[]>([])
const boundaries = ref<Record<string, EpisodeShotBoundaryRead | null>>({})
const loading = ref(false)
const uploading = ref(false)
const error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const selectedEpisodeId = computed(() => String(route.query.episode ?? ''))

function duration(us: number) {
  const totalSeconds = Math.max(0, Math.round(us / 1_000_000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function displayName(filename: string) {
  return filename.replace(/\.[^.]+$/, '')
}

async function selectEpisode(episode: EpisodeRead) {
  await router.replace({ path: route.path, query: { ...route.query, episode: episode.id, ep: String(episode.episode_order) } })
}

async function load() {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const [projectResult, episodeRows] = await Promise.all([getProject(projectId.value), listProjectEpisodes(projectId.value)])
    project.value = projectResult
    episodes.value = [...episodeRows].sort((a, b) => a.episode_order - b.episode_order)
    const rows = await Promise.all(episodes.value.map(async episode => {
      try { return [episode.id, await getEpisodeShotBoundary(projectId.value, episode.id)] as const }
      catch { return [episode.id, null] as const }
    }))
    boundaries.value = Object.fromEntries(rows)
    const selected = episodes.value.find(item => item.id === selectedEpisodeId.value) ?? episodes.value[0]
    if (selected && selected.id !== selectedEpisodeId.value) await selectEpisode(selected)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '读取剧集失败'
  } finally {
    loading.value = false
  }
}

function chooseFiles() { fileInput.value?.click() }

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  if (!input.files?.length || uploading.value) return
  uploading.value = true
  error.value = ''
  try {
    const data = new FormData()
    Array.from(input.files).forEach(file => data.append('files', file))
    await apiRequest<EpisodeRead[]>(`/projects/${projectId.value}/sources/videos`, { method: 'POST', body: data })
    await load()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '新增剧集失败'
  } finally {
    uploading.value = false
    input.value = ''
  }
}

onMounted(() => { void load() })
watch(projectId, () => { void load() })
</script>

<template>
  <section id="episode-workspace-nav" class="episode-workspace-nav" aria-label="剧集选择">
    <div class="project-crumb"><span>项目</span><i>/</i><strong>{{ project?.name || '当前项目' }}</strong></div>
    <p v-if="error" class="episode-error">{{ error }}</p>
    <div class="episode-rail" :class="{ loading }">
      <button v-for="episode in episodes" :key="episode.id" type="button" class="episode-card" :class="{ active: selectedEpisodeId === episode.id }" @click="selectEpisode(episode)">
        <span class="episode-index">{{ episode.episode_order }}</span>
        <span class="episode-copy"><strong>第 {{ episode.episode_order }} 集</strong><small :title="episode.source_asset.original_filename">{{ displayName(episode.source_asset.original_filename) }}</small><em>{{ boundaries[episode.id]?.shot_count ?? 0 }} 镜 · {{ duration(episode.duration_us) }}</em></span>
        <span v-if="boundaries[episode.id]?.status === 'CURRENT'" class="episode-ready" aria-label="已完成镜头分析">✓</span>
      </button>
      <button type="button" class="add-episode" :disabled="uploading" @click="chooseFiles"><b>＋</b><span>{{ uploading ? '正在上传…' : '新增剧集' }}</span></button>
      <input ref="fileInput" class="visually-hidden" type="file" multiple accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm,.avi,.m4v" @change="upload" />
    </div>
  </section>
</template>

<style scoped>
.episode-workspace-nav{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:8px 14px;padding:6px 14px 7px;border-bottom:1px solid #e7e8ef;background:#fff}.project-crumb{display:flex;align-items:center;gap:7px;min-width:0;color:#7f8ba0;font-size:10px}.project-crumb i{color:#c3c8d2;font-style:normal}.project-crumb strong{max-width:180px;overflow:hidden;color:#253655;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.episode-error{grid-column:1/-1;margin:0;padding:6px 8px;border-radius:7px;background:#fff1ef;color:#a33b32;font-size:10px}.episode-rail{display:flex;gap:7px;min-width:0;overflow-x:auto;padding:1px 0;scrollbar-width:thin}.episode-rail.loading{opacity:.72}.episode-card,.add-episode{position:relative;display:flex;align-items:center;flex:0 0 194px;gap:8px;min-height:50px;padding:6px 9px;border:1px solid #e1e4eb;border-radius:9px;background:#fff;color:#344562;text-align:left;cursor:pointer}.episode-card:hover{border-color:#c8c2ff;background:#fbfaff}.episode-card.active{border-color:#745af5;background:linear-gradient(135deg,#fbfaff,#f4f1ff);box-shadow:inset 0 0 0 1px rgba(116,90,245,.14)}.episode-index{display:grid;place-items:center;flex:0 0 28px;width:28px;height:28px;border-radius:8px;background:#f1f2f6;color:#50617e;font-size:11px;font-weight:850}.active .episode-index{background:#ebe7ff;color:#634cf0}.episode-copy{display:grid;min-width:0;gap:0}.episode-copy strong{font-size:12px}.episode-copy small,.episode-copy em{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.episode-copy small{color:#6352df;font-size:10px}.episode-copy em{color:#7f8ba0;font-size:10px;font-style:normal}.episode-ready{position:absolute;top:5px;right:5px;display:grid;place-items:center;width:14px;height:14px;border-radius:50%;background:#3db46c;color:#fff;font-size:9px;font-weight:900}.add-episode{flex-basis:130px;justify-content:center;border-style:dashed;color:#51617c}.add-episode b{font-size:17px;font-weight:400}.add-episode span{font-size:11px;font-weight:700}.add-episode:disabled{opacity:.55;cursor:wait}@media(max-width:1180px){.episode-workspace-nav{grid-template-columns:1fr;gap:5px}.project-crumb strong{max-width:420px}.episode-card,.add-episode{flex-basis:180px}}@media(max-width:980px){.episode-workspace-nav{padding:7px 10px}.episode-card,.add-episode{flex-basis:170px}}
</style>
