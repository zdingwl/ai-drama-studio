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
const statusText = computed(() => {
  if (!result.value) return '读取中'
  if (result.value.status === 'CURRENT') return `CURRENT · rev ${result.value.revision}`
  if (result.value.status === 'STALE') return `STALE · rev ${result.value.revision}`
  return 'NOT_BUILT · 尚未生成'
})
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
    ? '请先在上方 P7「源作概览分析」重新运行整集原片理解，生成新的 CURRENT SOURCE_BIBLE。'
    : '请先在上方 P7「源作概览分析」运行整集原片理解，待 SOURCE_BIBLE 变为 CURRENT。'
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
      errorMessage.value = error instanceof Error ? error.message : 'P8 任务状态读取失败'
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
    errorMessage.value = error instanceof Error ? error.message : 'P8 逐镜精细拉片加载失败'
  } finally {
    loading.value = false
  }
}

async function runP8(): Promise<void> {
  if (taskActive.value) return
  if (!sourceBibleReady.value) {
    errorMessage.value = `P8 前置未就绪：${sourceBibleStatusText.value}。${sourceBibleRecoveryText.value}`
    return
  }
  starting.value = true
  errorMessage.value = ''
  try {
    const task = await startShotBreakdown(projectId.value, commandKey())
    activeTask.value = task
    startPolling(task.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P8 任务启动失败'
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
  <section v-if="visible" class="p8-panel">
    <details open>
      <summary>
        <div>
          <strong>P8 开发验收 · 逐镜精细拉片</strong>
          <span>完整 Episode + CURRENT Source Bible + P5 Shot Anchors + P6 canonical Evidence → SOURCE_SHOT_FACTS</span>
        </div>
        <small>{{ statusText }}</small>
      </summary>

      <div class="panel-body">
        <div class="principle">
          <strong>source-bible-shot-facts-v1</strong>
          <span>镜头时间只认 P5；对白正文只认 P6 canonical Evidence；人物、场景、道具只能绑定 P7 candidate；逐镜视觉、镜头语言和声音描述必须直接观察完整 Episode。Reference Clip 只用于下面的局部人工核对。</span>
        </div>

        <div
          v-if="sourceBible"
          class="prerequisite"
          :class="sourceBibleReady ? 'ready' : 'blocked'"
          data-testid="p8-source-bible-preflight"
        >
          <div>
            <strong>P7 SOURCE_BIBLE</strong>
            <span>{{ sourceBibleStatusText }}</span>
            <small v-if="!sourceBibleReady">{{ sourceBibleRecoveryText }}</small>
          </div>
          <b>{{ sourceBibleReady ? 'P8 前置已就绪' : 'P8 暂不可运行' }}</b>
        </div>

        <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        <p v-if="loading" class="muted">正在读取 P8 状态…</p>

        <template v-else>
          <div class="toolbar">
            <div class="provider-line">
              <span>Provider</span>
              <strong>{{ result?.provenance?.provider ?? '沿用项目 Source Understanding Provider' }}</strong>
              <span>{{ result?.provenance?.model ?? '待真实调用' }}</span>
            </div>
            <div class="actions">
              <button
                type="button"
                :disabled="starting || taskActive || !sourceBibleReady"
                :title="sourceBibleReady ? '' : sourceBibleRecoveryText"
                @click="runP8"
              >
                {{ starting ? '正在提交…' : result?.status === 'CURRENT' ? '重新运行逐镜精细拉片' : '运行逐镜精细拉片' }}
              </button>
              <button class="secondary" type="button" :disabled="taskActive" @click="refreshResult">刷新结果</button>
            </div>
          </div>

          <div v-if="activeTask" class="task-strip">
            <div>
              <strong>{{ activeTask.task_name }}</strong>
              <span>{{ activeTask.status }} · attempt {{ activeTask.attempt }}/{{ activeTask.max_attempts }}</span>
            </div>
            <b>{{ activeTask.progress_percent }}%</b>
          </div>

          <p v-if="result?.status === 'STALE'" class="stale-note">
            上游 SOURCE_VIDEO / SOURCE_BIBLE / SHOT_ANCHORS / canonical Source Evidence 已变化；以下保留旧 revision 供核对，但不能再作为 CURRENT 下游输入。
          </p>

          <div v-if="result?.content && result.provenance" class="metrics">
            <article><span>Artifact revision</span><strong>{{ result.revision }}</strong></article>
            <article><span>Episode</span><strong>{{ result.content.episodes.length }}</strong></article>
            <article><span>Shots</span><strong>{{ result.content.episodes.reduce((sum, episode) => sum + episode.shots.length, 0) }}</strong></article>
            <article><span>Schema</span><strong>{{ result.content.schema_version }}</strong></article>
            <article><span>ProviderJob</span><strong>{{ result.provenance.provider_jobs.length }}</strong></article>
          </div>

          <template v-if="result?.content">
            <article v-for="episode in result.content.episodes" :key="episode.episode_id" class="episode-result">
              <header class="episode-heading">
                <div>
                  <span class="eyebrow">Episode {{ episode.episode_order }}</span>
                  <h3>{{ episode.source_filename }}</h3>
                </div>
                <strong>{{ episode.shots.length }} 镜头</strong>
              </header>

              <div class="shot-table-wrap">
                <table class="shot-table">
                  <thead>
                    <tr>
                      <th>镜头</th>
                      <th>源片段 / 时长</th>
                      <th>画面描述</th>
                      <th>镜头语言</th>
                      <th>绑定主体</th>
                      <th>对白 / 旁白</th>
                      <th>音效 / 环境声</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="shot in episode.shots" :key="shot.shot_anchor_id" :data-testid="`p8-shot-${shot.shot_number}`">
                      <td class="shot-number-cell">
                        <strong>#{{ String(shot.shot_number).padStart(3, '0') }}</strong>
                        <small>{{ formatTime(shot.start_us) }}<br />→ {{ formatTime(shot.end_us) }}</small>
                      </td>
                      <td class="source-cell">
                        <button class="clip-button" type="button" @click="openPreview(episode.episode_id, shot)">▶ Reference Clip</button>
                        <span>{{ formatDuration(shot.duration_us) }}</span>
                        <small>P5 · {{ shortId(shot.shot_anchor_id) }}</small>
                      </td>
                      <td class="visual-cell">
                        <p>{{ shot.visual_description }}</p>
                        <small v-if="shot.visual_text_evidence_ids.length">OCR overlap {{ shot.visual_text_evidence_ids.length }} 条</small>
                      </td>
                      <td class="camera-cell">
                        <dl>
                          <div><dt>景别</dt><dd>{{ shot.camera_language.shot_size }}</dd></div>
                          <div><dt>构图</dt><dd>{{ shot.camera_language.composition }}</dd></div>
                          <div><dt>角度/类型</dt><dd>{{ shot.camera_language.angle_or_type }}</dd></div>
                          <div><dt>运镜</dt><dd>{{ shot.camera_language.movement }}</dd></div>
                          <div><dt>焦距/景深</dt><dd>{{ shot.camera_language.focal_length_dof }}</dd></div>
                        </dl>
                      </td>
                      <td class="binding-cell">
                        <div v-if="shot.bindings.characters.length" class="binding-group">
                          <b>人物</b><span v-for="item in shot.bindings.characters" :key="item.id">{{ item.label }}</span>
                        </div>
                        <div v-if="shot.bindings.scenes.length" class="binding-group">
                          <b>场景</b><span v-for="item in shot.bindings.scenes" :key="item.id">{{ item.label }}</span>
                        </div>
                        <div v-if="shot.bindings.props.length" class="binding-group">
                          <b>道具</b><span v-for="item in shot.bindings.props" :key="item.id">{{ item.label }}</span>
                        </div>
                        <div v-if="shot.bindings.unresolved_subject_notes.length" class="unresolved">
                          <b>未归一</b><span v-for="item in shot.bindings.unresolved_subject_notes" :key="item">{{ item }}</span>
                        </div>
                        <span v-if="!shot.bindings.characters.length && !shot.bindings.scenes.length && !shot.bindings.props.length && !shot.bindings.unresolved_subject_notes.length" class="muted">无主体绑定</span>
                      </td>
                      <td class="dialogue-cell">
                        <div v-for="line in shot.dialogue" :key="line.utterance_id" class="dialogue-line">
                          <span class="delivery" :class="`delivery-${line.delivery.toLowerCase()}`">{{ deliveryText[line.delivery] }}</span>
                          <p>{{ line.text }}</p>
                          <small>P6 #{{ line.utterance_number }} · overlap {{ formatTime(line.overlap_start_us) }} → {{ formatTime(line.overlap_end_us) }}</small>
                        </div>
                        <span v-if="!shot.dialogue.length" class="muted">无 canonical 对白 overlap</span>
                      </td>
                      <td class="sound-cell">
                        <div v-if="shot.sound_effects.length"><b>音效</b><span v-for="item in shot.sound_effects" :key="item">{{ item }}</span></div>
                        <div v-if="shot.ambience.length"><b>环境</b><span v-for="item in shot.ambience" :key="item">{{ item }}</span></div>
                        <span v-if="!shot.sound_effects.length && !shot.ambience.length" class="muted">未确认额外声音</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </article>
          </template>

          <div v-else class="empty-state">
            <strong>还没有逐镜精细拉片结果</strong>
            <span>P8 是真实重任务，页面打开不会自动调用模型。只有 P7 SOURCE_BIBLE 为 CURRENT 时才能显式运行；P5 / P6 的硬前置仍由服务端再次校验。</span>
          </div>

          <details v-if="result?.provenance" class="provenance">
            <summary>Revision / Provenance</summary>
            <div class="provenance-grid">
              <div><span>Professional Skill</span><strong>{{ result.provenance.professional_skill_id }}@{{ result.provenance.professional_skill_version }}</strong></div>
              <div><span>Source Truth contract</span><strong>{{ result.provenance.source_truth_contract }}</strong></div>
              <div><span>Prompt</span><strong>{{ result.provenance.prompt_version }}</strong></div>
              <div><span>Schema</span><strong>{{ result.provenance.schema_version }}</strong></div>
              <div><span>SOURCE_VIDEO</span><strong>{{ shortId(result.provenance.source_video_artifact_id) }}</strong></div>
              <div><span>SOURCE_BIBLE</span><strong>{{ shortId(result.provenance.source_bible_artifact_id) }}</strong></div>
              <div><span>SHOT_ANCHORS</span><strong>{{ shortId(result.provenance.shot_anchors_artifact_id) }}</strong></div>
              <div><span>SOURCE_DIALOGUE</span><strong>{{ shortId(result.provenance.source_dialogue_artifact_id) }}</strong></div>
              <div><span>ProviderJob</span><strong>{{ result.provenance.provider_jobs.length }}</strong></div>
              <div><span>Supersedes</span><strong>{{ shortId(result.provenance.supersedes_artifact_id) }}</strong></div>
            </div>
          </details>

          <details v-if="revisions.length" class="revision-history">
            <summary>历史 revisions · {{ revisions.length }}</summary>
            <div class="revision-list">
              <div v-for="item in revisions" :key="item.artifact_id">
                <strong>rev {{ item.revision }}</strong>
                <span :class="item.status.toLowerCase()">{{ item.status }}</span>
                <small>{{ shortId(item.artifact_id) }}</small>
              </div>
            </div>
          </details>
        </template>
      </div>
    </details>

    <div v-if="preview" class="preview-overlay" role="presentation" @click.self="closePreview">
      <section class="preview-dialog" role="dialog" aria-modal="true" :aria-label="`镜头 ${preview.shot.shot_number} Reference Clip`">
        <header>
          <div>
            <strong>镜头 {{ String(preview.shot.shot_number).padStart(3, '0') }}</strong>
            <span>{{ formatTime(preview.shot.start_us) }} → {{ formatTime(preview.shot.end_us) }} · {{ formatDuration(preview.shot.duration_us) }}</span>
          </div>
          <button type="button" @click="closePreview">关闭</button>
        </header>
        <video :src="referenceClipUrl(preview.episodeId, preview.shot)" controls autoplay preload="metadata"></video>
        <p>Reference Clip 只用于当前 Shot 的局部人工核对；P8 Provider 的正式默认输入仍是完整 Episode。</p>
      </section>
    </div>
  </section>
</template>

<style scoped>
.p8-panel {
  max-width: 1360px;
  margin: 18px auto 0;
  padding: 0 2px;
}

.p8-panel > details {
  overflow: hidden;
  border: 1px solid #d8dbe5;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 12px 32px rgb(20 25 50 / 6%);
}

.p8-panel > details > summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px;
  cursor: pointer;
  list-style: none;
  background: #f7f7fb;
}

.p8-panel > details > summary::-webkit-details-marker { display: none; }
.p8-panel > details > summary div { display: grid; gap: 4px; }
.p8-panel > details > summary strong { font-size: 17px; color: #22253a; }
.p8-panel > details > summary span { color: #686d82; font-size: 13px; }
.p8-panel > details > summary small { color: #5146d9; font-weight: 800; white-space: nowrap; }
.panel-body { display: grid; gap: 16px; padding: 20px 22px 24px; }

.principle {
  display: grid;
  gap: 5px;
  padding: 14px 16px;
  border: 1px solid #dedcf8;
  border-radius: 12px;
  background: #f8f7ff;
}
.principle strong { color: #4539c8; font-size: 13px; }
.principle span { color: #555a6e; font-size: 13px; line-height: 1.65; }

.prerequisite {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid;
  border-radius: 11px;
}
.prerequisite > div { display: grid; gap: 3px; }
.prerequisite strong { font-size: 12px; }
.prerequisite span { font-size: 13px; }
.prerequisite small { font-size: 12px; line-height: 1.5; }
.prerequisite > b { white-space: nowrap; font-size: 12px; }
.prerequisite.ready { border-color: #cce8d7; background: #f0faf4; color: #246b43; }
.prerequisite.blocked { border-color: #f2d5b8; background: #fff7eb; color: #8a5819; }

.toolbar, .task-strip, .episode-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}
.provider-line { display: flex; align-items: center; gap: 8px; color: #6e7284; font-size: 13px; }
.provider-line strong { color: #282b3c; }
.actions { display: flex; gap: 8px; }
.actions button, .clip-button, .preview-dialog header button {
  border: 0;
  border-radius: 9px;
  padding: 9px 13px;
  background: #5146d9;
  color: #fff;
  font: inherit;
  font-size: 13px;
  font-weight: 750;
  cursor: pointer;
}
.actions button:disabled { opacity: .5; cursor: not-allowed; }
.actions .secondary { background: #ececf4; color: #34374a; }

.task-strip {
  padding: 12px 14px;
  border-radius: 11px;
  background: #f4f5f9;
}
.task-strip div { display: grid; gap: 3px; }
.task-strip span { color: #74788b; font-size: 12px; }
.task-strip b { color: #5146d9; }

.error, .stale-note { margin: 0; padding: 11px 13px; border-radius: 10px; font-size: 13px; }
.error { background: #fff0f0; color: #a82d2d; }
.stale-note { background: #fff6df; color: #7a5612; }
.muted { color: #8a8d9d; font-size: 12px; }

.metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 9px;
}
.metrics article { display: grid; gap: 4px; padding: 11px 12px; border-radius: 10px; background: #f6f7fa; }
.metrics span { color: #777b8e; font-size: 11px; text-transform: uppercase; }
.metrics strong { color: #242738; }

.episode-result { display: grid; gap: 12px; margin-top: 4px; }
.episode-heading { padding-top: 4px; }
.episode-heading div { display: grid; gap: 2px; }
.eyebrow { color: #7168dc; font-size: 11px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; }
.episode-heading h3 { margin: 0; color: #242738; font-size: 18px; }
.episode-heading > strong { color: #585d70; font-size: 13px; }

.shot-table-wrap { overflow-x: auto; border: 1px solid #e2e4eb; border-radius: 13px; }
.shot-table { width: 100%; min-width: 1260px; border-collapse: collapse; table-layout: fixed; }
.shot-table th {
  padding: 10px 11px;
  background: #f3f4f8;
  color: #555a6e;
  text-align: left;
  font-size: 12px;
  font-weight: 800;
  border-bottom: 1px solid #dddfe7;
}
.shot-table th:nth-child(1) { width: 88px; }
.shot-table th:nth-child(2) { width: 145px; }
.shot-table th:nth-child(3) { width: 210px; }
.shot-table th:nth-child(4) { width: 250px; }
.shot-table th:nth-child(5) { width: 180px; }
.shot-table th:nth-child(6) { width: 240px; }
.shot-table th:nth-child(7) { width: 170px; }
.shot-table td { padding: 12px 11px; vertical-align: top; border-bottom: 1px solid #eceef3; color: #303344; font-size: 13px; line-height: 1.55; }
.shot-table tbody tr:last-child td { border-bottom: 0; }
.shot-table tbody tr:hover { background: #fcfcfe; }
.shot-number-cell { display: grid; gap: 7px; }
.shot-number-cell strong { color: #5146d9; font-size: 15px; }
.shot-number-cell small, .source-cell small, .visual-cell small, .dialogue-line small { color: #898c9c; font-size: 10px; }
.source-cell { display: grid; gap: 7px; }
.clip-button { padding: 7px 9px; background: #ecebff; color: #5146d9; text-align: left; }
.visual-cell p, .dialogue-line p { margin: 0; }
.camera-cell dl { display: grid; gap: 5px; margin: 0; }
.camera-cell dl div { display: grid; grid-template-columns: 58px 1fr; gap: 6px; }
.camera-cell dt { color: #898c9c; font-size: 11px; }
.camera-cell dd { margin: 0; }
.binding-cell, .sound-cell { display: grid; gap: 8px; }
.binding-group, .unresolved, .sound-cell > div { display: grid; gap: 4px; }
.binding-group b, .unresolved b, .sound-cell b { color: #7a7e91; font-size: 10px; text-transform: uppercase; }
.binding-group span, .sound-cell span { display: block; }
.unresolved span { color: #9a681c; }
.dialogue-cell { display: grid; gap: 10px; }
.dialogue-line { display: grid; gap: 4px; }
.delivery { width: fit-content; padding: 2px 6px; border-radius: 999px; background: #eeedf9; color: #5146d9; font-size: 10px; font-weight: 800; }
.delivery-voiceover { background: #eaf6ef; color: #267249; }
.delivery-offscreen { background: #fff2df; color: #9a6419; }
.delivery-unknown { background: #f0f1f4; color: #6f7382; }

.empty-state { display: grid; gap: 5px; padding: 24px; border: 1px dashed #d9dbe5; border-radius: 12px; text-align: center; color: #74788a; }
.empty-state strong { color: #343747; }
.provenance, .revision-history { border-top: 1px solid #eceef3; padding-top: 12px; }
.provenance summary, .revision-history summary { cursor: pointer; color: #555a70; font-size: 13px; font-weight: 800; }
.provenance-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; margin-top: 11px; }
.provenance-grid div { display: grid; gap: 3px; padding: 9px 10px; border-radius: 8px; background: #f7f8fa; }
.provenance-grid span { color: #898c9b; font-size: 10px; }
.provenance-grid strong { overflow-wrap: anywhere; color: #333648; font-size: 12px; }
.revision-list { display: grid; gap: 6px; margin-top: 10px; }
.revision-list div { display: grid; grid-template-columns: 70px 80px 1fr; gap: 8px; align-items: center; padding: 8px 10px; border-radius: 8px; background: #f7f8fa; }
.revision-list span { font-size: 11px; font-weight: 800; }
.revision-list .current { color: #218650; }
.revision-list .stale { color: #9a6419; }
.revision-list small { color: #898c9b; }

.preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(17 19 30 / 66%);
}
.preview-dialog { width: min(880px, 94vw); display: grid; gap: 12px; padding: 16px; border-radius: 16px; background: #fff; box-shadow: 0 24px 70px rgb(0 0 0 / 28%); }
.preview-dialog header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.preview-dialog header div { display: grid; gap: 3px; }
.preview-dialog header span { color: #737789; font-size: 12px; }
.preview-dialog video { width: 100%; max-height: 70vh; border-radius: 10px; background: #111; }
.preview-dialog p { margin: 0; color: #777b8e; font-size: 12px; }
.preview-dialog header button { background: #ececf4; color: #34374a; }

@media (max-width: 900px) {
  .p8-panel > details > summary, .toolbar, .task-strip, .prerequisite { align-items: flex-start; flex-direction: column; }
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .provenance-grid { grid-template-columns: 1fr; }
}
</style>