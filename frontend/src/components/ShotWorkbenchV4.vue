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
const nextShot = computed(() => {
  const index = selectedShotIndex.value
  return index >= 0 && index < shots.value.length - 1 ? shots.value[index + 1] : null
})
const currentRevision = computed(() => revisions.value.find((item) => item.is_current) ?? null)
const finishedEpisodes = computed(() => props.episodes.filter((item) => item.shot_count > 0).length)
const pendingEpisodes = computed(() => Math.max(0, props.episodes.length - finishedEpisodes.value))
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
  if (shot.duration_us < 500_000 && !reasons.some((item) => item.includes('极短'))) reasons.push('极短 Shot（< 500ms）')
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
  if (typeof value !== 'number') return shot.status === 'MANUAL' ? '人工' : '—'
  return `${Math.round(value * 100)}%`
}

function confidenceClass(shot: Shot): 'ready' | 'warning' {
  return needsReview(shot) ? 'warning' : 'ready'
}

function seconds(us: number | null | undefined): string {
  if (us === null || us === undefined) return '—'
  return `${(us / 1_000_000).toFixed(2)}s`
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
    AUTO: '自动拉片',
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

async function startSingle(): Promise<void> {
  const episode = selectedEpisode.value
  if (!episode) return
  busy.value = episode.shot_count ? '正在启动 V4 重新自动拉片' : '正在启动 V4 拉片'
  error.value = ''
  try {
    await api.startEpisodeShotsTask(episode.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '启动拉片失败'
  } finally {
    busy.value = ''
  }
}

async function startBatch(): Promise<void> {
  busy.value = '正在启动 V4 顺序批量拉片'
  error.value = ''
  try {
    await api.startBatchShotsTask(props.projectId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '启动批量拉片失败'
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
  if (!window.confirm(`恢复 R${revision.revision}（${revisionKind(revision.kind)}）？系统会创建一个新的恢复版本，不覆盖历史。`)) return
  await applyEdit(`正在恢复 R${revision.revision}`, () => api.restoreShotRevision(revision.id))
  revisionOpen.value = false
}

function episodeStatus(episode: Episode): 'ready' | 'warning' | 'pending' {
  if (!episode.shot_count) return 'pending'
  if (episode.id === selectedEpisodeId.value && suspiciousShots.value.length) return 'warning'
  return 'ready'
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
  <section class="shot-v3 shot-v4">
    <header class="shot-v3-header">
      <div class="shot-v3-title">
        <h1>拉片</h1>
        <div class="shot-v3-stats">
          <span>{{ episodes.length }} 集</span><i>·</i>
          <span>{{ episodes.reduce((sum, item) => sum + item.shot_count, 0) }} Shots</span><i>·</i>
          <span>{{ finishedEpisodes }} 已完成</span><i>·</i>
          <span v-if="pendingEpisodes">{{ pendingEpisodes }} 待拉片</span><i v-if="pendingEpisodes">·</i>
          <span :class="{ warning: suspiciousShots.length > 0 }">{{ suspiciousShots.length }} 待检查</span>
        </div>
      </div>
      <div class="shot-v3-header-actions">
        <span class="shot-v4-engine">V4 · Source PTS 精修</span>
        <button class="shot-v3-secondary" :disabled="!!busy || !selectedEpisode" @click="startSingle">
          {{ selectedEpisode?.shot_count ? '重新自动拉片' : episodes.length === 1 ? '开始拉片' : '拉片当前集' }}
        </button>
        <button v-if="episodes.length > 1" class="shot-v3-primary" :disabled="!!busy || !episodes.length" @click="startBatch">▶ 顺序批量拉片</button>
      </div>
    </header>

    <p v-if="error" class="shot-v3-error">{{ error }}</p>
    <div v-if="busy" class="shot-v3-busy"><span></span>{{ busy }}…</div>

    <div class="shot-v3-layout">
      <aside class="shot-v3-episodes">
        <div class="shot-v3-panel-title"><strong>剧集列表</strong><span>{{ episodes.length }}</span></div>
        <div class="shot-v3-episode-list">
          <button v-for="episode in episodes" :key="episode.id" :class="['shot-v3-episode', { active: episode.id === selectedEpisodeId }]" @click="chooseEpisode(episode.id)">
            <span class="episode-code">E{{ String(episode.sort_order).padStart(2, '0') }}</span>
            <span class="episode-count">{{ episode.shot_count ? `${episode.shot_count} Shots` : '待拉片' }}</span>
            <span :class="['episode-state', episodeStatus(episode)]">{{ episodeStatus(episode) === 'ready' ? '✓' : episodeStatus(episode) === 'warning' ? '!' : '○' }}</span>
          </button>
        </div>
        <div class="shot-v3-legend"><span><i class="ready"></i>完成</span><span><i class="warning"></i>待检查</span><span><i class="pending"></i>待处理</span></div>
      </aside>

      <main class="shot-v3-center">
        <div class="shot-v3-episode-head">
          <div>
            <strong>{{ selectedEpisode?.title || '请选择剧集' }}</strong>
            <span v-if="selectedEpisode">{{ shots.length }} Shots</span>
            <span v-if="currentRevision">Current R{{ currentRevision.revision }}</span>
            <span v-if="currentRevision">{{ revisionKind(currentRevision.kind) }}</span>
          </div>
          <button v-if="revisions.length" class="shot-v3-history-button" @click="revisionOpen = !revisionOpen">版本历史 {{ revisionOpen ? '▴' : '▾' }}</button>
        </div>

        <div v-if="revisionOpen" class="shot-v3-history-popover">
          <div class="history-title"><strong>版本历史</strong><span>恢复会创建新 Revision</span></div>
          <div v-for="revision in revisions" :key="revision.id" :class="['history-row', { current: revision.is_current }]">
            <b>R{{ revision.revision }}</b>
            <div><strong>{{ revisionKind(revision.kind) }}</strong><small>{{ revision.shot_count }} Shots · {{ revision.note || '—' }}</small></div>
            <span>{{ revision.is_current ? 'CURRENT' : 'HISTORY' }}</span>
            <button v-if="!revision.is_current" @click="restoreRevision(revision)">恢复</button>
          </div>
        </div>

        <div v-if="!selectedShot" class="shot-v3-empty">
          <strong>{{ selectedEpisode?.shot_count ? '没有可用 Shot' : '当前剧集还没有拉片' }}</strong>
          <span>V4 会自动完成 TransNet 候选、PySceneDetect 辅助和原片帧级边界精修。</span>
          <button class="shot-v3-primary" :disabled="!!busy || !selectedEpisode" @click="startSingle">▶ 开始当前剧集拉片</button>
        </div>

        <template v-else>
          <div class="shot-v3-player">
            <video ref="videoRef" :key="selectedEpisodeId" :src="episodeProxyUrl" controls preload="metadata" @loadedmetadata="onVideoLoaded" @timeupdate="onVideoTimeUpdate" @seeked="onVideoSeeked"></video>
            <div class="shot-v3-player-meta">
              <span>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</span>
              <span>播放头 {{ timecode(playheadUs) }} · 当前 Shot {{ timecode(selectedShot.start_us) }} → {{ timecode(selectedShot.end_us) }}</span>
            </div>
          </div>

          <div class="shot-v3-filmstrip-head">
            <div><strong>Shots 列表</strong><span>（{{ shots.length }}）</span></div>
            <div class="shot-v3-filmstrip-summary">
              <span v-if="suspiciousShots.length" class="warning">⚠ {{ suspiciousShots.length }} 个边界待检查</span>
              <span v-else class="ready">✓ 当前集边界均为高可信</span>
            </div>
          </div>

          <div class="shot-v3-filmstrip">
            <button v-for="shot in shots" :key="shot.id" :class="['shot-v3-card', { active: selectedShot.id === shot.id, warning: needsReview(shot) }]" @click="selectShot(shot)">
              <div class="shot-v3-thumb">
                <img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" alt="" />
                <span v-else>SHOT</span>
                <i v-if="needsReview(shot)">!</i>
              </div>
              <strong>{{ String(shot.ordinal).padStart(4, '0') }}</strong>
              <small>{{ timecode(shot.start_us) }}</small>
              <small>{{ timecode(shot.end_us) }}</small>
              <div class="shot-v3-card-foot"><span>{{ seconds(shot.duration_us) }}</span><i :class="confidenceClass(shot)">{{ confidencePercent(shot) }}</i></div>
            </button>
          </div>
        </template>
      </main>

      <aside v-if="selectedShot" class="shot-v3-inspector shot-v4-inspector">
        <div class="shot-v3-inspector-title">
          <strong>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</strong>
          <span :class="confidenceClass(selectedShot)">{{ needsReview(selectedShot) ? '待检查' : '边界正常' }}</span>
        </div>

        <section class="shot-v4-quality">
          <div><span>边界置信度</span><strong>{{ confidencePercent(selectedShot) }}</strong></div>
          <div><span>TransNet</span><strong>{{ typeof selectedBoundaryMeta?.transnet_score === 'number' ? `${Math.round(selectedBoundaryMeta.transnet_score * 100)}%` : '—' }}</strong></div>
          <div><span>原片帧差</span><strong>{{ typeof selectedBoundaryMeta?.visual_score === 'number' ? selectedBoundaryMeta.visual_score.toFixed(2) : '—' }}</strong></div>
          <div><span>PySceneDetect</span><strong>{{ selectedBoundaryMeta?.pyscenedetect_confirmed ? '确认' : selectedBoundaryMeta?.pyscenedetect_status === 'READY' ? '未确认' : '不可用' }}</strong></div>
        </section>

        <section class="shot-v4-review-block">
          <div class="shot-v4-section-title"><strong>镜头检查帧</strong><span>IN / MID / OUT 均来自当前 Reference Clip</span></div>
          <div class="shot-v4-triple">
            <ShotFramePreviewV4 :src="referenceUrl(selectedShot)" :at-us="frameLocalUs(selectedShot, 'start')" label="IN 首帧" :subtitle="timecode(selectedShot.start_us)" @open="openFrame" />
            <ShotFramePreviewV4 :src="referenceUrl(selectedShot)" :at-us="frameLocalUs(selectedShot, 'middle')" label="MID 中间帧" @open="openFrame" />
            <ShotFramePreviewV4 :src="referenceUrl(selectedShot)" :at-us="frameLocalUs(selectedShot, 'end')" label="OUT 尾帧" :subtitle="`< ${timecode(selectedShot.end_us)}`" @open="openFrame" />
          </div>
        </section>

        <section class="shot-v4-review-block">
          <div class="shot-v4-section-title"><strong>Cut 边界对照</strong><span>[start, end) · OUT 必须属于当前镜，NEXT IN 必须属于下一镜</span></div>
          <div class="shot-v4-cut-pair">
            <ShotFramePreviewV4 :src="referenceUrl(selectedShot)" :at-us="frameLocalUs(selectedShot, 'end')" label="当前 OUT" :subtitle="`SHOT ${String(selectedShot.ordinal).padStart(4, '0')}`" @open="openFrame" />
            <div class="shot-v4-cut-mark"><span>CUT</span><b>{{ timecode(selectedShot.end_us) }}</b></div>
            <ShotFramePreviewV4 v-if="nextShot" :src="referenceUrl(nextShot)" :at-us="frameLocalUs(nextShot, 'start')" label="下一镜 IN" :subtitle="`SHOT ${String(nextShot.ordinal).padStart(4, '0')}`" @open="openFrame" />
            <div v-else class="shot-v4-video-end">视频结束</div>
          </div>
        </section>

        <div v-if="reviewReasons(selectedShot).length" class="shot-v4-reasons">
          <strong>为什么需要检查</strong>
          <ul><li v-for="reason in reviewReasons(selectedShot)" :key="reason">{{ reason }}</li></ul>
        </div>

        <div class="shot-v3-field"><label>开始时间（In）</label><div><input v-model.number="startSeconds" type="number" step="0.001" min="0" /><button :disabled="selectedShotIndex <= 0 || !!busy" @click="saveTypedStart">保存</button></div></div>
        <div class="shot-v3-field"><label>结束时间（Out / 下一镜 In）</label><div><input v-model.number="endSeconds" type="number" step="0.001" min="0" /><button :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="saveTypedEnd">保存</button></div></div>
        <div class="shot-v3-duration"><span>持续时长</span><strong>{{ seconds(selectedShot.duration_us) }}</strong></div>

        <button class="shot-v3-primary wide" :disabled="selectedShotIndex <= 0 || !!busy" @click="usePlayheadAsStart">◀ 使用当前播放头设为开始</button>
        <button class="shot-v3-primary wide" :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="usePlayheadAsEnd">▶ 使用当前播放头设为结束</button>
        <button class="shot-v3-secondary wide" :disabled="!!busy" @click="splitAtPlayhead">✂ 在播放头拆分</button>
        <div class="shot-v3-merge-row">
          <button :disabled="selectedShotIndex <= 0 || !!busy" @click="mergePrevious">← 合并上一镜</button>
          <button :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="mergeNext">合并下一镜 →</button>
        </div>
        <div class="shot-v3-note"><span>ⓘ</span><p><strong>V4 边界定义： [start_us, end_us)</strong>end_us 是下一镜第一帧 Source PTS，不属于当前 Shot。修改 Shot 后旧资产自动标记 STALE。</p></div>
      </aside>
    </div>

    <div v-if="lightboxSrc" class="shot-v4-lightbox" @click.self="closeLightbox" @wheel="onLightboxWheel">
      <div class="shot-v4-lightbox-head"><strong>{{ lightboxTitle }}</strong><span>{{ Math.round(lightboxScale * 100) }}%</span></div>
      <div class="shot-v4-lightbox-stage" @click.self="closeLightbox"><img :src="lightboxSrc" :alt="lightboxTitle" :style="{ transform: `scale(${lightboxScale})` }" /></div>
      <div class="shot-v4-lightbox-controls">
        <button @click="zoomLightbox(-0.25)">−</button><button @click="lightboxScale = 1">1:1</button><button @click="zoomLightbox(0.25)">+</button><button @click="closeLightbox">关闭</button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.shot-v4-engine { border: 1px solid #ccdafb; border-radius: 999px; padding: 5px 9px; background: #f2f6ff; color: #315ba9; font-size: 10px; font-weight: 850; white-space: nowrap; }
.shot-v4-inspector { width: auto; }
.shot-v4-quality { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-bottom: 12px; }
.shot-v4-quality > div { display: grid; gap: 2px; border: 1px solid #e3e8f0; border-radius: 8px; padding: 7px 8px; background: #fbfcfe; }
.shot-v4-quality span { color: #7a8596; font-size: 9px; }
.shot-v4-quality strong { color: #263247; font-size: 11px; }
.shot-v4-review-block { display: grid; gap: 7px; margin: 13px 0; }
.shot-v4-section-title { display: grid; gap: 2px; }
.shot-v4-section-title strong { font-size: 11px; color: #344055; }
.shot-v4-section-title span { color: #7a8596; font-size: 9px; line-height: 1.35; }
.shot-v4-triple { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 5px; }
.shot-v4-cut-pair { display: grid; grid-template-columns: minmax(0, 1fr) 42px minmax(0, 1fr); gap: 5px; align-items: center; }
.shot-v4-cut-mark { display: grid; justify-items: center; gap: 2px; color: #d05b40; }
.shot-v4-cut-mark span { font-size: 9px; font-weight: 950; }
.shot-v4-cut-mark b { font-size: 8px; font-weight: 800; writing-mode: vertical-rl; }
.shot-v4-video-end { min-height: 90px; display: grid; place-items: center; border: 1px dashed #d8deea; border-radius: 9px; color: #8d97a7; font-size: 10px; }
.shot-v4-reasons { margin: 10px 0; border: 1px solid #f3d6a4; border-radius: 9px; padding: 9px 10px; background: #fff9ed; color: #8a5b0d; }
.shot-v4-reasons strong { font-size: 10px; }
.shot-v4-reasons ul { margin: 5px 0 0; padding-left: 17px; }
.shot-v4-reasons li { margin: 2px 0; font-size: 9px; line-height: 1.4; }
.shot-v4-lightbox { position: fixed; z-index: 1000; inset: 0; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; background: rgba(6, 10, 18, .92); color: #fff; }
.shot-v4-lightbox-head { display: flex; justify-content: space-between; padding: 14px 18px; font-size: 13px; }
.shot-v4-lightbox-stage { min-height: 0; display: grid; place-items: center; overflow: auto; padding: 20px; }
.shot-v4-lightbox-stage img { max-width: 88vw; max-height: 78vh; transform-origin: center center; transition: transform .12s ease; box-shadow: 0 15px 60px rgba(0,0,0,.45); }
.shot-v4-lightbox-controls { display: flex; justify-content: center; gap: 8px; padding: 12px 18px 18px; }
.shot-v4-lightbox-controls button { min-width: 54px; min-height: 34px; border: 1px solid #5d6675; border-radius: 8px; background: #171d27; color: #fff; cursor: pointer; }
@media (max-width: 1500px) { .shot-v4-triple { grid-template-columns: 1fr; } .shot-v4-cut-pair { grid-template-columns: 1fr 32px 1fr; } }
</style>
