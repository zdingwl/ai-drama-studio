<script setup lang="ts">
import { computed, ref } from 'vue'
import { breakdownApi } from '../api/breakdown'
import type { BreakdownRunSummary } from '../types/breakdown'
import type { Episode } from '../types/studio'
import { componentStatusLabel, runStatusLabel } from '../utils/breakdownUiText'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
  selectedEpisodeId: string
  run: BreakdownRunSummary | null
}>()

const emit = defineEmits<{
  (event: 'update:selectedEpisodeId', episodeId: string): void
}>()

const starting = ref(false)
const error = ref('')
const notice = ref('')

const selectedEpisode = computed(() => props.episodes.find((item) => item.id === props.selectedEpisodeId) ?? null)
const pipelineComponents = [
  { key: 'ASR', label: 'ASR 语音识别' },
  { key: 'OCR', label: 'OCR 文字识别' },
  { key: 'VLM', label: 'VLM 画面理解' },
  { key: 'FUSION', label: '融合' },
]

function onEpisodeChange(event: Event): void {
  emit('update:selectedEpisodeId', (event.target as HTMLSelectElement).value)
}

function revisionLabel(run: BreakdownRunSummary | null): string {
  return run?.source_shot_revision ? `R${run.source_shot_revision.revision}` : 'R?'
}

function runStatusClass(status: string | undefined): string {
  if (status === 'READY') return 'ready'
  if (status === 'READY_WITH_WARNINGS') return 'warning'
  if (status === 'FAILED') return 'danger'
  if (status === 'STALE') return 'stale'
  if (status === 'PROCESSING') return 'processing'
  return 'neutral'
}

function componentStatus(key: string): string {
  const value = props.run?.component_status?.[key]
  if (typeof value === 'string') return value.toUpperCase()
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    for (const field of ['status', 'state', 'result']) {
      if (typeof record[field] === 'string') return String(record[field]).toUpperCase()
    }
  }
  return '—'
}

function componentStatusClass(status: string): string {
  if (status === 'READY') return 'ready'
  if (status === 'READY_WITH_WARNINGS' || status === 'NO_EVIDENCE') return 'warning'
  if (status === 'FAILED' || status === 'NOT_AVAILABLE') return 'danger'
  if (status === 'PROCESSING') return 'processing'
  return 'neutral'
}

async function startEpisode(): Promise<void> {
  if (!props.selectedEpisodeId || starting.value) return
  starting.value = true
  error.value = ''
  notice.value = ''
  try {
    const task = await breakdownApi.startEpisode(props.selectedEpisodeId)
    notice.value = `已进入后台任务：${task.title}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'AI 拉片任务创建失败'
  } finally {
    starting.value = false
  }
}

async function startBatch(): Promise<void> {
  if (!props.projectId || !props.episodes.length || starting.value) return
  starting.value = true
  error.value = ''
  notice.value = ''
  try {
    const task = await breakdownApi.startBatch(props.projectId)
    notice.value = `已进入后台任务：${task.title}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '批量 AI 拉片任务创建失败'
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <section class="breakdown-task-bar-v2">
    <div class="task-context-row">
      <label class="episode-context">
        <span>当前剧集</span>
        <select :value="selectedEpisodeId" :disabled="starting || !episodes.length" @change="onEpisodeChange">
          <option v-for="episode in episodes" :key="episode.id" :value="episode.id">
            E{{ String(episode.sort_order).padStart(2, '0') }} · {{ episode.title }} · {{ episode.shot_count }} 个镜头
          </option>
        </select>
      </label>

      <div class="run-context">
        <span>{{ run?.is_current ? '当前采用草稿' : '查看中的草稿' }}</span>
        <div v-if="run">
          <strong>{{ revisionLabel(run) }}</strong>
          <i :class="runStatusClass(run.status)">{{ runStatusLabel(run.status) }}</i>
          <small :class="['viewing-mode', { history: !run.is_current }]">{{ run.is_current ? '当前采用' : '历史查看' }}</small>
        </div>
        <b v-else>尚无草稿</b>
      </div>

      <div class="revision-context">
        <span>来源镜头版本</span>
        <strong v-if="run">{{ revisionLabel(run) }} · {{ run.source_shot_revision?.is_current ? '当前版本' : '历史版本' }}</strong>
        <strong v-else>—</strong>
      </div>

      <div class="task-actions">
        <button
          type="button"
          class="primary"
          :disabled="starting || !selectedEpisode || selectedEpisode.shot_count === 0"
          @click="startEpisode"
        >{{ starting ? '正在创建任务…' : '重新运行本集' }}</button>
        <button type="button" :disabled="starting || !episodes.length" @click="startBatch">按顺序批量拉片</button>
      </div>
    </div>

    <div class="pipeline-row">
      <span class="pipeline-label">处理链</span>
      <div class="pipeline-components">
        <span
          v-for="component in pipelineComponents"
          :key="component.key"
          :class="['pipeline-chip', componentStatusClass(componentStatus(component.key))]"
        >
          <b>{{ component.label }}</b>
          <i>{{ componentStatusLabel(componentStatus(component.key)) }}</i>
        </span>
      </div>

      <div class="task-meta">
        <span v-if="run">{{ run.pipeline_profile || run.schema_version }}</span>
        <span v-if="run">{{ run.schema_version }}</span>
        <span v-if="run && !run.is_current">历史 Run · 只读</span>
        <span>AI 草稿 · 不等同最终资产</span>
      </div>
    </div>

    <div v-if="error || notice" :class="['task-notice', { error: Boolean(error) }]">
      {{ error || `${notice} · 进度见全局后台任务栏` }}
    </div>
  </section>
</template>

<style scoped>
.breakdown-task-bar-v2 { display: grid; gap: 0; border: 1px solid #dce4ef; border-radius: 13px; background: #fff; box-shadow: 0 6px 22px rgba(42, 59, 90, .04); overflow: hidden; }
.task-context-row { display: grid; grid-template-columns: minmax(290px, 1.4fr) minmax(170px, .7fr) minmax(170px, .72fr) auto; gap: 14px; align-items: end; padding: 11px 13px; }
.episode-context, .run-context, .revision-context { min-width: 0; display: grid; gap: 5px; }
.episode-context > span, .run-context > span, .revision-context > span { color: #8190a5; font-size: 11px; font-weight: 800; }
.episode-context select { width: 100%; min-width: 0; height: 40px; border: 1px solid #d7e0ed; border-radius: 9px; padding: 0 10px; background: #f9fbfe; color: #344761; font-size: 13px; font-weight: 750; outline: none; }
.episode-context select:focus { border-color: #8dace8; box-shadow: 0 0 0 3px rgba(82, 126, 218, .1); }
.run-context > div { min-height: 40px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.run-context strong, .revision-context strong, .run-context > b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #2c3f5e; font-size: 13px; }
.run-context i, .viewing-mode { border-radius: 999px; padding: 4px 7px; font-size: 10px; font-style: normal; font-weight: 850; white-space: nowrap; }
.run-context i.ready { background: #e7f7ee; color: #13804d; }
.run-context i.warning { background: #fff3d7; color: #91610d; }
.run-context i.danger { background: #ffe7e7; color: #b64040; }
.run-context i.stale { background: #f0edf7; color: #756395; }
.run-context i.processing { background: #eaf2ff; color: #3569bf; }
.viewing-mode { background: #eef2f7; color: #67758a; }
.viewing-mode.history { background: #f0edf7; color: #756395; }
.revision-context strong { min-height: 40px; display: flex; align-items: center; }
.task-actions { display: flex; gap: 8px; justify-content: flex-end; }
.task-actions button { min-height: 40px; border: 1px solid #d3deed; border-radius: 9px; padding: 0 13px; background: #fff; color: #4f617c; cursor: pointer; font-size: 12px; font-weight: 800; white-space: nowrap; }
.task-actions button.primary { border-color: #4f7ee0; background: #4f7ee0; color: #fff; box-shadow: 0 5px 13px rgba(79, 126, 224, .18); }
.task-actions button:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }
.pipeline-row { display: flex; gap: 10px; align-items: center; min-width: 0; border-top: 1px solid #edf0f5; padding: 9px 13px; background: #fbfcfe; }
.pipeline-label { color: #6e7d94; font-size: 11px; font-weight: 850; }
.pipeline-components { display: flex; flex-wrap: wrap; gap: 5px; }
.pipeline-chip { display: inline-flex; gap: 4px; align-items: center; border-radius: 999px; padding: 5px 8px; background: #eef1f5; color: #6e7b8d; font-size: 10px; }
.pipeline-chip b { font-size: 10px; }
.pipeline-chip i { font-size: 9px; font-style: normal; }
.pipeline-chip.ready { background: #e7f7ee; color: #147f4e; }
.pipeline-chip.warning { background: #fff4db; color: #90620f; }
.pipeline-chip.danger { background: #ffe8e8; color: #b64242; }
.pipeline-chip.processing { background: #eaf2ff; color: #3569bf; }
.task-meta { min-width: 0; margin-left: auto; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 5px; }
.task-meta span { border-left: 1px solid #dfe5ed; padding-left: 8px; color: #7e8b9e; font-size: 10px; white-space: nowrap; }
.task-notice { border-top: 1px solid #dfe8f6; padding: 8px 13px; background: #f5f9ff; color: #5270a8; font-size: 11px; }
.task-notice.error { border-color: #efd1d1; background: #fff4f4; color: #a34848; }
@media (max-width: 1180px) {
  .task-context-row { grid-template-columns: 1fr 1fr; }
  .task-actions { justify-content: flex-start; }
  .pipeline-row { align-items: flex-start; flex-wrap: wrap; }
  .task-meta { width: 100%; margin-left: 0; justify-content: flex-start; }
}
@media (max-width: 720px) {
  .task-context-row { grid-template-columns: 1fr; }
  .task-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .pipeline-components { width: 100%; }
}
</style>