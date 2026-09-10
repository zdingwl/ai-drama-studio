<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  adjudicateEpisodeDialogue,
  getEpisodeSourceEvidence,
  getProject,
  listProjectEpisodes,
  listProjectTasks,
  startEpisodeSourceEvidence,
} from '@/features/projects/api'
import {
  VIDEO_PROJECT_TYPES,
  type DialogueManualAdjudicationPayload,
  type DialogueUtteranceRead,
  type EpisodeRead,
  type EpisodeSourceEvidenceRead,
  type ManualDialogueChoice,
  type ProjectRead,
  type TaskRead,
  type VisualTextSpanRead,
} from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const episodes = ref<EpisodeRead[]>([])
const selectedEpisodeId = ref('')
const evidence = ref<EpisodeSourceEvidenceRead | null>(null)
const activeTask = ref<TaskRead | null>(null)
const loading = ref(true)
const loadingEvidence = ref(false)
const starting = ref(false)
const savingAdjudication = ref(false)
const editingUtteranceId = ref<string | null>(null)
const editChoice = ref<ManualDialogueChoice>('ASR')
const editOcrSpanNumber = ref<number | null>(null)
const editCustomText = ref('')
const errorMessage = ref('')
const successMessage = ref('')
let taskPollTimer: number | null = null
let evidencePollTimer: number | null = null

const visible = computed(() => Boolean(project.value && VIDEO_PROJECT_TYPES.has(project.value.project_type)))
const selectedEpisode = computed(() => episodes.value.find((item) => item.id === selectedEpisodeId.value) ?? null)
const taskActive = computed(() => activeTask.value?.status === 'queued' || activeTask.value?.status === 'running')

const evidenceStatusText = computed(() => {
  if (!evidence.value) return '读取中'
  if (evidence.value.status === 'CURRENT') return 'CURRENT · 当前有效'
  if (evidence.value.status === 'STALE') return 'STALE · 原片已变化'
  return 'NOT_BUILT · 尚未提取'
})

function formatTime(us: number): string {
  const totalMs = Math.max(0, Math.round(us / 1000))
  const milliseconds = totalMs % 1000
  const totalSeconds = Math.floor(totalMs / 1000)
  const seconds = totalSeconds % 60
  const totalMinutes = Math.floor(totalSeconds / 60)
  const minutes = totalMinutes % 60
  const hours = Math.floor(totalMinutes / 60)
  const core = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(milliseconds).padStart(3, '0')}`
  return hours > 0 ? `${String(hours).padStart(2, '0')}:${core}` : core
}

function commandKey(): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
  return `p6-acceptance-${selectedEpisodeId.value}-${suffix}`.slice(0, 128)
}

function adjudicationKey(utteranceId: string): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
  return `p6-human-${selectedEpisodeId.value}-${utteranceId}-${suffix}`.slice(0, 128)
}

function isUserAdjudicated(item: DialogueUtteranceRead): boolean {
  return item.text_source.startsWith('USER_')
}

function overlappingOcr(item: DialogueUtteranceRead): VisualTextSpanRead[] {
  const rows = (evidence.value?.visual_text ?? []).filter(
    (span) => span.end_us > item.start_us && span.start_us < item.end_us,
  )
  const linked = new Set(item.ocr_span_numbers)
  return rows.sort((left, right) => {
    const linkedDelta = Number(linked.has(right.span_number)) - Number(linked.has(left.span_number))
    if (linkedDelta !== 0) return linkedDelta
    return (right.confidence ?? -1) - (left.confidence ?? -1)
  })
}

function cancelAdjudication(): void {
  editingUtteranceId.value = null
  editChoice.value = 'ASR'
  editOcrSpanNumber.value = null
  editCustomText.value = ''
}

function beginAdjudication(item: DialogueUtteranceRead): void {
  if (evidence.value?.status !== 'CURRENT' || evidence.value.revision === null || savingAdjudication.value) return
  successMessage.value = ''
  editingUtteranceId.value = item.id
  editCustomText.value = item.text
  const candidates = overlappingOcr(item)
  const linked = candidates.find((span) => item.ocr_span_numbers.includes(span.span_number))
  if ((item.text_source === 'OCR_SUBTITLE_ADJUDICATED' || item.text_source === 'USER_OCR_SELECTED') && linked) {
    editChoice.value = 'OCR'
    editOcrSpanNumber.value = linked.span_number
  } else if (item.text_source === 'USER_EDITED') {
    editChoice.value = 'CUSTOM'
    editOcrSpanNumber.value = null
  } else {
    editChoice.value = 'ASR'
    editOcrSpanNumber.value = candidates[0]?.span_number ?? null
  }
}

function canSaveAdjudication(item: DialogueUtteranceRead): boolean {
  if (savingAdjudication.value || evidence.value?.status !== 'CURRENT' || evidence.value.revision === null) return false
  if (editingUtteranceId.value !== item.id) return false
  if (editChoice.value === 'OCR') return editOcrSpanNumber.value !== null
  if (editChoice.value === 'CUSTOM') return Boolean(editCustomText.value.trim())
  return Boolean(item.asr_text?.trim() || item.text.trim())
}

async function saveAdjudication(item: DialogueUtteranceRead): Promise<void> {
  if (!canSaveAdjudication(item) || !evidence.value || evidence.value.revision === null) return
  const payload: DialogueManualAdjudicationPayload = {
    expected_revision: evidence.value.revision,
    utterance_id: item.id,
    choice: editChoice.value,
  }
  if (editChoice.value === 'OCR') payload.ocr_span_number = editOcrSpanNumber.value
  if (editChoice.value === 'CUSTOM') payload.custom_text = editCustomText.value.trim()

  savingAdjudication.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    evidence.value = await adjudicateEpisodeDialogue(
      projectId.value,
      selectedEpisodeId.value,
      payload,
      adjudicationKey(item.id),
    )
    const revision = evidence.value.revision ?? '新'
    successMessage.value = `已保存为 P6 rev ${revision}。Canonical 改变后，旧 P7 / P8 会转为 STALE；继续验收前请按 P6 → P7 → P8 恢复链重跑。`
    cancelAdjudication()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P6 人工对白裁决保存失败'
  } finally {
    savingAdjudication.value = false
  }
}

function stopEvidencePolling(): void {
  if (evidencePollTimer !== null) {
    window.clearInterval(evidencePollTimer)
    evidencePollTimer = null
  }
}

function startEvidencePolling(): void {
  if (evidencePollTimer !== null || !selectedEpisodeId.value || evidence.value?.status === 'CURRENT') return
  evidencePollTimer = window.setInterval(async () => {
    if (loadingEvidence.value || taskActive.value || savingAdjudication.value) return
    await refreshEvidence(false)
  }, 2500)
}

async function refreshEvidence(showLoading = true): Promise<void> {
  if (!selectedEpisodeId.value) {
    evidence.value = null
    stopEvidencePolling()
    cancelAdjudication()
    return
  }
  if (showLoading) loadingEvidence.value = true
  errorMessage.value = ''
  try {
    evidence.value = await getEpisodeSourceEvidence(projectId.value, selectedEpisodeId.value)
    cancelAdjudication()
    if (evidence.value.status === 'CURRENT') {
      stopEvidencePolling()
    } else {
      startEvidencePolling()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Source Evidence 读取失败'
  } finally {
    if (showLoading) loadingEvidence.value = false
  }
}

async function changeEpisode(): Promise<void> {
  activeTask.value = null
  successMessage.value = ''
  cancelAdjudication()
  stopEvidencePolling()
  await refreshEvidence()
}

function stopTaskPolling(): void {
  if (taskPollTimer !== null) {
    window.clearInterval(taskPollTimer)
    taskPollTimer = null
  }
}

function startTaskPolling(taskId: string): void {
  stopTaskPolling()
  taskPollTimer = window.setInterval(async () => {
    try {
      const tasks = await listProjectTasks(projectId.value)
      const task = tasks.find((item) => item.id === taskId) ?? null
      activeTask.value = task
      if (!task || (task.status !== 'queued' && task.status !== 'running')) {
        stopTaskPolling()
        await refreshEvidence()
      }
    } catch (error) {
      stopTaskPolling()
      errorMessage.value = error instanceof Error ? error.message : 'P6 任务状态读取失败'
    }
  }, 900)
}

async function startEvidence(): Promise<void> {
  if (!selectedEpisodeId.value || taskActive.value || savingAdjudication.value) return
  starting.value = true
  errorMessage.value = ''
  successMessage.value = ''
  cancelAdjudication()
  try {
    const task = await startEpisodeSourceEvidence(
      projectId.value,
      selectedEpisodeId.value,
      commandKey(),
    )
    activeTask.value = task
    startTaskPolling(task.id)
    startEvidencePolling()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P6 Source Evidence 任务启动失败'
  } finally {
    starting.value = false
  }
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    project.value = await getProject(projectId.value)
    if (!VIDEO_PROJECT_TYPES.has(project.value.project_type)) return
    episodes.value = await listProjectEpisodes(projectId.value)
    selectedEpisodeId.value = episodes.value[0]?.id ?? ''
    await refreshEvidence()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P6 验收面板加载失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
onBeforeUnmount(() => {
  stopTaskPolling()
  stopEvidencePolling()
})
</script>

<template>
  <section v-if="visible" class="p6-acceptance-panel">
    <details open>
      <summary>
        <div>
          <strong>P6 开发验收 · Source Evidence</strong>
          <span>真实 ASR + OCR，不是模拟任务</span>
        </div>
        <small>{{ evidenceStatusText }}</small>
      </summary>

      <div class="panel-body">
        <p class="notice">
          这里仅用于 P6 人工验收，不是普通用户独立流程。任务直接读取完整 Episode：ASR 连续读取整集音轨，OCR 扫描完整视频时间轴；Shot Anchors 只用于可选采样提示和对白投影。自动字幕校正保留完整证据；你也可以对每条 canonical 对白显式选择 ASR、时间重叠 OCR，或输入自己的文本，保存后生成新的可追溯 P6 revision。
        </p>

        <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
        <p v-if="successMessage" class="success">{{ successMessage }}</p>
        <p v-if="loading" class="muted">正在加载 P6 验收信息…</p>

        <template v-else>
          <div class="toolbar">
            <label>
              <span>验收 Episode</span>
              <select v-model="selectedEpisodeId" :disabled="taskActive || savingAdjudication" @change="changeEpisode">
                <option v-for="episode in episodes" :key="episode.id" :value="episode.id">
                  第 {{ episode.episode_order }} 集 · {{ episode.source_asset.original_filename }}
                </option>
              </select>
            </label>
            <div class="actions">
              <button type="button" :disabled="starting || taskActive || savingAdjudication || !selectedEpisodeId" @click="startEvidence">
                {{ starting ? '正在提交…' : evidence?.status === 'CURRENT' ? '重新运行真实 ASR + OCR' : '运行真实 ASR + OCR' }}
              </button>
              <button class="secondary" type="button" :disabled="loadingEvidence || taskActive || savingAdjudication || !selectedEpisodeId" @click="refreshEvidence()">
                {{ loadingEvidence ? '刷新中…' : '刷新结果' }}
              </button>
            </div>
          </div>

          <div v-if="activeTask" class="task-strip">
            <div>
              <strong>{{ activeTask.task_name }}</strong>
              <span>{{ activeTask.status }} · attempt {{ activeTask.attempt }}/{{ activeTask.max_attempts }}</span>
            </div>
            <b>{{ activeTask.progress_percent }}%</b>
          </div>

          <template v-if="evidence">
            <div class="metrics">
              <article><span>Evidence 状态</span><strong>{{ evidenceStatusText }}</strong></article>
              <article><span>Episode revision</span><strong>{{ evidence.revision ?? '—' }}</strong></article>
              <article><span>项目 Artifact revision</span><strong>{{ evidence.artifact_revision ?? '未发布' }}</strong></article>
              <article><span>Canonical 对白</span><strong>{{ evidence.dialogue_count }}</strong></article>
              <article><span>OCR 文本段</span><strong>{{ evidence.visual_text_count }}</strong></article>
              <article><span>Raw ASR / OCR</span><strong>{{ evidence.raw_asr_segment_count }} / {{ evidence.raw_ocr_observation_count }}</strong></article>
            </div>

            <p v-if="evidence.status === 'CURRENT' && evidence.artifact_revision === null" class="artifact-note">
              本集 Evidence 已 CURRENT，但当前项目还有 Episode 未完成 P6，因此项目级 SOURCE_DIALOGUE 尚未发布。所有当前 Episode 完成后才会生成正式 Artifact。
            </p>
            <p v-if="evidence.status === 'STALE'" class="stale-note">
              该结果属于旧 Source Video。请确认旧 Evidence 保留可读但不能继续作为 CURRENT 输入使用，然后重新运行当前 Episode。
            </p>

            <div class="acceptance-checklist">
              <strong>人工验收时重点看</strong>
              <span>① 对白正文与原片连续语义是否一致；② 起止时间是否贴合说话；③ 跨 Shot 的一句话是否仍是一条 canonical dialogue；④ 自动字幕校正是否有同时间 OCR 依据；⑤ 不确定时可自己选择 ASR / OCR / 自定义文本，保存会生成新 revision 并让旧下游 STALE。</span>
            </div>

            <section class="result-section">
              <div class="section-title">
                <div>
                  <strong>Canonical 对白</strong>
                  <span>正文是 P6 正式 Source Evidence；自动与人工裁决都保留 ASR / OCR provenance</span>
                </div>
                <small>{{ evidence.dialogue.length }} 条</small>
              </div>
              <div v-if="evidence.dialogue.length" class="rows">
                <article
                  v-for="item in evidence.dialogue"
                  :key="item.id"
                  class="result-row"
                  :class="{
                    adjudicated: item.text_source === 'OCR_SUBTITLE_ADJUDICATED',
                    'user-adjudicated': isUserAdjudicated(item),
                    editing: editingUtteranceId === item.id,
                  }"
                >
                  <div class="time">{{ formatTime(item.start_us) }} → {{ formatTime(item.end_us) }}</div>
                  <div class="dialogue-copy">
                    <div v-if="item.text_source === 'OCR_SUBTITLE_ADJUDICATED'" class="adjudication-heading">
                      <span class="adjudication-badge">字幕校正</span>
                      <small>OCR span {{ item.ocr_span_numbers.map((value) => `#${value}`).join(', ') }}</small>
                    </div>
                    <div v-else-if="isUserAdjudicated(item)" class="adjudication-heading">
                      <span class="adjudication-badge manual">人工确认</span>
                      <small v-if="item.text_source === 'USER_ASR_SELECTED'">采用 ASR 原文</small>
                      <small v-else-if="item.text_source === 'USER_OCR_SELECTED'">采用 OCR span {{ item.ocr_span_numbers.map((value) => `#${value}`).join(', ') }}</small>
                      <small v-else>自定义文本</small>
                    </div>
                    <p class="canonical-text">{{ item.text }}</p>
                    <p v-if="item.asr_text && item.asr_text !== item.text" class="asr-original">
                      ASR 原文：{{ item.asr_text }}
                    </p>
                    <p v-if="item.text_source === 'USER_OCR_SELECTED' && item.ocr_text" class="ocr-selected">
                      OCR 选择：{{ item.ocr_text }}
                    </p>
                    <p v-if="item.adjudication_reason === 'AMBIGUOUS_OCR_SUBTITLE_CANDIDATES'" class="evidence-conflict">
                      字幕证据存在冲突，当前保留 ASR 正文，需人工核对。
                    </p>

                    <button
                      v-if="evidence.status === 'CURRENT' && editingUtteranceId !== item.id"
                      class="inline-edit"
                      type="button"
                      :disabled="taskActive || savingAdjudication"
                      @click="beginAdjudication(item)"
                    >
                      人工确认 / 修改
                    </button>

                    <div v-if="editingUtteranceId === item.id" class="adjudication-editor">
                      <div class="editor-current">
                        <span>当前 canonical</span>
                        <strong>{{ item.text }}</strong>
                      </div>
                      <label class="choice-row">
                        <input v-model="editChoice" type="radio" value="ASR">
                        <span><b>使用 ASR 原文</b><small>{{ item.asr_text || item.text }}</small></span>
                      </label>
                      <label class="choice-row" :class="{ disabled: !overlappingOcr(item).length }">
                        <input v-model="editChoice" type="radio" value="OCR" :disabled="!overlappingOcr(item).length">
                        <span><b>使用 OCR 字幕</b><small>只能选择与这条对白时间重叠的 canonical OCR span</small></span>
                      </label>
                      <select
                        v-if="editChoice === 'OCR'"
                        v-model.number="editOcrSpanNumber"
                        class="ocr-picker"
                        :disabled="!overlappingOcr(item).length"
                      >
                        <option :value="null" disabled>选择 OCR span</option>
                        <option v-for="span in overlappingOcr(item)" :key="span.id" :value="span.span_number">
                          #{{ span.span_number }} · {{ span.confidence === null ? '无置信度' : span.confidence.toFixed(3) }} · {{ span.text }}
                        </option>
                      </select>
                      <label class="choice-row">
                        <input v-model="editChoice" type="radio" value="CUSTOM">
                        <span><b>自定义文本</b><small>你的输入会成为新的 canonical，但不会改写 raw ASR / OCR</small></span>
                      </label>
                      <textarea
                        v-if="editChoice === 'CUSTOM'"
                        v-model="editCustomText"
                        class="custom-text"
                        rows="3"
                        maxlength="4000"
                        placeholder="输入你确认后的正确台词"
                      />
                      <div class="editor-actions">
                        <button class="secondary" type="button" :disabled="savingAdjudication" @click="cancelAdjudication">
                          取消
                        </button>
                        <button type="button" :disabled="!canSaveAdjudication(item)" @click="saveAdjudication(item)">
                          {{ savingAdjudication ? '保存中…' : '保存为新 revision' }}
                        </button>
                      </div>
                    </div>
                  </div>
                  <div class="meta">
                    <span>#{{ item.utterance_number }}</span>
                    <span v-if="item.language">{{ item.language }}</span>
                    <span v-if="item.projected_shot_numbers.length">Shot {{ item.projected_shot_numbers.join(', ') }}</span>
                    <span v-else>无 Shot 投影</span>
                  </div>
                </article>
              </div>
              <p v-else class="empty">当前没有 canonical 对白。</p>
            </section>

            <section class="result-section">
              <div class="section-title">
                <div>
                  <strong>画面文字 OCR</strong>
                  <span>按完整视频时间轴采样并合并为 canonical visual text span；对白人工选择只会列出时间重叠项</span>
                </div>
                <small>{{ evidence.visual_text.length }} 条</small>
              </div>
              <div v-if="evidence.visual_text.length" class="rows">
                <article v-for="item in evidence.visual_text" :key="item.id" class="result-row">
                  <div class="time">{{ formatTime(item.start_us) }} → {{ formatTime(item.end_us) }}</div>
                  <p>{{ item.text }}</p>
                  <div class="meta">
                    <span>#{{ item.span_number }}</span>
                    <span v-if="item.confidence !== null">confidence {{ item.confidence.toFixed(3) }}</span>
                  </div>
                </article>
              </div>
              <p v-else class="empty">当前没有 canonical OCR 文本。</p>
            </section>
          </template>

          <p v-else class="muted">{{ selectedEpisode ? `正在读取第 ${selectedEpisode.episode_order} 集结果…` : '当前项目没有 Episode。' }}</p>
        </template>
      </div>
    </details>
  </section>
</template>

<style scoped>
.p6-acceptance-panel { max-width: 1360px; margin: 18px auto 0; border: 1px dashed #c9c7d8; border-radius: 16px; background: #fff; }
summary { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 18px; cursor: pointer; list-style: none; }
summary::-webkit-details-marker { display: none; }
summary > div { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
summary strong { font-size: 13px; }
summary span, summary small { color: #777771; font-size: 11px; }
.panel-body { display: grid; gap: 14px; padding: 16px 18px 18px; border-top: 1px solid #ecebe8; }
.notice, .artifact-note, .stale-note, .acceptance-checklist, .success { margin: 0; padding: 10px 12px; border-radius: 9px; font-size: 12px; line-height: 1.6; }
.notice { background: #f7f6ff; }
.artifact-note { background: #f7f7f4; }
.stale-note { background: #fff8e8; }
.success { background: #eff8ef; color: #3e6944; }
.acceptance-checklist { display: grid; gap: 4px; background: #f7f7f4; }
.acceptance-checklist span { color: #666660; }
.error { margin: 0; color: #a33b32; font-size: 12px; }
.muted, .empty { margin: 0; color: #777771; font-size: 12px; }
.toolbar { display: flex; align-items: end; justify-content: space-between; gap: 14px; }
.toolbar label { display: grid; gap: 5px; min-width: min(560px, 60%); }
.toolbar label > span { color: #6d6d67; font-size: 11px; font-weight: 800; }
select, textarea { border: 1px solid #d8d8d2; border-radius: 8px; background: #fff; color: #20201d; font: inherit; }
select { min-height: 38px; padding: 0 10px; }
textarea { width: 100%; box-sizing: border-box; padding: 9px 10px; resize: vertical; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; }
button { min-height: 36px; padding: 0 13px; border: 1px solid #20201d; border-radius: 9px; background: #20201d; color: #fff; font-weight: 750; cursor: pointer; }
button.secondary { border-color: #d6d6d0; background: #fff; color: #20201d; }
button:disabled { cursor: wait; opacity: .55; }
.task-strip { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 10px 12px; border: 1px solid #e5e5df; border-radius: 9px; background: #fafaf8; }
.task-strip > div { display: grid; gap: 3px; }
.task-strip span { color: #777771; font-size: 11px; }
.metrics { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 8px; }
.metrics article { display: grid; gap: 5px; padding: 10px; border: 1px solid #e7e7e1; border-radius: 9px; background: #fafaf8; }
.metrics span { color: #777771; font-size: 10px; }
.metrics strong { font-size: 12px; overflow-wrap: anywhere; }
.result-section { display: grid; gap: 8px; }
.section-title { display: flex; align-items: end; justify-content: space-between; gap: 12px; }
.section-title > div { display: grid; gap: 3px; }
.section-title strong { font-size: 13px; }
.section-title span, .section-title small { color: #777771; font-size: 10px; }
.rows { display: grid; gap: 6px; max-height: 520px; overflow: auto; padding-right: 3px; }
.result-row { display: grid; grid-template-columns: 170px minmax(0, 1fr) auto; gap: 10px; align-items: start; padding: 10px; border: 1px solid #e7e7e1; border-radius: 8px; background: #fff; }
.result-row.adjudicated { border-color: #d9c7ff; background: #fcfaff; }
.result-row.user-adjudicated { border-color: #bed9c2; background: #fbfefb; }
.result-row.editing { border-color: #9f8dc8; box-shadow: 0 0 0 1px #eee8ff inset; }
.result-row .time { color: #666660; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 10px; white-space: nowrap; }
.result-row p { margin: 0; font-size: 12px; line-height: 1.55; white-space: pre-wrap; }
.dialogue-copy { display: grid; gap: 6px; min-width: 0; }
.canonical-text { font-weight: 650; }
.adjudication-heading { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.adjudication-heading small { color: #8067a8; font-size: 9px; }
.adjudication-badge { padding: 2px 6px; border-radius: 5px; background: #efe7ff; color: #664796; font-size: 9px; font-weight: 800; }
.adjudication-badge.manual { background: #e8f4ea; color: #3f7047; }
.result-row .asr-original, .result-row .ocr-selected { color: #77718a; font-size: 10px; }
.result-row .evidence-conflict { color: #9a6414; font-size: 10px; }
button.inline-edit { justify-self: start; min-height: 28px; padding: 0 9px; border-color: #d6d0e5; background: #fff; color: #584b70; font-size: 10px; }
.adjudication-editor { display: grid; gap: 8px; margin-top: 4px; padding: 10px; border: 1px solid #ddd5ee; border-radius: 9px; background: #faf8ff; }
.editor-current { display: grid; gap: 3px; padding-bottom: 7px; border-bottom: 1px solid #ebe6f4; }
.editor-current span { color: #77718a; font-size: 9px; }
.editor-current strong { font-size: 12px; }
.choice-row { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; align-items: start; cursor: pointer; }
.choice-row input { margin-top: 3px; }
.choice-row > span { display: grid; gap: 2px; }
.choice-row b { font-size: 11px; }
.choice-row small { color: #777771; font-size: 9px; line-height: 1.45; }
.choice-row.disabled { opacity: .55; cursor: not-allowed; }
.ocr-picker { width: 100%; font-size: 10px; }
.custom-text { font-size: 11px; line-height: 1.5; }
.editor-actions { display: flex; justify-content: flex-end; gap: 7px; padding-top: 2px; }
.editor-actions button { min-height: 30px; font-size: 10px; }
.meta { display: flex; justify-content: flex-end; gap: 5px; flex-wrap: wrap; max-width: 220px; }
.meta span { padding: 2px 5px; border-radius: 5px; background: #f0f0ec; color: #686863; font-size: 9px; }
@media (max-width: 980px) {
  .metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .toolbar { align-items: stretch; flex-direction: column; }
  .toolbar label { min-width: 0; }
  .result-row { grid-template-columns: 1fr; }
  .meta { justify-content: flex-start; max-width: none; }
}
@media (max-width: 620px) {
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  summary > div { display: grid; gap: 3px; }
  .actions, .actions button, .editor-actions, .editor-actions button { width: 100%; }
  .editor-actions { flex-direction: column-reverse; }
}
</style>