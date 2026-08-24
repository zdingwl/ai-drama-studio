<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import StudioShell from '../components/StudioShell.vue'
import { characterCandidateCoverUrl } from '../api/character-detection'
import { shotWorkbenchProxyUrl } from '../api/shot-workbench'
import { useCharacterDetectionStore } from '../stores/character-detection'
import { useProjectStore } from '../stores/project'
import { useShotWorkbenchStore } from '../stores/shot-workbench'
import type { CharacterCandidate, CharacterTrack } from '../types/character-detection'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()
const workbenchStore = useShotWorkbenchStore()
const characterStore = useCharacterDetectionStore()
const videoRef = ref<HTMLVideoElement | null>(null)
const selectedCandidateId = ref('')
const selectedTrackId = ref('')
const currentSourceUs = ref(0)

const projectId = computed(() => String(route.params.projectId || ''))
const project = computed(() => projectStore.currentProject)
const workbench = computed(() => workbenchStore.currentWorkbench)
const detection = computed(() => characterStore.currentDetection)
const candidates = computed(() => detection.value?.candidates ?? [])
const selectedCandidate = computed<CharacterCandidate | null>(() => {
  return candidates.value.find((item) => item.id === selectedCandidateId.value) ?? candidates.value[0] ?? null
})
const selectedTrack = computed<CharacterTrack | null>(() => {
  const candidate = selectedCandidate.value
  if (!candidate) return null
  return candidate.tracks.find((item) => item.id === selectedTrackId.value) ?? candidate.tracks[0] ?? null
})
const proxyUrl = computed(() => shotWorkbenchProxyUrl(projectId.value))
const fatalError = computed(() => projectStore.errorMessage || workbenchStore.errorMessage)

onMounted(async () => {
  characterStore.resetCharacterDetectionState()
  workbenchStore.reset()
  try {
    if (projectStore.currentProject?.id !== projectId.value) await projectStore.openProject(projectId.value)
    const result = await workbenchStore.loadOrInitialize(projectId.value)
    if (result.status === 'confirmed') {
      const current = await characterStore.loadCharacterDetection(projectId.value)
      if (current?.candidates.length) selectCandidate(current.candidates[0], false)
      currentSourceUs.value = current?.source_start_us ?? result.source_start_us
    }
  } catch {
    // Store 已保存可展示错误。
  }
})

watch(candidates, (value) => {
  if (!value.length) {
    selectedCandidateId.value = ''
    selectedTrackId.value = ''
    return
  }
  if (!value.some((item) => item.id === selectedCandidateId.value)) selectCandidate(value[0], false)
})

function formatTimecode(value: number): string {
  const totalMs = Math.round(value / 1000)
  const ms = Math.abs(totalMs % 1000)
  const totalSeconds = Math.floor(Math.abs(totalMs) / 1000)
  const seconds = totalSeconds % 60
  const minutes = Math.floor(totalSeconds / 60) % 60
  const hours = Math.floor(totalSeconds / 3600)
  const sign = value < 0 ? '-' : ''
  return `${sign}${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
}

function formatScore(value: number | null): string {
  return value == null ? '单 Track' : `${(value * 100).toFixed(1)}%`
}

function playerSeconds(sourceUs: number): number {
  const start = detection.value?.source_start_us ?? workbench.value?.source_start_us ?? 0
  return Math.max(0, (sourceUs - start) / 1_000_000)
}

function seekSource(sourceUs: number): void {
  currentSourceUs.value = sourceUs
  if (videoRef.value) videoRef.value.currentTime = playerSeconds(sourceUs)
}

function selectCandidate(candidate: CharacterCandidate, seek = true): void {
  selectedCandidateId.value = candidate.id
  selectedTrackId.value = candidate.tracks[0]?.id ?? ''
  if (seek) seekSource(candidate.cover_source_us)
}

function selectTrack(track: CharacterTrack): void {
  selectedTrackId.value = track.id
  seekSource(track.representative_source_us)
}

function onTimeUpdate(): void {
  if (!videoRef.value || !detection.value) return
  currentSourceUs.value = Math.min(
    detection.value.source_end_us,
    detection.value.source_start_us + Math.round(videoRef.value.currentTime * 1_000_000),
  )
}

function trackStyle(track: CharacterTrack): Record<string, string> {
  const run = detection.value
  if (!run) return {}
  const total = Math.max(1, run.source_end_us - run.source_start_us)
  const left = ((track.start_us - run.source_start_us) / total) * 100
  const width = Math.max(0.7, ((Math.max(track.end_us, track.start_us + 40_000) - track.start_us) / total) * 100)
  return { left: `${Math.max(0, Math.min(100, left))}%`, width: `${Math.min(100 - left, width)}%` }
}

async function startDetection(): Promise<void> {
  try {
    const result = await characterStore.runCharacterDetection(projectId.value)
    if (result.candidates.length) selectCandidate(result.candidates[0])
  } catch {
    // Store 已保存错误。
  }
}

async function rerunDetection(): Promise<void> {
  if (!window.confirm('重新自动识别人​​物？旧 Ready 结果会保留到新 Run 完整成功。')) return
  try {
    const result = await characterStore.rerunCharacterDetection(projectId.value)
    if (result.candidates.length) selectCandidate(result.candidates[0])
  } catch {
    // Store 已保存错误，旧结果仍保留。
  }
}
</script>

<template>
  <StudioShell
    title="人物候选"
    :subtitle="project ? `${project.name} · F06 自动人物识别` : '正在读取项目'"
    project-mode
    :project-name="project?.name || ''"
  >
    <template #topbar>
      <span v-if="detection?.status === 'ready'" class="workspace-status-chip"><i></i> F06 · READY</span>
      <span v-else-if="characterStore.processing || detection?.status === 'processing'" class="workspace-status-chip"><i></i> F06 · PROCESSING</span>
      <button type="button" class="secondary-button compact-button" @click="router.push(`/projects/${projectId}/shot-workbench`)">查看 Final Shots</button>
    </template>

    <div v-if="projectStore.opening || workbenchStore.loading || characterStore.loading" class="workspace-loading">
      <div class="loading-ring"></div><strong>正在打开人物识别工作区</strong><p>校验 F05 Final Shots，并读取已有 Character Candidate…</p>
    </div>

    <div v-else-if="fatalError" class="workspace-error-panel">
      <div class="error-visual">!</div><div><span class="panel-eyebrow">F06 UPSTREAM ERROR</span><h2>人物识别暂时不可用</h2><p>{{ fatalError }}</p><button type="button" class="secondary-button" @click="router.push(`/projects/${projectId}/shot-workbench`)">返回镜头工作台</button></div>
    </div>

    <section v-else-if="workbench?.status !== 'confirmed'" class="content-panel character-blocked-panel">
      <span class="panel-eyebrow">F05 REQUIRED</span><h2>请先确认 Final Shots</h2><p>F06 只读取已 confirmed 的生产级 Final Shot ID 和 Source Timeline。</p><button type="button" class="primary-button" @click="router.push(`/projects/${projectId}/shot-workbench`)">进入镜头修正</button>
    </section>

    <template v-else>
      <div v-if="characterStore.errorMessage" class="inline-alert error-alert character-alert">
        <span>!</span><div><strong>人物识别未完成</strong><p>{{ characterStore.errorMessage }}</p></div>
      </div>

      <section v-if="!detection || detection.status === 'failed'" class="content-panel character-start-panel">
        <div class="character-start-icon">06</div>
        <span class="panel-eyebrow">LOCAL CHARACTER DETECTION</span>
        <h2>{{ detection?.status === 'failed' ? '上一次人物识别失败' : '开始自动人物识别' }}</h2>
        <p>本地 YuNet 负责找脸，SFace 负责身份 Embedding；系统只生成 Character Candidate，不会自动给人物命名。</p>
        <div class="character-tech-grid">
          <div><span>采样</span><strong>约 4 FPS</strong><small>每 Shot 3–12 个真实 PTS 帧</small></div>
          <div><span>检测</span><strong>YuNet</strong><small>OpenCV CPU DNN</small></div>
          <div><span>身份</span><strong>SFace</strong><small>保守跨 Shot 聚类</small></div>
        </div>
        <div class="character-model-note"><strong>首次使用需要准备固定模型</strong><code>python -m engine.app.character_models</code><small>模型下载后做固定大小 + SHA-256 校验，推理本身完全在本机执行。</small></div>
        <button type="button" class="primary-button" :disabled="characterStore.processing" @click="startDetection">
          {{ characterStore.processing ? '正在识别人​​物…' : detection?.status === 'failed' ? '重新尝试人物识别' : '开始自动人物识别' }}
        </button>
      </section>

      <section v-else-if="characterStore.processing || detection.status === 'processing'" class="content-panel character-start-panel">
        <div class="loading-ring"></div><span class="panel-eyebrow">PROCESSING</span><h2>正在本地识别人​​物</h2><p>顺序解码 Proxy，并逐个 Final Shot 建立人脸 Evidence。请不要重复提交。</p>
      </section>

      <template v-else-if="detection.status === 'ready'">
        <section class="character-heading">
          <div><span class="panel-eyebrow">CHARACTER CANDIDATE · F06</span><h2>自动人物候选</h2><p>这里只展示算法 Evidence。人物命名、合并、拆分、删除和正式 Reference 都留给 F07。</p></div>
          <div class="character-summary">
            <span>{{ detection.candidate_count }} CANDIDATES</span><span>{{ detection.track_count }} TRACKS</span><span>{{ detection.sampled_frame_count }} FRAMES</span><span>{{ detection.runtime_device.toUpperCase() }}</span>
          </div>
        </section>

        <div v-if="detection.candidate_count === 0" class="content-panel character-empty-panel">
          <span class="panel-eyebrow">NO FACE CANDIDATE</span><h2>没有检测到合格人物候选</h2><p>Run 已正常完成，但当前阈值下没有稳定人脸 Evidence。F06 不会为了凑人物数量而伪造 Candidate。</p><button type="button" class="secondary-button" @click="rerunDetection">重新自动识别</button>
        </div>

        <section v-else class="character-workbench-grid">
          <aside class="content-panel character-candidate-column">
            <div class="character-column-header"><div><span class="panel-eyebrow">CANDIDATES</span><h3>人物候选</h3></div><span>{{ candidates.length }}</span></div>
            <div class="character-candidate-list">
              <button v-for="candidate in candidates" :key="candidate.id" type="button" class="character-candidate-card" :class="{ active: candidate.id === selectedCandidate?.id }" @click="selectCandidate(candidate)">
                <img :src="characterCandidateCoverUrl(projectId, candidate.id)" alt="" />
                <span><strong>Candidate #{{ String(candidate.ordinal).padStart(2, '0') }}</strong><small>{{ candidate.shot_count }} 镜头 · {{ candidate.track_count }} Tracks</small><em>{{ formatTimecode(candidate.first_seen_us) }}</em></span>
              </button>
            </div>
          </aside>

          <main class="character-center-column">
            <section class="content-panel character-player-panel">
              <div class="character-player-topline"><div><span class="panel-eyebrow">SOURCE VIDEO</span><strong>{{ selectedCandidate ? `Candidate #${String(selectedCandidate.ordinal).padStart(2, '0')}` : '人物候选' }}</strong></div><span>{{ formatTimecode(currentSourceUs) }}</span></div>
              <video ref="videoRef" class="character-video" :src="proxyUrl" controls preload="metadata" playsinline @timeupdate="onTimeUpdate" @seeked="onTimeUpdate"></video>
            </section>

            <section v-if="selectedCandidate" class="content-panel character-timeline-panel">
              <div class="character-column-header"><div><span class="panel-eyebrow">APPEARANCE TIMELINE</span><h3>人物出现位置</h3></div><span>{{ selectedCandidate.track_count }} TRACKS</span></div>
              <div class="character-track-timeline">
                <button v-for="track in selectedCandidate.tracks" :key="track.id" type="button" :style="trackStyle(track)" :class="{ active: track.id === selectedTrack?.id }" :title="`Shot #${track.final_shot_ordinal} · ${formatTimecode(track.start_us)}`" @click="selectTrack(track)"></button>
              </div>
              <div class="character-timeline-labels"><span>{{ formatTimecode(detection.source_start_us) }}</span><span>{{ formatTimecode(detection.source_end_us) }}</span></div>
            </section>
          </main>

          <aside v-if="selectedCandidate" class="content-panel character-detail-column">
            <div class="character-detail-head"><div><span class="panel-eyebrow">AUTO EVIDENCE</span><h3>Candidate #{{ String(selectedCandidate.ordinal).padStart(2, '0') }}</h3></div><img :src="characterCandidateCoverUrl(projectId, selectedCandidate.id)" alt="" /></div>
            <dl class="character-stats">
              <div><dt>出现镜头</dt><dd>{{ selectedCandidate.shot_count }}</dd></div><div><dt>Tracks</dt><dd>{{ selectedCandidate.track_count }}</dd></div>
              <div><dt>首次出现</dt><dd>{{ formatTimecode(selectedCandidate.first_seen_us) }}</dd></div><div><dt>最后出现</dt><dd>{{ formatTimecode(selectedCandidate.last_seen_us) }}</dd></div>
              <div><dt>聚类置信</dt><dd>{{ formatScore(selectedCandidate.cluster_score) }}</dd></div><div><dt>Run</dt><dd>{{ detection.profile_version }}</dd></div>
            </dl>
            <div class="character-track-list">
              <div class="character-column-header"><div><span class="panel-eyebrow">TRACK EVIDENCE</span><h3>出现记录</h3></div></div>
              <button v-for="track in selectedCandidate.tracks" :key="track.id" type="button" :class="{ active: track.id === selectedTrack?.id }" @click="selectTrack(track)">
                <span><strong>Shot #{{ String(track.final_shot_ordinal).padStart(3, '0') }}</strong><small>{{ formatTimecode(track.representative_source_us) }}</small></span><em>{{ track.sample_count }} samples · Q {{ (track.max_face_quality * 100).toFixed(0) }}</em>
              </button>
            </div>
            <div class="character-f07-note"><strong>F07 再做人​​工人物确认</strong><p>当前页故意没有命名、合并、拆分、删除或主角标签按钮，避免人工 Final 覆盖 F06 自动证据。</p></div>
            <button type="button" class="secondary-button character-rerun-button" :disabled="characterStore.processing" @click="rerunDetection">重新自动识别</button>
          </aside>
        </section>
      </template>
    </template>
  </StudioShell>
</template>
