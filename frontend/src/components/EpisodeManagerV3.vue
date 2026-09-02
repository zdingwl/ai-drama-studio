<script setup lang="ts">
import { computed, ref } from 'vue'
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

const totalDurationUs = computed(() => props.project.episodes.reduce((sum, episode) => sum + (episode.duration_us ?? 0), 0))
const totalShots = computed(() => props.project.episodes.reduce((sum, episode) => sum + episode.shot_count, 0))

function durationLabel(us: number | null): string {
  if (us === null) return '时长读取中'
  const seconds = Math.max(0, Math.round(us / 1_000_000))
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
}

function episodeState(episode: Episode): { label: string; tone: string } {
  const status = String(episode.preprocess_status || '').toUpperCase()
  if (status === 'FAILED') return { label: '素材准备失败', tone: 'blocked' }
  if (status === 'QUEUED' || status === 'PROCESSING') return { label: '素材准备中', tone: 'processing' }
  if (status === 'READY_WITH_WARNINGS') return { label: '素材需要检查', tone: 'review' }
  if (episode.shot_count > 0) return { label: `已有 ${episode.shot_count} 个镜头`, tone: 'ready' }
  if (status === 'READY') return { label: '素材已准备', tone: 'ready' }
  return { label: '等待自动处理', tone: 'idle' }
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
  <section class="source-stage-v1">
    <header class="source-stage-header">
      <div>
        <small>01 · 源片与剧集</small>
        <h1>导入并确认剧集顺序</h1>
        <p>导入原始视频并按真实剧集顺序排列。确认顺序后，项目会按这里的顺序逐集自动完成拉片、人物、场景、对白和后续生成准备。</p>
      </div>
      <label class="primary-button file-button">+ 导入视频<input type="file" multiple accept="video/*" @change="uploadFiles" /></label>
    </header>

    <p v-if="error" class="error-banner">{{ error }}</p>
    <div v-if="busy" class="busy-banner"><span class="spinner"></span>{{ busy }}…</div>

    <section class="source-summary-strip">
      <div><small>剧集</small><strong>{{ project.episodes.length }} 集</strong></div>
      <div><small>总时长</small><strong>{{ project.episodes.length ? durationLabel(totalDurationUs) : '—' }}</strong></div>
      <div><small>已生成镜头</small><strong>{{ totalShots }} 个</strong></div>
      <div><small>处理顺序</small><strong>从上到下</strong></div>
    </section>

    <div v-if="project.episodes.length === 0" class="source-empty">
      <strong>先导入原始剧集</strong>
      <p>可以一次选择多个视频。导入后只需要拖动调整真实剧集顺序，后续分析由“开始自动处理”统一完成。</p>
      <label class="primary-button file-button">选择视频文件<input type="file" multiple accept="video/*" @change="uploadFiles" /></label>
    </div>

    <section v-else class="source-episode-section">
      <header class="source-list-head">
        <div><strong>剧集顺序</strong><span>拖动左侧手柄即可调整；这里的顺序就是自动处理顺序</span></div>
        <span>{{ project.episodes.length }} 集</span>
      </header>

      <div class="source-episode-list">
        <article
          v-for="episode in project.episodes"
          :key="episode.id"
          class="source-episode-row"
          draggable="true"
          @dragstart="dragStart(episode.id)"
          @dragover.prevent
          @drop="dropOn(episode.id)"
        >
          <div class="source-drag" title="拖动排序">⋮⋮</div>
          <div class="source-order"><small>第</small><strong>{{ String(episode.sort_order).padStart(2, '0') }}</strong><small>集</small></div>
          <div class="source-episode-main">
            <strong>{{ episode.title }}</strong>
            <span>{{ episode.original_filename }}</span>
          </div>
          <div class="source-duration"><small>时长</small><strong>{{ durationLabel(episode.duration_us) }}</strong></div>
          <div :class="['source-state', `tone-${episodeState(episode).tone}`]">
            <span></span><strong>{{ episodeState(episode).label }}</strong>
          </div>
          <button class="source-delete" :disabled="!!busy" @click="removeEpisode(episode)">删除</button>
        </article>
      </div>

      <footer class="source-order-confirmed">
        <span>顺序确认后无需再进入“剧情与镜头”等内部阶段。</span>
        <strong>下一步由项目页的自动处理统一完成。</strong>
      </footer>
    </section>
  </section>
</template>

<style scoped>
.source-stage-v1 {
  max-width: 1420px;
  margin: 0 auto;
  display: grid;
  gap: 14px;
}
.source-stage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding: 22px 24px;
  border: 1px solid #dfe5ed;
  border-radius: 16px;
  background: #fff;
}
.source-stage-header > div { min-width: 0; display: grid; gap: 4px; }
.source-stage-header small { color: #7288ad; font-size: 11px; font-weight: 850; letter-spacing: .04em; }
.source-stage-header h1 { margin: 0; color: #26384f; font-size: 25px; line-height: 1.2; }
.source-stage-header p { margin: 0; max-width: 900px; color: #748196; font-size: 13px; }
.source-summary-strip {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 9px;
}
.source-summary-strip > div {
  display: grid;
  gap: 2px;
  padding: 12px 14px;
  border: 1px solid #e1e6ed;
  border-radius: 11px;
  background: #fff;
}
.source-summary-strip small { color: #8793a4; font-size: 10px; }
.source-summary-strip strong { color: #35465d; font-size: 14px; }
.source-empty {
  min-height: 260px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 9px;
  border: 1px dashed #cfd8e5;
  border-radius: 16px;
  background: #fff;
  text-align: center;
}
.source-empty strong { color: #34465f; font-size: 18px; }
.source-empty p { max-width: 620px; margin: 0 0 5px; color: #7d899b; font-size: 13px; }
.source-episode-section {
  display: grid;
  gap: 10px;
  padding: 16px;
  border: 1px solid #dfe5ed;
  border-radius: 16px;
  background: #fff;
}
.source-list-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 1px 3px 5px; }
.source-list-head > div { display: flex; gap: 9px; align-items: baseline; }
.source-list-head strong { color: #35465f; font-size: 14px; }
.source-list-head span { color: #8995a7; font-size: 11px; }
.source-episode-list { display: grid; gap: 7px; }
.source-episode-row {
  display: grid;
  grid-template-columns: 34px 58px minmax(260px, 1fr) 90px 150px 52px;
  gap: 12px;
  align-items: center;
  min-height: 70px;
  padding: 9px 12px;
  border: 1px solid #e4e8ee;
  border-radius: 11px;
  background: #fbfcfe;
}
.source-episode-row:hover { border-color: #c7d3e3; background: #fff; }
.source-drag { color: #98a4b3; font-weight: 900; letter-spacing: -2px; cursor: grab; user-select: none; }
.source-order { display: flex; gap: 2px; align-items: baseline; color: #8290a3; }
.source-order strong { color: #38506f; font-size: 19px; }
.source-order small { font-size: 9px; }
.source-episode-main { min-width: 0; display: grid; gap: 2px; }
.source-episode-main strong { overflow: hidden; color: #32445d; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.source-episode-main span { overflow: hidden; color: #8a96a7; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.source-duration { display: grid; gap: 1px; }
.source-duration small { color: #929dab; font-size: 9px; }
.source-duration strong { color: #58677b; font-size: 11px; }
.source-state { display: flex; gap: 7px; align-items: center; min-width: 0; }
.source-state > span { flex: none; width: 7px; height: 7px; border-radius: 50%; background: #aab3bf; }
.source-state strong { overflow: hidden; color: #68758a; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.source-state.tone-ready > span { background: #2ca36d; }
.source-state.tone-ready strong { color: #267653; }
.source-state.tone-processing > span { background: #5179d6; box-shadow: 0 0 0 3px #edf2ff; }
.source-state.tone-processing strong { color: #4263aa; }
.source-state.tone-review > span { background: #d59a2d; }
.source-state.tone-review strong { color: #94691c; }
.source-state.tone-blocked > span { background: #d55b5b; }
.source-state.tone-blocked strong { color: #b54747; }
.source-delete { border: 0; background: transparent; color: #b95858; font-size: 10px; font-weight: 750; cursor: pointer; }
.source-order-confirmed {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 12px 14px;
  border-radius: 10px;
  background: #f7f9fc;
  color: #7b8798;
  font-size: 10px;
}
.source-order-confirmed strong { color: #50627a; font-size: 10px; }
@media (max-width: 1200px) {
  .source-episode-row { grid-template-columns: 30px 54px minmax(220px, 1fr) 80px 120px 48px; gap: 8px; }
}
</style>
