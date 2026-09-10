<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getProject, listProjectTasks } from '@/features/projects/api'
import { dialogueContinuityText } from '@/features/projects/dialogueContinuity'
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
    return `STALE${sourceBible.value.revision == null ? '' : ` · rev ${sourceBible.value.revision}`} · 该 P7 revision 已失效`
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
      <div>
        <p class="section-kicker">原片理解 · 逐镜拉片</p>
        <div class="title-line">
          <h2>逐镜分镜表</h2>
          <span class="status-pill" :class="statusClass">{{ statusText }}</span>
        </div>
        <p class="workspace-subtitle">逐镜核对源片段、画面、镜头语言、主体、说话人、对白和声音。</p>
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

    <div class="preflight-strip" data-testid="p8-source-bible-preflight">
      <b>P7 SOURCE_BIBLE</b>
      <span>{{ sourceBibleStatusText }}</span>
      <em v-if="sourceBibleReady">P8 前置已就绪</em>
      <small v-else>{{ sourceBibleRecoveryText }}</small>
    </div>

    <p v-if="errorMessage" class="message error-message">{{ errorMessage }}</p>
    <p v-if="loading" class="loading-message">正在读取逐镜拉片结果…</p>

    <template v-else>
      <div v-if="sourceBible && !sourceBibleReady" class="dependency-alert">
        <div>
          <strong>需要先完成「源作概览分析」</strong>
          <span>{{ sourceBibleStatusText }}</span>
          <small>{{ sourceBibleRecoveryText }}</small>
        </div>
        <b>暂不可运行</b>
      </div>

      <div v-if="activeTask" class="task-progress">
        <div>
          <strong>{{ activeTask.task_name }}</strong>
          <span>{{ activeTask.status }} · attempt {{ activeTask.attempt }}/{{ activeTask.max_attempts }}</span>
        </div>
        <div class="progress-right">
          <b>{{ activeTask.progress_percent }}%</b>
          <div class="progress-track"><i :style="{ width: `${activeTask.progress_percent}%` }"></i></div>
        </div>
      </div>

      <p v-if="result?.status === 'STALE'" class="message stale-message">
        当前分镜表来自旧契约或旧上游，保留供核对；请重新分析生成包含说话人候选的新 CURRENT 结果。
      </p>

      <template v-if="result?.content">
        <div class="result-summary">
          <div><span>{{ result.content.episodes.length }} 集</span><strong>{{ totalShots }} 镜头</strong></div>
          <small>镜头时间来自 P5；对白正文来自 P6；同一 canonical utterance 跨镜时按 overlap 显示承接关系，不拆成两句。</small>
        </div>

        <!-- 产品语义索引：保留 docs/05 的八类信息，但不再硬塞成传统横向 table。 -->
        <div class="semantic-index" aria-label="逐镜分镜表字段">
          <span>镜头编号</span><span>源片段</span><span>时长</span><span>画面描述</span><span>镜头语言</span><span>绑定主体</span><span>对白 / 旁白</span><span>音效</span>
        </div>

        <article v-for="episode in result.content.episodes" :key="episode.episode_id" class="episode-board">
          <header class="episode-header">
            <div><span>第 {{ episode.episode_order }} 集</span><h3>{{ episode.source_filename }}</h3></div>
            <b>{{ episode.shots.length }} 镜头</b>
          </header>

          <div class="shot-list">
            <article
              v-for="shot in episode.shots"
              :key="shot.shot_anchor_id"
              class="shot-row"
              :data-testid="`p8-shot-${shot.shot_number}`"
            >
              <aside class="shot-meta">
                <strong>#{{ String(shot.shot_number).padStart(3, '0') }}</strong>
                <span>{{ formatTime(shot.start_us) }}</span>
                <span>→ {{ formatTime(shot.end_us) }}</span>
                <b>{{ formatDuration(shot.duration_us) }}</b>
              </aside>

              <button
                class="clip-button shot-media-button"
                type="button"
                :aria-label="`播放镜头 ${shot.shot_number} 源片段`"
                @click="openPreview(episode.episode_id, shot)"
              >
                <img :src="thumbnailUrl(episode.episode_id, shot)" :alt="`镜头 ${shot.shot_number} 缩略图`" loading="lazy" />
                <span class="play-overlay">▶</span>
              </button>

              <div class="shot-main">
                <section class="visual-block">
                  <h4>画面描述</h4>
                  <p>{{ shot.visual_description }}</p>
                </section>
                <section class="camera-block">
                  <h4>镜头语言</h4>
                  <dl>
                    <div><dt>景别</dt><dd>{{ shot.camera_language.shot_size }}</dd></div>
                    <div><dt>构图</dt><dd>{{ shot.camera_language.composition }}</dd></div>
                    <div><dt>角度</dt><dd>{{ shot.camera_language.angle_or_type }}</dd></div>
                    <div><dt>运镜</dt><dd>{{ shot.camera_language.movement }}</dd></div>
                    <div><dt>焦距 / 景深</dt><dd>{{ shot.camera_language.focal_length_dof }}</dd></div>
                  </dl>
                </section>

                <section class="binding-block">
                  <h4>绑定主体</h4>
                  <div class="binding-grid">
                    <div><b>人物</b><span v-for="item in shot.bindings.characters" :key="item.id" class="entity-chip character-chip">{{ item.label }}</span><em v-if="!shot.bindings.characters.length">—</em></div>
                    <div><b>场景</b><span v-for="item in shot.bindings.scenes" :key="item.id" class="entity-chip scene-chip">{{ item.label }}</span><em v-if="!shot.bindings.scenes.length">—</em></div>
                    <div><b>道具</b><span v-for="item in shot.bindings.props" :key="item.id" class="entity-chip prop-chip">{{ item.label }}</span><em v-if="!shot.bindings.props.length">—</em></div>
                  </div>
                  <p v-if="shot.bindings.unresolved_subject_notes.length" class="unresolved-copy">
                    待确认：{{ shot.bindings.unresolved_subject_notes.join('；') }}
                  </p>
                </section>
              </div>

              <div class="shot-audio">
                <section class="dialogue-block">
                  <h4>对白 / 旁白</h4>
                  <div
                    v-for="line in shot.dialogue"
                    :key="`${line.utterance_id}-${line.overlap_start_us}`"
                    class="dialogue-line"
                  >
                    <div class="dialogue-heading">
                      <strong class="speaker-name" :class="{ unresolved: !line.speaker }">
                        {{ line.speaker?.label ?? '说话人未确认' }}
                      </strong>
                      <span class="delivery" :class="`delivery-${line.delivery.toLowerCase()}`">{{ deliveryText[line.delivery] }}</span>
                      <span
                        v-if="dialogueContinuityText(line, shot)"
                        class="continuity"
                        :class="{ 'continuity-from-previous': line.utterance_start_us < shot.start_us }"
                        :title="`同一条 canonical 对白 #${line.utterance_number}：整句 ${formatTime(line.utterance_start_us)} → ${formatTime(line.utterance_end_us)}；本镜 ${formatTime(line.overlap_start_us)} → ${formatTime(line.overlap_end_us)}`"
                      >
                        {{ dialogueContinuityText(line, shot) }}
                      </span>
                    </div>
                    <p>{{ line.text }}</p>
                  </div>
                  <span v-if="!shot.dialogue.length" class="empty-copy">—</span>
                </section>

                <section class="sound-block">
                  <h4>声音</h4>
                  <div v-if="shot.sound_effects.length"><b>音效</b><p>{{ shot.sound_effects.join('；') }}</p></div>
                  <div v-if="shot.ambience.length"><b>环境声</b><p>{{ shot.ambience.join('；') }}</p></div>
                  <span v-if="!shot.sound_effects.length && !shot.ambience.length" class="empty-copy">—</span>
                </section>
              </div>
            </article>
          </div>
        </article>

        <details class="technical-details">
          <summary>技术信息</summary>
          <div class="technical-grid">
            <span><b>Artifact</b>{{ shortId(result.artifact_id) }}</span>
            <span><b>Schema</b>{{ result.content.schema_version }}</span>
            <span><b>Provider</b>{{ result.provenance?.provider ?? '—' }}</span>
            <span><b>Model</b>{{ result.provenance?.model ?? '—' }}</span>
            <span><b>Skill</b>{{ result.provenance?.professional_skill_id ?? '—' }}@{{ result.provenance?.professional_skill_version ?? '—' }}</span>
            <span><b>Contract</b>{{ result.provenance?.source_truth_contract ?? '—' }}</span>
          </div>
          <p>历史 revision：{{ revisions.map((item) => `rev ${item.revision} ${item.status}`).join(' · ') || '—' }}</p>
        </details>
      </template>

      <div v-else-if="result?.status === 'NOT_BUILT'" class="empty-state">
        <strong>还没有逐镜精细拉片结果</strong>
        <p>确保 P5 / P6 / P7 均为 CURRENT 后，点击“生成逐镜拉片”。</p>
      </div>
    </template>

    <div v-if="preview" class="preview-backdrop" @click.self="closePreview">
      <div class="preview-dialog" role="dialog" aria-modal="true">
        <header>
          <div>
            <strong>镜头 #{{ String(preview.shot.shot_number).padStart(3, '0') }}</strong>
            <span>{{ formatTime(preview.shot.start_us) }} → {{ formatTime(preview.shot.end_us) }}</span>
          </div>
          <button type="button" @click="closePreview">关闭</button>
        </header>
        <video :src="referenceClipUrl(preview.episodeId, preview.shot)" controls autoplay playsinline></video>
        <p>源片段用于当前镜头的局部核对；完整 Episode 仍是 P8 Source Truth。</p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.shot-breakdown-workspace {
  padding: 28px;
  background: #fff;
  border: 1px solid #e7e9ee;
  border-radius: 18px;
  color: #172033;
}
.workspace-header,.title-line,.workspace-actions,.result-summary,.episode-header,.task-progress,.dialogue-heading {
  display: flex;
  align-items: center;
}
.workspace-header,.result-summary,.episode-header,.task-progress { justify-content: space-between; gap: 20px; }
.section-kicker { margin: 0 0 5px; color: #7b8495; font-size: 12px; font-weight: 700; }
.title-line { gap: 10px; }
h2,h3,h4,p { margin-top: 0; }
h2 { margin-bottom: 0; font-size: 27px; letter-spacing: -0.02em; }
.workspace-subtitle { margin: 7px 0 0; color: #6d7688; font-size: 13px; }
.status-pill { padding: 5px 9px; border-radius: 999px; font-size: 11px; font-weight: 800; background: #f0f2f6; color: #646d7f; }
.status-pill.current { background: #eaf8ef; color: #267a48; }
.status-pill.stale { background: #fff1dc; color: #9a6414; }
.workspace-actions { gap: 8px; }
button { font: inherit; }
.primary-action,.ghost-action { border-radius: 10px; padding: 10px 15px; font-weight: 700; cursor: pointer; }
.primary-action { border: 0; background: #202632; color: white; }
.ghost-action { border: 1px solid #d9dde5; background: white; color: #333b49; }
button:disabled { opacity: .45; cursor: not-allowed; }
.preflight-strip { margin-top: 18px; min-height: 38px; display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: 10px; background: #f7f8fa; color: #657083; font-size: 12px; }
.preflight-strip b { color: #343d4d; }.preflight-strip em { margin-left: auto; color: #267a48; font-style: normal; font-weight: 700; }.preflight-strip small { margin-left: auto; color: #a05e24; }
.message,.dependency-alert,.task-progress { margin-top: 14px; border-radius: 12px; padding: 12px 14px; }
.error-message { background: #fff0f0; color: #a92b2b; }.stale-message { background: #fff6e5; color: #875f1f; }
.dependency-alert { display: flex; justify-content: space-between; gap: 20px; background: #fff3f0; color: #8e3c31; }.dependency-alert div { display: grid; gap: 4px; }
.task-progress { background: #f5f7fb; }.task-progress > div:first-child { display: grid; gap: 3px; }.progress-right { min-width: 240px; }.progress-track { height: 6px; margin-top: 5px; background: #e3e7ef; border-radius: 99px; overflow: hidden; }.progress-track i { display: block; height: 100%; background: #525f76; }
.loading-message { padding: 35px 0; color: #80899a; text-align: center; }
.result-summary { margin: 24px 0 12px; }.result-summary div { display: flex; gap: 8px; align-items: baseline; }.result-summary strong { font-size: 17px; }.result-summary small { color: #7b8495; }
.semantic-index { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 18px; color: #8992a2; font-size: 11px; }.semantic-index span { padding: 3px 7px; border: 1px solid #eceef2; border-radius: 6px; background: #fafbfc; }
.episode-board + .episode-board { margin-top: 30px; }.episode-header { margin-bottom: 12px; }.episode-header span { color: #7b8495; font-size: 12px; }.episode-header h3 { margin: 3px 0 0; font-size: 16px; }.episode-header > b { color: #687184; font-size: 12px; }
.shot-list { display: grid; gap: 12px; }
.shot-row { display: grid; grid-template-columns: 82px 138px minmax(0, 1fr) minmax(300px, 35%); gap: 16px; align-items: stretch; padding: 16px; border: 1px solid #e6e9ef; border-radius: 14px; background: #fff; }
.shot-meta { display: flex; flex-direction: column; gap: 5px; padding-top: 2px; color: #7b8495; font-size: 11px; }.shot-meta > strong { color: #172033; font-size: 17px; }.shot-meta > b { margin-top: 6px; color: #4c5566; font-size: 12px; }
.shot-media-button { position: relative; width: 138px; min-height: 238px; padding: 0; overflow: hidden; border: 0; border-radius: 10px; background: #111; cursor: pointer; }.shot-media-button img { width: 100%; height: 100%; min-height: 238px; display: block; object-fit: cover; }.play-overlay { position: absolute; left: 50%; top: 50%; translate: -50% -50%; display: grid; place-items: center; width: 42px; height: 42px; border-radius: 50%; background: rgba(255,255,255,.9); color: #161b24; box-shadow: 0 5px 18px rgba(0,0,0,.18); }
.shot-main { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(260px, .85fr); gap: 14px 18px; }
.shot-main section,.shot-audio section { min-width: 0; }.shot-main h4,.shot-audio h4 { margin-bottom: 8px; color: #687184; font-size: 11px; letter-spacing: .04em; }
.visual-block p { margin-bottom: 0; font-size: 14px; line-height: 1.75; }.camera-block dl { margin: 0; }.camera-block dl div { display: grid; grid-template-columns: 65px 1fr; gap: 8px; padding: 5px 0; border-bottom: 1px solid #f0f1f4; font-size: 12px; }.camera-block dt { color: #8a93a2; }.camera-block dd { margin: 0; line-height: 1.5; }
.binding-block { grid-column: 1 / -1; padding-top: 12px; border-top: 1px solid #eef0f4; }.binding-grid { display: flex; flex-wrap: wrap; gap: 8px 15px; }.binding-grid > div { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; }.binding-grid b { color: #8a93a2; font-size: 11px; }.binding-grid em { color: #a1a8b3; font-style: normal; }.entity-chip { padding: 4px 7px; border-radius: 7px; font-size: 11px; border: 1px solid #e0e4eb; }.character-chip { background: #f4f0ff; color: #624f9b; }.scene-chip { background: #edf8f2; color: #39765a; }.prop-chip { background: #fff5e8; color: #8c6127; }.unresolved-copy { margin: 8px 0 0; color: #9b6b32; font-size: 11px; }
.shot-audio { padding-left: 16px; border-left: 1px solid #e8ebf0; }.dialogue-line { padding: 10px 0; border-bottom: 1px solid #eef0f4; }.dialogue-line:last-child { border-bottom: 0; }.dialogue-heading { gap: 7px; margin-bottom: 6px; flex-wrap: wrap; }.speaker-name { color: #1d2430; font-size: 13px; }.speaker-name.unresolved { color: #8f98a8; }.delivery { padding: 3px 6px; border-radius: 5px; background: #eef4ff; color: #4e6b98; font-size: 10px; font-weight: 700; }.delivery-voiceover { background: #fff2d9; color: #8d601e; }.delivery-offscreen { background: #f4ecff; color: #72509e; }.delivery-unknown { background: #f0f1f3; color: #7c8490; }.continuity { padding: 3px 6px; border-radius: 5px; background: #edf8f2; color: #39765a; font-size: 10px; font-weight: 700; }.continuity-from-previous { background: #f3f0ff; color: #66539a; }.dialogue-line p { margin: 0; font-size: 14px; line-height: 1.65; }.sound-block { margin-top: 18px; padding-top: 14px; border-top: 1px solid #eef0f4; }.sound-block div { margin-bottom: 8px; }.sound-block b { color: #8a93a2; font-size: 10px; }.sound-block p { margin: 2px 0 0; font-size: 12px; line-height: 1.5; }.empty-copy { color: #a1a8b3; }
.technical-details { margin-top: 24px; border-top: 1px solid #eceef2; padding-top: 14px; color: #7b8495; font-size: 11px; }.technical-details summary { cursor: pointer; color: #505969; font-weight: 700; }.technical-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 8px; margin-top: 12px; }.technical-grid span { display: grid; gap: 2px; }.technical-grid b { color: #9aa1ad; font-size: 9px; text-transform: uppercase; }
.empty-state { padding: 50px 20px; text-align: center; color: #697386; }.empty-state strong { color: #303846; font-size: 17px; }
.preview-backdrop { position: fixed; inset: 0; z-index: 1000; display: grid; place-items: center; padding: 28px; background: rgba(17,22,30,.72); }.preview-dialog { width: min(760px, 92vw); max-height: 92vh; padding: 16px; overflow: auto; border-radius: 16px; background: #fff; }.preview-dialog header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }.preview-dialog header div { display: grid; gap: 3px; }.preview-dialog header span { color: #7b8495; font-size: 11px; }.preview-dialog header button { border: 0; background: transparent; cursor: pointer; color: #6b7484; }.preview-dialog video { width: 100%; max-height: 70vh; border-radius: 10px; background: #000; }.preview-dialog > p { margin: 10px 0 0; color: #7b8495; font-size: 11px; }
@media (max-width: 1180px) {
  .shot-row { grid-template-columns: 72px 120px minmax(0,1fr); }.shot-media-button { width: 120px; min-height: 210px; }.shot-media-button img { min-height: 210px; }.shot-audio { grid-column: 3; padding: 14px 0 0; border-left: 0; border-top: 1px solid #e8ebf0; }.shot-main { grid-template-columns: 1fr; }.binding-block { grid-column: auto; }
}
@media (max-width: 760px) {
  .shot-breakdown-workspace { padding: 16px; border-radius: 12px; }.workspace-header,.result-summary { align-items: flex-start; flex-direction: column; }.shot-row { grid-template-columns: 70px 105px 1fr; gap: 10px; padding: 12px; }.shot-media-button { width: 105px; min-height: 185px; }.shot-media-button img { min-height: 185px; }.shot-main,.shot-audio { grid-column: 1 / -1; }.shot-audio { padding-left: 0; }.preflight-strip { align-items: flex-start; flex-wrap: wrap; }.preflight-strip em,.preflight-strip small { margin-left: 0; width: 100%; }.technical-grid { grid-template-columns: 1fr; }
}
</style>