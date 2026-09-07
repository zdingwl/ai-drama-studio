<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  compileSourceScreenplay,
  getSourceScreenplay,
  type SourceScreenplayCompilation,
  type SourceScreenplayRead,
} from '../api/source-screenplay'
import { listProjectSourceVideos, type SourceVideoEpisode } from '../api/source-video-management'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))

const episodes = ref<SourceVideoEpisode[]>([])
const selectedEpisodeId = ref('')
const readModel = ref<SourceScreenplayRead | null>(null)
const loading = ref(true)
const compiling = ref(false)
const pageError = ref('')

const currentEpisode = computed(() => episodes.value.find((episode) => episode.id === selectedEpisodeId.value) || null)
const compilation = computed<SourceScreenplayCompilation | null>(() => readModel.value?.compilation || null)
const screenplay = computed(() => compilation.value?.screenplay || null)
const summary = computed(() => compilation.value?.episode_understanding?.episode_summary || '')
const canCompile = computed(() => Boolean(selectedEpisodeId.value) && !compiling.value)
const actionLabel = computed(() => {
  if (compiling.value) return '正在理解整集并整理剧本…'
  if (readModel.value?.state === 'READY') return '重新生成原剧剧本'
  return '生成原剧剧本'
})

function episodeLabel(episode: SourceVideoEpisode, index: number): string {
  const title = episode.title || episode.original_filename || `第 ${index + 1} 集`
  return `${String(index + 1).padStart(2, '0')} · ${title}`
}

async function loadScreenplay(): Promise<void> {
  readModel.value = null
  pageError.value = ''
  if (!selectedEpisodeId.value) return
  try {
    readModel.value = await getSourceScreenplay(selectedEpisodeId.value)
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : '读取原剧本失败'
  }
}

async function loadPage(): Promise<void> {
  loading.value = true
  pageError.value = ''
  try {
    episodes.value = (await listProjectSourceVideos(projectId.value)).sort((a, b) => a.sort_order - b.sort_order)
    const requestedEpisodeId = String(route.query.episodeId || '')
    selectedEpisodeId.value = episodes.value.some((episode) => episode.id === requestedEpisodeId)
      ? requestedEpisodeId
      : (episodes.value[0]?.id || '')
    await loadScreenplay()
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : '加载剧本母版失败'
  } finally {
    loading.value = false
  }
}

async function handleCompile(): Promise<void> {
  if (!canCompile.value) return
  compiling.value = true
  pageError.value = ''
  try {
    const result = await compileSourceScreenplay(selectedEpisodeId.value)
    readModel.value = {
      state: 'READY',
      episode_id: result.episode_id,
      source_fingerprint: result.source_fingerprint,
      message: '原片还原剧本已生成。',
      compilation: result,
    }
  } catch (error) {
    pageError.value = error instanceof Error ? error.message : '生成原剧本失败'
  } finally {
    compiling.value = false
  }
}

function goBack(): void {
  router.push({ name: 'breakdown', params: { projectId: projectId.value } })
}

watch(selectedEpisodeId, async (episodeId, previous) => {
  if (!episodeId || episodeId === previous || loading.value) return
  await router.replace({
    name: 'source-screenplay',
    params: { projectId: projectId.value },
    query: { episodeId },
  })
  await loadScreenplay()
})

onMounted(loadPage)
</script>

<template>
  <main class="screenplay-page">
    <header class="topbar">
      <div>
        <button class="back-button" type="button" @click="goBack">← 返回拉片</button>
        <p class="eyebrow">原片还原剧本</p>
        <h1>剧本母版</h1>
        <p class="subtitle">AI 先理解整集，再把镜头事实整理成可读剧本。这里不展示 Track、证据 ID、置信度等技术信息。</p>
      </div>
      <div class="top-actions">
        <label class="episode-select">
          <span>剧集</span>
          <select v-model="selectedEpisodeId" :disabled="loading || compiling || !episodes.length">
            <option v-for="(episode, index) in episodes" :key="episode.id" :value="episode.id">
              {{ episodeLabel(episode, index) }}
            </option>
          </select>
        </label>
        <button class="primary-button" type="button" :disabled="!canCompile" @click="handleCompile">
          {{ actionLabel }}
        </button>
      </div>
    </header>

    <section v-if="loading" class="state-card">正在读取剧本状态…</section>

    <section v-else-if="pageError" class="state-card error-card">
      <strong>暂时无法显示剧本</strong>
      <p>{{ pageError }}</p>
    </section>

    <section v-else-if="!episodes.length" class="state-card">
      <strong>还没有原短剧视频</strong>
      <p>先上传剧集并完成拉片，再生成原片还原剧本。</p>
    </section>

    <section v-else-if="readModel?.state === 'MISSING'" class="state-card empty-card">
      <span class="state-badge">尚未生成</span>
      <h2>{{ currentEpisode?.title || '当前剧集' }}</h2>
      <p>拉片结果已经存在时，点击“生成原剧剧本”。系统会读取整集事实，先理解剧情，再整理成剧本，不会逐镜照抄拉片字段。</p>
    </section>

    <section v-else-if="readModel?.state === 'STALE'" class="state-card stale-card">
      <span class="state-badge">需要更新</span>
      <h2>原片内容已经变化</h2>
      <p>{{ readModel.message }}</p>
    </section>

    <template v-else-if="screenplay">
      <section class="summary-card">
        <div>
          <span class="state-badge ready">原剧本已生成</span>
          <h2>{{ screenplay.title }}</h2>
        </div>
        <div class="summary-copy">
          <span>整集理解</span>
          <p>{{ summary || '已完成整集剧情理解。' }}</p>
        </div>
      </section>

      <section class="script-card">
        <div class="script-heading">
          <div>
            <p class="eyebrow">SCREENPLAY</p>
            <h2>原片还原剧本</h2>
          </div>
          <p>对白保持正式原片正文；动作段落由 AI 在原片证据范围内合并整理。</p>
        </div>
        <pre class="screenplay-text">{{ screenplay.screenplay_text }}</pre>
      </section>

      <section v-if="screenplay.unresolved.length" class="state-card warning-card">
        <strong>还有 {{ screenplay.unresolved.length }} 项需要确认</strong>
        <p>这些问题不会被 AI 猜测补全，处理原片确认后再重新生成剧本即可。</p>
      </section>
    </template>
  </main>
</template>

<style scoped>
.screenplay-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 34px 42px 64px;
  background: #f5f6f8;
  color: #17191d;
}

.topbar {
  max-width: 1180px;
  margin: 0 auto 24px;
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 28px;
}

.back-button {
  border: 0;
  background: transparent;
  padding: 0;
  margin-bottom: 24px;
  color: #5c6470;
  font-size: 15px;
  cursor: pointer;
}

.eyebrow {
  margin: 0 0 7px;
  color: #7a818c;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .12em;
}

h1, h2, p { margin-top: 0; }
h1 { margin-bottom: 8px; font-size: 34px; line-height: 1.15; }
h2 { margin-bottom: 8px; font-size: 24px; }
.subtitle { margin-bottom: 0; max-width: 700px; color: #656d78; font-size: 15px; line-height: 1.7; }

.top-actions {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  flex-shrink: 0;
}

.episode-select { display: grid; gap: 7px; color: #626a75; font-size: 13px; }
.episode-select select {
  min-width: 220px;
  height: 42px;
  border: 1px solid #d9dde3;
  border-radius: 10px;
  padding: 0 12px;
  background: white;
  color: #1d2128;
  font-size: 15px;
}

.primary-button {
  height: 42px;
  border: 0;
  border-radius: 10px;
  padding: 0 18px;
  background: #181b20;
  color: white;
  font-size: 15px;
  font-weight: 650;
  cursor: pointer;
}
.primary-button:disabled { opacity: .45; cursor: default; }

.state-card, .summary-card, .script-card {
  max-width: 1180px;
  box-sizing: border-box;
  margin: 0 auto 18px;
  border: 1px solid #e0e3e8;
  border-radius: 16px;
  background: white;
  padding: 26px 30px;
  box-shadow: 0 8px 30px rgba(28, 35, 43, .04);
}
.state-card p { margin-bottom: 0; color: #6a717c; line-height: 1.7; }
.error-card { border-color: #f0c8c8; }
.stale-card, .warning-card { border-color: #ead9ae; }

.state-badge {
  display: inline-flex;
  margin-bottom: 12px;
  border-radius: 999px;
  padding: 5px 9px;
  background: #eef0f3;
  color: #5f6670;
  font-size: 12px;
  font-weight: 700;
}
.state-badge.ready { background: #edf5ef; color: #3f6b4c; }

.summary-card {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 34px;
  align-items: start;
}
.summary-copy > span { display: block; margin-bottom: 7px; color: #777e88; font-size: 12px; font-weight: 700; }
.summary-copy p { margin-bottom: 0; color: #30353c; font-size: 16px; line-height: 1.75; }

.script-card { padding: 0; overflow: hidden; }
.script-heading {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  align-items: end;
  padding: 24px 30px 20px;
  border-bottom: 1px solid #eceef1;
}
.script-heading h2 { margin-bottom: 0; }
.script-heading > p { max-width: 430px; margin-bottom: 0; color: #747b85; font-size: 13px; line-height: 1.6; text-align: right; }

.screenplay-text {
  margin: 0;
  padding: 34px 48px 54px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  background: #fff;
  color: #202329;
  font-family: "Noto Sans SC", "Microsoft YaHei", sans-serif;
  font-size: 17px;
  line-height: 2;
}

@media (max-width: 850px) {
  .screenplay-page { padding: 24px 18px 48px; }
  .topbar, .script-heading { align-items: stretch; flex-direction: column; }
  .top-actions { align-items: stretch; flex-direction: column; }
  .episode-select select { width: 100%; }
  .summary-card { grid-template-columns: 1fr; gap: 12px; }
  .screenplay-text { padding: 26px 22px 40px; font-size: 16px; }
  .script-heading > p { text-align: left; }
}
</style>
