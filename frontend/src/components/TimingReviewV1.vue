<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { remakeApi } from '../api/remake'
import type { RemakeProjectTimeline, RemakeShotPlan, TimingStrategy } from '../types/remake'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()

const timeline = ref<RemakeProjectTimeline | null>(null)
const loading = ref(false)
const savingId = ref('')
const error = ref('')
const drafts = reactive<Record<string, { strategy: TimingStrategy; seconds: number; carry: string; reason: string }>>({})

const reviewRows = computed(() => {
  const rows: Array<{ timelineId: string; episodeId: string; shot: RemakeShotPlan; nextShot: RemakeShotPlan | null }> = []
  for (const episode of timeline.value?.episodes ?? []) {
    episode.shot_plans.forEach((shot, index) => {
      if (shot.status !== 'REVIEW') return
      rows.push({ timelineId: episode.id, episodeId: episode.episode_id, shot, nextShot: episode.shot_plans[index + 1] ?? null })
    })
  }
  return rows
})

function seconds(us: number | null | undefined): string {
  return `${Math.max(0, Number(us || 0)) / 1_000_000}`
}

function syncDrafts(): void {
  for (const row of reviewRows.value) {
    const recommendedSeconds = Math.max(row.shot.source_duration_us, row.shot.planned_duration_us) / 1_000_000
    drafts[row.shot.shot_plan_id] = {
      strategy: 'EXTEND',
      seconds: Number(recommendedSeconds.toFixed(3)),
      carry: row.nextShot?.shot_key ?? '',
      reason: '用户确认目标语音时长后的镜头策略',
    }
  }
}

async function load(): Promise<void> {
  if (!props.projectId) return
  loading.value = true
  try {
    timeline.value = await remakeApi.getRemakeTimeline(props.projectId)
    syncDrafts()
    error.value = ''
  } catch (err) {
    timeline.value = null
    error.value = err instanceof Error ? err.message : '目标时间轴读取失败'
  } finally {
    loading.value = false
  }
}

async function save(row: { timelineId: string; shot: RemakeShotPlan }): Promise<void> {
  const draft = drafts[row.shot.shot_plan_id]
  if (!draft || !Number.isFinite(draft.seconds) || draft.seconds < 0.4) {
    error.value = '目标镜头时长至少需要 0.4 秒'
    return
  }
  if (draft.strategy === 'CARRY_OVER_REACTION' && !draft.carry) {
    error.value = '跨反应镜策略必须选择紧邻下一镜头'
    return
  }
  savingId.value = row.shot.shot_plan_id
  try {
    await remakeApi.updateRemakeShotTiming(row.timelineId, row.shot.shot_plan_id, {
      strategy: draft.strategy,
      planned_duration_us: Math.round(draft.seconds * 1_000_000),
      carry_over_shot_key: draft.strategy === 'CARRY_OVER_REACTION' ? draft.carry : null,
      reason: draft.reason.trim() || null,
    })
    try { await remakeApi.compileGenerationSegments(props.projectId) } catch { /* remaining reviews may still block some segments */ }
    await load()
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '镜头时间策略保存失败'
  } finally {
    savingId.value = ''
  }
}

watch(() => props.projectId, () => void load())
onMounted(() => void load())
</script>

<template>
  <section v-if="loading || reviewRows.length || error" class="timing-review">
    <header>
      <div><small>对白时间</small><strong>只处理自动延长会明显破坏节奏的镜头</strong></div>
      <button :disabled="loading" @click="load">刷新</button>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading && !timeline" class="empty">正在读取目标时间轴…</p>
    <article v-for="row in reviewRows" :key="row.shot.shot_plan_id" class="card">
      <div class="summary">
        <div><small>镜头</small><strong>Shot {{ row.shot.ordinal }}</strong></div>
        <div><small>原时长</small><strong>{{ seconds(row.shot.source_duration_us) }}s</strong></div>
        <div><small>自动建议</small><strong>{{ seconds(row.shot.planned_duration_us) }}s</strong></div>
        <div><small>变化</small><strong>{{ row.shot.duration_delta_us >= 0 ? '+' : '' }}{{ seconds(row.shot.duration_delta_us) }}s</strong></div>
      </div>
      <p>{{ row.shot.reason }}</p>
      <div class="dialogues" v-if="row.shot.dialogue_plans.length">
        <span v-for="dialogue in row.shot.dialogue_plans" :key="dialogue.target_dialogue_id">
          语音 {{ seconds(dialogue.speech_duration_us) }}s · 超出 {{ seconds(dialogue.overrun_us) }}s
        </span>
      </div>
      <div class="choices">
        <button :class="{ active: drafts[row.shot.shot_plan_id]?.strategy === 'EXTEND' }" @click="drafts[row.shot.shot_plan_id].strategy = 'EXTEND'">接受延长</button>
        <button v-if="row.nextShot" :class="{ active: drafts[row.shot.shot_plan_id]?.strategy === 'CARRY_OVER_REACTION' }" @click="drafts[row.shot.shot_plan_id].strategy = 'CARRY_OVER_REACTION'">借下一反应镜</button>
        <button :class="{ active: drafts[row.shot.shot_plan_id]?.strategy === 'KEEP' }" @click="drafts[row.shot.shot_plan_id].strategy = 'KEEP'">保持原时长</button>
      </div>
      <label><span>目标镜头时长（秒）</span><input v-model.number="drafts[row.shot.shot_plan_id].seconds" type="number" min="0.4" step="0.05" /></label>
      <label v-if="drafts[row.shot.shot_plan_id]?.strategy === 'CARRY_OVER_REACTION'">
        <span>承接镜头</span>
        <select v-model="drafts[row.shot.shot_plan_id].carry"><option v-if="row.nextShot" :value="row.nextShot.shot_key">下一镜头 · Shot {{ row.nextShot.ordinal }}</option></select>
      </label>
      <label><span>确认说明</span><input v-model="drafts[row.shot.shot_plan_id].reason" /></label>
      <div class="actions"><button class="primary" :disabled="savingId === row.shot.shot_plan_id" @click="save(row)">确认时间策略</button></div>
    </article>
  </section>
</template>

<style scoped>
.timing-review{display:grid;gap:10px;padding:14px;border:1px solid #dfe5ed;border-radius:14px;background:#fff}.timing-review>header{display:flex;justify-content:space-between;align-items:center;gap:12px}.timing-review>header>div{display:grid;gap:2px}.timing-review small{font-size:9px;color:#8793a4}.timing-review strong{font-size:11px;color:#43546b}.timing-review header button,.choices button,.actions button{min-height:32px;border:1px solid #dce2e9;border-radius:8px;padding:0 10px;background:#fff;color:#617086;font-size:9px;cursor:pointer}.card{display:grid;gap:9px;padding:12px;border:1px solid #ead4b2;border-radius:10px;background:#fffaf3}.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:7px}.summary>div{display:grid;gap:2px;padding:7px;border-radius:7px;background:#fff}.card p{margin:0;color:#7a6851;font-size:10px;line-height:1.55}.dialogues{display:flex;flex-wrap:wrap;gap:5px}.dialogues span{padding:5px 7px;border-radius:999px;background:#f4eee5;color:#806d56;font-size:9px}.choices{display:flex;gap:6px;flex-wrap:wrap}.choices button.active{border-color:#8ba7dd;background:#edf4ff;color:#315dab}label{display:grid;gap:4px}label span{font-size:9px;font-weight:750;color:#6e7d90}input,select{min-height:34px;border:1px solid #dce2e9;border-radius:7px;padding:0 8px;background:#fff;color:#405168;font-size:10px}.actions{display:flex;justify-content:flex-end}.actions .primary{border-color:#3566d6;background:#3566d6;color:#fff}.error{margin:0;padding:8px 10px;border-radius:7px;background:#fff2f2;color:#a94e4e;font-size:10px}.empty{margin:0;color:#8793a4;font-size:10px}@media(max-width:900px){.summary{grid-template-columns:1fr 1fr}}
</style>
