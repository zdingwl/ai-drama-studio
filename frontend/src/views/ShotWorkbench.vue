<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { shotWorkbenchFrameUrl, shotWorkbenchProxyUrl } from '../api/shot-workbench'
import { useProjectStore } from '../stores/project'
import { useShotDetectionStore } from '../stores/shot-detection'
import { useShotWorkbenchStore } from '../stores/shot-workbench'
import type { FinalShot } from '../types/shot-workbench'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const detectionStore = useShotDetectionStore()
const workbenchStore = useShotWorkbenchStore()

const videoRef = ref<HTMLVideoElement | null>(null)
const selectedShotId = ref('')
const currentSourceUs = ref(0)
const draftStartSeconds = ref(0)
const draftEndSeconds = ref(0)

const projectId = computed(() => String(route.params.projectId || ''))
const project = computed(() => projectStore.currentProject)
const detection = computed(() => detectionStore.currentDetection)
const workbench = computed(() => workbenchStore.currentWorkbench)
const shots = computed(() => workbench.value?.shots ?? [])
const selectedIndex = computed(() => shots.value.findIndex((shot) => shot.id === selectedShotId.value))
const selectedShot = computed(() => selectedIndex.value >= 0 ? shots.value[selectedIndex.value] : shots.value[0] ?? null)
const isLocked = computed(() => workbench.value?.status === 'confirmed')
const totalDurationUs = computed(() => workbench.value ? workbench.value.source_end_us - workbench.value.source_start_us : 0)
const proxyUrl = computed(() => shotWorkbenchProxyUrl(projectId.value))
const fatalError = computed(() => projectStore.errorMessage || detectionStore.errorMessage || (!workbench.value ? workbenchStore.errorMessage : ''))

onMounted(async () => {
  workbenchStore.reset()
  try {
    if (projectStore.currentProject?.id !== projectId.value) await projectStore.openProject(projectId.value)
    await detectionStore.loadShotDetection(projectId.value)
    if (detectionStore.currentDetection?.status === 'ready') {
      const result = await workbenchStore.loadOrInitialize(projectId.value)
      selectedShotId.value = result.shots[0]?.id ?? ''
      currentSourceUs.value = result.source_start_us
      syncDraftInputs()
    }
  } catch {
    // Store 保存可展示错误；页面不猜测数据库/媒体修复方式。
  }
})

watch(selectedShotId, () => syncDraftInputs())
watch(() => workbench.value?.revision, () => syncDraftInputs())

function syncDraftInputs(): void {
  const shot = selectedShot.value
  if (!shot) return
  draftStartSeconds.value = shot.final_start_us / 1_000_000
  draftEndSeconds.value = shot.final_end_us / 1_000_000
}

function formatTimecode(value: number): string {
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
  return value < 1_000_000 ? `${Math.round(value / 1000)} ms` : `${(value / 1_000_000).toFixed(3)} s`
}

function frameUrl(sourceTimeUs: number): string {
  return shotWorkbenchFrameUrl(projectId.value, sourceTimeUs)
}

function thumbnailTime(shot: FinalShot): number {
  const offset = Math.min(50_000, Math.max(0, Math.floor(shot.duration_us / 10)))
  return Math.min(shot.final_end_us - 1, shot.final_start_us + offset)
}

function keyframeTimes(shot: FinalShot): Array<{ label: string; timeUs: number }> {
  const fractions = [0, 0.25, 0.5, 0.75, 1]
  const labels = ['首帧', '25%', '中帧', '75%', '尾帧']
  return fractions.map((fraction, index) => ({
    label: labels[index],
    timeUs: Math.min(shot.final_end_us - 1, shot.final_start_us + Math.floor(shot.duration_us * fraction)),
  }))
}

function playerSecondsFromSource(sourceUs: number): number {
  const start = workbench.value?.source_start_us ?? 0
  return Math.max(0, (sourceUs - start) / 1_000_000)
}

function selectShot(shot: FinalShot, seek = true): void {
  selectedShotId.value = shot.id
  currentSourceUs.value = shot.final_start_us
  if (seek && videoRef.value) videoRef.value.currentTime = playerSecondsFromSource(shot.final_start_us)
}

function onTimeUpdate(): void {
  if (!workbench.value || !videoRef.value) return
  const sourceUs = workbench.value.source_start_us + Math.round(videoRef.value.currentTime * 1_000_000)
  currentSourceUs.value = Math.min(workbench.value.source_end_us, sourceUs)
  const current = shots.value.find((shot) => sourceUs >= shot.final_start_us && sourceUs < shot.final_end_us)
  if (current && current.id !== selectedShotId.value) selectedShotId.value = current.id
}

async function saveStartBoundary(): Promise<void> {
  if (isLocked.value || selectedIndex.value <= 0 || !selectedShot.value) return
  const previous = shots.value[selectedIndex.value - 1]
  const keepId = selectedShot.value.id
  try {
    await workbenchStore.adjustBoundary(projectId.value, previous.id, Math.round(draftStartSeconds.value * 1_000_000))
    selectedShotId.value = keepId
  } catch {
    syncDraftInputs()
  }
}

async function saveEndBoundary(): Promise<void> {
  if (isLocked.value || selectedIndex.value < 0 || selectedIndex.value >= shots.value.length - 1 || !selectedShot.value) return
  const keepId = selectedShot.value.id
  try {
    await workbenchStore.adjustBoundary(projectId.value, keepId, Math.round(draftEndSeconds.value * 1_000_000))
    selectedShotId.value = keepId
  } catch {
    syncDraftInputs()
  }
}

async function splitAtPlayhead(): Promise<void> {
  const shot = selectedShot.value
  if (!shot || isLocked.value) return
  const splitUs = currentSourceUs.value
  if (!(splitUs > shot.final_start_us && splitUs < shot.final_end_us)) {
    window.alert('请先把播放器停在当前镜头内部，再执行拆分。')
    return
  }
  if (!window.confirm(`在 ${formatTimecode(splitUs)} 拆分当前镜头？`)) return
  try {
    await workbenchStore.split(projectId.value, shot.id, splitUs)
    const current = shots.value.find((item) => splitUs >= item.final_start_us && splitUs < item.final_end_us)
    if (current) selectedShotId.value = current.id
  } catch {
    // Store 已保存错误。
  }
}

async function mergePrevious(): Promise<void> {
  if (isLocked.value || selectedIndex.value <= 0) return
  const previous = shots.value[selectedIndex.value - 1]
  if (!window.confirm(`把 #${String(previous.ordinal).padStart(3, '0')} 与当前镜头合并？`)) return
  try {
    await workbenchStore.merge(projectId.value, previous.id)
    selectedShotId.value = previous.id
    await nextTick()
    if (videoRef.value) videoRef.value.currentTime = playerSecondsFromSource(previous.final_start_us)
  } catch {
    // Store 已保存错误。
  }
}

async function mergeNext(): Promise<void> {
  const shot = selectedShot.value
  if (!shot || isLocked.value || selectedIndex.value >= shots.value.length - 1) return
  if (!window.confirm(`把当前镜头与 #${String(shot.ordinal + 1).padStart(3, '0')} 合并？`)) return
  try {
    await workbenchStore.merge(projectId.value, shot.id)
    selectedShotId.value = shot.id
  } catch {
    // Store 已保存错误。
  }
}

async function confirmTimeline(): Promise<void> {
  if (!workbench.value || isLocked.value) return
  if (!window.confirm('确认后 Final Shot 将锁定，F05 不再允许修改。确定继续吗？')) return
  try {
    await workbenchStore.confirm(projectId.value)
  } catch {
    // Store 已保存错误。
  }
}
</script>

<template>
  <StudioShell
    title="镜头工作台"
    :subtitle="project ? `${project.name} · Final Shot 人工修正` : '正在读取项目'"
    project-mode
    :project-name="project?.name || ''"
  >
    <template #topbar>
      <span v-if="workbench" class="workspace-status-chip"><i></i> {{ isLocked ? 'FINAL SHOTS CONFIRMED' : 'F05 · EDITING' }}</span>
      <button type="button" class="secondary-button compact-button" @click="router.push(`/projects/${projectId}/shot-detection`)">查看自动拉片</button>
    </template>

    <div v-if="projectStore.opening || detectionStore.loading || workbenchStore.loading" class="workspace-loading">
      <div class="loading-ring"></div><strong>正在打开镜头工作台</strong><p>读取 F04 Auto Evidence，并准备独立 Final Shot Timeline…</p>
    </div>

    <div v-else-if="fatalError" class="workspace-error-panel">
      <div class="error-visual">!</div>
      <div><span class="panel-eyebrow">SHOT WORKBENCH ERROR</span><h2>镜头工作台暂时不可用</h2><p>{{ fatalError }}</p><button type="button" class="secondary-button" @click="router.push(`/projects/${projectId}`)">返回项目总览</button></div>
    </div>

    <section v-else-if="detection?.status !== 'ready'" class="content-panel shot-workbench-blocked">
      <span class="panel-eyebrow">F04 REQUIRED</span><h2>请先完成自动拉片</h2><p>F05 必须以一份 READY 的 F04 Auto Shot Candidate 作为只读来源。</p><button type="button" class="primary-button" @click="router.push(`/projects/${projectId}/shot-detection`)">进入自动拉片</button>
    </section>

    <template v-else-if="workbench && selectedShot">
      <section class="shot-workbench-heading">
        <div><span class="panel-eyebrow">FINAL SHOT WORKBENCH · F05</span><h2>逐镜头检查、播放和修正</h2><p>F04 自动证据保持只读；这里的每一次修改只作用于 Final Shot。</p></div>
        <div class="shot-workbench-summary"><span>{{ shots.length }} SHOTS</span><span>REV {{ workbench.revision }}</span><span :class="{ locked: isLocked }">{{ isLocked ? '已确认' : '编辑中' }}</span></div>
      </section>

      <div v-if="workbenchStore.errorMessage" class="inline-alert error-alert shot-workbench-alert">
        <span>!</span><div><strong>修改未保存</strong><p>{{ workbenchStore.errorMessage }}</p></div>
      </div>

      <section class="shot-workbench-grid">
        <aside class="content-panel shot-list-column">
          <div class="shot-column-header"><div><span class="panel-eyebrow">SHOT LIST</span><h3>镜头列表</h3></div><span>{{ shots.length }}</span></div>
          <div class="final-shot-list">
            <button v-for="shot in shots" :key="shot.id" type="button" class="final-shot-card" :class="{ active: shot.id === selectedShotId, manual: shot.origin_kind === 'manual' }" @click="selectShot(shot)">
              <img :src="frameUrl(thumbnailTime(shot))" loading="lazy" alt="" />
              <span class="final-shot-copy"><strong>#{{ String(shot.ordinal).padStart(3, '0') }}</strong><small>{{ formatTimecode(shot.final_start_us) }}</small><em>{{ formatDuration(shot.duration_us) }}</em></span>
              <span v-if="shot.origin_kind === 'manual'" class="manual-dot" title="已人工修改"></span>
            </button>
          </div>
        </aside>

        <main class="shot-center-column">
          <section class="content-panel shot-player-panel">
            <div class="shot-player-topline"><div><span class="panel-eyebrow">NOW REVIEWING</span><strong>#{{ String(selectedShot.ordinal).padStart(3, '0') }}</strong></div><span class="mono-value">{{ formatTimecode(selectedShot.final_start_us) }} → {{ formatTimecode(selectedShot.final_end_us) }}</span></div>
            <video ref="videoRef" class="shot-workbench-video" :src="proxyUrl" controls preload="metadata" @timeupdate="onTimeUpdate" @seeked="onTimeUpdate"></video>
            <div class="player-time-row"><span>播放点</span><strong class="mono-value">{{ formatTimecode(currentSourceUs) }}</strong><small>Source Timeline</small></div>
          </section>

          <section class="content-panel shot-timeline-panel">
            <div class="shot-column-header"><div><span class="panel-eyebrow">SHOT TIMELINE</span><h3>镜头时间轴</h3></div><span>{{ formatDuration(totalDurationUs) }}</span></div>
            <div class="shot-timeline-track">
              <button v-for="shot in shots" :key="shot.id" type="button" class="shot-timeline-segment" :class="{ active: shot.id === selectedShotId, manual: shot.origin_kind === 'manual' }" :style="{ flexGrow: Math.max(1, shot.duration_us) }" :title="`#${shot.ordinal} ${formatTimecode(shot.final_start_us)} - ${formatTimecode(shot.final_end_us)}`" @click="selectShot(shot)"><span>{{ shot.ordinal }}</span></button>
            </div>
          </section>

          <section class="content-panel shot-keyframes-panel">
            <div class="shot-column-header"><div><span class="panel-eyebrow">KEYFRAMES</span><h3>当前镜头关键帧</h3></div><span>5 FRAMES</span></div>
            <div class="shot-keyframe-grid">
              <button v-for="frame in keyframeTimes(selectedShot)" :key="frame.label" type="button" @click="videoRef && (videoRef.currentTime = playerSecondsFromSource(frame.timeUs))">
                <img :src="frameUrl(frame.timeUs)" loading="lazy" alt="" /><span>{{ frame.label }}</span><small>{{ formatTimecode(frame.timeUs) }}</small>
              </button>
            </div>
          </section>
        </main>

        <aside class="content-panel shot-detail-column">
          <div class="shot-detail-header"><div><span class="panel-eyebrow">FINAL SHOT</span><h3>#{{ String(selectedShot.ordinal).padStart(3, '0') }}</h3></div><span class="shot-origin-chip">{{ selectedShot.origin_kind === 'manual' ? 'MANUAL' : 'AUTO COPY' }}</span></div>

          <div class="shot-time-editor">
            <label><span>Final Start · 秒</span><div><input v-model.number="draftStartSeconds" type="number" step="0.001" :disabled="isLocked || selectedIndex === 0 || workbenchStore.saving" /><button type="button" :disabled="isLocked || selectedIndex === 0 || workbenchStore.saving" @click="saveStartBoundary">保存</button></div><small>{{ selectedIndex === 0 ? '首镜起点由整集范围锁定' : '保存时会同步修改前一镜的结束点' }}</small></label>
            <label><span>Final End · 秒</span><div><input v-model.number="draftEndSeconds" type="number" step="0.001" :disabled="isLocked || selectedIndex === shots.length - 1 || workbenchStore.saving" /><button type="button" :disabled="isLocked || selectedIndex === shots.length - 1 || workbenchStore.saving" @click="saveEndBoundary">保存</button></div><small>{{ selectedIndex === shots.length - 1 ? '末镜终点由整集范围锁定' : '保存时会同步修改后一镜的开始点' }}</small></label>
          </div>

          <div class="shot-edit-actions">
            <button type="button" class="primary-button" :disabled="isLocked || workbenchStore.saving" @click="splitAtPlayhead">在播放点拆分（新增镜头）</button>
            <div><button type="button" class="secondary-button" :disabled="isLocked || selectedIndex <= 0 || workbenchStore.saving" @click="mergePrevious">与前一镜合并</button><button type="button" class="secondary-button" :disabled="isLocked || selectedIndex >= shots.length - 1 || workbenchStore.saving" @click="mergeNext">与后一镜合并</button></div>
          </div>

          <div class="shot-origin-block"><span>Auto Evidence 来源</span><strong>{{ selectedShot.origin_candidate_ids.length }} Candidate</strong><small>{{ selectedShot.origin_candidate_ids.join(' · ') }}</small></div>

          <div class="shot-semantic-placeholder">
            <div class="shot-column-header"><div><span class="panel-eyebrow">LATER FEATURES</span><h3>镜头语义</h3></div><span>待分析</span></div>
            <dl><div><dt>人物</dt><dd>F06+</dd></div><div><dt>场景</dt><dd>F11+</dd></div><div><dt>景别</dt><dd>后续 VLM</dd></div><div><dt>运镜</dt><dd>后续 VLM</dd></div><div><dt>动作</dt><dd>后续 VLM</dd></div><div><dt>对白</dt><dd>F08+</dd></div></dl>
            <p>这里只预留展示位置，F05 不伪造人物、对白、景别或运镜结果。</p>
          </div>

          <div class="shot-confirm-block">
            <div><strong>{{ isLocked ? 'Final Shots 已确认' : '完成全部人工检查后确认' }}</strong><p>{{ isLocked ? '当前时间轴已经锁定，可供后续 Feature 稳定引用。' : '确认后 F05 不再允许调整、拆分或合并。' }}</p></div>
            <button v-if="!isLocked" type="button" class="primary-button" :disabled="workbenchStore.saving" @click="confirmTimeline">确认 Final Shots</button><span v-else class="online-chip"><i></i> CONFIRMED</span>
          </div>
        </aside>
      </section>
    </template>
  </StudioShell>
</template>
