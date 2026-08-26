<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import { shotCacheApi, type ShotCacheScope, type ShotCacheStatus, type ShotRecomputeMode } from '../api/shotCacheV51'
import type { BackgroundTask, Episode } from '../types/studio'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

const selectedEpisodeId = ref('')
const mode = ref<ShotRecomputeMode>('auto')
const cache = ref<ShotCacheStatus | null>(null)
const loading = ref(false)
const error = ref('')
const message = ref('')

const selectedEpisode = computed(() => props.episodes.find((item) => item.id === selectedEpisodeId.value) ?? null)

const modes: Array<{ value: ShotRecomputeMode; label: string; help: string }> = [
  { value: 'auto', label: '正常重新拉片', help: '优先复用最深层有效缓存；结果没变时最快。' },
  { value: 'transitions', label: '只重建 Transition', help: '保留 Qwen Window 输出，只重新解析合并转场。' },
  { value: 'transvlm', label: '从 TransVLM 重新分析', help: '保留 RGB + Flow，只重新运行 Qwen3-VL。' },
  { value: 'flow', label: '从 NeuFlow 重新计算', help: '保留模型 RGB，重新计算 Flow + Qwen3-VL。' },
  { value: 'preprocess', label: '从模型输入重新计算', help: '丢弃 RGB/Flow/Qwen/Transition，从 Source 重建。' },
  { value: 'all', label: '完全重新计算', help: '清空本集 Stage 02 缓存后从 Source 完整运行。' },
]

const selectedMode = computed(() => modes.find((item) => item.value === mode.value) ?? modes[0])

function formatBytes(value: number | null | undefined): string {
  const bytes = Math.max(0, Number(value || 0))
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

async function loadCache(): Promise<void> {
  if (!selectedEpisodeId.value) {
    cache.value = null
    return
  }
  loading.value = true
  error.value = ''
  try {
    cache.value = await shotCacheApi.getEpisodeCache(selectedEpisodeId.value)
  } catch (err) {
    cache.value = null
    error.value = err instanceof Error ? err.message : '缓存状态读取失败'
  } finally {
    loading.value = false
  }
}

async function runSelectedMode(): Promise<void> {
  const episode = selectedEpisode.value
  if (!episode || loading.value) return
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    if (mode.value !== 'auto') {
      await shotCacheApi.clearEpisodeCache(episode.id, mode.value as ShotCacheScope)
    }
    await api.startEpisodeShotsTask(episode.id)
    message.value = mode.value === 'auto'
      ? '已启动：系统会自动复用有效缓存。'
      : `已按“${selectedMode.value.label}”清理依赖缓存并启动拉片。`
    await loadCache()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '启动拉片失败'
  } finally {
    loading.value = false
  }
}

async function clearAll(): Promise<void> {
  const episode = selectedEpisode.value
  if (!episode || loading.value) return
  if (!window.confirm(`清空 ${episode.title} 的 Stage 02 拉片缓存？原视频、Shot、Reference Clip 和人工 Revision 不会删除。`)) return
  loading.value = true
  error.value = ''
  message.value = ''
  try {
    const result = await shotCacheApi.clearEpisodeCache(episode.id, 'all')
    cache.value = result.cache
    message.value = `已清空本集拉片缓存，释放 ${formatBytes(result.cleared.bytes_removed)}。`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '清除缓存失败'
  } finally {
    loading.value = false
  }
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== props.projectId) return
  if (task.task_type !== 'EPISODE_SHOTS' && task.task_type !== 'BATCH_SHOTS') return
  if (task.task_type === 'EPISODE_SHOTS' && task.episode_id && task.episode_id !== selectedEpisodeId.value) return
  void loadCache()
}

watch(
  () => props.episodes.map((item) => item.id).join('|'),
  () => {
    if (!props.episodes.length) {
      selectedEpisodeId.value = ''
      cache.value = null
      return
    }
    if (!props.episodes.some((item) => item.id === selectedEpisodeId.value)) {
      selectedEpisodeId.value = props.episodes[0].id
    }
  },
  { immediate: true },
)

watch(selectedEpisodeId, () => {
  message.value = ''
  void loadCache()
})

onMounted(() => {
  window.addEventListener('studio-task-finished', onTaskFinished)
  if (selectedEpisodeId.value) void loadCache()
})

onUnmounted(() => {
  window.removeEventListener('studio-task-finished', onTaskFinished)
})
</script>

<template>
  <section class="shot-cache-v51">
    <div class="cache-title">
      <div>
        <strong>V5.1 拉片缓存</strong>
        <span>自动失效 · Source / Shot / Revision 与缓存隔离</span>
      </div>
      <span v-if="cache" class="cache-size">{{ formatBytes(cache.bytes) }}</span>
    </div>

    <div class="cache-controls">
      <label>
        <span>剧集</span>
        <select v-model="selectedEpisodeId" :disabled="loading || !episodes.length">
          <option v-for="episode in episodes" :key="episode.id" :value="episode.id">
            E{{ String(episode.sort_order).padStart(2, '0') }} · {{ episode.title }}
          </option>
        </select>
      </label>

      <label class="mode-select">
        <span>重新计算范围</span>
        <select v-model="mode" :disabled="loading || !selectedEpisode">
          <option v-for="item in modes" :key="item.value" :value="item.value">{{ item.label }}</option>
        </select>
      </label>

      <button class="run" :disabled="loading || !selectedEpisode" @click="runSelectedMode">
        {{ loading ? '处理中…' : '按此方式重新拉片' }}
      </button>
      <button class="clear" :disabled="loading || !selectedEpisode" @click="clearAll">清空本集缓存</button>
    </div>

    <div class="cache-foot">
      <div class="layers" aria-label="缓存层状态">
        <span :class="{ ready: cache?.layers.preprocess }">RGB</span>
        <i>→</i>
        <span :class="{ ready: cache?.layers.flow }">Flow</span>
        <i>→</i>
        <span :class="{ ready: cache?.layers.transvlm }">Qwen</span>
        <i>→</i>
        <span :class="{ ready: cache?.layers.transitions }">Transition</span>
      </div>
      <p>{{ selectedMode.help }}</p>
      <small v-if="cache && !cache.manifest_valid">当前 manifest 已失效，下次拉片会自动重建。</small>
      <small v-else-if="message" class="ok">{{ message }}</small>
      <small v-else-if="error" class="err">{{ error }}</small>
    </div>
  </section>
</template>

<style scoped>
.shot-cache-v51 {
  margin: 14px 22px 0;
  padding: 12px 14px;
  border: 1px solid #dbe3ef;
  border-radius: 12px;
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 6px 18px rgba(34, 49, 76, .05);
  color: #1b2638;
}
.cache-title,
.cache-controls,
.cache-foot,
.layers {
  display: flex;
  align-items: center;
}
.cache-title { justify-content: space-between; gap: 16px; margin-bottom: 10px; }
.cache-title > div { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.cache-title strong { font-size: 13px; }
.cache-title span { color: #758198; font-size: 11px; }
.cache-size { flex: 0 0 auto; font-weight: 800; }
.cache-controls { gap: 10px; flex-wrap: wrap; }
.cache-controls label { display: grid; gap: 4px; min-width: 170px; }
.cache-controls label > span { font-size: 10px; font-weight: 800; color: #7b879b; }
.cache-controls .mode-select { min-width: 230px; }
.cache-controls select,
.cache-controls button {
  min-height: 34px;
  border-radius: 8px;
  border: 1px solid #d5deeb;
  background: #fff;
  padding: 0 10px;
  font: inherit;
  font-size: 12px;
}
.cache-controls button { font-weight: 800; cursor: pointer; }
.cache-controls button:disabled,
.cache-controls select:disabled { opacity: .55; cursor: not-allowed; }
.cache-controls .run { border-color: #2d62e8; background: #2d62e8; color: #fff; }
.cache-controls .clear { color: #a44132; }
.cache-foot { gap: 12px; margin-top: 9px; min-height: 20px; flex-wrap: wrap; }
.layers { gap: 5px; flex: 0 0 auto; }
.layers span {
  padding: 2px 6px;
  border-radius: 999px;
  background: #eef1f6;
  color: #8a95a7;
  font-size: 10px;
  font-weight: 900;
}
.layers span.ready { background: #e5f6ec; color: #287348; }
.layers i { color: #aeb7c6; font-style: normal; font-size: 10px; }
.cache-foot p { margin: 0; color: #667287; font-size: 11px; }
.cache-foot small { font-size: 11px; color: #9a6b15; }
.cache-foot small.ok { color: #287348; }
.cache-foot small.err { color: #b03a2e; }
@media (max-width: 1100px) {
  .shot-cache-v51 { margin-left: 14px; margin-right: 14px; }
  .cache-controls label,
  .cache-controls .mode-select { min-width: 190px; flex: 1 1 190px; }
}
</style>
