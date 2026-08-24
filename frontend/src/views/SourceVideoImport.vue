<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { useProjectStore } from '../stores/project'
import { useSourceVideoStore } from '../stores/source-video'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const sourceStore = useSourceVideoStore()

const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const dragging = ref(false)
const projectId = computed(() => String(route.params.projectId || ''))
const project = computed(() => projectStore.currentProject)
const sourceVideo = computed(() => sourceStore.currentSourceVideo)

onMounted(async () => {
  sourceStore.resetSourceVideoState()
  try {
    if (projectStore.currentProject?.id !== projectId.value) {
      await projectStore.openProject(projectId.value)
    }
    await sourceStore.loadSourceVideo(projectId.value)
  } catch {
    // Store 已保存错误信息，页面统一展示。
  }
})

function chooseFile(): void {
  if (sourceVideo.value || sourceStore.uploading) return
  fileInput.value?.click()
}

function setSelectedFile(file: File | null): void {
  if (!file || sourceVideo.value || sourceStore.uploading) return
  selectedFile.value = file
  sourceStore.errorMessage = ''
}

function handleInputChange(event: Event): void {
  const input = event.target as HTMLInputElement
  setSelectedFile(input.files?.[0] ?? null)
  input.value = ''
}

function handleDrop(event: DragEvent): void {
  dragging.value = false
  setSelectedFile(event.dataTransfer?.files?.[0] ?? null)
}

async function startImport(): Promise<void> {
  if (!selectedFile.value || sourceStore.uploading) return
  try {
    await sourceStore.importSourceVideo(projectId.value, selectedFile.value)
    selectedFile.value = null
  } catch {
    // 错误文案已经写入 Store，保留已选择文件，方便用户确认后重新操作。
  }
}

function formatBytes(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index += 1
  }
  return `${size >= 100 || index === 0 ? size.toFixed(0) : size.toFixed(1)} ${units[index]}`
}

function formatDuration(durationUs: number): string {
  const totalSeconds = Math.max(0, Math.round(durationUs / 1_000_000))
  const hours = Math.floor(totalSeconds / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  return hours > 0
    ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
    : `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function formatFps(num: number | null, den: number | null): string {
  if (!num || !den) return '未知'
  return `${(num / den).toFixed(3).replace(/\.000$/, '')} fps (${num}/${den})`
}

async function copySha256(): Promise<void> {
  if (!sourceVideo.value) return
  try {
    await navigator.clipboard.writeText(sourceVideo.value.sha256)
  } catch {
    sourceStore.errorMessage = '浏览器无法访问剪贴板，请手动复制 SHA-256'
  }
}
</script>

<template>
  <StudioShell
    title="视频导入"
    :subtitle="project ? `${project.name} · 导入只读 Source Video` : '正在读取项目'"
    project-mode
    :project-name="project?.name || ''"
  >
    <template #topbar>
      <span v-if="project" class="workspace-status-chip"><i></i> 本地项目</span>
      <button type="button" class="secondary-button compact-button" @click="router.push(`/projects/${projectId}`)">
        返回项目总览
      </button>
    </template>

    <div v-if="projectStore.opening || sourceStore.loading" class="workspace-loading">
      <div class="loading-ring"></div>
      <strong>正在读取原视频状态</strong>
      <p>检查项目 Workspace 和 Source Video 记录…</p>
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
      <section class="source-page-heading">
        <div>
          <span class="panel-eyebrow">SOURCE VIDEO · F02</span>
          <h2>导入原始视频</h2>
          <p>原片会完整复制进当前 Project Workspace，导入完成后作为后续生产流程的只读源证据。</p>
        </div>
        <span class="source-policy-chip">一项目一原片 · 导入后锁定</span>
      </section>

      <div v-if="sourceStore.errorMessage" class="inline-alert error-alert source-error-alert">
        <span>!</span>
        <div><strong>原视频操作失败</strong><p>{{ sourceStore.errorMessage }}</p></div>
      </div>

      <template v-if="sourceVideo">
        <section class="content-panel source-ready-panel">
          <div class="source-ready-header">
            <div class="source-ready-icon">▶</div>
            <div class="source-ready-title">
              <span class="online-chip"><i></i> SOURCE READY</span>
              <h2>{{ sourceVideo.original_filename }}</h2>
              <p>{{ sourceVideo.id }}</p>
            </div>
            <div class="source-lock-badge">只读原片</div>
          </div>

          <div class="source-metadata-grid">
            <article><span>文件大小</span><strong>{{ formatBytes(sourceVideo.file_size_bytes) }}</strong></article>
            <article><span>时长</span><strong>{{ formatDuration(sourceVideo.duration_us) }}</strong></article>
            <article><span>分辨率</span><strong>{{ sourceVideo.width }} × {{ sourceVideo.height }}</strong></article>
            <article><span>视频编码</span><strong>{{ sourceVideo.video_codec.toUpperCase() }}</strong></article>
            <article><span>帧率</span><strong>{{ formatFps(sourceVideo.fps_num, sourceVideo.fps_den) }}</strong></article>
            <article><span>容器格式</span><strong>{{ sourceVideo.container_format }}</strong></article>
            <article><span>音频编码</span><strong>{{ sourceVideo.audio_codec?.toUpperCase() || '无音频' }}</strong></article>
            <article><span>采样率 / 声道</span><strong>{{ sourceVideo.audio_sample_rate ? `${sourceVideo.audio_sample_rate} Hz / ${sourceVideo.audio_channels ?? '-'} ch` : '—' }}</strong></article>
          </div>

          <div class="source-integrity-grid">
            <div class="source-path-card">
              <span>Workspace 相对路径</span>
              <strong>{{ sourceVideo.relative_path }}</strong>
            </div>
            <div class="source-hash-card">
              <span>SHA-256</span>
              <div><strong>{{ sourceVideo.sha256 }}</strong><button type="button" class="ghost-button" @click="copySha256">复制</button></div>
            </div>
          </div>
        </section>

        <section class="content-panel source-next-panel">
          <div class="next-step-icon">03</div>
          <div>
            <span class="panel-eyebrow">SOURCE LOCKED</span>
            <h2>原片已经安全导入</h2>
            <p>F02 不允许覆盖、替换或删除这份 Source Video。Proxy、WAV 和缩略图将在 F03「视频预处理」中从这份只读原片派生。</p>
          </div>
        </section>
      </template>

      <template v-else>
        <section class="content-panel source-import-panel">
          <input
            ref="fileInput"
            class="source-file-input"
            type="file"
            accept="video/*,.mkv,.mov,.m4v,.avi,.ts,.m2ts"
            @change="handleInputChange"
          />

          <div
            v-if="!selectedFile && !sourceStore.uploading"
            class="source-dropzone"
            :class="{ dragging }"
            @click="chooseFile"
            @dragover.prevent="dragging = true"
            @dragleave.prevent="dragging = false"
            @drop.prevent="handleDrop"
          >
            <div class="source-drop-icon">＋</div>
            <h2>选择或拖入原视频</h2>
            <p>支持浏览器可选择的视频文件，以及 MP4 / MOV / MKV / M4V / AVI / TS / M2TS。最终是否可用由后端 FFprobe 实际验证。</p>
            <button type="button" class="primary-button" @click.stop="chooseFile">选择视频</button>
            <small>文件不会上传到云端，只发送给本机 127.0.0.1 FastAPI 并保存到当前 Workspace。</small>
          </div>

          <div v-else class="source-selection-card">
            <div class="source-selection-main">
              <div class="source-file-icon">▶</div>
              <div>
                <span>{{ sourceStore.uploading ? '正在导入' : '已选择原视频' }}</span>
                <h2>{{ selectedFile?.name || '正在处理视频' }}</h2>
                <p v-if="selectedFile">{{ formatBytes(selectedFile.size) }} · {{ selectedFile.type || '浏览器未提供 MIME' }}</p>
              </div>
            </div>

            <template v-if="sourceStore.uploading">
              <div class="source-progress-block">
                <div class="source-progress-heading">
                  <span>{{ sourceStore.processing ? '文件已发送，正在读取媒体信息…' : '正在复制到项目 Workspace…' }}</span>
                  <strong>{{ sourceStore.uploadPercent }}%</strong>
                </div>
                <div class="source-progress-track"><i :style="{ width: `${sourceStore.uploadPercent}%` }"></i></div>
                <p>{{ formatBytes(sourceStore.uploadedBytes) }} / {{ formatBytes(sourceStore.totalBytes) }}</p>
              </div>
            </template>

            <div v-else class="source-selection-actions">
              <button type="button" class="secondary-button" @click="chooseFile">重新选择</button>
              <button type="button" class="primary-button" @click="startImport">开始导入</button>
            </div>
          </div>
        </section>

        <section class="source-rules-grid">
          <article class="content-panel source-rule-card"><span>01</span><div><strong>完整复制原片</strong><p>不会直接引用外部文件路径，避免用户移动原文件后项目失效。</p></div></article>
          <article class="content-panel source-rule-card"><span>02</span><div><strong>SHA-256 完整性</strong><p>写入过程中同步计算文件大小和 Hash，不额外把大视频读第二遍。</p></div></article>
          <article class="content-panel source-rule-card"><span>03</span><div><strong>FFprobe 验证</strong><p>扩展名和浏览器 MIME 只作提示，真正视频合法性以后端 FFprobe 为准。</p></div></article>
        </section>
      </template>
    </template>
  </StudioShell>
</template>
