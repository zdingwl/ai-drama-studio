<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getReplicaTargetBible } from '@/features/projects/targetBible'
import { getReplicaTargetScript } from '@/features/projects/targetScript'
import { getTargetAudio, getTimingPlan, listAudioCandidates, listTimingCandidates, reviewAudioCandidate, reviewTimingCandidate, startTargetAudio, startTimingPlan, type AudioCandidate, type TimingCandidate, type VoiceBinding } from '@/features/projects/p14'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const loading = ref(false)
const error = ref('')
const script = ref<any>(null)
const bible = ref<any>(null)
const audio = ref<any>(null)
const audioCandidates = ref<AudioCandidate[]>([])
const timing = ref<any>(null)
const timingCandidates = ref<TimingCandidate[]>([])
const characterVoices = reactive<Record<string, string>>({})
const utteranceVoices = reactive<Record<string, string>>({})
const reviewReason = ref('已逐句听审目标配音与时序结果')

const latestAudioCandidate = computed(() => audioCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const latestTimingCandidate = computed(() => timingCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const unresolvedLines = computed(() => (script.value?.content?.episodes ?? []).flatMap((episode: any) => episode.dialogue ?? []).filter((line: any) => !line.target_character_id))

async function refresh() {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const [scriptResult, bibleResult, audioResult, candidates, timingResult, timingCandidateRows] = await Promise.all([
      getReplicaTargetScript(projectId.value), getReplicaTargetBible(projectId.value), getTargetAudio(projectId.value), listAudioCandidates(projectId.value), getTimingPlan(projectId.value), listTimingCandidates(projectId.value),
    ])
    script.value = scriptResult
    bible.value = bibleResult.target_bible
    audio.value = audioResult
    audioCandidates.value = candidates
    timing.value = timingResult
    timingCandidates.value = timingCandidateRows
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '加载配音与时序失败'
  } finally {
    loading.value = false
  }
}

function bindings(): VoiceBinding[] {
  const rows: VoiceBinding[] = []
  for (const character of bible.value?.content?.characters ?? []) {
    const voice = characterVoices[character.target_character_id]?.trim()
    if (voice) rows.push({ scope: 'CHARACTER', target_character_id: character.target_character_id, voice_id: voice })
  }
  for (const line of unresolvedLines.value) {
    const voice = utteranceVoices[line.utterance_id]?.trim()
    if (voice) rows.push({ scope: 'UTTERANCE', utterance_id: line.utterance_id, voice_id: voice })
  }
  return rows
}

async function generateAudio() {
  try {
    error.value = ''
    await startTargetAudio(projectId.value, bindings(), crypto.randomUUID())
    await refresh()
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '启动配音失败' }
}

async function reviewAudio(candidate: AudioCandidate, accept: boolean) {
  try {
    await reviewAudioCandidate(projectId.value, candidate, accept, candidate.content.target_script_artifact_id, candidate.content.target_bible_artifact_id, reviewReason.value)
    await refresh()
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '审核配音失败' }
}

async function generateTiming() {
  try {
    await startTimingPlan(projectId.value, crypto.randomUUID())
    await refresh()
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '计算时序失败' }
}

async function reviewTiming(candidate: TimingCandidate, accept: boolean) {
  try {
    await reviewTimingCandidate(projectId.value, candidate, accept, candidate.content.target_script_artifact_id, candidate.content.target_audio_artifact_id, reviewReason.value)
    await refresh()
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '审核时序失败' }
}

const seconds = (us: number) => `${(us / 1_000_000).toFixed(2)}s`
onMounted(refresh)
</script>

<template>
  <section class="p14-workspace">
    <header><div><p class="eyebrow">配音与时序</p><h2>目标对白音频与真实时长</h2></div><button type="button" @click="refresh">刷新</button></header>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading">正在读取当前结果…</p>

    <template v-if="script?.status === 'CURRENT' && bible?.status === 'CURRENT'">
      <div class="panel">
        <h3>1. 目标声线绑定</h3>
        <p>声线必须显式绑定；未知人物对白不能自动猜默认 narrator。</p>
        <label v-for="character in bible.content.characters" :key="character.target_character_id">
          <span>{{ character.display_name }}</span>
          <input v-model="characterVoices[character.target_character_id]" placeholder="Provider voice id" />
        </label>
        <label v-for="line in unresolvedLines" :key="line.utterance_id">
          <span>未绑定人物 · #{{ line.utterance_number }} {{ line.final_target_dialogue }}</span>
          <input v-model="utteranceVoices[line.utterance_id]" placeholder="该句 Provider voice id" />
        </label>
        <button type="button" :disabled="bindings().length === 0" @click="generateAudio">生成目标配音候选</button>
      </div>

      <div v-if="latestAudioCandidate" class="panel">
        <h3>2. 配音听审</h3>
        <article v-for="clip in latestAudioCandidate.content.clips" :key="clip.clip_id" class="clip">
          <div><strong>#{{ clip.utterance_number }}</strong> {{ clip.final_target_dialogue }}</div>
          <audio :src="clip.media_url" controls preload="none" />
          <small>voice {{ clip.voice_id }} · 实际时长 {{ seconds(clip.actual_speech_duration_us) }}</small>
        </article>
        <input v-model="reviewReason" placeholder="审核理由" />
        <div class="actions"><button type="button" @click="reviewAudio(latestAudioCandidate, true)">确认配音</button><button type="button" @click="reviewAudio(latestAudioCandidate, false)">拒绝</button></div>
      </div>

      <div class="panel">
        <h3>3. 对白时序</h3>
        <p v-if="audio?.status !== 'CURRENT'">只有人工确认后的 CURRENT TARGET_AUDIO 才能计算正式时序。</p>
        <button v-else type="button" @click="generateTiming">计算时序候选</button>
        <template v-if="latestTimingCandidate">
          <p v-if="latestTimingCandidate.content.has_overflow" class="error">存在超时 {{ seconds(latestTimingCandidate.content.total_overflow_us) }}，必须重录或返回目标剧本修改，不能直接确认。</p>
          <table><thead><tr><th>句</th><th>原时段</th><th>真实语音</th><th>余量</th><th>超时</th><th>状态</th></tr></thead><tbody><tr v-for="item in latestTimingCandidate.content.items" :key="item.utterance_id"><td>#{{ item.utterance_number }}</td><td>{{ seconds(item.source_slot_duration_us) }}</td><td>{{ seconds(item.actual_speech_duration_us) }}</td><td>{{ seconds(item.residual_hold_us) }}</td><td>{{ seconds(item.overflow_us) }}</td><td>{{ item.fit_status }}</td></tr></tbody></table>
          <div class="actions"><button type="button" :disabled="latestTimingCandidate.content.has_overflow" @click="reviewTiming(latestTimingCandidate, true)">确认时序</button><button type="button" @click="reviewTiming(latestTimingCandidate, false)">拒绝</button></div>
        </template>
      </div>
    </template>
    <p v-else>需要先完成并确认当前目标设定与目标剧本。</p>
  </section>
</template>

<style scoped>
.p14-workspace{margin:24px 0;padding:24px;border:1px solid var(--border-color,#ddd);border-radius:16px}.p14-workspace header{display:flex;justify-content:space-between;align-items:center}.eyebrow{margin:0;font-size:12px;opacity:.65}.panel{margin-top:18px;padding:18px;border-radius:12px;background:rgba(127,127,127,.06)}label{display:grid;gap:6px;margin:12px 0}input{padding:9px 11px}.clip{display:grid;gap:6px;padding:12px 0;border-bottom:1px solid rgba(127,127,127,.2)}audio{width:100%}.actions{display:flex;gap:10px;margin-top:12px}.error{color:#b42318}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:8px;border-bottom:1px solid rgba(127,127,127,.2);font-size:13px}
</style>
