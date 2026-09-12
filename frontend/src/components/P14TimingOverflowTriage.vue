<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { listTimingCandidates, type TimingCandidate } from '@/features/projects/p14'
import {
  buildTimingTriageRows,
  summarizeTimingTriage,
  summarizeTimingTriageByEpisode,
  type TimingTriageRow,
} from '@/features/projects/p14TimingTriage'
import { getReplicaTargetScript, type ReplicaTargetScriptContent } from '@/features/projects/targetScript'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const loading = ref(false)
const error = ref('')
const timingCandidates = ref<TimingCandidate[]>([])
const script = ref<ReplicaTargetScriptContent | null>(null)

const latestTimingCandidate = computed(() => timingCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const rows = computed(() => buildTimingTriageRows(latestTimingCandidate.value?.content.items ?? [], script.value))
const summary = computed(() => summarizeTimingTriage(rows.value))
const episodeSummaries = computed(() => summarizeTimingTriageByEpisode(rows.value))
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
  if (row.route === 'RETAKE_TRY') return '可尝试 Retake'
  if (row.route === 'SCRIPT_REWRITE') return '优先回 P12 缩短对白'
  return 'FIT'
}

async function refresh() {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const [candidates, scriptResult] = await Promise.all([
      listTimingCandidates(projectId.value),
      getReplicaTargetScript(projectId.value),
    ])
    timingCandidates.value = candidates
    script.value = scriptResult.content
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '加载 Timing 超时分诊失败'
  } finally {
    loading.value = false
  }
}

onMounted(() => { void refresh() })
</script>

<template>
  <section v-if="latestTimingCandidate" class="timing-triage">
    <header>
      <div>
        <p class="eyebrow">P14 · Timing 分诊</p>
        <h2>超时对白先分流，再决定 Retake 还是回 P12</h2>
      </div>
      <button type="button" @click="refresh">刷新</button>
    </header>

    <p class="guidance">
      这里不修改 Timing、不自动加速，也不自动改写对白。它只用当前真实 ffprobe 时长和 source slot 做数学分诊：
      理论所需 duration factor = source slot / 当前真实时长。>= 0.80 的 overflow 可进入受控 Retake 尝试；低于 0.80 的句子即使使用产品允许的最快值也理论上放不下，应优先回 P12 缩短 Final Target Dialogue。
      IndexTTS 实际时长不会保证严格线性，因此任何 Retake 结果仍必须重新 ffprobe、重新计算 Timing。
    </p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading">正在读取 Timing candidate 与 CURRENT Target Script…</p>

    <div class="metrics">
      <article><strong>{{ summary.total }}</strong><span>总对白</span></article>
      <article><strong>{{ summary.fit }}</strong><span>FIT</span></article>
      <article class="warn"><strong>{{ summary.overflow }}</strong><span>OVERFLOW</span></article>
      <article class="retake"><strong>{{ summary.retake_try }}</strong><span>可尝试 Retake</span></article>
      <article class="rewrite"><strong>{{ summary.script_rewrite }}</strong><span>优先回 P12</span></article>
    </div>

    <div class="episode-grid">
      <article v-for="episode in episodeSummaries" :key="`${episode.episode_order}:${episode.episode_id}`" class="episode-card">
        <strong>{{ episodeLabel(episode.episode_order) }}</strong>
        <span>{{ episode.total }} 句 · FIT {{ episode.fit }} · OVERFLOW {{ episode.overflow }}</span>
        <span>Retake 候选 {{ episode.retake_try }} · 回 P12 {{ episode.script_rewrite }}</span>
      </article>
    </div>

    <div v-if="summary.script_rewrite" class="decision rewrite-decision">
      <strong>不要直接把 {{ summary.script_rewrite }} 句全部拉到 0.8。</strong>
      <span>这些句子按当前真实时长计算，理论所需 factor 已低于产品下限；继续只调语速大概率仍失败，应先检查本土化对白是否过长、是否能在不改变语义与人物口吻的前提下缩短。</span>
    </div>
    <div v-else-if="summary.retake_try" class="decision retake-decision">
      <strong>当前 overflow 都位于 Retake 可尝试区间。</strong>
      <span>可以在逐句 Retake 面板人工调整 duration factor；不要一次性盲重录，优先从理论 factor 最接近 1.0、超时最小的句子开始验证。</span>
    </div>

    <div v-if="worstRows.length" class="table-wrap">
      <h3>最严重的超时对白（最多 24 条）</h3>
      <table>
        <thead>
          <tr>
            <th>集 / #</th>
            <th>Final Target Dialogue</th>
            <th>Source slot</th>
            <th>真实时长</th>
            <th>超时</th>
            <th>理论 factor</th>
            <th>分诊</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in worstRows" :key="row.item.utterance_id">
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
