<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import { listTimingCandidates, type TimingCandidate } from '@/features/projects/p14'
import {
  buildTimingTriageRows,
  summarizeTimingTriage,
  summarizeTimingTriageByEpisode,
  type TimingTriageRow,
} from '@/features/projects/p14TimingTriage'
import {
  getReplicaTargetScript,
  startReplicaTargetScriptTimingRewrite,
  type ReplicaTargetScriptContent,
  type ReplicaTargetScriptRead,
} from '@/features/projects/targetScript'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const loading = ref(false)
const rewriting = ref(false)
const error = ref('')
const message = ref('')
const timingCandidates = ref<TimingCandidate[]>([])
const script = ref<ReplicaTargetScriptContent | null>(null)
const scriptResult = ref<ReplicaTargetScriptRead | null>(null)
const rewriteIds = ref<string[]>([])
let taskPollTimer: number | null = null

const latestTimingCandidate = computed(() => timingCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const rows = computed(() => buildTimingTriageRows(latestTimingCandidate.value?.content.items ?? [], script.value))
const summary = computed(() => summarizeTimingTriage(rows.value))
const episodeSummaries = computed(() => summarizeTimingTriageByEpisode(rows.value))
const rewriteRows = computed(() => rows.value.filter((row) => row.route === 'SCRIPT_REWRITE'))
const selectedRewriteCount = computed(() => rewriteIds.value.length)
const worstRows = computed(() => rows.value
  .filter((row) => row.route !== 'FIT')
  .slice()
  .sort((left, right) => right.item.overflow_us - left.item.overflow_us)
  .slice(0, 24))

function episodeLabel(order: number): string {
  return order >= 999999 ? '未知集' : `第 ${order} 集`
}

function seconds(us: number): string {
  return `${(us / 1_000_000).toFixed(2)}s`
}

function factorLabel(row: TimingTriageRow): string {
  if (row.required_duration_factor === null) return '—'
  return row.required_duration_factor.toFixed(2)
}

function routeLabel(row: TimingTriageRow): string {
  if (row.route === 'RETAKE_TRY') return '调整语速并重录'
  if (row.route === 'SCRIPT_REWRITE') return '缩短这句对白'
  return '时长合适'
}

async function refresh() {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const [candidates, currentScript] = await Promise.all([
      listTimingCandidates(projectId.value),
      getReplicaTargetScript(projectId.value),
    ])
    timingCandidates.value = candidates
    scriptResult.value = currentScript
    script.value = currentScript.content
    const allowed = new Set(buildTimingTriageRows(
      (candidates.find((item) => item.review_status === 'NEEDS_REVIEW')?.content.items ?? []),
      currentScript.content,
    ).filter((row) => row.route === 'SCRIPT_REWRITE').map((row) => row.item.utterance_id))
    rewriteIds.value = rewriteIds.value.filter((id) => allowed.has(id))
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '加载 Timing 超时分诊失败'
  } finally {
    loading.value = false
  }
}

function selectAllRewrite() {
  rewriteIds.value = rewriteRows.value.map((row) => row.item.utterance_id)
}

function clearRewriteSelection() {
  rewriteIds.value = []
}

function stopTaskPoll() {
  if (taskPollTimer !== null) {
    window.clearInterval(taskPollTimer)
    taskPollTimer = null
  }
}

function pollRewriteTask(taskId: string) {
  stopTaskPoll()
  taskPollTimer = window.setInterval(async () => {
    try {
      const tasks = await listProjectTasks(projectId.value)
      const task = tasks.find((item) => item.id === taskId)
      if (!task || task.status === 'queued' || task.status === 'running') return
      stopTaskPoll()
      rewriting.value = false
      if (task.status === 'succeeded') {
        message.value = '目标对白定向修订已发布为新版本。旧配音与 Timing 已失效，请重新生成并听审目标配音。'
        rewriteIds.value = []
        await refresh()
      } else {
        error.value = task.last_error || '目标对白定向修订未完成，请检查任务状态。'
      }
    } catch (exc) {
      stopTaskPoll()
      rewriting.value = false
      error.value = exc instanceof Error ? exc.message : '读取对白修订任务失败'
    }
  }, 1200)
}

async function rewriteSelected() {
  const timing = latestTimingCandidate.value
  const currentScript = scriptResult.value
  if (!timing || !currentScript?.artifact_id || !currentScript.revision || !rewriteIds.value.length) return
  rewriting.value = true
  error.value = ''
  message.value = ''
  try {
    const task = await startReplicaTargetScriptTimingRewrite(
      projectId.value,
      {
        expected_target_script_artifact_id: currentScript.artifact_id,
        expected_target_script_revision: currentScript.revision,
        timing_candidate_id: timing.id,
        expected_timing_generation_sequence: timing.generation_sequence,
        utterance_ids: rewriteIds.value,
      },
      crypto.randomUUID(),
    )
    if (task.status === 'succeeded') {
      rewriting.value = false
      message.value = '目标对白定向修订已完成，请重新生成目标配音。'
      rewriteIds.value = []
      await refresh()
    } else if (task.status === 'failed' || task.status === 'cancelled') {
      rewriting.value = false
      error.value = task.last_error || '目标对白定向修订启动失败'
    } else {
      message.value = `已提交 ${rewriteIds.value.length} 句目标对白定向缩写；只会修改这些句子。`
      pollRewriteTask(task.id)
    }
  } catch (exc) {
    rewriting.value = false
    error.value = exc instanceof Error ? exc.message : '启动目标对白定向修订失败'
  }
}

onMounted(() => { void refresh() })
onBeforeUnmount(stopTaskPoll)
</script>

<template>
  <section v-if="latestTimingCandidate" class="timing-triage">
    <header>
      <div>
        <p class="eyebrow">对白时长处理</p>
        <h2>处理放不下的对白</h2>
      </div>
      <button type="button" @click="refresh">刷新</button>
    </header>

    <p class="guidance">
      系统已经按每句可用时长自动分类。轻微超时可以调整语速后重录；严重超时建议只缩短当前对白。每次修改都会重新生成并测量，不会影响其他对白或原片内容。
    </p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="success">{{ message }}</p>
    <p v-if="loading">正在读取 Timing candidate 与 CURRENT Target Script…</p>

    <div class="metrics">
      <article><strong>{{ summary.total }}</strong><span>总对白</span></article>
      <article><strong>{{ summary.fit }}</strong><span>时长合适</span></article>
      <article class="warn"><strong>{{ summary.overflow }}</strong><span>需要处理</span></article>
      <article class="retake"><strong>{{ summary.retake_try }}</strong><span>建议重录</span></article>
      <article class="rewrite"><strong>{{ summary.script_rewrite }}</strong><span>建议缩短对白</span></article>
    </div>

    <div class="episode-grid">
      <article v-for="episode in episodeSummaries" :key="`${episode.episode_order}:${episode.episode_id}`" class="episode-card">
        <strong>{{ episodeLabel(episode.episode_order) }}</strong>
        <span>{{ episode.total }} 句 · 合适 {{ episode.fit }} · 需处理 {{ episode.overflow }}</span>
        <span>建议重录 {{ episode.retake_try }} · 建议缩短 {{ episode.script_rewrite }}</span>
      </article>
    </div>

    <div v-if="summary.script_rewrite" class="decision rewrite-decision">
      <strong>{{ summary.script_rewrite }} 句对白明显超出可用时长。</strong>
      <span>继续加快语速会影响自然度。建议在不改变意思和人物口吻的前提下，只缩短这些句子的最终对白。</span>
      <div class="rewrite-actions">
        <button type="button" @click="selectAllRewrite">选择全部 {{ summary.script_rewrite }} 句</button>
        <button v-if="selectedRewriteCount" type="button" @click="clearRewriteSelection">清空选择</button>
        <button class="primary" type="button" :disabled="rewriting || selectedRewriteCount === 0" @click="rewriteSelected">
          {{ rewriting ? '正在生成…' : `缩短选中的 ${selectedRewriteCount} 句` }}
        </button>
      </div>
      <small>只会修改选中的最终对白；原文、直译和其他对白保持不变。完成后需要重新配音并试听确认。</small>
    </div>
    <div v-else-if="summary.retake_try" class="decision retake-decision">
      <strong>这些对白只需小幅调整。</strong>
      <span>建议先从超时最少的句子开始，调整语速并重录，确认表达自然后再继续。</span>
    </div>

    <div v-if="worstRows.length" class="table-wrap">
      <h3>优先处理的对白</h3>
      <table>
        <thead>
          <tr>
            <th>选择</th>
            <th>集 / #</th>
            <th>最终对白</th>
            <th>可用时长</th>
            <th>语音时长</th>
            <th>超出</th>
            <th>建议语速</th>
            <th>建议处理</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in worstRows" :key="row.item.utterance_id">
            <td><input v-if="row.route === 'SCRIPT_REWRITE'" v-model="rewriteIds" type="checkbox" :value="row.item.utterance_id" /></td>
            <td>{{ episodeLabel(row.episode_order) }} · #{{ row.item.utterance_number }}</td>
            <td class="dialogue">{{ row.final_target_dialogue || row.item.utterance_id }}</td>
            <td>{{ seconds(row.item.source_slot_duration_us) }}</td>
            <td>{{ seconds(row.item.actual_speech_duration_us) }}</td>
            <td>{{ seconds(row.item.overflow_us) }}</td>
            <td>{{ factorLabel(row) }}</td>
            <td :class="row.route === 'SCRIPT_REWRITE' ? 'route-rewrite' : 'route-retake'">{{ routeLabel(row) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.timing-triage { margin: 22px auto; max-width: 1330px; border: 1px solid #ddd; border-radius: 18px; padding: 22px; background: #fff; }
header { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
.eyebrow { margin: 0 0 8px; color: #888; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
h2 { margin: 0; font-size: 22px; }
.guidance { margin: 18px 0; padding: 14px 16px; background: #f6f7fb; border-left: 3px solid #94a8ff; line-height: 1.65; }
.error { color: #c62828; }
.success { color: #067647; }
.metrics { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.metrics article { display: flex; flex-direction: column; gap: 6px; padding: 14px; border: 1px solid #e0e0e0; border-radius: 12px; }
.metrics strong { font-size: 24px; }
.metrics span { color: #666; font-size: 12px; }
.metrics .warn { border-color: #f0b7a8; }
.metrics .retake { border-color: #d6c98f; }
.metrics .rewrite { border-color: #e6a0a0; background: #fff8f7; }
.episode-grid { margin-top: 14px; display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; }
.episode-card { display: flex; flex-direction: column; gap: 6px; padding: 12px 14px; border: 1px solid #e2e2e2; border-radius: 10px; }
.episode-card span { color: #666; font-size: 13px; }
.decision { margin-top: 14px; padding: 14px; border-radius: 10px; display: flex; flex-direction: column; gap: 7px; line-height: 1.55; }
.rewrite-decision { background: #fff0ed; border: 1px solid #efb1a7; }
.retake-decision { background: #fffbea; border: 1px solid #e5d486; }
.rewrite-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.rewrite-actions .primary { background: #20201d; color: #fff; border-color: #20201d; }
.rewrite-decision small { color: #6f514b; }
.table-wrap { margin-top: 18px; overflow-x: auto; }
.table-wrap h3 { margin: 0 0 10px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 9px 10px; border-bottom: 1px solid #e7e7e7; text-align: left; vertical-align: top; }
th { white-space: nowrap; background: #fafafa; }
.dialogue { min-width: 300px; max-width: 560px; line-height: 1.45; }
.route-rewrite { color: #b3261e; font-weight: 700; }
.route-retake { color: #8a6d00; font-weight: 700; }
@media (max-width: 900px) { .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
