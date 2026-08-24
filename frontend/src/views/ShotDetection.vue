<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { usePreprocessStore } from '../stores/preprocess'
import { useProjectStore } from '../stores/project'
import { useShotDetectionStore } from '../stores/shot-detection'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const preprocessStore = usePreprocessStore()
const shotStore = useShotDetectionStore()

const projectId = computed(() => String(route.params.projectId || ''))
const project = computed(() => projectStore.currentProject)
const preprocess = computed(() => preprocessStore.currentPreprocess)
const detection = computed(() => shotStore.currentDetection)

onMounted(async () => {
  shotStore.resetShotDetectionState()
  try {
    if (projectStore.currentProject?.id !== projectId.value) {
      await projectStore.openProject(projectId.value)
    }
    if (preprocessStore.currentPreprocess?.project_id !== projectId.value) {
      await preprocessStore.loadPreprocess(projectId.value)
    }
    if (preprocessStore.currentPreprocess) {
      await shotStore.loadShotDetection(projectId.value)
    }
  } catch {
    // Store 已保留具体错误；页面只负责展示，不在这里猜测修复方式。
  }
})

async function startDetection(): Promise<void> {
  if (!preprocess.value || shotStore.processing || detection.value?.status === 'ready') return
  try {
    await shotStore.runShotDetection(projectId.value)
  } catch {
    // 错误文案由 Store 保存。
  }
}

async function rerunDetection(): Promise<void> {
  if (!preprocess.value || shotStore.processing || detection.value?.status !== 'ready') return
  const confirmed = window.confirm(
    '重新自动拉片会使用当前本机的 TransNetV2 / PyTorch / CUDA 环境重新计算。\n\n新结果完整成功前，当前 Auto Evidence 会一直保留；如果重跑失败，旧结果不会丢失。\n\n确定继续吗？',
  )
  if (!confirmed) return

  try {
    await shotStore.rerunShotDetection(projectId.value)
  } catch {
    // 错误文案由 Store 保存；后端保证失败时旧 READY 结果继续存在。
  }
}

function formatTimecode(value: number | null): string {
  if (value === null) return '—'
  const totalMs = Math.round(value / 1000)
  const milliseconds = Math.abs(totalMs % 1000)
  const totalSeconds = Math.floor(Math.abs(totalMs) / 1000)
  const seconds = totalSeconds % 60
  const minutes = Math.floor(totalSeconds / 60) % 60
  const hours = Math.floor(totalSeconds / 3600)
  const sign = value < 0 ? '-' : ''
  return `${sign}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`
}

function formatDuration(value: number): string {
  if (value < 1_000_000) return `${(value / 1000).toFixed(0)} ms`
  return `${(value / 1_000_000).toFixed(3)} s`
}

function formatScore(value: number | null): string {
  return value === null ? '视频结束' : value.toFixed(4)
}
</script>

<template>
  <StudioShell
    title="自动拉片"
    :subtitle="project ? `${project.name} · 本地镜头边界检测` : '正在读取项目'"
    project-mode
    :project-name="project?.name || ''"
  >
    <template #topbar>
      <span v-if="project" class="workspace-status-chip"><i></i> LOCAL · TRANSNETV2</span>
      <button type="button" class="secondary-button compact-button" @click="router.push(`/projects/${projectId}`)">
        返回项目总览
      </button>
    </template>

    <div v-if="projectStore.opening || preprocessStore.loading || shotStore.loading" class="workspace-loading">
      <div class="loading-ring"></div>
      <strong>正在读取自动拉片状态</strong>
      <p>检查 F03 Proxy、时间映射和已有 Detection Run…</p>
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
      <section class="shot-page-heading">
        <div>
          <span class="panel-eyebrow">AUTO SHOT DETECTION · F04</span>
          <h2>用本地 TransNetV2 自动找切镜点</h2>
          <p>模型只判断“哪一帧发生转场”；正式镜头时间全部由 FFprobe 真实 PTS 生成，再映射回 Source Timeline。</p>
        </div>
        <span class="shot-profile-chip">Profile V1 · 固定参数</span>
      </section>

      <div v-if="shotStore.errorMessage || preprocessStore.errorMessage" class="inline-alert error-alert shot-alert">
        <span>!</span>
        <div>
          <strong>自动拉片失败</strong>
          <p>{{ shotStore.errorMessage || preprocessStore.errorMessage }}</p>
        </div>
      </div>

      <section v-if="!preprocess" class="content-panel shot-blocked-panel">
        <div class="shot-blocked-icon">03</div>
        <span class="panel-eyebrow">UPSTREAM REQUIRED</span>
        <h2>请先完成视频预处理</h2>
        <p>F04 只读取 F03 已校验的 proxy.mp4 和 Proxy → Source 时间映射。当前项目还没有可用的 F03 结果。</p>
        <button type="button" class="primary-button" @click="router.push(`/projects/${projectId}/preprocess`)">进入视频预处理</button>
      </section>

      <template v-else-if="detection?.status === 'ready'">
        <section class="content-panel shot-ready-panel">
          <div class="shot-ready-header">
            <div class="shot-ready-icon">✓</div>
            <div>
              <span class="online-chip"><i></i> SHOT DETECTION READY</span>
              <h2>自动拉片完成</h2>
              <p>自动证据已经锁定。F05 人工修正会另存 Final Shot，不覆盖这里的 detected_* 结果。</p>
            </div>
            <div class="topbar-actions">
              <span class="shot-lock-badge">Auto Evidence</span>
              <button
                type="button"
                class="secondary-button compact-button"
                :disabled="shotStore.processing"
                @click="rerunDetection"
              >
                {{ shotStore.processing ? '正在重新检测…' : '重新自动拉片' }}
              </button>
            </div>
          </div>

          <div class="shot-stat-grid">
            <article><span>镜头数</span><strong>{{ detection.shot_count ?? detection.candidates.length }}</strong><small>Shot Candidates</small></article>
            <article><span>自动切点</span><strong>{{ detection.detected_cut_count ?? 0 }}</strong><small>Normalized Cuts</small></article>
            <article><span>分析帧</span><strong>{{ detection.analyzed_frame_count ?? '—' }}</strong><small>PTS Aligned Frames</small></article>
            <article><span>计算设备</span><strong>{{ detection.detector_device || '—' }}</strong><small>PyTorch {{ detection.torch_version || '—' }}</small></article>
          </div>
        </section>

        <section class="content-panel shot-runtime-panel">
          <div class="section-heading compact">
            <div><h2>Detector Runtime</h2><p>这组信息用于复现同一次自动判断。</p></div>
            <span class="online-chip"><i></i> LOCAL MODEL</span>
          </div>
          <div class="shot-runtime-grid">
            <div><span>Detector</span><strong>{{ detection.detector_name }}</strong></div>
            <div><span>Package</span><strong>{{ detection.detector_package_version }}</strong></div>
            <div><span>Threshold</span><strong>{{ detection.detector_threshold.toFixed(2) }}</strong></div>
            <div><span>近邻去抖</span><strong>{{ detection.min_boundary_gap_us / 1000 }} ms</strong></div>
            <div><span>Proxy Range</span><strong>{{ formatTimecode(detection.proxy_start_us) }} → {{ formatTimecode(detection.proxy_end_us) }}</strong></div>
            <div><span>Source Range</span><strong>{{ formatTimecode(detection.source_start_us) }} → {{ formatTimecode(detection.source_end_us) }}</strong></div>
          </div>
        </section>

        <section class="content-panel shot-list-panel">
          <div class="section-heading">
            <div>
              <h2>Shot Candidates</h2>
              <p>时间以 Source Domain 为主；边界分数只是模型 transition score，不代表“准确率”。</p>
            </div>
            <span class="progress-summary">{{ detection.candidates.length }} SHOTS</span>
          </div>

          <div class="shot-table-wrap">
            <table class="shot-table">
              <thead>
                <tr>
                  <th>镜头</th>
                  <th>Source 开始</th>
                  <th>Source 结束</th>
                  <th>时长</th>
                  <th>结束边界</th>
                  <th>边界分数</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="candidate in detection.candidates" :key="candidate.id">
                  <td><strong>#{{ String(candidate.ordinal).padStart(3, '0') }}</strong></td>
                  <td class="mono-value">{{ formatTimecode(candidate.detected_start_us) }}</td>
                  <td class="mono-value">{{ formatTimecode(candidate.detected_end_us) }}</td>
                  <td>{{ formatDuration(candidate.duration_us) }}</td>
                  <td><span class="shot-boundary-chip" :class="candidate.end_boundary_kind">{{ candidate.end_boundary_kind === 'cut' ? 'CUT' : 'VIDEO END' }}</span></td>
                  <td class="mono-value">{{ formatScore(candidate.end_boundary_score) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="content-panel shot-next-panel">
          <div class="next-step-icon">05</div>
          <div>
            <span class="panel-eyebrow">NEXT FEATURE</span>
            <h2>下一步：人工修正镜头边界</h2>
            <p>F04 只保留自动检测结果。F05 再处理误切、漏切、拆分和合并，并形成独立 Final Shot。</p>
          </div>
          <span class="shot-next-status">F05 待开发</span>
        </section>
      </template>

      <template v-else>
        <section class="shot-profile-grid">
          <article class="content-panel shot-profile-card">
            <span>01</span><div><strong>TransNetV2</strong><p>本地神经网络检测硬切与渐变转场，不使用云端 API。</p></div>
          </article>
          <article class="content-panel shot-profile-card">
            <span>02</span><div><strong>真实 PTS</strong><p>逐帧 FFprobe 时间戳与模型 prediction 一一对齐，VFR 不按 FPS 猜时间。</p></div>
          </article>
          <article class="content-panel shot-profile-card">
            <span>03</span><div><strong>Source Mapping</strong><p>复用 F03 固定 offset，把 Proxy 边界映射为后续功能统一使用的 Source 时间。</p></div>
          </article>
        </section>

        <section class="content-panel shot-input-panel">
          <div class="section-heading">
            <div><h2>F03 输入已经就绪</h2><p>运行前和保存结果前都会再次校验 Proxy SHA-256。</p></div>
            <span class="online-chip"><i></i> PREPROCESS READY</span>
          </div>
          <div class="shot-input-grid">
            <div><span>Proxy</span><strong>{{ preprocess.proxy_relative_path }}</strong></div>
            <div><span>Proxy 时长</span><strong>{{ formatDuration(preprocess.proxy_duration_us) }}</strong></div>
            <div><span>Profile</span><strong>F03 V{{ preprocess.profile_version }}</strong></div>
            <div><span>Proxy → Source Offset</span><strong>{{ (preprocess.proxy_to_source_offset_us / 1_000_000).toFixed(6) }} s</strong></div>
          </div>
        </section>

        <section class="content-panel shot-run-panel">
          <div v-if="shotStore.processing" class="shot-processing-state">
            <div class="loading-ring"></div>
            <div>
              <strong>正在自动拉片…</strong>
              <p>正在执行 Proxy 完整性校验、FFprobe 逐帧 PTS、TransNetV2 本地推理、转场归并和 Shot 连续性校验。此阶段不显示虚假百分比。</p>
            </div>
          </div>
          <template v-else>
            <div>
              <span class="panel-eyebrow">READY TO DETECT</span>
              <h2>开始本地自动拉片</h2>
              <p>Profile V1 固定使用 threshold 0.5 和 120ms 近邻去抖。页面不开放随意填写算法参数，避免同一功能产生不可比较结果。</p>
            </div>
            <button type="button" class="primary-button shot-start-button" @click="startDetection">开始自动拉片</button>
          </template>
        </section>
      </template>
    </template>
  </StudioShell>
</template>
