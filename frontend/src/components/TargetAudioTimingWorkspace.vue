<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getReplicaTargetBible } from '@/features/projects/targetBible'
import { getReplicaTargetScript } from '@/features/projects/targetScript'
import { getTargetAudio, getTimingPlan, listAudioCandidates, listTimingCandidates, reviewAudioCandidate, reviewTimingCandidate, startTargetAudio, startTimingPlan, type AudioCandidate, type TimingCandidate, type VoiceBinding } from '@/features/projects/p14'
import { apiRequest } from '@/lib/api'

interface VoiceOption {
  voice_key: string
  display_name: string
  preview_url: string
  locale: string | null
  tags: string[]
}

interface VoiceCatalogRead {
  provider: string
  model: string
  target_language: string
  configured: boolean
  runtime_ready: boolean
  runtime_message: string
  voices: VoiceOption[]
}

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
const voiceCatalog = ref<VoiceCatalogRead | null>(null)
const characterVoices = reactive<Record<string, string>>({})
const utteranceVoices = reactive<Record<string, string>>({})
const activeVoicePicker = ref<string | null>(null)
const reviewReason = ref('已逐句听审目标配音与时序结果')
let runtimePoll: number | undefined

const genericDemoTags = new Set(['IndexTTS-2.5', '官方示例', '开发验收'])
const latestAudioCandidate = computed(() => audioCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const latestTimingCandidate = computed(() => timingCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const scriptLines = computed(() => (script.value?.content?.episodes ?? []).flatMap((episode: any) => episode.dialogue ?? []))
const unresolvedLines = computed(() => scriptLines.value.filter((line: any) => !line.target_character_id))
const speakingCharacterIds = computed(() => new Set(scriptLines.value.map((line: any) => line.target_character_id).filter(Boolean)))
const speakingCharacters = computed(() => (bible.value?.content?.characters ?? []).filter((character: any) => speakingCharacterIds.value.has(character.target_character_id)))
const availableVoices = computed(() => voiceCatalog.value?.voices ?? [])
const catalogConfigured = computed(() => Boolean(voiceCatalog.value?.configured && availableVoices.value.length))
const runtimeReady = computed(() => Boolean(voiceCatalog.value?.runtime_ready))

function voiceOption(key: string): VoiceOption | undefined {
  return availableVoices.value.find((item) => item.voice_key === key)
}

function voiceMetadata(voice: VoiceOption): string {
  const details: string[] = []
  if (voice.locale) details.push(voice.locale)
  for (const tag of voice.tags) {
    if (!genericDemoTags.has(tag)) details.push(tag)
  }
  return details.length ? details.join(' · ') : '官方未提供可信的性别、年龄或风格标签'
}

function pickerKey(scope: 'character' | 'utterance', id: string): string {
  return `${scope}:${id}`
}

function toggleVoicePicker(key: string) {
  activeVoicePicker.value = activeVoicePicker.value === key ? null : key
}

function chooseCharacterVoice(characterId: string, voiceKey: string) {
  characterVoices[characterId] = voiceKey
  activeVoicePicker.value = null
}

function chooseUtteranceVoice(utteranceId: string, voiceKey: string) {
  utteranceVoices[utteranceId] = voiceKey
  activeVoicePicker.value = null
}

function selectedCharacterVoice(characterId: string): VoiceOption | undefined {
  return voiceOption(characterVoices[characterId] ?? '')
}

function selectedUtteranceVoice(utteranceId: string): VoiceOption | undefined {
  return voiceOption(utteranceVoices[utteranceId] ?? '')
}

const allBindingsResolved = computed(() => {
  if (!catalogConfigured.value || !runtimeReady.value) return false
  return speakingCharacters.value.every((character: any) => Boolean(characterVoices[character.target_character_id]))
    && unresolvedLines.value.every((line: any) => Boolean(utteranceVoices[line.utterance_id]))
})

async function readVoiceCatalog() {
  if (!projectId.value) return
  voiceCatalog.value = await apiRequest<VoiceCatalogRead>(`/projects/${projectId.value}/target-audio/voices`, { cache: 'no-store' })
}

async function refresh() {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const [scriptResult, bibleResult, audioResult, candidates, timingResult, timingCandidateRows, catalogResult] = await Promise.all([
      getReplicaTargetScript(projectId.value),
      getReplicaTargetBible(projectId.value),
      getTargetAudio(projectId.value),
      listAudioCandidates(projectId.value),
      getTimingPlan(projectId.value),
      listTimingCandidates(projectId.value),
      apiRequest<VoiceCatalogRead>(`/projects/${projectId.value}/target-audio/voices`, { cache: 'no-store' }),
    ])
    script.value = scriptResult
    bible.value = bibleResult.target_bible
    audio.value = audioResult
    audioCandidates.value = candidates
    timing.value = timingResult
    timingCandidates.value = timingCandidateRows
    voiceCatalog.value = catalogResult
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '加载配音与时序失败'
  } finally {
    loading.value = false
  }
}

function bindings(): VoiceBinding[] {
  const rows: VoiceBinding[] = []
  for (const character of speakingCharacters.value) {
    const voiceKey = characterVoices[character.target_character_id]
    const option = voiceOption(voiceKey)
    if (option) rows.push({ scope: 'CHARACTER', target_character_id: character.target_character_id, voice_id: option.voice_key, voice_label: option.display_name })
  }
  for (const line of unresolvedLines.value) {
    const voiceKey = utteranceVoices[line.utterance_id]
    const option = voiceOption(voiceKey)
    if (option) rows.push({ scope: 'UTTERANCE', utterance_id: line.utterance_id, voice_id: option.voice_key, voice_label: option.display_name })
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
onMounted(() => {
  void refresh()
  runtimePoll = window.setInterval(() => {
    if (runtimeReady.value || !projectId.value) return
    void readVoiceCatalog().catch(() => undefined)
  }, 5000)
})
onBeforeUnmount(() => {
  if (runtimePoll !== undefined) window.clearInterval(runtimePoll)
})
</script>

<template>
  <section class="p14-workspace">
    <header>
      <div><p class="eyebrow">配音与时序</p><h2>目标对白音频与真实时长</h2></div>
      <button type="button" @click="refresh">刷新</button>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading">正在读取当前结果…</p>

    <template v-if="script?.status === 'CURRENT' && bible?.status === 'CURRENT'">
      <div class="panel">
        <h3>1. IndexTTS-2.5 参考声线绑定</h3>
        <p>每个声线都对应一段 Reference Audio，由本地 IndexTTS-2.5 做 zero-shot voice cloning；这里不存在需要用户填写的 Provider voice id，也不会自动从原剧演员音轨克隆。</p>
        <p :class="runtimeReady ? 'runtime-ok' : 'error'">本地 IndexTTS-2.5：{{ voiceCatalog?.runtime_message || '正在探测…' }}</p>
        <p v-if="!catalogConfigured" class="error">当前 IndexTTS-2.5 参考声线目录为空。请先配置有使用授权的 Reference Audio，再生成目标配音。</p>
        <p v-else-if="!runtimeReady" class="error">IndexTTS-2.5 由 AI Drama Studio 统一启动器自动管理。若当前应用是手工启动的，请关闭旧进程并从仓库根目录运行 start.cmd（Windows）或 ./start.sh（Linux）。首次启动会自动准备运行时和模型，本页会自动等待 READY。</p>
        <template v-else>
          <p class="voice-guidance">上游官方示例只有编号与 Reference Audio，没有可信的性别、年龄或风格元数据；系统不会猜。请先试听，再把合适声线分配给角色。</p>

          <section v-for="character in speakingCharacters" :key="character.target_character_id" class="voice-binding">
            <div class="binding-head">
              <div>
                <strong>{{ character.display_name }}</strong>
                <p class="muted">为这个角色固定一条参考声线</p>
              </div>
              <button class="picker-toggle" type="button" @click="toggleVoicePicker(pickerKey('character', character.target_character_id))">
                {{ selectedCharacterVoice(character.target_character_id) ? '更换声线' : '选择声线' }}
              </button>
            </div>
            <div v-if="selectedCharacterVoice(character.target_character_id)" class="selected-voice">
              <div>
                <strong>{{ selectedCharacterVoice(character.target_character_id)?.display_name }}</strong>
                <p class="voice-meta">{{ voiceMetadata(selectedCharacterVoice(character.target_character_id)!) }}</p>
              </div>
              <audio :src="selectedCharacterVoice(character.target_character_id)?.preview_url" controls preload="none" />
            </div>
            <p v-else class="muted">尚未选择。打开声线库后先试听，再决定是否分配给这个角色。</p>

            <div v-if="activeVoicePicker === pickerKey('character', character.target_character_id)" class="voice-grid">
              <article v-for="voice in availableVoices" :key="voice.voice_key" class="voice-card" :class="{ selected: characterVoices[character.target_character_id] === voice.voice_key }">
                <strong>{{ voice.display_name }}</strong>
                <p class="voice-meta">{{ voiceMetadata(voice) }}</p>
                <audio :src="voice.preview_url" controls preload="none" />
                <button type="button" @click="chooseCharacterVoice(character.target_character_id, voice.voice_key)">选用这个声线</button>
              </article>
            </div>
          </section>

          <section v-for="line in unresolvedLines" :key="line.utterance_id" class="voice-binding">
            <div class="binding-head">
              <div>
                <strong>未绑定人物 · #{{ line.utterance_number }}</strong>
                <p>{{ line.final_target_dialogue }}</p>
              </div>
              <button class="picker-toggle" type="button" @click="toggleVoicePicker(pickerKey('utterance', line.utterance_id))">
                {{ selectedUtteranceVoice(line.utterance_id) ? '更换声线' : '为该句选声线' }}
              </button>
            </div>
            <div v-if="selectedUtteranceVoice(line.utterance_id)" class="selected-voice">
              <div>
                <strong>{{ selectedUtteranceVoice(line.utterance_id)?.display_name }}</strong>
                <p class="voice-meta">{{ voiceMetadata(selectedUtteranceVoice(line.utterance_id)!) }}</p>
              </div>
              <audio :src="selectedUtteranceVoice(line.utterance_id)?.preview_url" controls preload="none" />
            </div>
            <p v-else class="muted">这句没有人物绑定，必须显式试听并选择声线。</p>

            <div v-if="activeVoicePicker === pickerKey('utterance', line.utterance_id)" class="voice-grid">
              <article v-for="voice in availableVoices" :key="voice.voice_key" class="voice-card" :class="{ selected: utteranceVoices[line.utterance_id] === voice.voice_key }">
                <strong>{{ voice.display_name }}</strong>
                <p class="voice-meta">{{ voiceMetadata(voice) }}</p>
                <audio :src="voice.preview_url" controls preload="none" />
                <button type="button" @click="chooseUtteranceVoice(line.utterance_id, voice.voice_key)">选用这个声线</button>
              </article>
            </div>
          </section>
        </template>
        <button type="button" :disabled="!allBindingsResolved" @click="generateAudio">生成 IndexTTS-2.5 配音候选</button>
      </div>

      <div v-if="latestAudioCandidate" class="panel">
        <h3>2. 配音听审</h3>
        <article v-for="clip in latestAudioCandidate.content.clips" :key="clip.clip_id" class="clip">
          <div><strong>#{{ clip.utterance_number }}</strong> {{ clip.final_target_dialogue }}</div>
          <audio :src="clip.media_url" controls preload="none" />
          <small>{{ clip.voice_label || '已选参考声线' }} · 实际时长 {{ seconds(clip.actual_speech_duration_us) }}</small>
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
.p14-workspace{margin:24px 0;padding:24px;border:1px solid var(--border-color,#ddd);border-radius:16px}.p14-workspace header{display:flex;justify-content:space-between;align-items:center}.eyebrow{margin:0;font-size:12px;opacity:.65}.panel{margin-top:18px;padding:18px;border-radius:12px;background:rgba(127,127,127,.06)}input{padding:9px 11px}.clip{display:grid;gap:6px;padding:12px 0;border-bottom:1px solid rgba(127,127,127,.2)}audio{width:100%}.actions{display:flex;gap:10px;margin-top:12px}.error{color:#b42318}.runtime-ok{color:#067647}.voice-guidance{padding:10px 12px;border-left:3px solid rgba(127,127,127,.45);background:rgba(127,127,127,.05)}.voice-binding{margin:14px 0;padding:14px;border:1px solid rgba(127,127,127,.22);border-radius:10px}.binding-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.binding-head p{margin:4px 0 0}.picker-toggle{white-space:nowrap}.selected-voice{display:grid;grid-template-columns:minmax(180px,1fr) minmax(260px,2fr);gap:14px;align-items:center;margin-top:12px;padding:12px;border-radius:8px;background:rgba(127,127,127,.06)}.voice-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-top:14px}.voice-card{display:grid;gap:9px;padding:12px;border:1px solid rgba(127,127,127,.22);border-radius:10px;background:var(--surface-color,#fff)}.voice-card.selected{outline:2px solid rgba(6,118,71,.45)}.voice-meta,.muted{font-size:13px;opacity:.72;margin:3px 0}.voice-card button{justify-self:start}table{width:100%;border-collapse:collapse;margin-top:12px}th,td{text-align:left;padding:8px;border-bottom:1px solid rgba(127,127,127,.2);font-size:13px}@media(max-width:720px){.selected-voice{grid-template-columns:1fr}.binding-head{flex-direction:column}.voice-grid{grid-template-columns:1fr}}
</style>
