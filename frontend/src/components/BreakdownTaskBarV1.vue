<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { breakdownApi } from '../api/breakdown'
import type { BreakdownRunSummary } from '../types/breakdown'
import type { Episode } from '../types/studio'

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
const confirmationMode = ref<'episode' | 'batch' | null>(null)

const selectedEpisode = computed(() => props.episodes.find((item) => item.id === props.selectedEpisodeId) ?? null)
const hasAnyExistingShots = computed(() => props.episodes.some((episode) => episode.shot_count > 0))
const episodeActionLabel = computed(() => props.run ? '重新拉片本集' : '开始拉片本集')
const confirmationText = computed(() => {
  if (confirmationMode.value === 'batch') {
    return '将启动项目批量拉片流程。已有镜头或拉片结果的剧集可能再次计算；任务会按后端既定顺序执行并占用本地 GPU/CPU 时间。'
  }
  return '将创建新的完整拉片 Run。不会修改已经确认的镜头切点；新 Run 成为 Current 后，会替换本集当前 Scene / Shot 阅读结果。任务会重新占用本地 GPU/CPU，通常需要数分钟或更久。'
})

watch(() => props.selectedEpisodeId, () => {
  confirmationMode.value = null
  error.value = ''
  notice.value = ''
})

function onEpisodeChange(event: Event): void {
  emit('update:selectedEpisodeId', (event.target as HTMLSelectElement).value)
}

function resultStatus(run: BreakdownRunSummary | null): string {
  if (!run) return '尚无拉片结果'
  if (run.status === 'PROCESSING') return '正在生成拉片结果'
  if (run.status === 'FAILED') return '上次拉片失败'
  if (run.status === 'READY_WITH_WARNINGS') return '拉片结果可用 · 建议检查'
  if (!run.is_current) return '正在查看历史结果'
  return '拉片结果已生成'
}

function resultStatusClass(run: BreakdownRunSummary | null): string {
  if (!run) return 'neutral'
  if (run.status === 'PROCESSING') return 'processing'
  if (run.status === 'FAILED') return 'danger'
  if (run.status === 'READY_WITH_WARNINGS') return 'warning'
  if (!run.is_current) return 'history'
  return 'ready'
}

function requestEpisodeStart(): void {
  if (props.run) confirmationMode.value = 'episode'
  else void startEpisode()
}

function requestBatchStart(): void {
  if (hasAnyExistingShots.value) confirmationMode.value = 'batch'
  else void startBatch()
}

async function confirmStart(): Promise<void> {
  if (confirmationMode.value === 'batch') await startBatch()
  else if (confirmationMode.value === 'episode') await startEpisode()
}

async function startEpisode(): Promise<void> {
  if (!props.selectedEpisodeId || starting.value) return
  confirmationMode.value = null
  starting.value = true
  error.value = ''
  notice.value = ''
  try {
    const task = await breakdownApi.startEpisode(props.selectedEpisodeId)
    notice.value = `已开始：${task.title}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '本集拉片任务创建失败'
  } finally {
    starting.value = false
  }
}

async function startBatch(): Promise<void> {
  if (!props.projectId || !props.episodes.length || starting.value) return
  confirmationMode.value = null
  starting.value = true
  error.value = ''
  notice.value = ''
  try {
    const task = await breakdownApi.startBatch(props.projectId)
    notice.value = `已开始：${task.title}`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '批量拉片任务创建失败'
  } finally {
    starting.value = false
  }
}
</script>

<template>
  <section class="breakdown-task-bar-v3">
    <label class="episode-picker">
      <span>剧集</span>
      <select :value="selectedEpisodeId" :disabled="starting || !episodes.length" @change="onEpisodeChange">
        <option v-for="episode in episodes" :key="episode.id" :value="episode.id">
          E{{ String(episode.sort_order).padStart(2, '0') }} · {{ episode.title }} · {{ episode.shot_count }} 个镜头
        </option>
      </select>
    </label>

    <div :class="['result-status', resultStatusClass(run)]">
      <span class="status-dot"></span>
      <strong>{{ resultStatus(run) }}</strong>
    </div>

    <div class="task-actions">
      <button
        type="button"
        :class="{ primary: !run, 'rerun-button': Boolean(run) }"
        :disabled="starting || !selectedEpisode || selectedEpisode.shot_count === 0"
        @click="requestEpisodeStart"
      >{{ starting ? '正在创建任务…' : episodeActionLabel }}</button>
      <button type="button" :disabled="starting || !episodes.length" @click="requestBatchStart">按顺序批量拉片</button>
    </div>

    <div v-if="confirmationMode" class="rerun-confirmation" role="alert">
      <div>
        <strong>{{ confirmationMode === 'batch' ? '确认启动批量拉片？' : '确认重新拉片本集？' }}</strong>
        <p>{{ confirmationText }}</p>
        <small>影响范围：拉片结果与后续读取；不直接修改镜头切点。计算成本：本地 GPU / CPU 时间。</small>
      </div>
      <div class="confirm-actions">
        <button type="button" @click="confirmationMode = null">取消</button>
        <button type="button" class="confirm-danger" :disabled="starting" @click="confirmStart">确认启动</button>
      </div>
    </div>

    <div v-if="error || notice" :class="['task-notice', { error: Boolean(error) }]">
      {{ error || `${notice} · 进度可在后台任务栏查看` }}
    </div>
  </section>
</template>

<style scoped>
.breakdown-task-bar-v3 { display: grid; grid-template-columns: minmax(300px, 1fr) auto auto; gap: 12px; align-items: end; border: 1px solid #dce4ef; border-radius: 13px; padding: 10px 12px; background: #fff; box-shadow: 0 6px 22px rgba(42, 59, 90, .04); }
.episode-picker { min-width: 0; display: grid; gap: 5px; }
.episode-picker > span { color: #8190a5; font-size: 10px; font-weight: 850; }
.episode-picker select { width: 100%; min-width: 0; height: 38px; border: 1px solid #d7e0ed; border-radius: 9px; padding: 0 10px; background: #f9fbfe; color: #344761; font-size: 12px; font-weight: 750; outline: none; }
.episode-picker select:focus { border-color: #8dace8; box-shadow: 0 0 0 3px rgba(82, 126, 218, .1); }
.result-status { min-height: 38px; display: flex; gap: 7px; align-items: center; border-radius: 9px; padding: 0 10px; background: #f3f5f8; color: #6b788b; white-space: nowrap; }
.result-status strong { font-size: 11px; }
.status-dot { width: 7px; height: 7px; border-radius: 50%; background: #9ca8b8; }
.result-status.ready { background: #edf9f3; color: #177a4e; }
.result-status.ready .status-dot { background: #25a56a; }
.result-status.warning { background: #fff6e4; color: #93620c; }
.result-status.warning .status-dot { background: #d89a28; }
.result-status.processing { background: #eef4ff; color: #3b67b4; }
.result-status.processing .status-dot { background: #4e7ee0; }
.result-status.danger { background: #fff0f0; color: #aa4545; }
.result-status.danger .status-dot { background: #d75b5b; }
.result-status.history { background: #f3f0f9; color: #776397; }
.result-status.history .status-dot { background: #8a78b1; }
.task-actions { display: flex; gap: 7px; justify-content: flex-end; }
.task-actions button, .confirm-actions button { min-height: 38px; border: 1px solid #d3deed; border-radius: 9px; padding: 0 12px; background: #fff; color: #4f617c; cursor: pointer; font-size: 11px; font-weight: 800; white-space: nowrap; }
.task-actions button.primary { border-color: #4f7ee0; background: #4f7ee0; color: #fff; box-shadow: 0 5px 13px rgba(79, 126, 224, .18); }
.task-actions button.rerun-button { border-color: #d8c8a5; background: #fffaf0; color: #80642b; }
.task-actions button:disabled, .confirm-actions button:disabled { opacity: .45; cursor: not-allowed; box-shadow: none; }
.rerun-confirmation { grid-column: 1 / -1; display: flex; justify-content: space-between; gap: 16px; align-items: center; border: 1px solid #ead39d; border-radius: 10px; padding: 10px 12px; background: #fffaf0; color: #6f5726; }
.rerun-confirmation > div:first-child { display: grid; gap: 3px; }
.rerun-confirmation strong { font-size: 12px; }
.rerun-confirmation p { margin: 0; max-width: 820px; color: #7d683d; font-size: 11px; line-height: 1.5; }
.rerun-confirmation small { color: #927b4e; font-size: 10px; }
.confirm-actions { flex: none; display: flex; gap: 7px; }
.confirm-actions button.confirm-danger { border-color: #c98b3e; background: #b87526; color: #fff; }
.task-notice { grid-column: 1 / -1; border-top: 1px solid #dfe8f6; margin: 0 -12px -10px; padding: 8px 12px; background: #f5f9ff; color: #5270a8; font-size: 11px; }
.task-notice.error { border-color: #efd1d1; background: #fff4f4; color: #a34848; }
@media (max-width: 900px) {
  .breakdown-task-bar-v3 { grid-template-columns: 1fr auto; }
  .result-status { grid-row: 2; justify-self: start; }
  .task-actions { grid-column: 2; grid-row: 1 / span 2; align-self: center; }
  .rerun-confirmation { align-items: stretch; flex-direction: column; }
}
@media (max-width: 650px) {
  .breakdown-task-bar-v3 { grid-template-columns: 1fr; }
  .result-status, .task-actions { grid-column: 1; grid-row: auto; }
  .task-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .confirm-actions { display: grid; grid-template-columns: 1fr 1fr; }
}
</style>
