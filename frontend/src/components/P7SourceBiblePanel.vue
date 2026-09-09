<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  getEpisodeSourceEvidence,
  getProject,
  listProjectEpisodes,
  listProjectTasks,
} from '@/features/projects/api'
import {
  editSourceBible,
  getSourceBible,
  listSourceBibleRevisions,
  startSourceBible,
  type SourceBibleContent,
  type SourceBibleRead,
  type SourceBibleRevisionSummary,
  type TimeRange,
} from '@/features/projects/sourceBible'
import type { EpisodeSourceEvidenceRead, ProjectRead, TaskRead } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const bible = ref<SourceBibleRead | null>(null)
const revisions = ref<SourceBibleRevisionSummary[]>([])
const evidenceText = ref<Record<string, string>>({})
const activeTask = ref<TaskRead | null>(null)
const loading = ref(true)
const starting = ref(false)
const saving = ref(false)
const editing = ref(false)
const draft = ref<SourceBibleContent | null>(null)
const errorMessage = ref('')
let pollTimer: number | null = null

const visible = computed(() => project.value?.project_type === 'REPLICA' || project.value?.project_type === 'REDRAW')
const taskActive = computed(() => activeTask.value?.status === 'queued' || activeTask.value?.status === 'running')
const statusText = computed(() => {
  if (!bible.value) return '读取中'
  if (bible.value.status === 'CURRENT') return `CURRENT · rev ${bible.value.revision}`
  if (bible.value.status === 'STALE') return `STALE · rev ${bible.value.revision}`
  return 'NOT_BUILT · 尚未生成'
})

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

function rangeText(range: TimeRange | null): string {
  return range ? `${formatTime(range.start_us)} → ${formatTime(range.end_us)}` : '未单独裁定'
}

function commandKey(): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
  return `p7-source-bible-${suffix}`.slice(0, 128)
}

function shortId(value: string | null | undefined): string {
  if (!value) return '—'
  return value.length > 18 ? `${value.slice(0, 8)}…${value.slice(-6)}` : value
}

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshEvidence(): Promise<void> {
  const episodes = await listProjectEpisodes(projectId.value)
  const results = await Promise.all(
    episodes.map(async (episode) => {
      try {
        return await getEpisodeSourceEvidence(projectId.value, episode.id)
      } catch {
        return null
      }
    }),
  )
  const next: Record<string, string> = {}
  for (const result of results.filter((item): item is EpisodeSourceEvidenceRead => Boolean(item))) {
    for (const item of result.dialogue) next[item.id] = `对白 ${formatTime(item.start_us)} · ${item.text}`
    for (const item of result.visual_text) next[item.id] = `OCR ${formatTime(item.start_us)} · ${item.text}`
  }
  evidenceText.value = next
}

async function refreshResult(): Promise<void> {
  const [result, history] = await Promise.all([
    getSourceBible(projectId.value),
    listSourceBibleRevisions(projectId.value),
  ])
  bible.value = result
  revisions.value = history
  if (result.content) await refreshEvidence()
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
      (item) => (item.status === 'queued' || item.status === 'running') && item.task_name.includes('源作概览分析'),
    )
    if (running) {
      activeTask.value = running
      startPolling(running.id)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P7 源作概览加载失败'
  } finally {
    loading.value = false
  }
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
      errorMessage.value = error instanceof Error ? error.message : 'P7 任务状态读取失败'
    }
  }, 1000)
}

async function runP7(): Promise<void> {
  if (taskActive.value) return
  starting.value = true
  errorMessage.value = ''
  try {
    const task = await startSourceBible(projectId.value, commandKey())
    activeTask.value = task
    startPolling(task.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P7 任务启动失败'
  } finally {
    starting.value = false
  }
}

function beginEdit(): void {
  if (!bible.value?.content) return
  draft.value = JSON.parse(JSON.stringify(bible.value.content)) as SourceBibleContent
  editing.value = true
}

function cancelEdit(): void {
  draft.value = null
  editing.value = false
}

async function saveEdit(): Promise<void> {
  if (!draft.value || !bible.value?.content) return
  saving.value = true
  errorMessage.value = ''
  try {
    bible.value = await editSourceBible(projectId.value, draft.value)
    revisions.value = await listSourceBibleRevisions(projectId.value)
    draft.value = null
    editing.value = false
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'SOURCE_BIBLE 新 revision 保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
onBeforeUnmount(stopPolling)
</script>

<template>
  <section v-if="visible" class="p7-panel">
    <details open>
      <summary>
        <div>
          <strong>P7 开发验收 · 源作概览分析</strong>
          <span>完整 Episode + CURRENT Source Evidence → SOURCE_BIBLE</span>
        </div>
        <small>{{ statusText }}</small>
      </summary>

      <div class="panel-body">
        <div class="principle">
          <strong>输入契约</strong>
          <span>完整 Episode 是 Source Truth；P6 canonical 对白/OCR 是文字证据事实源；CURRENT Shot Anchors 仅为可选定位提示。语义时间窗口允许重叠，绝不冒充 Shot Boundary。</span>
        </div>

        <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        <p v-if="loading" class="muted">正在读取 P7 状态…</p>

        <template v-else>
          <div class="toolbar">
            <div class="provider-line">
              <span>Provider</span>
              <strong>{{ bible?.provenance?.provider ?? '待真实调用' }}</strong>
              <span>{{ bible?.provenance?.model ?? '待真实调用' }}</span>
            </div>
            <div class="actions">
              <button type="button" :disabled="starting || taskActive" @click="runP7">
                {{ starting ? '正在提交…' : bible?.status === 'CURRENT' ? '重新运行整集多模态理解' : '运行整集多模态理解' }}
              </button>
              <button class="secondary" type="button" :disabled="taskActive" @click="refreshResult">刷新结果</button>
              <button v-if="bible?.status === 'CURRENT' && bible.content && !editing" class="secondary" type="button" @click="beginEdit">编辑 SOURCE_BIBLE</button>
            </div>
          </div>

          <div v-if="activeTask" class="task-strip">
            <div>
              <strong>{{ activeTask.task_name }}</strong>
              <span>{{ activeTask.status }} · attempt {{ activeTask.attempt }}/{{ activeTask.max_attempts }}</span>
            </div>
            <b>{{ activeTask.progress_percent }}%</b>
          </div>

          <div v-if="bible?.content && bible.provenance" class="metrics">
            <article><span>Artifact revision</span><strong>{{ bible.revision }}</strong></article>
            <article><span>Episode</span><strong>{{ bible.content.episodes.length }}</strong></article>
            <article><span>Schema</span><strong>{{ bible.content.schema_version }}</strong></article>
            <article><span>ProviderJob</span><strong>{{ bible.provenance.provider_jobs.length }}</strong></article>
            <article><span>Story Skeleton</span><strong>{{ bible.story_skeleton_artifact_id ? 'CURRENT' : '—' }}</strong></article>
            <article><span>Rhythm Skeleton</span><strong>{{ bible.rhythm_skeleton_artifact_id ? 'CURRENT' : '—' }}</strong></article>
          </div>

          <div v-if="editing && draft" class="editor">
            <div class="section-title">
              <div>
                <strong>人工编辑 SOURCE_BIBLE</strong>
                <span>保存会生成新 revision；旧 revision 与基于旧版本的 Story/Rhythm 会变为 STALE，canonical Source Evidence 不会被修改。</span>
              </div>
            </div>
            <article v-for="episode in draft.episodes" :key="episode.material_baseline.episode_id" class="edit-card">
              <h4>第 {{ episode.material_baseline.episode_order }} 集 · 总体分析</h4>
              <label><span>故事概述</span><textarea v-model="episode.overall_analysis.story_summary" rows="3" /></label>
              <label><span>故事背景</span><textarea v-model="episode.overall_analysis.story_background" rows="3" /></label>
              <label><span>叙事结构</span><textarea v-model="episode.overall_analysis.narrative_structure" rows="3" /></label>
              <label><span>视听风格</span><textarea v-model="episode.overall_analysis.audiovisual_style" rows="3" /></label>
              <label><span>节奏概述</span><textarea v-model="episode.overall_analysis.rhythm_overview" rows="3" /></label>
            </article>
            <div class="actions">
              <button type="button" :disabled="saving" @click="saveEdit">{{ saving ? '正在生成新 revision…' : '保存为新 revision' }}</button>
              <button class="secondary" type="button" :disabled="saving" @click="cancelEdit">取消</button>
            </div>
          </div>

          <template v-if="bible?.content && !editing">
            <article v-for="episode in bible.content.episodes" :key="episode.material_baseline.episode_id" class="episode-result">
              <header class="episode-heading">
                <div>
                  <span class="eyebrow">Episode {{ episode.material_baseline.episode_order }}</span>
                  <h3>{{ episode.material_baseline.source_filename }}</h3>
                </div>
                <strong>{{ formatTime(episode.material_baseline.media_duration_us) }}</strong>
              </header>

              <section class="result-section">
                <div class="section-title"><strong>素材基线</strong><span>媒体事实由服务端 Episode/SourceAsset 固化，不交给模型改写</span></div>
                <div class="baseline-grid">
                  <span>{{ episode.material_baseline.width }}×{{ episode.material_baseline.height }}</span>
                  <span>{{ episode.material_baseline.aspect_ratio }}</span>
                  <span>{{ episode.material_baseline.avg_frame_rate }} fps</span>
                  <span>{{ episode.material_baseline.codec_name }}</span>
                  <span>{{ episode.material_baseline.has_audio ? '含音轨' : '无音轨' }}</span>
                  <span>有效内容 {{ rangeText(episode.material_baseline.effective_content_range) }}</span>
                </div>
                <p v-if="episode.material_baseline.visual_format_notes.length" class="tags">
                  <span v-for="item in episode.material_baseline.visual_format_notes" :key="item">{{ item }}</span>
                </p>
              </section>

              <section class="result-section analysis-grid">
                <div><strong>故事概述</strong><p>{{ episode.overall_analysis.story_summary }}</p></div>
                <div><strong>故事背景</strong><p>{{ episode.overall_analysis.story_background }}</p></div>
                <div><strong>叙事结构</strong><p>{{ episode.overall_analysis.narrative_structure }}</p></div>
                <div><strong>视听风格</strong><p>{{ episode.overall_analysis.audiovisual_style }}</p></div>
                <div><strong>节奏概述</strong><p>{{ episode.overall_analysis.rhythm_overview }}</p></div>
                <div class="analysis-fact-block">
                  <strong>类型</strong>
                  <p v-if="episode.overall_analysis.genre.length" class="inline-tags">
                    <span v-for="item in episode.overall_analysis.genre" :key="item">{{ item }}</span>
                  </p>
                  <p v-else class="muted">未归纳类型</p>
                </div>
                <div class="analysis-fact-block world-rules">
                  <strong>世界规则</strong>
                  <ul v-if="episode.overall_analysis.world_rules.length">
                    <li v-for="item in episode.overall_analysis.world_rules" :key="item">{{ item }}</li>
                  </ul>
                  <p v-else class="muted">无明确片内世界规则</p>
                </div>
              </section>

              <section class="result-section">
                <div class="section-title"><strong>时间化原作剧情</strong><span>语义窗口可重叠；证据默认折叠，可按需反查 P6 canonical 正文</span></div>
                <div class="timeline">
                  <article v-for="segment in episode.timed_script" :key="segment.segment_number" class="timeline-row">
                    <div class="time">{{ rangeText(segment.time_range) }}</div>
                    <div>
                      <strong>#{{ segment.segment_number }} · {{ segment.narrative_function }}</strong>
                      <p>{{ segment.visual_description }}</p>
                      <p class="story">{{ segment.story_summary }}</p>
                      <details v-if="segment.dialogue_evidence_ids.length || segment.visual_text_evidence_ids.length" class="evidence-disclosure">
                        <summary>
                          <span>证据 · 对白 {{ segment.dialogue_evidence_ids.length }} 条 · OCR {{ segment.visual_text_evidence_ids.length }} 条</span>
                          <small>查看依据</small>
                        </summary>
                        <div class="evidence-refs">
                          <span v-for="id in [...segment.dialogue_evidence_ids, ...segment.visual_text_evidence_ids]" :key="id">
                            {{ evidenceText[id] ?? `Evidence ${shortId(id)}` }}
                          </span>
                        </div>
                      </details>
                    </div>
                  </article>
                </div>
              </section>

              <div class="two-column">
                <section class="result-section">
                  <div class="section-title"><strong>人物与关系</strong><span>{{ episode.characters.length }} 人</span></div>
                  <article v-for="character in episode.characters" :key="character.character_id" class="compact-card">
                    <strong>{{ character.name }}</strong>
                    <p>{{ character.story_function }}</p>
                    <small>{{ character.appearance_baseline }}</small>
                  </article>
                  <p v-for="relation in episode.relationships" :key="`${relation.source_character_id}-${relation.target_character_id}`" class="relation">
                    {{ relation.source_character_id }} → {{ relation.target_character_id }}：{{ relation.relationship }}
                  </p>
                </section>

                <section class="result-section">
                  <div class="section-title"><strong>场景与关键道具</strong><span>{{ episode.scenes.length }} 场景 · {{ episode.key_props.length }} 道具</span></div>
                  <article v-for="scene in episode.scenes" :key="scene.scene_id" class="compact-card">
                    <strong>{{ scene.name }}</strong><p>{{ scene.environment_details }}</p><small>{{ scene.spatial_relationship }}</small>
                  </article>
                  <article v-for="prop in episode.key_props" :key="prop.prop_id" class="compact-card">
                    <strong>{{ prop.name }}</strong><p>{{ prop.story_function ?? '未确认独立剧情作用' }}</p><small>{{ prop.appearance_state }}</small>
                  </article>
                </section>
              </div>

              <div class="two-column">
                <section class="result-section">
                  <div class="section-title"><strong>关键事件 / Story Skeleton</strong><span>{{ episode.story_skeleton.beats.length }} beats</span></div>
                  <p><b>Premise：</b>{{ episode.story_skeleton.premise }}</p>
                  <p><b>Central Conflict：</b>{{ episode.story_skeleton.central_conflict }}</p>
                  <article v-for="beat in episode.story_skeleton.beats" :key="`${beat.beat_type}-${beat.time_range.start_us}`" class="beat-row">
                    <span>{{ beat.beat_type }} · {{ rangeText(beat.time_range) }}</span><p>{{ beat.summary }}</p>
                  </article>
                  <article v-for="event in episode.story_events" :key="event.event_id" class="beat-row">
                    <span>EVENT · {{ rangeText(event.time_range) }}</span><p>{{ event.summary }} → {{ event.consequences }}</p>
                  </article>
                </section>

                <section class="result-section">
                  <div class="section-title"><strong>Rhythm Skeleton</strong><span>{{ episode.rhythm_skeleton.phases.length }} phases</span></div>
                  <p>{{ episode.rhythm_skeleton.overall_pace }}</p>
                  <article v-for="phase in episode.rhythm_skeleton.phases" :key="`${phase.time_range.start_us}-${phase.time_range.end_us}`" class="beat-row">
                    <span>{{ phase.pace }} · {{ rangeText(phase.time_range) }} · ±{{ phase.allowable_deviation_ms }}ms</span>
                    <p>{{ phase.scene_rhythm }}</p>
                    <small>{{ phase.dialogue_reaction_rhythm }} · {{ phase.cut_timing_notes }}</small>
                  </article>
                </section>
              </div>
            </article>

            <details class="provenance">
              <summary><strong>Revision / Provenance</strong><span>{{ revisions.length }} 个 SOURCE_BIBLE revision · 展开技术审计详情</span></summary>
              <div v-if="bible.provenance" class="provenance-body">
                <section class="provenance-section">
                  <strong>生成</strong>
                  <div class="audit-grid">
                    <span>Provider</span><b>{{ bible.provenance.provider ?? '—' }}</b>
                    <span>Model</span><b>{{ bible.provenance.model ?? '—' }}</b>
                    <span>Generated Task</span><b>{{ shortId(bible.provenance.generated_by_task_id) }}</b>
                    <span>ProviderJob</span><b>{{ bible.provenance.provider_jobs.length }} 个</b>
                  </div>
                  <div v-if="bible.provenance.provider_jobs.length" class="provider-job-list">
                    <span v-for="job in bible.provenance.provider_jobs" :key="job.provider_job_id">
                      {{ shortId(job.provider_job_id) }} · {{ job.provider }} / {{ job.model }}<template v-if="job.remote_job_id"> · remote {{ shortId(job.remote_job_id) }}</template>
                    </span>
                  </div>
                </section>

                <section class="provenance-section">
                  <strong>分析契约</strong>
                  <div class="audit-grid">
                    <span>Schema</span><b>{{ bible.provenance.schema_version }}</b>
                    <span>Prompt</span><b>{{ bible.provenance.prompt_version }}</b>
                    <span>Professional Skill</span><b>{{ bible.provenance.professional_skill_id ?? '—' }}<template v-if="bible.provenance.professional_skill_version">@{{ bible.provenance.professional_skill_version }}</template></b>
                    <span>Grounding</span><b>{{ bible.provenance.grounding_contract ?? '—' }}</b>
                  </div>
                </section>

                <section class="provenance-section">
                  <strong>上游</strong>
                  <div class="audit-grid">
                    <span>Source Video</span><b>{{ shortId(bible.provenance.source_video_artifact_id) }} · {{ shortId(bible.provenance.source_video_fingerprint) }}</b>
                    <span>Source Evidence</span><b>{{ shortId(bible.provenance.source_dialogue_artifact_id) }} · {{ shortId(bible.provenance.source_dialogue_fingerprint) }}</b>
                    <span>Shot Anchors</span><b>{{ shortId(bible.provenance.shot_anchors_artifact_id) }}（可选）</b>
                    <span>Input fingerprint</span><b>{{ shortId(bible.input_fingerprint) }}</b>
                  </div>
                  <p v-if="bible.provenance.edit_parent_artifact_id">编辑父版本：{{ shortId(bible.provenance.edit_parent_artifact_id) }}</p>
                </section>

                <section class="provenance-section">
                  <strong>Revision</strong>
                  <div class="revision-list">
                    <span v-for="item in revisions" :key="item.artifact_id">rev {{ item.revision }} · {{ item.status }} · {{ shortId(item.artifact_id) }}</span>
                  </div>
                </section>
              </div>
            </details>
          </template>

          <div v-else-if="bible?.status === 'STALE'" class="stale-note">
            当前只剩旧 SOURCE_BIBLE。上游 Source/Evidence 已变化，旧版本保留可读但不能作为 CURRENT 下游输入。
          </div>
          <div v-else-if="bible?.status === 'NOT_BUILT'" class="empty-state">
            <strong>还没有《源作概览分析》</strong>
            <span>先确保所有当前 Episode 的 P6 Source Evidence 已完成，再显式运行 P7。页面 GET 不会自动调用模型。</span>
          </div>

          <div class="acceptance-checklist">
            <strong>真实短剧人工验收</strong>
            <span>① 故事梗概/背景/结构与整集成立；② 人物关系、场景、道具、事件不靠单镜头臆测；③ 时间化剧情与完整原片同步且允许语义窗口重叠；④ Evidence 引用能反查 P6 正文且正文不被模型改写；⑤ 编辑后出现 rev2、rev1/旧 Story/Rhythm STALE；⑥ ProviderJob、模型、Prompt/Skill/Grounding、上游 fingerprint 可追溯；⑦ 记录真实 API 延迟与成本。验收通过前不进入 P8。</span>
          </div>
        </template>
      </div>
    </details>
  </section>
</template>

<style scoped>
.p7-panel { max-width: 1360px; margin: 18px auto 0; border: 1px dashed #bbb9ca; border-radius: 16px; background: #fff; }
summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 18px; cursor: pointer; list-style: none; }
summary::-webkit-details-marker { display: none; }
summary > div { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
summary strong { font-size: 13px; }
summary span, summary small { color: #777771; font-size: 11px; }
.panel-body { display: grid; gap: 14px; padding: 16px 18px 20px; border-top: 1px solid #ecebe8; }
.principle, .acceptance-checklist, .stale-note, .empty-state { display: grid; gap: 5px; margin: 0; padding: 11px 13px; border-radius: 10px; background: #f7f6ff; font-size: 12px; line-height: 1.6; }
.acceptance-checklist { background: #f7f7f4; }
.stale-note { background: #fff8e8; }
.error { margin: 0; color: #a33b32; font-size: 12px; }
.muted { margin: 0; color: #777771; font-size: 12px; }
.toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.provider-line { display: flex; align-items: baseline; gap: 8px; font-size: 12px; }
.provider-line span { color: #777771; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
button { min-height: 36px; padding: 0 13px; border: 1px solid #20201d; border-radius: 9px; background: #20201d; color: #fff; font-weight: 750; cursor: pointer; }
button.secondary { border-color: #d6d6d0; background: #fff; color: #20201d; }
button:disabled { opacity: .55; cursor: wait; }
.task-strip { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; border: 1px solid #e5e5df; border-radius: 9px; background: #fafaf8; }
.task-strip > div { display: grid; gap: 3px; }
.task-strip span { color: #777771; font-size: 11px; }
.metrics { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }
.metrics article { display: grid; gap: 4px; padding: 10px; border: 1px solid #ecebe8; border-radius: 9px; }
.metrics span { color: #777771; font-size: 10px; }
.metrics strong { font-size: 13px; }
.episode-result { display: grid; gap: 12px; padding-top: 6px; }
.episode-heading { display: flex; align-items: end; justify-content: space-between; border-bottom: 1px solid #ecebe8; padding-bottom: 9px; }
.episode-heading h3 { margin: 2px 0 0; font-size: 17px; }
.eyebrow { color: #777771; font-size: 10px; font-weight: 800; text-transform: uppercase; }
.result-section { padding: 12px; border: 1px solid #e8e7e2; border-radius: 10px; background: #fff; }
.section-title { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin-bottom: 9px; }
.section-title span { color: #777771; font-size: 10px; }
.baseline-grid { display: flex; flex-wrap: wrap; gap: 7px; }
.baseline-grid span, .tags span, .inline-tags span { padding: 5px 7px; border-radius: 6px; background: #f4f4f1; font-size: 11px; }
.tags, .inline-tags { display: flex; gap: 6px; flex-wrap: wrap; margin: 9px 0 0; }
.analysis-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.analysis-grid > div { min-width: 0; }
.analysis-grid p, .compact-card p, .beat-row p, .result-section > p { margin: 4px 0 0; font-size: 12px; line-height: 1.55; }
.analysis-fact-block { padding-top: 2px; }
.world-rules ul { margin: 5px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.55; }
.timeline { display: grid; gap: 8px; }
.timeline-row { display: grid; grid-template-columns: 130px minmax(0, 1fr); gap: 12px; padding: 9px 0; border-top: 1px solid #f0efeb; }
.timeline-row:first-child { border-top: 0; }
.time { color: #5f5f5a; font-size: 11px; font-variant-numeric: tabular-nums; }
.timeline-row p { margin: 4px 0; font-size: 12px; line-height: 1.55; }
.timeline-row p.story { color: #555550; }
.evidence-disclosure { margin-top: 7px; border: 1px solid #ecebf2; border-radius: 7px; background: #fafafe; }
.evidence-disclosure summary { padding: 6px 8px; }
.evidence-disclosure summary span { color: #55556a; font-size: 10px; font-weight: 750; }
.evidence-disclosure summary small { margin-left: auto; }
.evidence-disclosure[open] summary { border-bottom: 1px solid #ecebf2; }
.evidence-refs { display: grid; gap: 3px; padding: 7px 8px 8px; }
.evidence-refs span { padding: 5px 7px; border-left: 2px solid #c8c7d8; background: #fff; color: #55556a; font-size: 10px; }
.two-column { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.compact-card, .beat-row { padding: 8px 0; border-top: 1px solid #f0efeb; }
.compact-card:first-of-type, .beat-row:first-of-type { border-top: 0; }
.compact-card small, .beat-row small { color: #777771; font-size: 10px; line-height: 1.5; }
.relation { padding: 7px; background: #f8f8f5; border-radius: 6px; font-size: 11px !important; }
.beat-row > span { color: #666660; font-size: 10px; font-weight: 800; }
.editor { display: grid; gap: 12px; padding: 14px; border: 1px solid #cfcddd; border-radius: 11px; background: #fafafe; }
.edit-card { display: grid; gap: 8px; }
.edit-card h4 { margin: 0; }
.edit-card label { display: grid; gap: 4px; }
.edit-card label span { color: #666660; font-size: 10px; font-weight: 800; }
textarea { width: 100%; box-sizing: border-box; padding: 8px 9px; border: 1px solid #d8d8d2; border-radius: 7px; resize: vertical; font: inherit; line-height: 1.5; }
.provenance { border: 1px solid #ecebe8; border-radius: 10px; }
.provenance summary { padding: 10px 12px; }
.provenance-body { display: grid; gap: 12px; padding: 0 12px 12px; font-size: 10px; color: #666660; }
.provenance-body p { margin: 5px 0; }
.provenance-section { display: grid; gap: 7px; padding-top: 10px; border-top: 1px solid #f0efeb; }
.provenance-section:first-child { border-top: 0; }
.provenance-section > strong { color: #31312d; font-size: 11px; }
.audit-grid { display: grid; grid-template-columns: 120px minmax(0, 1fr); gap: 5px 10px; align-items: baseline; }
.audit-grid span { color: #888880; }
.audit-grid b { min-width: 0; overflow-wrap: anywhere; color: #4f4f49; font-weight: 650; }
.provider-job-list { display: grid; gap: 4px; }
.provider-job-list span { padding: 5px 7px; border-radius: 5px; background: #f7f7f4; overflow-wrap: anywhere; }
.revision-list { display: flex; gap: 6px; flex-wrap: wrap; }
.revision-list span { padding: 4px 6px; background: #f4f4f1; border-radius: 5px; }
@media (max-width: 900px) {
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .analysis-grid, .two-column { grid-template-columns: 1fr; }
  .toolbar { align-items: stretch; flex-direction: column; }
  .timeline-row { grid-template-columns: 1fr; gap: 4px; }
  .audit-grid { grid-template-columns: 1fr; gap: 2px; }
}
</style>
