<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type { Episode, Shot, ShotRevision } from '../types/studio'

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
const startSeconds = ref(0)
const endSeconds = ref(0)

const selectedEpisode = computed(() => props.episodes.find((item) => item.id === selectedEpisodeId.value) ?? null)
const selectedShotIndex = computed(() => selectedShot.value ? shots.value.findIndex((item) => item.id === selectedShot.value?.id) : -1)
const suspiciousShots = computed(() => shots.value.filter((shot) => shot.duration_us < 500_000))
const currentRevision = computed(() => revisions.value.find((item) => item.is_current) ?? null)
const finishedEpisodes = computed(() => props.episodes.filter((item) => item.shot_count > 0).length)

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

function shotMediaUrl(shot: Shot): string {
  return `${shot.reference_url}?v=${shot.start_us}-${shot.end_us}`
}

function selectShot(shot: Shot | null): void {
  selectedShot.value = shot
  if (!shot) return
  startSeconds.value = shot.start_us / 1_000_000
  endSeconds.value = shot.end_us / 1_000_000
}

async function loadEpisodeData(episodeId: string): Promise<void> {
  if (!episodeId) {
    shots.value = []
    revisions.value = []
    selectShot(null)
    return
  }
  const previousId = selectedShot.value?.id
  const [nextShots, nextRevisions] = await Promise.all([
    api.listShots(episodeId),
    api.listShotRevisions(episodeId),
  ])
  shots.value = nextShots
  revisions.value = nextRevisions
  selectShot(nextShots.find((shot) => shot.id === previousId) ?? nextShots[0] ?? null)
}

async function chooseEpisode(episodeId: string): Promise<void> {
  selectedEpisodeId.value = episodeId
  revisionOpen.value = false
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
  busy.value = episode.shot_count ? '正在启动重新自动拉片' : '正在启动拉片'
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
  busy.value = '正在启动顺序批量拉片'
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
    const updated = await action()
    shots.value = updated
    selectShot(updated.find((item) => item.id === preferredId) ?? updated[Math.max(0, Math.min(oldIndex, updated.length - 1))] ?? null)
    revisions.value = selectedEpisodeId.value ? await api.listShotRevisions(selectedEpisodeId.value) : []
    emit('refreshProject')
  } catch (err) {
    error.value = err instanceof Error ? err.message : `${label}失败`
  } finally {
    busy.value = ''
  }
}

/**
 * 职责：把当前 Reference Clip 播放头换算回 Source Domain 时间。
 * 输入：当前 Shot + video.currentTime；输出：Source 微秒。
 * 为什么：用户应该直接停在画面上设 Cut，不应该手算绝对时间。
 */
function playheadSourceUs(): number | null {
  const shot = selectedShot.value
  const video = videoRef.value
  if (!shot || !video) return null
  return shot.start_us + Math.round(video.currentTime * 1_000_000)
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
  <section class="shot-v3">
    <header class="shot-v3-header">
      <div class="shot-v3-title">
        <h1>拉片</h1>
        <div class="shot-v3-stats">
          <span>{{ episodes.length }} 集</span>
          <i>·</i>
          <span>{{ episodes.reduce((sum, item) => sum + item.shot_count, 0) }} Shots</span>
          <i>·</i>
          <span>{{ finishedEpisodes }} 已完成</span>
          <i>·</i>
          <span :class="{ warning: suspiciousShots.length > 0 }">{{ suspiciousShots.length }} 待检查</span>
        </div>
      </div>
      <div class="shot-v3-header-actions">
        <button class="shot-v3-secondary" :disabled="!!busy || !selectedEpisode" @click="startSingle">
          {{ selectedEpisode?.shot_count ? '重新自动拉片' : '单集拉片' }}
        </button>
        <button class="shot-v3-primary" :disabled="!!busy || !episodes.length" @click="startBatch">▶ 顺序批量拉片</button>
      </div>
    </header>

    <p v-if="error" class="shot-v3-error">{{ error }}</p>
    <div v-if="busy" class="shot-v3-busy"><span></span>{{ busy }}…</div>

    <div class="shot-v3-layout">
      <aside class="shot-v3-episodes">
        <div class="shot-v3-panel-title"><strong>剧集列表</strong><span>{{ episodes.length }}</span></div>
        <div class="shot-v3-episode-list">
          <button
            v-for="episode in episodes"
            :key="episode.id"
            :class="['shot-v3-episode', { active: episode.id === selectedEpisodeId }]"
            @click="chooseEpisode(episode.id)"
          >
            <span class="episode-code">E{{ String(episode.sort_order).padStart(2, '0') }}</span>
            <span class="episode-count">{{ episode.shot_count }} Shots</span>
            <span :class="['episode-state', episodeStatus(episode)]">
              {{ episodeStatus(episode) === 'ready' ? '✓' : episodeStatus(episode) === 'warning' ? '!' : '○' }}
            </span>
          </button>
        </div>
        <div class="shot-v3-legend">
          <span><i class="ready"></i>完成</span>
          <span><i class="warning"></i>待检查</span>
          <span><i class="pending"></i>待处理</span>
        </div>
      </aside>

      <main class="shot-v3-center">
        <div class="shot-v3-episode-head">
          <div>
            <strong>{{ selectedEpisode?.title || '请选择剧集' }}</strong>
            <span v-if="selectedEpisode">{{ shots.length }} Shots</span>
            <span v-if="currentRevision">Current R{{ currentRevision.revision }}</span>
            <span v-if="currentRevision">{{ currentRevision.kind }}</span>
          </div>
          <button v-if="revisions.length" class="shot-v3-history-button" @click="revisionOpen = !revisionOpen">
            版本历史 {{ revisionOpen ? '▴' : '▾' }}
          </button>
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
          <span>点击右上方“单集拉片”即可开始；媒体预处理会自动完成。</span>
        </div>
        <template v-else>
          <div class="shot-v3-player">
            <video
              ref="videoRef"
              :key="`${selectedShot.id}-${selectedShot.start_us}-${selectedShot.end_us}`"
              :src="shotMediaUrl(selectedShot)"
              controls
              preload="metadata"
            ></video>
            <div class="shot-v3-player-meta">
              <span>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</span>
              <span>{{ timecode(selectedShot.start_us) }} → {{ timecode(selectedShot.end_us) }}</span>
            </div>
          </div>

          <div class="shot-v3-filmstrip-head">
            <div><strong>Shots 列表</strong><span>（{{ shots.length }}）</span></div>
            <div class="shot-v3-filmstrip-summary">
              <span v-if="suspiciousShots.length" class="warning">⚠ {{ suspiciousShots.length }} 个极短 Shot</span>
              <span v-else class="ready">✓ 未发现明显短镜头</span>
            </div>
          </div>

          <div class="shot-v3-filmstrip">
            <button
              v-for="shot in shots"
              :key="shot.id"
              :class="['shot-v3-card', { active: selectedShot.id === shot.id, warning: shot.duration_us < 500000 }]"
              @click="selectShot(shot)"
            >
              <div class="shot-v3-thumb">
                <img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" alt="" />
                <span v-else>SHOT</span>
                <i v-if="shot.duration_us < 500000">!</i>
              </div>
              <strong>{{ String(shot.ordinal).padStart(4, '0') }}</strong>
              <small>{{ timecode(shot.start_us) }}</small>
              <small>{{ timecode(shot.end_us) }}</small>
              <div class="shot-v3-card-foot">
                <span>{{ seconds(shot.duration_us) }}</span>
                <i :class="shot.duration_us < 500000 ? 'warning' : 'ready'">{{ shot.duration_us < 500000 ? '▲' : '●' }}</i>
              </div>
            </button>
          </div>
        </template>
      </main>

      <aside v-if="selectedShot" class="shot-v3-inspector">
        <div class="shot-v3-inspector-title">
          <strong>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</strong>
          <span :class="selectedShot.duration_us < 500000 ? 'warning' : 'ready'">{{ selectedShot.duration_us < 500000 ? '待检查' : selectedShot.status }}</span>
        </div>

        <div class="shot-v3-inspector-preview">
          <img v-if="selectedShot.thumbnail_url" :src="thumbnailUrl(selectedShot)" alt="" />
        </div>

        <div class="shot-v3-field">
          <label>开始时间（In）</label>
          <div><input v-model.number="startSeconds" type="number" step="0.001" min="0" /><button :disabled="selectedShotIndex <= 0 || !!busy" @click="saveTypedStart">保存</button></div>
        </div>
        <div class="shot-v3-field">
          <label>结束时间（Out）</label>
          <div><input v-model.number="endSeconds" type="number" step="0.001" min="0" /><button :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="saveTypedEnd">保存</button></div>
        </div>
        <div class="shot-v3-duration"><span>持续时长</span><strong>{{ seconds(selectedShot.duration_us) }}</strong></div>

        <button class="shot-v3-primary wide" :disabled="selectedShotIndex <= 0 || !!busy" @click="usePlayheadAsStart">◀ 使用当前播放头设为开始</button>
        <button class="shot-v3-primary wide" :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="usePlayheadAsEnd">▶ 使用当前播放头设为结束</button>
        <button class="shot-v3-secondary wide" :disabled="!!busy" @click="splitAtPlayhead">✂ 在播放头拆分</button>

        <div class="shot-v3-merge-row">
          <button :disabled="selectedShotIndex <= 0 || !!busy" @click="mergePrevious">← 合并 SHOT {{ String(Math.max(1, selectedShot.ordinal - 1)).padStart(4, '0') }}</button>
          <button :disabled="selectedShotIndex >= shots.length - 1 || !!busy" @click="mergeNext">合并 SHOT {{ String(selectedShot.ordinal + 1).padStart(4, '0') }} →</button>
        </div>

        <div class="shot-v3-note">
          <span>ⓘ</span>
          <p><strong>资产会在下一步绑定到 Shot</strong>修改镜头边界、拆分或合并后，旧资产结果会标记为 STALE。</p>
        </div>
      </aside>
    </div>
  </section>
</template>
