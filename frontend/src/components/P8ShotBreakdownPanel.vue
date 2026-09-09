<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getProject, listProjectTasks } from '@/features/projects/api'
import {
  getShotBreakdown,
  listShotBreakdownRevisions,
  startShotBreakdown,
  type DialogueDelivery,
  type ShotBreakdownRead,
  type ShotBreakdownRevisionSummary,
  type SourceShotFact,
} from '@/features/projects/shotBreakdown'
import { getSourceBible, type SourceBibleRead } from '@/features/projects/sourceBible'
import type { ProjectRead, TaskRead } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const result = ref<ShotBreakdownRead | null>(null)
const sourceBible = ref<SourceBibleRead | null>(null)
const revisions = ref<ShotBreakdownRevisionSummary[]>([])
const activeTask = ref<TaskRead | null>(null)
const loading = ref(true)
const starting = ref(false)
const errorMessage = ref('')
const preview = ref<{ episodeId: string; shot: SourceShotFact } | null>(null)
let pollTimer: number | null = null

const visible = computed(() => project.value?.project_type === 'REPLICA' || project.value?.project_type === 'REDRAW')
const taskActive = computed(() => activeTask.value?.status === 'queued' || activeTask.value?.status === 'running')
const sourceBibleReady = computed(() => sourceBible.value?.status === 'CURRENT')
const totalShots = computed(() => result.value?.content?.episodes.reduce((sum, episode) => sum + episode.shots.length, 0) ?? 0)
const statusText = computed(() => {
  if (!result.value) return '读取中'
  if (result.value.status === 'CURRENT') return `CURRENT · rev ${result.value.revision}`
  if (result.value.status === 'STALE') return `STALE · rev ${result.value.revision}`
  return 'NOT_BUILT'
})
const statusClass = computed(() => result.value?.status?.toLowerCase() ?? 'not-built')
const sourceBibleStatusText = computed(() => {
  if (!sourceBible.value) return '正在读取 P7 状态…'
  if (sourceBible.value.status === 'CURRENT') return `CURRENT · rev ${sourceBible.value.revision}`
  if (sourceBible.value.status === 'STALE') {
    return `STALE${sourceBible.value.revision == null ? '' : ` · rev ${sourceBible.value.revision}`} · 该 P7 revision 已失效，不能作为 P8 输入`
  }
  return 'NOT_BUILT · 尚未生成正式 P7 SOURCE_BIBLE'
})
const sourceBibleRecoveryText = computed(() => {
  if (!sourceBible.value || sourceBible.value.status === 'CURRENT') return ''
  return sourceBible.value.status === 'STALE'
    ? '请先在上方「源作概览分析」重新运行整集原片理解，生成新的 CURRENT SOURCE_BIBLE。'
    : '请先在上方「源作概览分析」运行整集原片理解，待 SOURCE_BIBLE 变为 CURRENT。'
})

const deliveryText: Record<DialogueDelivery, string> = {
  DIALOGUE: '对白',
  VOICEOVER: '旁白',
  OFFSCREEN: '画外对白',
  UNKNOWN: '未确认',
}

function formatTime(us: number): string {
  const totalMs = Math.max(0, Math.round(us / 1000))
  const ms = totalMs % 1000
  const secondsTotal = Math.floor(totalMs / 1000)
  const seconds = secondsTotal % 60
  const minutesTotal = Math.floor(secondsTotal / 60)
  const minutes = minutesTotal % 60
  const hours = Math.floor(minutesTotal / 60)
  const core = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms).padStart(3, '0')}`
  return hours ? `${String(hours).padStart(2, '0')}:${core}` : core
}

function formatDuration(us: number): string {
  const seconds = us / 1_000_000
  return seconds >= 10 ? `${seconds.toFixed(2)}s` : `${seconds.toFixed(3)}s`
}

function shortId(value: string | null | undefined): string {
  if (!value) return '—'
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value
}

function commandKey(): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
  return `p8-shot-breakdown-${suffix}`.slice(0, 128)
}

function thumbnailUrl(episodeId: string, shot: SourceShotFact): string {
  return `/api/v3/projects/${projectId.value}/episodes/${episodeId}/shot-boundary/shots/${shot.shot_anchor_id}/thumbnail`
}

function referenceClipUrl(episodeId: string, shot: SourceShotFact): string {
  return `/api/v3/projects/${projectId.value}/episodes/${episodeId}/shot-boundary/shots/${shot.shot_anchor_id}/reference-clip`
}

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshResult(): Promise<void> {
  const [current, history, bible] = await Promise.all([
    getShotBreakdown(projectId.value),
    listShotBreakdownRevisions(projectId.value),
    getSourceBible(projectId.value),
  ])
  result.value = current
  revisions.value = history
  sourceBible.value = bible
}

function startPolling(taskId: string): void {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      const tasks = await listProjectTasks(projectId.value)
      const task = tasks.find((item) => item.id === taskId) ?? null
      activeTask.value = task
      if (!task || (task.status !== 'queued' && task.status !== 'running')) {
        stopPolling()
        await refreshResult()
      }
    } catch (error) {
      stopPolling()
      errorMessage.value = error instanceof Error ? error.message : '逐镜拉片任务状态读取失败'
    }
  }, 1000)
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    project.value = await getProject(projectId.value)
    if (!visible.value) return
    await refreshResult()
    const tasks = await listProjectTasks(projectId.value)
    const running = tasks.find(
      (item) => (item.status === 'queued' || item.status === 'running') && item.task_name.includes('逐镜精细拉片'),
    )
    if (running) {
      activeTask.value = running
      startPolling(running.id)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '逐镜拉片加载失败'
  } finally {
    loading.value = false
  }
}

async function runP8(): Promise<void> {
  if (taskActive.value) return
  if (!sourceBibleReady.value) {
    errorMessage.value = `逐镜拉片前置未就绪：${sourceBibleStatusText.value}。${sourceBibleRecoveryText.value}`
    return
  }
  starting.value = true
  errorMessage.value = ''
  try {
    const task = await startShotBreakdown(projectId.value, commandKey())
    activeTask.value = task
    startPolling(task.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '逐镜拉片任务启动失败'
  } finally {
    starting.value = false
  }
}

function openPreview(episodeId: string, shot: SourceShotFact): void {
  preview.value = { episodeId, shot }
}

function closePreview(): void {
  preview.value = null
}

onMounted(load)
onBeforeUnmount(stopPolling)
</script>

<template>
  <section v-if="visible" class="shot-breakdown-workspace">
    <header class="workspace-header">
      <div class="workspace-title">
        <span class="section-kicker">原片理解 · 逐镜拉片</span>
        <div class="title-line">
          <h2>逐镜分镜表</h2>
          <span class="status-pill" :class="statusClass">{{ statusText }}</span>
        </div>
        <p>按原片镜头逐条查看源片段、画面、镜头语言、主体、对白和声音。</p>
      </div>

      <div class="workspace-actions">
        <button
          class="primary-action"
          type="button"
          :disabled="starting || taskActive || !sourceBibleReady"
          :title="sourceBibleReady ? '' : sourceBibleRecoveryText"
          @click="runP8"
        >
          {{ starting ? '正在提交…' : result?.status === 'CURRENT' ? '重新分析' : '生成逐镜拉片' }}
        </button>
        <button class="ghost-action" type="button" :disabled="taskActive" @click="refreshResult">刷新</button>
      </div>
    </header>

    <p v-if="errorMessage" class="message error-message">{{ errorMessage }}</p>
    <p v-if="loading" class="loading-message">正在读取逐镜拉片结果…</p>

    <template v-else>
      <div
        v-if="sourceBible && !sourceBibleReady"
        class="dependency-alert"
      >
        <div>
          <strong>需要先完成「源作概览分析」</strong>
          <span>{{ sourceBibleStatusText }}</span>
          <small>{{ sourceBibleRecoveryText }}</small>
        </div>
        <b>暂不可运行</b>
      </div>

      <div v-if="activeTask" class="task-progress">
        <div class="progress-copy">
          <strong>{{ activeTask.task_name }}</strong>
          <span>{{ activeTask.status }} · attempt {{ activeTask.attempt }}/{{ activeTask.max_attempts }}</span>
        </div>
        <div class="progress-right">
          <b>{{ activeTask.progress_percent }}%</b>
          <div class="progress-track"><i :style="{ width: `${activeTask.progress_percent}%` }"></i></div>
        </div>
      </div>

      <p v-if="result?.status === 'STALE'" class="message stale-message">
        上游原片理解结果已变化。下面保留旧分镜表供核对，但需要重新分析后才能继续作为当前结果使用。
      </p>

      <template v-if="result?.content">
        <div class="result-summary">
          <div>
            <span>{{ result.content.episodes.length }} 集</span>
            <strong>{{ totalShots }} 镜头</strong>
          </div>
          <small>镜头时间来自 P5；对白正文来自 P6 canonical Evidence。</small>
        </div>

        <article v-for="episode in result.content.episodes" :key="episode.episode_id" class="episode-board">
          <header class="episode-header">
            <div>
              <span>第 {{ episode.episode_order }} 集</span>
              <h3>{{ episode.source_filename }}</h3>
            </div>
            <b>{{ episode.shots.length }} 镜头</b>
          </header>

          <div class="storyboard-table-wrap">
            <table class="storyboard-table">
              <thead>
                <tr>
                  <th>镜头编号</th>
                  <th>源片段</th>
                  <th>时长</th>
                  <th>画面描述</th>
                  <th>镜头语言</th>
                  <th>绑定主体</th>
                  <th>对白 / 旁白</th>
                  <th>音效</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="shot in episode.shots" :key="shot.shot_anchor_id" :data-testid="`p8-shot-${shot.shot_number}`">
                  <td class="shot-id-cell">
                    <strong>#{{ String(shot.shot_number).padStart(3, '0') }}</strong>
                    <span>{{ formatTime(shot.start_us) }}</span>
                    <small>→ {{ formatTime(shot.end_us) }}</small>
                  </td>

                  <td class="source-clip-cell">
                    <button
                      class="clip-button shot-media-button"
                      type="button"
                      :aria-label="`播放镜头 ${shot.shot_number} 源片段`"
                      @click="openPreview(episode.episode_id, shot)"
                    >
                      <img :src="thumbnailUrl(episode.episode_id, shot)" :alt="`镜头 ${shot.shot_number} 缩略图`" loading="lazy" />
                      <span class="play-overlay"><i>▶</i></span>
                    </button>
                  </td>

                  <td class="duration-cell">
                    <strong>{{ formatDuration(shot.duration_us) }}</strong>
                  </td>

                  <td class="visual-cell">
                    <p>{{ shot.visual_description }}</p>
                  </td>

                  <td class="camera-cell">
                    <dl>
                      <div><dt>景别</dt><dd>{{ shot.camera_language.shot_size }}</dd></div>
                      <div><dt>构图</dt><dd>{{ shot.camera_language.composition }}</dd></div>
                      <div><dt>角度</dt><dd>{{ shot.camera_language.angle_or_type }}</dd></div>
                      <div><dt>运镜</dt><dd>{{ shot.camera_language.movement }}</dd></div>
                      <div><dt>焦距 / 景深</dt><dd>{{ shot.camera_language.focal_length_dof }}</dd></div>
                    </dl>
                  </td>

                  <td class="binding-cell">
                    <div v-if="shot.bindings.characters.length" class="binding-row">
                      <b>人物</b>
                      <span v-for="item in shot.bindings.characters" :key="item.id" class="entity-chip character-chip">{{ item.label }}</span>
                    </div>
                    <div v-if="shot.bindings.scenes.length" class="binding-row">
                      <b>场景</b>
                      <span v-for="item in shot.bindings.scenes" :key="item.id" class="entity-chip scene-chip">{{ item.label }}</span>
                    </div>
                    <div v-if="shot.bindings.props.length" class="binding-row">
                      <b>道具</b>
                      <span v-for="item in shot.bindings.props" :key="item.id" class="entity-chip prop-chip">{{ item.label }}</span>
                    </div>
                    <div v-if="shot.bindings.unresolved_subject_notes.length" class="binding-row unresolved-row">
                      <b>待确认</b>
                      <span v-for="item in shot.bindings.unresolved_subject_notes" :key="item">{{ item }}</span>
                    </div>
                    <span
                      v-if="!shot.bindings.characters.length && !shot.bindings.scenes.length && !shot.bindings.props.length && !shot.bindings.unresolved_subject_notes.length"
                      class="empty-copy"
                    >—</span>
                  </td>

                  <td class="dialogue-cell">
                    <div v-for="line in shot.dialogue" :key="`${line.utterance_id}-${line.overlap_start_us}`" class="dialogue-line">
                      <span class="delivery" :class="`delivery-${line.delivery.toLowerCase()}`">{{ deliveryText[line.delivery] }}</span>
                      <p>{{ line.text }}</p>
                    </div>
                    <span v-if="!shot.dialogue.length" class="empty-copy">—</span>
                  </td>

                  <td class="sound-cell">
                    <div v-if="shot.sound_effects.length" class="sound-group">
                      <b>音效</b>
                      <span v-for="item in shot.sound_effects" :key="item">{{ item }}</span>
                    </div>
                    <div v-if="shot.ambience.length" class="sound-group ambience-group">
                      <b>环境声</b>
                      <span v-for="item in shot.ambience" :key="item">{{ item }}</span>
                    </div>
                    <span v-if="!shot.sound_effects.length && !shot.ambience.length" class="empty-copy">—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </article>
      </template>

      <div v-else class="empty-state">
        <div class="empty-symbol">▦</div>
        <strong>还没有逐镜分镜表</strong>
        <span>完成「源作概览分析」后，点击“生成逐镜拉片”。页面打开不会自动调用模型。</span>
      </div>

      <details class="technical-panel">
        <summary>
          <span>技术信息</span>
          <small>数据来源、revision 与 provenance</small>
        </summary>
        <div class="technical-body">
          <div
            v-if="sourceBible"
            class="technical-state"
            data-testid="p8-source-bible-preflight"
          >
            <span>P7 SOURCE_BIBLE</span>
            <strong>{{ sourceBibleStatusText }}</strong>
            <small>{{ sourceBibleReady ? 'P8 前置已就绪' : sourceBibleRecoveryText }}</small>
          </div>

          <div class="contract-note">
            <strong>source-bible-shot-facts-v1</strong>
            <span>完整 Episode 是 Source Truth；镜头时间只认 P5；对白正文只认 P6；人物、场景、道具只绑定 CURRENT SOURCE_BIBLE candidate。</span>
          </div>

          <div v-if="result?.content && result.provenance" class="technical-metrics">
            <div><span>Artifact revision</span><strong>{{ result.revision }}</strong></div>
            <div><span>Schema</span><strong>{{ result.content.schema_version }}</strong></div>
            <div><span>Provider</span><strong>{{ result.provenance.provider }}</strong></div>
            <div><span>Model</span><strong>{{ result.provenance.model }}</strong></div>
            <div><span>ProviderJob</span><strong>{{ result.provenance.provider_jobs.length }}</strong></div>
          </div>

          <div v-if="result?.provenance" class="provenance-grid">
            <div><span>Professional Skill</span><strong>{{ result.provenance.professional_skill_id }}@{{ result.provenance.professional_skill_version }}</strong></div>
            <div><span>Prompt</span><strong>{{ result.provenance.prompt_version }}</strong></div>
            <div><span>SOURCE_VIDEO</span><strong>{{ shortId(result.provenance.source_video_artifact_id) }}</strong></div>
            <div><span>SOURCE_BIBLE</span><strong>{{ shortId(result.provenance.source_bible_artifact_id) }}</strong></div>
            <div><span>SHOT_ANCHORS</span><strong>{{ shortId(result.provenance.shot_anchors_artifact_id) }}</strong></div>
            <div><span>SOURCE_DIALOGUE</span><strong>{{ shortId(result.provenance.source_dialogue_artifact_id) }}</strong></div>
            <div><span>Supersedes</span><strong>{{ shortId(result.provenance.supersedes_artifact_id) }}</strong></div>
          </div>

          <div v-if="revisions.length" class="revision-history">
            <span class="subheading">历史 revisions</span>
            <div class="revision-list">
              <div v-for="item in revisions" :key="item.artifact_id">
                <strong>rev {{ item.revision }}</strong>
                <span :class="item.status.toLowerCase()">{{ item.status }}</span>
                <small>{{ shortId(item.artifact_id) }}</small>
              </div>
            </div>
          </div>
        </div>
      </details>
    </template>

    <div v-if="preview" class="preview-overlay" role="presentation" @click.self="closePreview">
      <section class="preview-dialog" role="dialog" aria-modal="true" :aria-label="`镜头 ${preview.shot.shot_number} 源片段`">
        <header>
          <div>
            <span>镜头 {{ String(preview.shot.shot_number).padStart(3, '0') }}</span>
            <strong>{{ formatTime(preview.shot.start_us) }} → {{ formatTime(preview.shot.end_us) }}</strong>
            <small>{{ formatDuration(preview.shot.duration_us) }}</small>
          </div>
          <button type="button" @click="closePreview">关闭</button>
        </header>
        <div class="preview-video-wrap">
          <video :src="referenceClipUrl(preview.episodeId, preview.shot)" controls autoplay preload="metadata"></video>
        </div>
        <p>源片段用于当前镜头的局部核对；正式逐镜分析仍以完整 Episode 为输入。</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.shot-breakdown-workspace {
  width: 100%;
  margin-top: 24px;
  border-top: 1px solid #e7e8ec;
  background: #fff;
  color: #1f232b;
}

.workspace-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  padding: 26px 2px 18px;
}

.workspace-title { min-width: 0; }
.section-kicker {
  display: block;
  margin-bottom: 7px;
  color: #777c87;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: .06em;
}
.title-line { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.title-line h2 { margin: 0; color: #181b22; font-size: 24px; line-height: 1.2; }
.workspace-title p { margin: 8px 0 0; color: #6c717d; font-size: 13px; }

.status-pill {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 9px;
  border-radius: 999px;
  background: #f1f2f4;
  color: #6c717b;
  font-size: 11px;
  font-weight: 800;
}
.status-pill.current { background: #eaf7ef; color: #247148; }
.status-pill.stale { background: #fff3df; color: #94611c; }
.status-pill.not_built, .status-pill.not-built { background: #f1f2f4; color: #6c717b; }

.workspace-actions { display: flex; gap: 8px; flex-shrink: 0; }
.workspace-actions button, .preview-dialog header button {
  min-height: 36px;
  border: 1px solid #d8dae0;
  border-radius: 8px;
  padding: 0 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}
.primary-action { border-color: #20242c !important; background: #20242c; color: #fff; }
.ghost-action, .preview-dialog header button { background: #fff; color: #333842; }
.workspace-actions button:disabled { opacity: .45; cursor: not-allowed; }

.message { margin: 0 0 14px; padding: 11px 13px; border-radius: 8px; font-size: 13px; }
.error-message { background: #fff1f1; color: #a43232; }
.stale-message { background: #fff6e7; color: #855b1f; }
.loading-message { margin: 0; padding: 28px 0; color: #858a94; font-size: 13px; }

.dependency-alert {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid #eed7b3;
  border-radius: 10px;
  background: #fff9ef;
  color: #76531e;
}
.dependency-alert > div { display: grid; gap: 3px; }
.dependency-alert strong { color: #5e431b; font-size: 13px; }
.dependency-alert span, .dependency-alert small { font-size: 12px; line-height: 1.45; }
.dependency-alert b { white-space: nowrap; font-size: 12px; }

.task-progress {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 16px;
  padding: 12px 14px;
  border: 1px solid #e4e6eb;
  border-radius: 9px;
  background: #fafbfc;
}
.progress-copy { display: grid; gap: 3px; }
.progress-copy strong { font-size: 13px; }
.progress-copy span { color: #7c818c; font-size: 11px; }
.progress-right { display: grid; grid-template-columns: 42px 120px; align-items: center; gap: 8px; }
.progress-right b { font-size: 12px; text-align: right; }
.progress-track { height: 5px; overflow: hidden; border-radius: 999px; background: #e7e9ed; }
.progress-track i { display: block; height: 100%; border-radius: inherit; background: #333843; transition: width .2s ease; }

.result-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 12px 0 15px;
  border-bottom: 1px solid #e9eaee;
}
.result-summary > div { display: flex; align-items: baseline; gap: 8px; }
.result-summary span { color: #737985; font-size: 12px; }
.result-summary strong { color: #20242c; font-size: 15px; }
.result-summary small { color: #8a8f98; font-size: 11px; }

.episode-board { margin-top: 20px; }
.episode-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
}
.episode-header > div { min-width: 0; }
.episode-header span { color: #7b808b; font-size: 11px; font-weight: 700; }
.episode-header h3 { overflow: hidden; margin: 3px 0 0; color: #22262e; font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }
.episode-header b { color: #5c626d; font-size: 12px; white-space: nowrap; }

.storyboard-table-wrap {
  overflow: auto;
  max-height: 76vh;
  border: 1px solid #dfe1e6;
  border-radius: 10px;
  background: #fff;
}
.storyboard-table {
  width: 100%;
  min-width: 1540px;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}
.storyboard-table thead th {
  position: sticky;
  top: 0;
  z-index: 3;
  padding: 11px 10px;
  border-bottom: 1px solid #dfe1e6;
  background: #f7f8f9;
  color: #555b66;
  text-align: left;
  font-size: 11px;
  font-weight: 800;
}
.storyboard-table th:nth-child(1) { width: 100px; }
.storyboard-table th:nth-child(2) { width: 128px; }
.storyboard-table th:nth-child(3) { width: 76px; }
.storyboard-table th:nth-child(4) { width: 255px; }
.storyboard-table th:nth-child(5) { width: 275px; }
.storyboard-table th:nth-child(6) { width: 210px; }
.storyboard-table th:nth-child(7) { width: 310px; }
.storyboard-table th:nth-child(8) { width: 186px; }
.storyboard-table td {
  padding: 12px 10px;
  border-bottom: 1px solid #eceef1;
  background: #fff;
  color: #30353d;
  vertical-align: top;
  font-size: 12px;
  line-height: 1.55;
}
.storyboard-table tbody tr:last-child td { border-bottom: 0; }
.storyboard-table tbody tr:hover td { background: #fbfbfc; }

.shot-id-cell { color: #757b86 !important; }
.shot-id-cell strong { display: block; margin-bottom: 9px; color: #20242c; font-size: 14px; }
.shot-id-cell span, .shot-id-cell small { display: block; color: #858a94; font-size: 10px; line-height: 1.45; }

.source-clip-cell { text-align: center; }
.shot-media-button {
  position: relative;
  display: block;
  width: 94px;
  aspect-ratio: 9 / 16;
  overflow: hidden;
  margin: 0 auto;
  border: 0;
  border-radius: 7px;
  padding: 0;
  background: #111;
  cursor: pointer;
}
.shot-media-button img { display: block; width: 100%; height: 100%; object-fit: cover; }
.play-overlay {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: linear-gradient(180deg, transparent 52%, rgb(0 0 0 / 42%));
  opacity: .92;
}
.play-overlay i {
  display: grid;
  place-items: center;
  width: 31px;
  height: 31px;
  border-radius: 50%;
  background: rgb(255 255 255 / 92%);
  color: #20242c;
  font-size: 11px;
  font-style: normal;
  box-shadow: 0 2px 8px rgb(0 0 0 / 18%);
}
.shot-media-button:hover .play-overlay i { transform: scale(1.05); }

.duration-cell strong { color: #30353d; font-size: 12px; font-variant-numeric: tabular-nums; }
.visual-cell p, .dialogue-line p { margin: 0; }
.visual-cell p { white-space: pre-line; }

.camera-cell dl { display: grid; gap: 7px; margin: 0; }
.camera-cell dl div { display: grid; grid-template-columns: 62px 1fr; gap: 8px; }
.camera-cell dt { color: #8b9099; font-size: 10px; }
.camera-cell dd { margin: 0; color: #363b43; }

.binding-cell { display: grid; align-content: start; gap: 9px; }
.binding-row { display: flex; align-items: flex-start; gap: 5px; flex-wrap: wrap; }
.binding-row > b { width: 36px; padding-top: 3px; color: #8a8f98; font-size: 9px; font-weight: 800; }
.entity-chip {
  display: inline-flex;
  align-items: center;
  min-height: 23px;
  border: 1px solid #e1e3e7;
  border-radius: 6px;
  padding: 2px 7px;
  background: #f8f9fa;
  color: #474c55;
  font-size: 10px;
}
.character-chip { background: #f6f2ff; border-color: #e6dcfb; color: #655291; }
.scene-chip { background: #eef8f3; border-color: #d8ece1; color: #3f7056; }
.prop-chip { background: #fff7eb; border-color: #f0dfc2; color: #86642c; }
.unresolved-row span { color: #8a6428; font-size: 10px; }

.dialogue-cell { display: grid; align-content: start; gap: 10px; }
.dialogue-line { display: grid; gap: 5px; }
.delivery {
  width: fit-content;
  min-height: 21px;
  padding: 2px 7px;
  border-radius: 5px;
  background: #eef1f5;
  color: #59616d;
  font-size: 9px;
  font-weight: 800;
}
.delivery-dialogue { background: #edf3ff; color: #496a99; }
.delivery-voiceover { background: #edf8f1; color: #3f7656; }
.delivery-offscreen { background: #fff5e6; color: #8b6324; }
.delivery-unknown { background: #f1f2f4; color: #727782; }
.dialogue-line p { color: #282d35; font-size: 12px; line-height: 1.62; }

.sound-cell { display: grid; align-content: start; gap: 10px; }
.sound-group { display: grid; gap: 3px; }
.sound-group b { color: #7f858f; font-size: 9px; }
.sound-group span { color: #3b4048; font-size: 11px; }
.ambience-group { padding-top: 7px; border-top: 1px dashed #e4e6e9; }
.empty-copy { color: #a0a4ac; }

.empty-state {
  display: grid;
  place-items: center;
  gap: 7px;
  min-height: 190px;
  margin-top: 12px;
  border: 1px dashed #d8dbe0;
  border-radius: 10px;
  color: #777c86;
  text-align: center;
}
.empty-symbol { color: #9ba0a9; font-size: 26px; }
.empty-state strong { color: #3a3f47; font-size: 14px; }
.empty-state span { max-width: 560px; font-size: 12px; }

.technical-panel { margin-top: 18px; border-top: 1px solid #e8e9ed; }
.technical-panel > summary {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 0;
  cursor: pointer;
  color: #5c626c;
  list-style: none;
  font-size: 12px;
  font-weight: 700;
}
.technical-panel > summary::-webkit-details-marker { display: none; }
.technical-panel > summary::before { content: '›'; color: #8e939b; font-size: 17px; transition: transform .15s ease; }
.technical-panel[open] > summary::before { transform: rotate(90deg); }
.technical-panel > summary small { color: #9a9ea7; font-weight: 400; }
.technical-body { display: grid; gap: 11px; padding: 0 0 18px 20px; }
.technical-state, .contract-note {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafbfc;
}
.technical-state span, .contract-note strong { color: #777d88; font-size: 10px; }
.technical-state strong, .contract-note span { color: #414650; font-size: 11px; }
.technical-state small { color: #858a94; font-size: 10px; }
.technical-metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 7px; }
.technical-metrics div, .provenance-grid div {
  display: grid;
  gap: 3px;
  padding: 9px 10px;
  border-radius: 7px;
  background: #f6f7f9;
}
.technical-metrics span, .provenance-grid span { color: #8a8f98; font-size: 9px; }
.technical-metrics strong, .provenance-grid strong { overflow-wrap: anywhere; color: #3f444d; font-size: 10px; }
.provenance-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; }
.subheading { color: #6d737d; font-size: 10px; font-weight: 800; }
.revision-history { display: grid; gap: 7px; }
.revision-list { display: grid; gap: 5px; }
.revision-list > div { display: grid; grid-template-columns: 64px 72px 1fr; gap: 8px; align-items: center; padding: 7px 9px; border-radius: 6px; background: #f7f8f9; font-size: 10px; }
.revision-list .current { color: #2f7951; }
.revision-list .stale { color: #976722; }
.revision-list small { color: #8d929b; }

.preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 120;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(13 15 19 / 76%);
  backdrop-filter: blur(3px);
}
.preview-dialog {
  width: min(760px, 94vw);
  max-height: 92vh;
  overflow: auto;
  border-radius: 13px;
  background: #fff;
  box-shadow: 0 28px 90px rgb(0 0 0 / 36%);
}
.preview-dialog header { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 14px 16px; border-bottom: 1px solid #e7e8ec; }
.preview-dialog header > div { display: grid; gap: 2px; }
.preview-dialog header span { color: #80858f; font-size: 10px; font-weight: 700; }
.preview-dialog header strong { color: #252931; font-size: 13px; }
.preview-dialog header small { color: #8b9099; font-size: 10px; }
.preview-video-wrap { display: grid; place-items: center; min-height: 360px; padding: 14px; background: #111318; }
.preview-dialog video { width: auto; max-width: 100%; max-height: 68vh; border-radius: 6px; background: #000; }
.preview-dialog > p { margin: 0; padding: 11px 16px 14px; color: #7e838d; font-size: 10px; }

@media (max-width: 900px) {
  .workspace-header { align-items: flex-start; flex-direction: column; }
  .workspace-actions { width: 100%; }
  .workspace-actions button { flex: 1; }
  .dependency-alert, .task-progress, .result-summary { align-items: flex-start; flex-direction: column; }
  .progress-right { width: 100%; grid-template-columns: 42px 1fr; }
  .technical-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .provenance-grid { grid-template-columns: 1fr; }
}
</style>
