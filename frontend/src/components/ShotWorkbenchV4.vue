<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type { Episode, Shot, ShotRevision } from '../types/studio'
import ShotFramePreviewV4 from './ShotFramePreviewV4.vue'

interface ReviewKeyframe {
  kind: string
  source_time_us?: number
  local_time_us?: number
  path?: string
  confidence?: number
  method?: string
  transnet_score?: number
  visual_score?: number
  visual_prominence?: number
  pyscenedetect_confirmed?: boolean
  pyscenedetect_distance_frames?: number | null
  pyscenedetect_status?: string
  offset_frames?: number
  review_reasons?: string[]
}

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

const emit = defineEmits<{
  refreshProject: []
}>()

const selectedEpisodeId = ref('')
const shots = ref<Shot[]>([])
const selectedShot = ref<Shot | null>(null)
const revisions = ref<ShotRevision[]>([])
const revisionOpen = ref(false)
const busy = ref('')
const error = ref('')
const videoRef = ref<HTMLVideoElement | null>(null)
const playheadUs = ref(0)
const startSeconds = ref(0)
const endSeconds = ref(0)
const manualSeekShotId = ref<string | null>(null)
const lightboxSrc = ref('')
const lightboxTitle = ref('')
const lightboxScale = ref(1)

const selectedEpisode = computed(() => props.episodes.find((item) => item.id === selectedEpisodeId.value) ?? null)
const selectedShotIndex = computed(() => selectedShot.value ? shots.value.findIndex((item) => item.id === selectedShot.value?.id) : -1)
const previousShot = computed(() => {
  const index = selectedShotIndex.value
  return index > 0 ? shots.value[index - 1] : null
})
const nextShot = computed(() => {
  const index = selectedShotIndex.value
  return index >= 0 && index < shots.value.length - 1 ? shots.value[index + 1] : null
})
const currentRevision = computed(() => revisions.value.find((item) => item.is_current) ?? null)
const episodeProxyUrl = computed(() => selectedEpisodeId.value ? `/api/episodes/${selectedEpisodeId.value}/proxy` : '')
const suspiciousShots = computed(() => shots.value.filter(needsReview))
const selectedBoundaryMeta = computed(() => selectedShot.value ? boundaryMeta(selectedShot.value) : null)

function keyframes(shot: Shot): ReviewKeyframe[] {
  return (shot.keyframes || []) as unknown as ReviewKeyframe[]
}

function boundaryMeta(shot: Shot): ReviewKeyframe | null {
  return keyframes(shot).find((item) => item.kind === 'boundary_meta') ?? null
}

function frameLocalUs(shot: Shot, kind: 'start' | 'middle' | 'end'): number {
  const item = keyframes(shot).find((frame) => frame.kind === kind)
  if (typeof item?.local_time_us === 'number') return Math.max(0, Math.min(shot.duration_us, item.local_time_us))
  if (kind === 'start') return 0
  if (kind === 'middle') return Math.max(0, Math.floor(shot.duration_us / 2))
  return Math.max(0, shot.duration_us - 1_000)
}

function reviewReasons(shot: Shot): string[] {
  const reasons = [...(boundaryMeta(shot)?.review_reasons || [])]
  if (shot.duration_us < 500_000 && !reasons.some((item) => item.includes('极短'))) reasons.push('镜头过短（少于 0.5 秒）')
  return Array.from(new Set(reasons))
}

function needsReview(shot: Shot): boolean {
  const meta = boundaryMeta(shot)
  if (shot.duration_us < 500_000) return true
  if (reviewReasons(shot).length) return true
  return typeof meta?.confidence === 'number' && meta.confidence < 0.68
}

function confidencePercent(shot: Shot): string {
  const value = boundaryMeta(shot)?.confidence
  if (typeof value !== 'number') return shot.status === 'MANUAL' ? '人工修正' : '—'
  return `${Math.round(value * 100)}%`
}

function seconds(us: number | null | undefined): string {
  if (us === null || us === undefined) return '—'
  return `${(us / 1_000_000).toFixed(2)} 秒`
}

function timecode(us: number | null | undefined): string {
  if (us === null || us === undefined) return '00:00.000'
  const totalMs = Math.max(0, Math.round(us / 1000))
  const minutes = Math.floor(totalMs / 60_000)
  const secondsPart = Math.floor((totalMs % 60_000) / 1000)
  const ms = totalMs % 1000
  return `${String(minutes).padStart(2, '0')}:${String(secondsPart).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function revisionKind(kind: string): string {
  const labels: Record<string, string> = {
    AUTO: '自动检测',
    MANUAL: '人工修正',
    RESTORE: '历史恢复',
    BASELINE: '历史基线',
  }
  return labels[kind] || kind
}

function thumbnailUrl(shot: Shot): string {
  return shot.thumbnail_url ? `${shot.thumbnail_url}?v=${shot.start_us}-${shot.end_us}` : ''
}

function referenceUrl(shot: Shot): string {
  return `${shot.reference_url}?v=${shot.start_us}-${shot.end_us}`
}

function openFrame(src: string, title: string): void {
  lightboxSrc.value = src
  lightboxTitle.value = title
  lightboxScale.value = 1
}

function closeLightbox(): void {
  lightboxSrc.value = ''
  lightboxTitle.value = ''
  lightboxScale.value = 1
}

function zoomLightbox(delta: number): void {
  lightboxScale.value = Math.max(0.5, Math.min(4, Number((lightboxScale.value + delta).toFixed(2))))
}

function onLightboxWheel(event: WheelEvent): void {
  if (!lightboxSrc.value) return
  event.preventDefault()
  zoomLightbox(event.deltaY < 0 ? 0.2 : -0.2)
}

function applySelectedShot(shot: Shot | null, seek: boolean): void {
  selectedShot.value = shot
  if (!shot) return
  startSeconds.value = shot.start_us / 1_000_000
  endSeconds.value = shot.end_us / 1_000_000

  if (seek && videoRef.value) {
    manualSeekShotId.value = shot.id
    const insetUs = Math.min(20_000, Math.max(1_000, Math.floor(shot.duration_us / 10)))
    const targetUs = Math.min(Math.max(shot.start_us, shot.end_us - 1_000), shot.start_us + insetUs)
    videoRef.value.currentTime = targetUs / 1_000_000
    playheadUs.value = targetUs
  }
}

function selectShot(shot: Shot): void {
  applySelectedShot(shot, true)
}

function selectAdjacent(offset: number): void {
  const index = selectedShotIndex.value
  if (index < 0) return
  const shot = shots.value[index + offset]
  if (shot) selectShot(shot)
}

async function loadEpisodeData(episodeId: string): Promise<void> {
  if (!episodeId) {
    shots.value = []
    revisions.value = []
    manualSeekShotId.value = null
    applySelectedShot(null, false)
    return
  }
  const previousId = selectedShot.value?.id
  const [nextShots, nextRevisions] = await Promise.all([
    api.listShots(episodeId),
    api.listShotRevisions(episodeId),
  ])
  shots.value = nextShots
  revisions.value = nextRevisions
  applySelectedShot(nextShots.find((shot) => shot.id === previousId) ?? nextShots[0] ?? null, false)
}

async function chooseEpisode(episodeId: string): Promise<void> {
  selectedEpisodeId.value = episodeId
  revisionOpen.value = false
  manualSeekShotId.value = null
  playheadUs.value = 0
  error.value = ''
  try {
    await loadEpisodeData(episodeId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '剧集读取失败'
  }
}

function onEpisodeChange(event: Event): void {
  void chooseEpisode((event.target as HTMLSelectElement).value)
}

async function startSingle(): Promise<void> {
  const episode = selectedEpisode.value
  if (!episode) return
  busy.value = episode.shot_count ? '正在重新检测镜头' : '正在检测镜头'
  error.value = ''
  try {
    await api.startEpisodeShotsTask(episode.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '启动镜头检测失败'
  } finally {
    busy.value = ''
  }
}

async function startBatch(): Promise<void> {
  busy.value = '正在启动顺序批量镜头检测'
  error.value = ''
  try {
    await api.startBatchShotsTask(props.projectId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '启动批量镜头检测失败'
  } finally {
    busy.value = ''
  }
}

async function applyEdit(label: string, action: () => Promise<Shot[]>, preferredId?: string): Promise<void> {
  busy.value = label
  error.value = ''
  try {
    const oldIndex = selectedShotIndex.value
    const oldPlayhead = playheadUs.value
    const updated = await action()
    shots.value = updated
    const nextSelected = updated.find((item) => item.id === preferredId)
      ?? updated.find((item) => oldPlayhead >= item.start_us && oldPlayhead < item.end_us)
      ?? updated[Math.max(0, Math.min(oldIndex, updated.length - 1))]
      ?? null
    manualSeekShotId.value = null
    applySelectedShot(nextSelected, false)
    revisions.value = selectedEpisodeId.value ? await api.listShotRevisions(selectedEpisodeId.value) : []
    emit('refreshProject')
  } catch (err) {
    error.value = err instanceof Error ? err.message : `${label}失败`
  } finally {
    busy.value = ''
  }
}

function playheadSourceUs(): number | null {
  const video = videoRef.value
  if (!video) return null
  return Math.max(0, Math.round(video.currentTime * 1_000_000))
}

function onVideoLoaded(): void {
  const shot = selectedShot.value
  if (!shot || !videoRef.value) return
  videoRef.value.currentTime = shot.start_us / 1_000_000
  playheadUs.value = shot.start_us
}

function onVideoTimeUpdate(): void {
  const sourceUs = playheadSourceUs()
  if (sourceUs === null) return
  playheadUs.value = sourceUs
  const video = videoRef.value
  if (video?.seeking || manualSeekShotId.value) return

  const current = shots.value.find((shot, index) => {
    if (index === shots.value.length - 1) return sourceUs >= shot.start_us && sourceUs <= shot.end_us
    return sourceUs >= shot.start_us && sourceUs < shot.end_us
  })
  if (current && current.id !== selectedShot.value?.id) applySelectedShot(current, false)
}

function onVideoSeeked(): void {
  const sourceUs = playheadSourceUs()
  if (sourceUs !== null) playheadUs.value = sourceUs
  const pendingId = manualSeekShotId.value
  if (pendingId) {
    const pendingShot = shots.value.find((shot) => shot.id === pendingId) ?? null
    if (pendingShot) applySelectedShot(pendingShot, false)
    manualSeekShotId.value = null
    return
  }
  onVideoTimeUpdate()
}

async function usePlayheadAsStart(): Promise<void> {
  const shot = selectedShot.value
  const sourceUs = playheadSourceUs()
  if (!shot || sourceUs === null) return
  await applyEdit('正在修改开始边界', () => api.adjustShotBoundary(shot.id, 'start', sourceUs), shot.id)
}

async function usePlayheadAsEnd(): Promise<void> {
  const shot = selectedShot.value
  const sourceUs = playheadSourceUs()
  if (!shot || sourceUs === null) return
  await applyEdit('正在修改结束边界', () => api.adjustShotBoundary(shot.id, 'end', sourceUs), shot.id)
}

async function saveTypedStart(): Promise<void> {
  const shot = selectedShot.value
  if (!shot) return
  await applyEdit('正在修改开始边界', () => api.adjustShotBoundary(shot.id, 'start', Math.round(startSeconds.value * 1_000_000)), shot.id)
}

async function saveTypedEnd(): Promise<void> {
  const shot = selectedShot.value
  if (!shot) return
  await applyEdit('正在修改结束边界', () => api.adjustShotBoundary(shot.id, 'end', Math.round(endSeconds.value * 1_000_000)), shot.id)
}

async function splitAtPlayhead(): Promise<void> {
  const shot = selectedShot.value
  const sourceUs = playheadSourceUs()
  if (!shot || sourceUs === null) return
  await applyEdit('正在拆分镜头', () => api.splitShot(shot.id, sourceUs), shot.id)
}

async function mergePrevious(): Promise<void> {
  const index = selectedShotIndex.value
  if (index <= 0) return
  const left = shots.value[index - 1]
  await applyEdit('正在合并上一镜', () => api.mergeShotWithNext(left.id), left.id)
}

async function mergeNext(): Promise<void> {
  const shot = selectedShot.value
  if (!shot || selectedShotIndex.value >= shots.value.length - 1) return
  await applyEdit('正在合并下一镜', () => api.mergeShotWithNext(shot.id), shot.id)
}

async function restoreRevision(revision: ShotRevision): Promise<void> {
  if (revision.is_current) return
  if (!window.confirm(`恢复 R${revision.revision}（${revisionKind(revision.kind)}）？系统会创建新的恢复版本，不覆盖历史。`)) return
  await applyEdit(`正在恢复 R${revision.revision}`, () => api.restoreShotRevision(revision.id))
  revisionOpen.value = false
}

watch(
  () => props.episodes.map((item) => `${item.id}:${item.shot_count}`).join('|'),
  async () => {
    if (!selectedEpisodeId.value && props.episodes.length) {
      await chooseEpisode(props.episodes[0].id)
      return
    }
    if (selectedEpisodeId.value) await loadEpisodeData(selectedEpisodeId.value)
  },
)

onMounted(async () => {
  if (props.episodes.length) await chooseEpisode(props.episodes[0].id)
})
</script>

<template>
  <section class="shot-manager-v5">
    <header class="shot-manager-toolbar">
      <div class="shot-manager-context">
        <label class="episode-picker">
          <span>当前剧集</span>
          <select :value="selectedEpisodeId" :disabled="!!busy || !episodes.length" @change="onEpisodeChange">
            <option v-for="episode in episodes" :key="episode.id" :value="episode.id">
              E{{ String(episode.sort_order).padStart(2, '0') }} · {{ episode.title }}
            </option>
          </select>
        </label>
        <div class="episode-summary" v-if="selectedEpisode">
          <strong>{{ shots.length }} 个镜头</strong>
          <span v-if="suspiciousShots.length" class="warning">{{ suspiciousShots.length }} 个建议检查</span>
          <span v-else class="ready">镜头边界正常</span>
        </div>
      </div>

      <div class="shot-manager-actions">
        <button class="plain" :disabled="!!busy || !selectedEpisode" @click="startSingle">
          {{ selectedEpisode?.shot_count ? '重新检测镜头' : '开始检测镜头' }}
        </button>
        <button v-if="episodes.length > 1" class="plain" :disabled="!!busy" @click="startBatch">顺序批量检测</button>
        <button v-if="revisions.length" class="plain" @click="revisionOpen = !revisionOpen">历史版本 {{ revisionOpen ? '▴' : '▾' }}</button>
      </div>
    </header>

    <p v-if="error" class="shot-manager-alert error">{{ error }}</p>
    <div v-if="busy" class="shot-manager-alert busy"><span></span>{{ busy }}…</div>

    <div v-if="revisionOpen" class="shot-history-panel">
      <div class="history-heading"><strong>历史版本</strong><span>恢复历史会创建新版本，不覆盖已有记录</span></div>
      <div class="history-list">
        <div v-for="revision in revisions" :key="revision.id" :class="['history-item', { current: revision.is_current }]">
          <div><b>R{{ revision.revision }}</b><span>{{ revisionKind(revision.kind) }}</span></div>
          <small>{{ revision.shot_count }} 个镜头 · {{ revision.note || '无备注' }}</small>
          <i>{{ revision.is_current ? '当前版本' : '历史版本' }}</i>
          <button v-if="!revision.is_current" :disabled="!!busy" @click="restoreRevision(revision)">恢复</button>
        </div>
      </div>
    </div>

    <div v-if="!selectedShot" class="shot-manager-empty">
      <strong>{{ selectedEpisode?.shot_count ? '没有可用镜头' : '当前剧集还没有检测镜头' }}</strong>
      <p>先完成镜头检测，再在这里检查和修正切点。</p>
      <button :disabled="!!busy || !selectedEpisode" @click="startSingle">开始检测镜头</button>
    </div>

    <div v-else class="shot-manager-workspace">
      <aside class="shot-list-panel">
        <header>
          <div><strong>镜头列表</strong><span>{{ shots.length }}</span></div>
          <small>选择镜头查看并修正</small>
        </header>
        <div class="shot-list-scroll">
          <button
            v-for="shot in shots"
            :key="shot.id"
            :class="['shot-list-row', { active: selectedShot.id === shot.id, warning: needsReview(shot) }]"
            @click="selectShot(shot)"
          >
            <div class="shot-list-thumb">
              <img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" alt="" />
              <span v-else>镜头</span>
            </div>
            <div class="shot-list-copy">
              <div><strong>镜头 {{ String(shot.ordinal).padStart(4, '0') }}</strong><i v-if="needsReview(shot)">检查</i></div>
              <span>{{ timecode(shot.start_us) }} → {{ timecode(shot.end_us) }}</span>
              <small>{{ seconds(shot.duration_us) }}</small>
            </div>
          </button>
        </div>
      </aside>

      <main class="shot-viewer-panel">
        <header class="shot-viewer-head">
          <div>
            <span>当前镜头</span>
            <strong>镜头 {{ String(selectedShot.ordinal).padStart(4, '0') }}</strong>
            <small>{{ timecode(selectedShot.start_us) }} → {{ timecode(selectedShot.end_us) }} · {{ seconds(selectedShot.duration_us) }}</small>
          </div>
          <div class="shot-nav-buttons">
            <button :disabled="!previousShot" @click="selectAdjacent(-1)">← 上一镜</button>
            <button :disabled="!nextShot" @click="selectAdjacent(1)">下一镜 →</button>
          </div>
        </header>

        <div class="shot-video-frame">
          <video
            ref="videoRef"
            :key="selectedEpisodeId"
            :src="episodeProxyUrl"
            controls
            preload="metadata"
            @loadedmetadata="onVideoLoaded"
            @timeupdate="onVideoTimeUpdate"
            @seeked="onVideoSeeked"
          ></video>
        </div>

        <div class="playhead-bar">
          <span>播放位置</span>
          <strong>{{ timecode(playheadUs) }}</strong>
          <small>拖动播放器到想要的切点，再使用右侧按钮修正。</small>
        </div>

        <section class="cut-compare-section">
          <header>
            <div><strong>切点对照</strong><span>只看当前镜尾帧和下一镜首帧，判断是否切对。</span></div>
            <b>{{ timecode(selectedShot.end_us) }}</b>
          </header>
          <div class="cut-compare-grid">
            <ShotFramePreviewV4
              :src="referenceUrl(selectedShot)"
              :at-us="frameLocalUs(selectedShot, 'end')"
              label="当前镜尾帧"
              :subtitle="`镜头 ${String(selectedShot.ordinal).padStart(4, '0')}`"
              @open="openFrame"
            />
            <div class="cut-divider"><span>切点</span><i></i></div>
            <ShotFramePreviewV4
              v-if="nextShot"
              :src="referenceUrl(nextShot)"
              :at-us="frameLocalUs(nextShot, 'start')"
              label="下一镜首帧"
              :subtitle="`镜头 ${String(nextShot.ordinal).padStart(4, '0')}`"
              @open="openFrame"
            />
            <div v-else class="video-end-card">视频结束</div>
          </div>
        </section>
      </main>

      <aside class="shot-boundary-panel">
        <header>
          <div><span>镜头边界</span><strong>修正切点</strong></div>
          <i :class="needsReview(selectedShot) ? 'warning' : 'ready'">{{ needsReview(selectedShot) ? '建议检查' : '正常' }}</i>
        </header>

        <div class="boundary-overview">
          <div><span>开始</span><strong>{{ timecode(selectedShot.start_us) }}</strong></div>
          <div><span>结束</span><strong>{{ timecode(selectedShot.end_us) }}</strong></div>
          <div><span>时长</span><strong>{{ seconds(selectedShot.duration_us) }}</strong></div>
        </div>

        <div class="boundary-field">
          <label>开始时间（秒）</label>
          <div><input v-model.number="startSeconds" type="number" step="0.001" min="0" /><button :disabled="selectedShotIndex <= 0 || !!busy" @click="saveTypedStart">保存</button></div>
        </div>
        <button class="boundary-action primary" :disabled="selectedShotIndex <= 0 || !!busy" @click="usePlayheadAsStart">使用当前播放位置作为开始</button>

        <div class="boundary-field">
          <label>结束时间（秒）</label>
          <div><input v-model.number="endSeconds" type="number" step="0.001" min="0" /><button :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="saveTypedEnd">保存</button></div>
        </div>
        <button class="boundary-action primary" :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="usePlayheadAsEnd">使用当前播放位置作为结束</button>

        <div class="boundary-separator"></div>

        <button class="boundary-action" :disabled="!!busy" @click="splitAtPlayhead">✂ 在当前播放位置拆分镜头</button>
        <div class="merge-actions">
          <button :disabled="selectedShotIndex <= 0 || !!busy" @click="mergePrevious">← 与上一镜合并</button>
          <button :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="mergeNext">与下一镜合并 →</button>
        </div>

        <div v-if="reviewReasons(selectedShot).length" class="review-notice">
          <strong>建议检查这个镜头</strong>
          <span v-for="reason in reviewReasons(selectedShot)" :key="reason">{{ reason }}</span>
        </div>

        <details class="technical-details">
          <summary>技术信息</summary>
          <div class="technical-grid">
            <div><span>边界可信度</span><strong>{{ confidencePercent(selectedShot) }}</strong></div>
            <div><span>TransNet</span><strong>{{ typeof selectedBoundaryMeta?.transnet_score === 'number' ? `${Math.round(selectedBoundaryMeta.transnet_score * 100)}%` : '—' }}</strong></div>
            <div><span>画面变化</span><strong>{{ typeof selectedBoundaryMeta?.visual_score === 'number' ? selectedBoundaryMeta.visual_score.toFixed(2) : '—' }}</strong></div>
            <div><span>辅助检测</span><strong>{{ selectedBoundaryMeta?.pyscenedetect_confirmed ? '确认' : selectedBoundaryMeta?.pyscenedetect_status === 'READY' ? '未确认' : '不可用' }}</strong></div>
            <div><span>当前版本</span><strong>{{ currentRevision ? `R${currentRevision.revision}` : '—' }}</strong></div>
            <div><span>来源</span><strong>{{ currentRevision ? revisionKind(currentRevision.kind) : '—' }}</strong></div>
          </div>
        </details>
      </aside>
    </div>

    <div v-if="lightboxSrc" class="shot-lightbox" @click.self="closeLightbox" @wheel="onLightboxWheel">
      <div class="shot-lightbox-head"><strong>{{ lightboxTitle }}</strong><span>{{ Math.round(lightboxScale * 100) }}%</span></div>
      <div class="shot-lightbox-stage" @click.self="closeLightbox"><img :src="lightboxSrc" :alt="lightboxTitle" :style="{ transform: `scale(${lightboxScale})` }" /></div>
      <div class="shot-lightbox-controls">
        <button @click="zoomLightbox(-0.25)">−</button><button @click="lightboxScale = 1">1:1</button><button @click="zoomLightbox(0.25)">+</button><button @click="closeLightbox">关闭</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.shot-manager-v5 {
  min-width: 0;
  display: grid;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 10px;
  color: #263650;
}
.shot-manager-v5 button,
.shot-manager-v5 input,
.shot-manager-v5 select { font: inherit; }
.shot-manager-toolbar {
  min-width: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 14px;
  border: 1px solid #dfe5ef;
  border-radius: 12px;
  padding: 10px 12px;
  background: #fff;
  box-shadow: 0 5px 18px rgba(42, 59, 90, .035);
}
.shot-manager-context { min-width: 0; display: flex; align-items: center; gap: 12px; }
.episode-picker { min-width: 320px; display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 4px 8px; align-items: center; }
.episode-picker > span { grid-column: 1 / -1; color: #8591a4; font-size: 10px; font-weight: 800; }
.episode-picker select { width: 100%; min-width: 0; height: 36px; border: 1px solid #d7e0ed; border-radius: 8px; padding: 0 9px; background: #f9fbfe; color: #344761; font-size: 12px; font-weight: 750; outline: none; }
.episode-summary { display: flex; gap: 7px; align-items: center; flex-wrap: wrap; }
.episode-summary strong { font-size: 12px; color: #364966; white-space: nowrap; }
.episode-summary span { border-radius: 999px; padding: 4px 7px; font-size: 10px; font-weight: 800; white-space: nowrap; }
.episode-summary .ready { background: #e9f7ef; color: #188055; }
.episode-summary .warning { background: #fff3db; color: #9b680d; }
.shot-manager-actions { flex: none; display: flex; gap: 7px; align-items: center; }
.shot-manager-actions button,
.shot-nav-buttons button,
.boundary-field button,
.boundary-action,
.merge-actions button,
.history-item button,
.shot-manager-empty button {
  min-height: 36px;
  border: 1px solid #d4deeb;
  border-radius: 8px;
  padding: 0 11px;
  background: #fff;
  color: #4b5d78;
  cursor: pointer;
  font-size: 11px;
  font-weight: 800;
}
.shot-manager-v5 button:hover:not(:disabled) { border-color: #8faeea; background: #f7faff; }
.shot-manager-v5 button:disabled { opacity: .42; cursor: not-allowed; }
.shot-manager-alert { margin: 0; border-radius: 10px; padding: 9px 12px; font-size: 11px; font-weight: 750; }
.shot-manager-alert.error { border: 1px solid #ffd1d1; background: #fff1f1; color: #a63d3d; }
.shot-manager-alert.busy { display: flex; gap: 8px; align-items: center; border: 1px solid #cfdcff; background: #eef4ff; color: #31559d; }
.shot-manager-alert.busy > span { width: 12px; height: 12px; border: 2px solid #aec1f7; border-top-color: #2d62e8; border-radius: 50%; animation: shot-spin .8s linear infinite; }
@keyframes shot-spin { to { transform: rotate(360deg); } }
.shot-history-panel { border: 1px solid #dfe5ef; border-radius: 12px; background: #fff; overflow: hidden; }
.history-heading { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px 12px; border-bottom: 1px solid #edf0f5; }
.history-heading strong { font-size: 12px; }
.history-heading span { color: #8591a3; font-size: 10px; }
.history-list { max-height: 220px; overflow: auto; }
.history-item { display: grid; grid-template-columns: 120px minmax(0, 1fr) auto auto; gap: 9px; align-items: center; padding: 9px 12px; border-bottom: 1px solid #f0f2f6; }
.history-item.current { background: #f5f8ff; }
.history-item > div { display: flex; gap: 6px; align-items: baseline; }
.history-item b { font-size: 12px; }
.history-item span,
.history-item small,
.history-item i { color: #7f8b9d; font-size: 10px; font-style: normal; }
.history-item button { min-height: 28px; padding: 0 8px; font-size: 10px; }
.shot-manager-empty { min-height: 520px; display: grid; place-content: center; justify-items: center; gap: 8px; border: 1px dashed #d8e0ec; border-radius: 14px; background: #fbfcfe; text-align: center; }
.shot-manager-empty strong { font-size: 16px; color: #3b4c66; }
.shot-manager-empty p { margin: 0; color: #8390a4; font-size: 12px; }
.shot-manager-empty button { margin-top: 6px; border-color: #4f7ee0; background: #4f7ee0; color: #fff; }
.shot-manager-workspace {
  min-height: 620px;
  height: calc(100vh - 210px);
  max-height: 820px;
  display: grid;
  grid-template-columns: 235px minmax(520px, 1fr) 300px;
  gap: 10px;
}
.shot-list-panel,
.shot-viewer-panel,
.shot-boundary-panel { min-width: 0; min-height: 0; border: 1px solid #dfe5ef; border-radius: 14px; background: #fff; box-shadow: 0 8px 26px rgba(37, 52, 82, .035); overflow: hidden; }
.shot-list-panel { display: grid; grid-template-rows: auto minmax(0, 1fr); }
.shot-list-panel > header { padding: 12px; border-bottom: 1px solid #edf0f5; }
.shot-list-panel > header > div { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.shot-list-panel > header strong { font-size: 13px; }
.shot-list-panel > header span { border-radius: 999px; padding: 2px 6px; background: #eef2f7; color: #718098; font-size: 10px; }
.shot-list-panel > header small { display: block; margin-top: 2px; color: #8a96a8; font-size: 10px; }
.shot-list-scroll { min-height: 0; overflow-y: auto; padding: 7px; scrollbar-width: thin; }
.shot-list-row { width: 100%; min-width: 0; display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 8px; align-items: center; border: 1px solid transparent; border-radius: 9px; padding: 6px; background: transparent; color: #405069; cursor: pointer; text-align: left; }
.shot-list-row + .shot-list-row { margin-top: 3px; }
.shot-list-row:hover { background: #f8faff; }
.shot-list-row.active { border-color: #b8ccfb; background: #eef4ff; box-shadow: inset 3px 0 0 #4f7ee0; }
.shot-list-row.warning:not(.active) { border-right-color: #efbd61; }
.shot-list-thumb { height: 46px; overflow: hidden; border-radius: 6px; background: #111720; }
.shot-list-thumb img { width: 100%; height: 100%; display: block; object-fit: cover; }
.shot-list-thumb span { height: 100%; display: grid; place-items: center; color: #b1bbc8; font-size: 10px; }
.shot-list-copy { min-width: 0; display: grid; gap: 2px; }
.shot-list-copy > div { min-width: 0; display: flex; justify-content: space-between; gap: 5px; align-items: center; }
.shot-list-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.shot-list-copy i { flex: none; border-radius: 999px; padding: 2px 5px; background: #fff1d4; color: #9a650c; font-size: 8px; font-style: normal; font-weight: 850; }
.shot-list-copy span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #78869a; font-size: 9px; font-variant-numeric: tabular-nums; }
.shot-list-copy small { color: #5f708a; font-size: 9px; }
.shot-viewer-panel { display: grid; grid-template-rows: auto minmax(300px, 1fr) auto auto; }
.shot-viewer-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; padding: 11px 13px; border-bottom: 1px solid #edf0f5; }
.shot-viewer-head > div:first-child { min-width: 0; display: flex; flex-wrap: wrap; gap: 6px 8px; align-items: center; }
.shot-viewer-head span { color: #8592a5; font-size: 10px; font-weight: 800; }
.shot-viewer-head strong { color: #2e425f; font-size: 14px; }
.shot-viewer-head small { color: #728096; font-size: 10px; font-variant-numeric: tabular-nums; }
.shot-nav-buttons { flex: none; display: flex; gap: 6px; }
.shot-nav-buttons button { min-height: 32px; padding: 0 9px; font-size: 10px; }
.shot-video-frame { min-height: 0; display: grid; place-items: center; margin: 10px 10px 0; overflow: hidden; border-radius: 10px; background: #0b1017; }
.shot-video-frame video { width: 100%; height: 100%; min-height: 0; display: block; object-fit: contain; background: #070b10; }
.playhead-bar { display: grid; grid-template-columns: auto auto minmax(0, 1fr); gap: 7px; align-items: center; margin: 0 10px; padding: 8px 10px; border-radius: 0 0 9px 9px; background: #f5f7fa; }
.playhead-bar span { color: #7e8b9f; font-size: 10px; }
.playhead-bar strong { color: #314866; font-size: 11px; font-variant-numeric: tabular-nums; }
.playhead-bar small { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #8a96a8; font-size: 9px; }
.cut-compare-section { margin: 10px; border: 1px solid #e3e8f0; border-radius: 10px; overflow: hidden; }
.cut-compare-section > header { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 8px 10px; background: #fbfcfe; border-bottom: 1px solid #edf0f5; }
.cut-compare-section > header > div { display: flex; gap: 7px; align-items: baseline; }
.cut-compare-section > header strong { font-size: 11px; }
.cut-compare-section > header span { color: #8995a7; font-size: 9px; }
.cut-compare-section > header b { color: #55709b; font-size: 10px; font-variant-numeric: tabular-nums; }
.cut-compare-grid { display: grid; grid-template-columns: minmax(0, 1fr) 54px minmax(0, 1fr); gap: 8px; align-items: center; padding: 9px; }
.cut-divider { display: grid; justify-items: center; gap: 5px; color: #c45c42; }
.cut-divider span { font-size: 9px; font-weight: 900; }
.cut-divider i { width: 1px; height: 64px; background: #e0a393; }
.video-end-card { min-height: 118px; display: grid; place-items: center; border: 1px dashed #d7deea; border-radius: 9px; color: #8b96a6; font-size: 10px; }
.shot-boundary-panel { padding: 13px; overflow-y: auto; scrollbar-width: thin; }
.shot-boundary-panel > header { display: flex; justify-content: space-between; gap: 10px; align-items: center; margin-bottom: 11px; }
.shot-boundary-panel > header > div { display: grid; gap: 1px; }
.shot-boundary-panel > header span { color: #8491a4; font-size: 10px; font-weight: 800; }
.shot-boundary-panel > header strong { font-size: 14px; color: #30445f; }
.shot-boundary-panel > header i { border-radius: 999px; padding: 4px 7px; font-size: 9px; font-style: normal; font-weight: 850; }
.shot-boundary-panel > header i.ready { background: #e7f7ee; color: #178153; }
.shot-boundary-panel > header i.warning { background: #fff2d7; color: #9e680b; }
.boundary-overview { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }
.boundary-overview > div { min-width: 0; display: grid; gap: 2px; border: 1px solid #e4e9f1; border-radius: 8px; padding: 8px; background: #fafbfd; }
.boundary-overview > div:last-child { grid-column: 1 / -1; grid-template-columns: auto auto; justify-content: space-between; align-items: center; }
.boundary-overview span { color: #8390a3; font-size: 9px; }
.boundary-overview strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #334861; font-size: 11px; font-variant-numeric: tabular-nums; }
.boundary-field { display: grid; gap: 5px; margin-top: 10px; }
.boundary-field label { color: #5f6e84; font-size: 10px; font-weight: 800; }
.boundary-field > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 6px; }
.boundary-field input { width: 100%; min-width: 0; height: 36px; box-sizing: border-box; border: 1px solid #d7e0ec; border-radius: 8px; padding: 0 9px; outline: none; color: #2d405a; font-size: 11px; font-weight: 800; font-variant-numeric: tabular-nums; }
.boundary-field input:focus { border-color: #7fa0e5; box-shadow: 0 0 0 3px rgba(79, 126, 224, .08); }
.boundary-field button { min-height: 36px; padding: 0 9px; font-size: 10px; }
.boundary-action { width: 100%; margin-top: 7px; min-height: 38px; }
.boundary-action.primary { border-color: #4f7ee0; background: #4f7ee0; color: #fff; }
.boundary-action.primary:hover:not(:disabled) { background: #416fce; color: #fff; }
.boundary-separator { height: 1px; margin: 13px 0 3px; background: #edf0f5; }
.merge-actions { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 7px; }
.merge-actions button { min-width: 0; padding: 0 6px; font-size: 9px; }
.review-notice { display: grid; gap: 4px; margin-top: 12px; border: 1px solid #f0d5a4; border-radius: 9px; padding: 9px; background: #fff9ee; }
.review-notice strong { color: #865a12; font-size: 10px; }
.review-notice span { color: #986b22; font-size: 9px; line-height: 1.4; }
.technical-details { margin-top: 12px; border-top: 1px solid #edf0f5; padding-top: 9px; }
.technical-details summary { color: #7c899d; font-size: 10px; font-weight: 800; cursor: pointer; }
.technical-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: 8px; }
.technical-grid > div { display: grid; gap: 2px; border-radius: 7px; padding: 7px; background: #f6f8fb; }
.technical-grid span { color: #8a95a6; font-size: 8px; }
.technical-grid strong { color: #536279; font-size: 9px; }
.shot-lightbox { position: fixed; z-index: 1000; inset: 0; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; background: rgba(6, 10, 18, .92); color: #fff; }
.shot-lightbox-head { display: flex; justify-content: space-between; padding: 14px 18px; font-size: 13px; }
.shot-lightbox-stage { min-height: 0; display: grid; place-items: center; overflow: auto; padding: 20px; }
.shot-lightbox-stage img { max-width: 88vw; max-height: 78vh; transform-origin: center center; transition: transform .12s ease; box-shadow: 0 15px 60px rgba(0,0,0,.45); }
.shot-lightbox-controls { display: flex; justify-content: center; gap: 8px; padding: 12px 18px 18px; }
.shot-lightbox-controls button { min-width: 54px; min-height: 34px; border: 1px solid #5d6675; border-radius: 8px; background: #171d27; color: #fff; cursor: pointer; }
@media (max-width: 1320px) {
  .shot-manager-workspace { grid-template-columns: 205px minmax(460px, 1fr) 270px; }
  .episode-picker { min-width: 260px; }
}
@media (max-width: 1040px) {
  .shot-manager-toolbar { align-items: stretch; flex-direction: column; }
  .shot-manager-actions { flex-wrap: wrap; }
  .shot-manager-workspace { height: auto; max-height: none; grid-template-columns: 210px minmax(0, 1fr); }
  .shot-boundary-panel { grid-column: 2; max-height: none; }
}
@media (max-width: 720px) {
  .shot-manager-context { align-items: stretch; flex-direction: column; }
  .episode-picker { min-width: 0; width: 100%; }
  .shot-manager-actions { display: grid; grid-template-columns: 1fr 1fr; }
  .shot-manager-workspace { grid-template-columns: 1fr; }
  .shot-list-panel { max-height: 360px; }
  .shot-boundary-panel { grid-column: 1; }
  .cut-compare-grid { grid-template-columns: 1fr; }
  .cut-divider { grid-template-columns: auto 1fr; align-items: center; }
  .cut-divider i { width: 100%; height: 1px; }
}
</style>
