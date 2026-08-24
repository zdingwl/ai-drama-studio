<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { usePreprocessStore } from '../stores/preprocess'
import { useProjectStore } from '../stores/project'
import { useSourceVideoStore } from '../stores/source-video'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const sourceStore = useSourceVideoStore()
const preprocessStore = usePreprocessStore()

const projectId = computed(() => String(route.params.projectId || ''))
const project = computed(() => projectStore.currentProject)
const sourceVideo = computed(() => sourceStore.currentSourceVideo)
const preprocess = computed(() => preprocessStore.currentPreprocess)

onMounted(async () => {
  preprocessStore.resetPreprocessState()
  try {
    if (projectStore.currentProject?.id !== projectId.value) {
      await projectStore.openProject(projectId.value)
    }
    if (sourceStore.currentSourceVideo?.project_id !== projectId.value) {
      await sourceStore.loadSourceVideo(projectId.value)
    }
    await preprocessStore.loadPreprocess(projectId.value)
  } catch {
    // 具体错误已经由对应 Store 保存，页面统一展示。
  }
})

async function startPreprocess(): Promise<void> {
  if (!sourceVideo.value || preprocessStore.processing || preprocess.value) return
  try {
    await preprocessStore.runPreprocess(projectId.value)
  } catch {
    // 错误文案已经写入 Store；保留页面状态方便用户检查环境后重试。
  }
}

function formatBytes(value: number | null): string {
  if (!value || value <= 0) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size >= 100 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`
}

function formatDuration(value: number | null): string {
  if (!value || value <= 0) return '—'
  const totalSeconds = Math.round(value / 1_000_000)
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return hours > 0
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function formatOffset(value: number | null): string {
  if (value === null) return '—'
  const sign = value >= 0 ? '+' : '-'
  return `${sign}${(Math.abs(value) / 1_000_000).toFixed(6)} s`
}

function formatFps(num: number | null, den: number | null): string {
  if (!num || !den) return 'VFR / 未固定'
  return `${(num / den).toFixed(3).replace(/\.000$/, '')} fps (${num}/${den})`
}
</script>

<template>
  <StudioShell
    title="视频预处理"
    :subtitle="project ? `${project.name} · 生成后续分析统一素材` : '正在读取项目'"
    project-mode
    :project-name="project?.name || ''"
  >
    <template #topbar>
      <span v-if="project" class="workspace-status-chip"><i></i> Source Domain</span>
      <button type="button" class="secondary-button compact-button" @click="router.push(`/projects/${projectId}`)">
        返回项目总览
      </button>
    </template>

    <div v-if="projectStore.opening || sourceStore.loading || preprocessStore.loading" class="workspace-loading">
      <div class="loading-ring"></div>
      <strong>正在读取视频预处理状态</strong>
      <p>检查 Project、Source Video 和已有派生资产…</p>
    </div>

    <div v-else-if="projectStore.errorMessage" class="workspace-error-panel">
      <div class="error-visual">!</div>
      <div>
        <span class="panel-eyebrow">PROJECT ERROR</span>
        <h2>项目无法打开</h2>
        <p>{{ projectStore.errorMessage }}</p>
        <button type="button" class="secondary-button" @click="router.push('/')">返回工作台</button>
      </div>
    </div>

    <template v-else-if="project">
      <section class="preprocess-page-heading">
        <div>
          <span class="panel-eyebrow">VIDEO PREPROCESS · F03</span>
          <h2>生成分析素材</h2>
          <p>从 F02 只读原片派生统一 Proxy、分析 WAV 和 Thumbnail，并保存明确的 Source Timeline 映射。</p>
        </div>
        <span class="preprocess-profile-chip">Profile V1 · 固定参数</span>
      </section>

      <div v-if="preprocessStore.errorMessage" class="inline-alert error-alert preprocess-alert">
        <span>!</span>
        <div><strong>视频预处理失败</strong><p>{{ preprocessStore.errorMessage }}</p></div>
      </div>

      <section v-if="!sourceVideo" class="content-panel preprocess-blocked-panel">
        <div class="preprocess-blocked-icon">02</div>
        <span class="panel-eyebrow">UPSTREAM REQUIRED</span>
        <h2>请先导入原视频</h2>
        <p>F03 只能处理 F02 已经锁定的 Source Video。当前项目还没有可用原片，因此不会生成任何 Proxy、WAV 或 Thumbnail。</p>
        <button type="button" class="primary-button" @click="router.push(`/projects/${projectId}/source-video`)">进入视频导入</button>
      </section>

      <template v-else-if="preprocess">
        <section class="content-panel preprocess-ready-panel">
          <div class="preprocess-ready-header">
            <div class="preprocess-ready-icon">✓</div>
            <div>
              <span class="online-chip"><i></i> PREPROCESS READY</span>
              <h2>分析素材已经生成</h2>
              <p>{{ sourceVideo.original_filename }} · Profile V{{ preprocess.profile_version }}</p>
            </div>
            <span class="preprocess-lock-badge">结果已锁定</span>
          </div>

          <div class="preprocess-assets-grid">
            <article>
              <span class="asset-type">PROXY</span>
              <h3>proxy.mp4</h3>
              <p>H.264 分析代理视频</p>
              <dl>
                <div><dt>大小</dt><dd>{{ formatBytes(preprocess.proxy_file_size_bytes) }}</dd></div>
                <div><dt>时长</dt><dd>{{ formatDuration(preprocess.proxy_duration_us) }}</dd></div>
                <div><dt>FPS</dt><dd>{{ formatFps(preprocess.proxy_fps_num, preprocess.proxy_fps_den) }}</dd></div>
                <div><dt>Time Base</dt><dd>{{ preprocess.proxy_video_time_base_num }}/{{ preprocess.proxy_video_time_base_den }}</dd></div>
              </dl>
              <code>{{ preprocess.proxy_relative_path }}</code>
            </article>

            <article :class="{ muted: !preprocess.audio_relative_path }">
              <span class="asset-type">AUDIO</span>
              <h3>{{ preprocess.audio_relative_path ? 'audio.wav' : '无分析音频' }}</h3>
              <p>{{ preprocess.audio_relative_path ? '16kHz · Mono · PCM16' : 'Source 本身没有音频流，不伪造静音 WAV' }}</p>
              <dl v-if="preprocess.audio_relative_path">
                <div><dt>大小</dt><dd>{{ formatBytes(preprocess.audio_file_size_bytes) }}</dd></div>
                <div><dt>时长</dt><dd>{{ formatDuration(preprocess.audio_duration_us) }}</dd></div>
                <div><dt>采样率</dt><dd>{{ preprocess.audio_sample_rate }} Hz</dd></div>
                <div><dt>声道</dt><dd>{{ preprocess.audio_channels }}</dd></div>
              </dl>
              <code v-if="preprocess.audio_relative_path">{{ preprocess.audio_relative_path }}</code>
            </article>

            <article>
              <span class="asset-type">THUMBNAIL</span>
              <h3>thumbnail.jpg</h3>
              <p>从 Proxy 确定性时间点抽取</p>
              <dl>
                <div><dt>大小</dt><dd>{{ formatBytes(preprocess.thumbnail_file_size_bytes) }}</dd></div>
                <div><dt>Source 时间</dt><dd>{{ (preprocess.thumbnail_source_time_us / 1_000_000).toFixed(3) }} s</dd></div>
                <div><dt>Hash</dt><dd>{{ preprocess.thumbnail_sha256.slice(0, 12) }}…</dd></div>
                <div><dt>状态</dt><dd>已校验</dd></div>
              </dl>
              <code>{{ preprocess.thumbnail_relative_path }}</code>
            </article>
          </div>
        </section>

        <section class="preprocess-bottom-grid">
          <article class="content-panel mapping-panel">
            <div class="section-heading compact">
              <div><h2>Timeline Mapping</h2><p>后续 F04/F08 不允许自行猜测时间偏移</p></div>
              <span class="online-chip"><i></i> Source Domain</span>
            </div>
            <div class="mapping-formula">
              <strong>Source = Derived + Offset</strong>
              <span>所有权威时间仍然使用 integer microseconds</span>
            </div>
            <div class="mapping-grid">
              <div><span>Proxy → Source</span><strong>{{ formatOffset(preprocess.proxy_to_source_offset_us) }}</strong></div>
              <div><span>Audio → Source</span><strong>{{ formatOffset(preprocess.audio_to_source_offset_us) }}</strong></div>
              <div><span>Source Video Time Base</span><strong>{{ preprocess.source_video_time_base_num }}/{{ preprocess.source_video_time_base_den }}</strong></div>
              <div><span>Source SHA Snapshot</span><strong>{{ preprocess.source_sha256_snapshot.slice(0, 16) }}…</strong></div>
            </div>
          </article>

          <article class="content-panel preprocess-next-panel">
            <div class="next-step-icon">04</div>
            <span class="panel-eyebrow">NEXT FEATURE</span>
            <h2>可以进入自动拉片阶段</h2>
            <p>F03 已经完成分析素材和 Source 时间映射。F04「自动拉片」尚未开发，因此当前不会提前生成 Shot 边界。</p>
            <div class="next-step-note"><span>✓</span><div><strong>F03 输入已经就绪</strong><small>Proxy、Audio、Thumbnail 和 Timeline Mapping 均已落盘并持久化。</small></div></div>
          </article>
        </section>
      </template>

      <template v-else>
        <section class="content-panel preprocess-source-panel">
          <div class="section-heading">
            <div><h2>Source Video</h2><p>预处理前会再次校验文件大小和 SHA-256，防止原片被系统外替换。</p></div>
            <span class="online-chip"><i></i> SOURCE READY</span>
          </div>
          <div class="preprocess-source-summary">
            <div><span>原文件</span><strong>{{ sourceVideo.original_filename }}</strong></div>
            <div><span>时长</span><strong>{{ formatDuration(sourceVideo.duration_us) }}</strong></div>
            <div><span>分辨率</span><strong>{{ sourceVideo.width }} × {{ sourceVideo.height }}</strong></div>
            <div><span>音频</span><strong>{{ sourceVideo.audio_stream_index === null ? '无音频' : sourceVideo.audio_codec?.toUpperCase() || '有音频' }}</strong></div>
          </div>
          <code class="preprocess-source-hash">SHA-256 · {{ sourceVideo.sha256 }}</code>
        </section>

        <section class="preprocess-profile-grid">
          <article class="content-panel profile-card"><span>01</span><div><strong>Proxy Video</strong><p>H.264 / CRF 23 / fast / yuv420p；最大 1280×720，保持比例，不放大小视频，不强制 CFR。</p></div></article>
          <article class="content-panel profile-card"><span>02</span><div><strong>Analysis Audio</strong><p>{{ sourceVideo.audio_stream_index === null ? 'Source 无音频，不生成静音 WAV。' : 'PCM16 · 16000Hz · Mono，用于后续 ASR / Speaker 分析。' }}</p></div></article>
          <article class="content-panel profile-card"><span>03</span><div><strong>Thumbnail</strong><p>从 Proxy 的确定性时间点抽取 JPEG，并记录它在 Source Timeline 中的实际位置。</p></div></article>
        </section>

        <section class="content-panel preprocess-run-panel">
          <div v-if="preprocessStore.processing" class="preprocess-processing-state">
            <div class="loading-ring"></div>
            <div>
              <strong>正在生成分析素材…</strong>
              <p>正在依次完成 Proxy、分析音频、Thumbnail、FFprobe 校验和 Timeline Mapping。此阶段不显示虚假百分比。</p>
            </div>
          </div>
          <template v-else>
            <div>
              <span class="panel-eyebrow">READY TO PROCESS</span>
              <h2>开始视频预处理</h2>
              <p>处理结果只写入 preprocess 目录，不会修改或覆盖 F02 原始视频。</p>
            </div>
            <button type="button" class="primary-button preprocess-start-button" @click="startPreprocess">开始视频预处理</button>
          </template>
        </section>
      </template>
    </template>
  </StudioShell>
</template>
