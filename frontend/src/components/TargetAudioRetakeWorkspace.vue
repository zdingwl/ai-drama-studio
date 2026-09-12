<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  getTargetAudio,
  listAudioCandidates,
  listTimingCandidates,
  retakeTargetAudio,
  type AudioCandidate,
  type AudioClip,
  type DeliveryControl,
  type TimingCandidate,
} from '@/features/projects/p14'

interface RetakeDraft {
  selected: boolean
  acting_direction: string
  emo_alpha: number
  duration_factor: number
}

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const loading = ref(false)
const retaking = ref(false)
const error = ref('')
const message = ref('')
const audio = ref<any>(null)
const candidates = ref<AudioCandidate[]>([])
const timingCandidates = ref<TimingCandidate[]>([])
const drafts = reactive<Record<string, RetakeDraft>>({})

const pendingCandidate = computed(() => candidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const acceptedCandidate = computed(() => {
  const candidateId = audio.value?.provenance?.candidate_id
  return candidateId ? candidates.value.find((item) => item.id === candidateId) ?? null : null
})
const latestTimingCandidate = computed(() => timingCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const overflowItems = computed(() => latestTimingCandidate.value?.content.items.filter((item) => item.fit_status === 'OVERFLOW') ?? [])
const baseCandidate = computed(() => overflowItems.value.length && acceptedCandidate.value
  ? acceptedCandidate.value
  : (pendingCandidate.value ?? acceptedCandidate.value))
const selectedCount = computed(() => Object.values(drafts).filter((item) => item.selected).length)

function syncDrafts(candidate: AudioCandidate | null) {
  const valid = new Set(candidate?.content.clips.map((clip) => clip.utterance_id) ?? [])
  for (const key of Object.keys(drafts)) {
    if (!valid.has(key)) delete drafts[key]
  }
  for (const clip of candidate?.content.clips ?? []) {
    drafts[clip.utterance_id] = {
      selected: drafts[clip.utterance_id]?.selected ?? false,
      acting_direction: clip.acting_direction ?? '',
      emo_alpha: clip.emo_alpha ?? 0.6,
      duration_factor: clip.duration_factor ?? 1.0,
    }
  }
}

async function refresh() {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const [audioResult, candidateRows, timingRows] = await Promise.all([
      getTargetAudio(projectId.value),
      listAudioCandidates(projectId.value),
      listTimingCandidates(projectId.value),
    ])
    audio.value = audioResult
    candidates.value = candidateRows
    timingCandidates.value = timingRows
    syncDrafts(baseCandidate.value)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '加载逐句重录工作区失败'
  } finally {
    loading.value = false
  }
}

function controlFor(clip: AudioClip): DeliveryControl {
  const draft = drafts[clip.utterance_id]
  return {
    utterance_id: clip.utterance_id,
    acting_direction: draft?.acting_direction.trim() || null,
    emo_alpha: Number(draft?.emo_alpha ?? clip.emo_alpha ?? 0.6),
    duration_factor: Number(draft?.duration_factor ?? clip.duration_factor ?? 1.0),
  }
}

function selectOverflow() {
  for (const item of overflowItems.value) {
    if (drafts[item.utterance_id]) drafts[item.utterance_id].selected = true
  }
}

function markOne(utteranceId: string) {
  if (drafts[utteranceId]) drafts[utteranceId].selected = true
  document.getElementById(`retake-${utteranceId}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function runRetake(onlyUtteranceId?: string) {
  const candidate = baseCandidate.value
  if (!candidate) return
  const clips = candidate.content.clips.filter((clip) => onlyUtteranceId ? clip.utterance_id === onlyUtteranceId : drafts[clip.utterance_id]?.selected)
  if (!clips.length) return
  retaking.value = true
  error.value = ''
  message.value = ''
  try {
    await retakeTargetAudio(projectId.value, candidate, clips.map(controlFor), crypto.randomUUID())
    message.value = `已启动 ${clips.length} 句重录。未选中的对白直接复用原 WAV，不会再次调用 IndexTTS。完成后刷新查看新候选。`
    for (const clip of clips) drafts[clip.utterance_id].selected = false
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '启动逐句重录失败'
  } finally {
    retaking.value = false
  }
}

const seconds = (us: number) => `${(us / 1_000_000).toFixed(2)}s`

onMounted(() => { void refresh() })
</script>

<template>
  <section class="retake-workspace">
    <header><div><p class="eyebrow">P14 · 表演与重录</p><h2>逐句语气控制与 Retake</h2></div><button type="button" @click="refresh">刷新</button></header>
    <p class="guidance">这里只改变表演方式，不改目标台词。表演指令通过 IndexTTS 的 emotion text 传递；情绪强度控制语气权重；时长因子 &lt; 1 会更快/更短，&gt; 1 会更慢/更长。系统不会因为 Timing 超时自动改速，必须由你显式重录并重新试听。</p>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="ok">{{ message }}</p><p v-if="loading">正在读取目标配音与时序…</p>
    <template v-if="baseCandidate">
      <div class="summary"><span>基线候选 #{{ baseCandidate.generation_sequence }}</span><span>{{ baseCandidate.review_status === 'NEEDS_REVIEW' ? '待听审' : '当前正式配音对应候选' }}</span><span v-if="baseCandidate.provenance?.retaken_utterance_ids?.length">上一轮重录 {{ baseCandidate.provenance.retaken_utterance_ids.length }} 句</span></div>
      <div v-if="overflowItems.length" class="overflow-box"><strong>Timing 检测到 {{ overflowItems.length }} 句超时</strong><p>当前会以产生正式 Timing 的已确认配音为重录基线。可把超时句加入重录，然后手动调整表演或时长因子；不要为了塞进时间槽直接极端加速。</p><button type="button" @click="selectOverflow">选中全部超时对白</button><div class="overflow-list"><button v-for="item in overflowItems" :key="item.utterance_id" type="button" @click="markOne(item.utterance_id)">#{{ item.utterance_number }} 超时 {{ seconds(item.overflow_us) }}</button></div></div>
      <article v-for="clip in baseCandidate.content.clips" :id="`retake-${clip.utterance_id}`" :key="clip.utterance_id" class="retake-row">
        <div class="row-head"><label class="select-line"><input v-model="drafts[clip.utterance_id].selected" type="checkbox" /> <strong>#{{ clip.utterance_number }}</strong> 加入本轮重录</label><small>{{ clip.voice_label || clip.voice_id }} · 当前 {{ seconds(clip.actual_speech_duration_us) }}</small></div>
        <p class="dialogue">{{ clip.final_target_dialogue }}</p><audio :src="clip.media_url" controls preload="none" />
        <div class="controls"><label class="direction"><span>表演指令（不会被念出来）</span><textarea v-model="drafts[clip.utterance_id].acting_direction" maxlength="600" rows="2" placeholder="例如：克制的愤怒，压低声音；在关键否定词前短暂停顿，不要喊叫" /></label><label><span>情绪强度 {{ Number(drafts[clip.utterance_id].emo_alpha).toFixed(2) }}</span><input v-model.number="drafts[clip.utterance_id].emo_alpha" type="range" min="0" max="1" step="0.05" /></label><label><span>时长因子 {{ Number(drafts[clip.utterance_id].duration_factor).toFixed(2) }}</span><input v-model.number="drafts[clip.utterance_id].duration_factor" type="range" min="0.8" max="1.25" step="0.05" /><small>0.80 更快/更短 · 1.00 原速 · 1.25 更慢/更长</small></label></div>
        <button type="button" :disabled="retaking" @click="runRetake(clip.utterance_id)">只重录这一句</button>
      </article>
      <div class="bulk-actions"><span>已选 {{ selectedCount }} 句</span><button type="button" :disabled="retaking || selectedCount === 0" @click="runRetake()">{{ retaking ? '正在启动…' : '重录选中对白' }}</button></div>
    </template>
    <p v-else>先在上方完成第一轮真实配音生成；有候选后才能做逐句表演调整和 Retake。</p>
  </section>
</template>

<style scoped>
.retake-workspace{margin:24px 0;padding:24px;border:1px solid var(--border-color,#ddd);border-radius:16px}.retake-workspace header{display:flex;justify-content:space-between;gap:16px;align-items:center}.eyebrow{margin:0;font-size:12px;opacity:.65}.guidance{padding:10px 12px;border-left:3px solid rgba(47,84,235,.45);background:rgba(47,84,235,.05)}.error{color:#b42318}.ok{color:#067647}.summary{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.summary span{padding:4px 8px;border-radius:999px;background:rgba(127,127,127,.08);font-size:12px}.overflow-box{margin:14px 0;padding:14px;border:1px solid rgba(180,83,9,.25);border-radius:10px;background:rgba(180,83,9,.055)}.overflow-box p{margin:6px 0 10px}.overflow-list{display:flex;flex-wrap:wrap;gap:7px;margin-top:8px}.retake-row{display:grid;gap:10px;margin:14px 0;padding:14px;border:1px solid rgba(127,127,127,.22);border-radius:10px}.row-head{display:flex;justify-content:space-between;gap:12px;align-items:center}.select-line{display:flex;gap:7px;align-items:center}.select-line input{width:auto}.dialogue{font-size:15px;margin:0}.retake-row audio{width:100%}.controls{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}.controls label{display:grid;gap:6px;font-size:13px}.controls textarea{box-sizing:border-box;width:100%;padding:9px 11px}.controls input[type=range]{width:100%}.bulk-actions{position:sticky;bottom:8px;display:flex;justify-content:flex-end;gap:12px;align-items:center;padding:12px;margin-top:16px;border:1px solid rgba(127,127,127,.22);border-radius:10px;background:var(--surface-color,#fff)}@media(max-width:900px){.controls{grid-template-columns:1fr}.row-head{align-items:flex-start;flex-direction:column}}
</style>
