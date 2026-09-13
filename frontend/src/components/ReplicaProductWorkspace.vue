<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getProject } from '@/features/projects/api'
import {
  getTargetAudio,
  getTimingPlan,
  listAudioCandidates,
  listTimingCandidates,
  retakeTargetAudio,
  reviewAudioCandidate,
  reviewTimingCandidate,
  startTargetAudio,
  startTimingPlan,
  type AudioCandidate,
  type TimingCandidate,
  type TimingItem,
  type VoiceBinding,
} from '@/features/projects/p14'
import {
  getFinalOutput,
  listGenerationCandidates,
  listPostCandidates,
  reviewGeneration,
  reviewPost,
  type FinalOutputRead,
  type GenerationCandidate,
  type PostCandidate,
} from '@/features/projects/production'
import {
  getReplicaWorkflow,
  startReplicaAdaptation,
  startReplicaFinalOutput,
  startReplicaGeneration,
  type ReplicaProductWorkflow,
} from '@/features/projects/replicaProduct'
import {
  acceptReplicaTargetAssets,
  listReplicaTargetAssetCandidates,
  rejectReplicaTargetAssets,
  type TargetAssetsCandidateRead,
} from '@/features/projects/targetAssets'
import { getReplicaTargetBible, type ReplicaTargetBibleRead } from '@/features/projects/targetBible'
import {
  getReplicaTargetScript,
  startReplicaTargetScriptTimingRewrite,
  type ReplicaTargetScriptRead,
} from '@/features/projects/targetScript'
import { apiRequest } from '@/lib/api'

interface VoiceOption {
  voice_key: string
  display_name: string
  preview_url: string
}

interface VoiceCatalogRead {
  configured: boolean
  runtime_ready: boolean
  runtime_message: string
  voices: VoiceOption[]
}

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const visible = ref(false)
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const message = ref('')
const workflow = ref<ReplicaProductWorkflow | null>(null)
const bible = ref<ReplicaTargetBibleRead | null>(null)
const script = ref<ReplicaTargetScriptRead | null>(null)
const assetCandidates = ref<TargetAssetsCandidateRead[]>([])
const audio = ref<Awaited<ReturnType<typeof getTargetAudio>> | null>(null)
const audioCandidates = ref<AudioCandidate[]>([])
const timing = ref<Awaited<ReturnType<typeof getTimingPlan>> | null>(null)
const timingCandidates = ref<TimingCandidate[]>([])
const generationCandidates = ref<GenerationCandidate[]>([])
const postCandidates = ref<PostCandidate[]>([])
const finalOutput = ref<FinalOutputRead | null>(null)
const voiceCatalog = ref<VoiceCatalogRead | null>(null)
const selectedVoices = ref<Record<string, string>>({})
const selectedUtteranceVoices = ref<Record<string, string>>({})
let pollTimer: number | undefined

const pendingAssets = computed(() => assetCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const pendingAudio = computed(() => audioCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const pendingTiming = computed(() => timingCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const pendingVideo = computed(() => generationCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const pendingFinal = computed(() => postCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const targetBible = computed(() => bible.value?.target_bible.content ?? null)
const scriptLines = computed(() => script.value?.content?.episodes.flatMap((episode) => episode.dialogue) ?? [])
const speakingCharacterIds = computed(() => new Set(scriptLines.value.map((line) => line.target_character_id).filter(Boolean)))
const speakingCharacters = computed(() => targetBible.value?.characters.filter((item) => speakingCharacterIds.value.has(item.target_character_id)) ?? [])
const unresolvedLines = computed(() => scriptLines.value.filter((line) => !line.target_character_id))
const voices = computed(() => voiceCatalog.value?.voices ?? [])
const runtimeReady = computed(() => Boolean(voiceCatalog.value?.configured && voiceCatalog.value.runtime_ready && voices.value.length))
const voiceBindingsReady = computed(() => speakingCharacters.value.every((item) => Boolean(selectedVoices.value[item.target_character_id]))
  && unresolvedLines.value.every((item) => Boolean(selectedUtteranceVoices.value[item.utterance_id])))
const overflowRows = computed(() => pendingTiming.value?.content.items.filter((item) => item.fit_status === 'OVERFLOW') ?? [])
const rewriteRows = computed(() => overflowRows.value.filter((item) => item.source_slot_duration_us / item.actual_speech_duration_us < 0.8))
const currentAudioCandidate = computed(() => {
  const candidateId = audio.value?.provenance?.candidate_id
  return candidateId ? audioCandidates.value.find((item) => item.id === candidateId) ?? null : null
})

function stepIcon(status: string): string {
  if (status === 'COMPLETE') return '✓'
  if (status === 'WORKING') return '…'
  if (status === 'NEEDS_ACTION') return '!'
  return ''
}

const seconds = (us: number) => `${(us / 1_000_000).toFixed(1)} 秒`

function voiceOption(voiceId: string): VoiceOption | undefined {
  return voices.value.find((item) => item.voice_key === voiceId)
}

function preloadVoiceBindings() {
  const clips = audio.value?.content?.clips ?? pendingAudio.value?.content.clips ?? []
  for (const clip of clips) {
    if (clip.target_character_id && !selectedVoices.value[clip.target_character_id]) {
      selectedVoices.value[clip.target_character_id] = clip.voice_id
    }
    if (!clip.target_character_id && !selectedUtteranceVoices.value[clip.utterance_id]) {
      selectedUtteranceVoices.value[clip.utterance_id] = clip.voice_id
    }
  }
}

async function readDetails() {
  const [bibleRead, scriptRead, assetsRead, audioRead, audioRows, timingRead, timingRows, generationRows, postRows, finalRead] = await Promise.all([
    getReplicaTargetBible(projectId.value),
    getReplicaTargetScript(projectId.value),
    listReplicaTargetAssetCandidates(projectId.value),
    getTargetAudio(projectId.value),
    listAudioCandidates(projectId.value),
    getTimingPlan(projectId.value),
    listTimingCandidates(projectId.value),
    listGenerationCandidates(projectId.value),
    listPostCandidates(projectId.value),
    getFinalOutput(projectId.value),
  ])
  bible.value = bibleRead
  script.value = scriptRead
  assetCandidates.value = assetsRead
  audio.value = audioRead
  audioCandidates.value = audioRows
  timing.value = timingRead
  timingCandidates.value = timingRows
  generationCandidates.value = generationRows
  postCandidates.value = postRows
  finalOutput.value = finalRead
  preloadVoiceBindings()
}

async function refresh(silent = false) {
  if (!projectId.value || loading.value) return
  if (!silent) loading.value = true
  if (!silent) error.value = ''
  try {
    const project = await getProject(projectId.value)
    visible.value = project.project_type === 'REPLICA'
    if (!visible.value) return

    workflow.value = await getReplicaWorkflow(projectId.value)
    await readDetails()

    if (workflow.value.next_action === 'CAST_VOICES') {
      try {
        voiceCatalog.value = await apiRequest<VoiceCatalogRead>(`/projects/${projectId.value}/target-audio/voices`, { cache: 'no-store' })
      } catch {
        voiceCatalog.value = null
      }
    }
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '复刻工作台加载失败'
  } finally {
    if (!silent) loading.value = false
  }
}

async function run(successMessage: string, action: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await action()
    message.value = successMessage
    await refresh(true)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '操作失败'
  } finally {
    busy.value = false
  }
}

const generateAdaptation = () => run('改编方案已经开始生成。', () => startReplicaAdaptation(projectId.value))

async function reviewAdaptation(accept: boolean) {
  const candidate = pendingAssets.value
  const bibleArtifactId = bible.value?.target_bible.artifact_id
  if (!candidate || !bibleArtifactId) return
  await run(accept ? '改编方向已确认。' : '这一版改编方向已退回。', async () => {
    const payload = {
      expected_target_bible_artifact_id: bibleArtifactId,
      expected_generation_sequence: candidate.generation_sequence,
      reason: accept ? '已检查人物、场景、道具和整体改编方向。' : '当前视觉实现方向需要重新生成。',
    }
    if (accept) await acceptReplicaTargetAssets(projectId.value, candidate.id, payload)
    else await rejectReplicaTargetAssets(projectId.value, candidate.id, payload)
  })
}

function bindings(): VoiceBinding[] {
  const rows: VoiceBinding[] = []
  for (const character of speakingCharacters.value) {
    const option = voiceOption(selectedVoices.value[character.target_character_id] ?? '')
    if (option) rows.push({
      scope: 'CHARACTER',
      target_character_id: character.target_character_id,
      voice_id: option.voice_key,
      voice_label: option.display_name,
    })
  }
  for (const line of unresolvedLines.value) {
    const option = voiceOption(selectedUtteranceVoices.value[line.utterance_id] ?? '')
    if (option) rows.push({
      scope: 'UTTERANCE',
      utterance_id: line.utterance_id,
      voice_id: option.voice_key,
      voice_label: option.display_name,
    })
  }
  return rows
}

const generateAudio = () => run('配音已经开始生成。', () => startTargetAudio(projectId.value, bindings(), crypto.randomUUID()))

async function reviewAudio(accept: boolean) {
  const candidate = pendingAudio.value
  if (!candidate) return
  await run(accept ? '配音已确认。' : '这一版配音已退回。', () => reviewAudioCandidate(
    projectId.value,
    candidate,
    accept,
    candidate.content.target_script_artifact_id,
    candidate.content.target_bible_artifact_id,
    accept ? '已试听目标对白并确认声线与表演可继续。' : '当前配音需要重新选择或生成。',
  ))
}

const checkDialogueTiming = () => run('正在检查对白节奏。', () => startTimingPlan(projectId.value, crypto.randomUUID()))

async function acceptTiming() {
  const candidate = pendingTiming.value
  if (!candidate || candidate.content.has_overflow) return
  await run('对白节奏已经匹配。', () => reviewTimingCandidate(
    projectId.value,
    candidate,
    true,
    candidate.content.target_script_artifact_id,
    candidate.content.target_audio_artifact_id,
    '全部对白已通过真实音频时长检查，可以进入视频生成。',
  ))
}

async function rewriteLongDialogue() {
  const candidate = pendingTiming.value
  if (!candidate || !script.value?.artifact_id || !script.value.revision || !rewriteRows.value.length) return
  await run('正在缩短明显过长的对白。', () => startReplicaTargetScriptTimingRewrite(
    projectId.value,
    {
      expected_target_script_artifact_id: script.value!.artifact_id!,
      expected_target_script_revision: script.value!.revision!,
      timing_candidate_id: candidate.id,
      expected_timing_generation_sequence: candidate.generation_sequence,
      utterance_ids: rewriteRows.value.map((item) => item.utterance_id),
    },
    crypto.randomUUID(),
  ))
}

async function retakeLine(item: TimingItem) {
  const base = currentAudioCandidate.value
  if (!base) {
    error.value = '没有找到当前配音版本，请重新生成配音。'
    return
  }
  const durationFactor = Math.max(0.8, Math.min(1, item.source_slot_duration_us / item.actual_speech_duration_us))
  await run('正在只重录这一句。', () => retakeTargetAudio(projectId.value, base, [{
    utterance_id: item.utterance_id,
    emo_alpha: 0.6,
    duration_factor: durationFactor,
  }], crypto.randomUUID()))
}

const generateVideo = () => run('视频生成已经开始。', () => startReplicaGeneration(projectId.value))

async function reviewVideo(accept: boolean) {
  const candidate = pendingVideo.value
  if (!candidate) return
  await run(accept ? '生成画面已确认。' : '这一版画面已退回。', () => reviewGeneration(
    projectId.value,
    candidate,
    accept,
    accept ? '已播放检查人物、动作、场景和连续性。' : '生成画面存在明显质量问题，需要重新生成。',
  ))
}

const buildFinal = () => run('正在制作最终成片。', () => startReplicaFinalOutput(projectId.value))

async function reviewFinal(accept: boolean) {
  const candidate = pendingFinal.value
  if (!candidate) return
  await run(accept ? '最终成片已确认。' : '最终成片已退回。', () => reviewPost(
    projectId.value,
    candidate,
    accept,
    accept ? '已播放最终成片并检查音画、字幕和连续性。' : '最终成片仍需调整。',
  ))
}

watch(projectId, () => { void refresh() }, { immediate: true })

onMounted(() => {
  pollTimer = window.setInterval(() => {
    if (visible.value && (workflow.value?.active_task || busy.value)) void refresh(true)
  }, 2500)
})

onBeforeUnmount(() => {
  if (pollTimer !== undefined) window.clearInterval(pollTimer)
})
</script>

<template>
  <section v-if="visible" class="replica-product-workspace" data-testid="replica-product-workspace">
    <header class="hero">
      <div>
        <p class="eyebrow">复刻短剧</p>
        <h2>从原片到成片，只做三步</h2>
        <p>系统在后台处理分镜、对白、生成和后期；只有真的需要你判断内容质量时才会停下来。</p>
      </div>
      <button type="button" class="quiet" :disabled="loading" @click="refresh()">刷新状态</button>
    </header>

    <div class="step-strip">
      <article v-for="(step, index) in workflow?.steps ?? []" :key="step.key" :class="['step', step.status.toLowerCase()]">
        <span class="step-number">{{ stepIcon(step.status) || index + 1 }}</span>
        <div><strong>{{ step.title }}</strong><small>{{ step.summary }}</small></div>
      </article>
    </div>

    <article v-if="workflow" class="next-card">
      <div>
        <span class="next-label">现在只需要做这一件事</span>
        <h3>{{ workflow.headline }}</h3>
        <p>{{ workflow.description }}</p>
      </div>
      <div v-if="workflow.active_task" class="progress-block">
        <div class="progress-track"><span :style="{ width: `${workflow.progress_percent}%` }" /></div>
        <small>{{ workflow.progress_percent }}%</small>
      </div>
    </article>

    <p v-if="error || workflow?.last_error" class="error">{{ error || workflow?.last_error }}</p>
    <p v-if="message" class="success">{{ message }}</p>

    <div v-if="workflow && !workflow.active_task" class="action-zone">
      <div v-if="workflow.next_action === 'UPLOAD_SOURCE' || workflow.next_action === 'ANALYZE_SOURCE'" class="handoff-note">
        原片上传和解析就在上方“原片”工作区完成。完成后这里会自动进入改编设定。
      </div>

      <button v-else-if="workflow.next_action === 'GENERATE_ADAPTATION'" type="button" class="primary large" :disabled="busy" @click="generateAdaptation">
        生成改编方案
      </button>

      <div v-else-if="workflow.next_action === 'REVIEW_ADAPTATION' && pendingAssets" class="review-card">
        <div class="summary-grid">
          <div><strong>{{ pendingAssets.content.characters.length }}</strong><span>个人物</span></div>
          <div><strong>{{ pendingAssets.content.scenes.length }}</strong><span>个场景</span></div>
          <div><strong>{{ pendingAssets.content.props.length }}</strong><span>个关键道具</span></div>
        </div>
        <p v-if="targetBible?.adaptation_summary" class="adaptation-summary">{{ targetBible.adaptation_summary }}</p>
        <div class="entity-list">
          <span v-for="item in pendingAssets.content.characters" :key="item.target_character_id">{{ item.display_name }}</span>
          <span v-for="item in pendingAssets.content.scenes" :key="item.target_scene_id">{{ item.display_name }}</span>
        </div>
        <details>
          <summary>查看目标对白示例</summary>
          <p v-for="line in scriptLines.slice(0, 8)" :key="line.utterance_id" class="dialogue-line">{{ line.final_target_dialogue }}</p>
        </details>
        <div class="actions">
          <button type="button" class="primary" :disabled="busy" @click="reviewAdaptation(true)">这个方向可以</button>
          <button type="button" class="secondary" :disabled="busy" @click="reviewAdaptation(false)">换一版视觉</button>
        </div>
      </div>

      <div v-else-if="workflow.next_action === 'CAST_VOICES'" class="review-card">
        <p v-if="!runtimeReady" class="warning">{{ voiceCatalog?.runtime_message || '声线服务暂未准备好，请从统一启动器启动应用后再试。' }}</p>
        <div v-for="character in speakingCharacters" :key="character.target_character_id" class="voice-row">
          <div><strong>{{ character.display_name }}</strong><small>{{ character.localized_identity }}</small></div>
          <select v-model="selectedVoices[character.target_character_id]">
            <option value="">选择声线</option>
            <option v-for="voice in voices" :key="voice.voice_key" :value="voice.voice_key">{{ voice.display_name }}</option>
          </select>
          <audio v-if="voiceOption(selectedVoices[character.target_character_id] ?? '')" :src="voiceOption(selectedVoices[character.target_character_id] ?? '')?.preview_url" controls preload="none" />
        </div>
        <div v-for="line in unresolvedLines" :key="line.utterance_id" class="voice-row">
          <div><strong>未绑定角色的对白 {{ line.utterance_number }}</strong><small>{{ line.final_target_dialogue }}</small></div>
          <select v-model="selectedUtteranceVoices[line.utterance_id]">
            <option value="">选择声线</option>
            <option v-for="voice in voices" :key="voice.voice_key" :value="voice.voice_key">{{ voice.display_name }}</option>
          </select>
          <span />
        </div>
        <button type="button" class="primary" :disabled="busy || !runtimeReady || !voiceBindingsReady" @click="generateAudio">生成配音</button>
      </div>

      <div v-else-if="workflow.next_action === 'REVIEW_AUDIO'" class="review-card">
        <template v-if="pendingAudio">
          <p>试听主要对白，判断声音是否适合角色、表演是否自然。满意后再继续。</p>
          <div class="audio-list">
            <article v-for="clip in pendingAudio.content.clips" :key="clip.clip_id">
              <div><strong>对白 {{ clip.utterance_number }}</strong><small>{{ clip.final_target_dialogue }}</small></div>
              <audio :src="clip.media_url" controls preload="none" />
            </article>
          </div>
          <div class="actions">
            <button type="button" class="primary" :disabled="busy" @click="reviewAudio(true)">配音可以，继续</button>
            <button type="button" class="secondary" :disabled="busy" @click="reviewAudio(false)">重新选声线</button>
          </div>
        </template>
        <template v-else-if="pendingTiming && !pendingTiming.content.has_overflow">
          <div class="fit-result">✓ 全部对白都能放进原片节奏</div>
          <button type="button" class="primary" :disabled="busy" @click="acceptTiming">继续生成视频</button>
        </template>
        <template v-else-if="audio?.status === 'CURRENT'">
          <p>配音已经确认。让系统用真实音频时长检查对白节奏，不需要你逐句计算。</p>
          <button type="button" class="primary" :disabled="busy" @click="checkDialogueTiming">检查对白节奏</button>
        </template>
      </div>

      <div v-else-if="workflow.next_action === 'FIX_DIALOGUE_DURATION' && pendingTiming" class="review-card">
        <p>只处理下面这些放不进原片节奏的对白，其他对白不会动。</p>
        <article v-for="item in overflowRows" :key="item.utterance_id" class="overflow-row">
          <div>
            <strong>对白 {{ item.utterance_number }}</strong>
            <small>{{ scriptLines.find((line) => line.utterance_id === item.utterance_id)?.final_target_dialogue }}</small>
            <span>原片可用 {{ seconds(item.source_slot_duration_us) }} · 当前 {{ seconds(item.actual_speech_duration_us) }}</span>
          </div>
          <button v-if="item.source_slot_duration_us / item.actual_speech_duration_us >= 0.8" type="button" class="secondary" :disabled="busy" @click="retakeLine(item)">只重录这一句</button>
          <span v-else class="rewrite-tag">需要缩短对白</span>
        </article>
        <button v-if="rewriteRows.length" type="button" class="primary" :disabled="busy" @click="rewriteLongDialogue">缩短 {{ rewriteRows.length }} 句明显过长的对白</button>
      </div>

      <button v-else-if="workflow.next_action === 'GENERATE_VIDEO'" type="button" class="primary large" :disabled="busy" @click="generateVideo">生成视频</button>

      <div v-else-if="workflow.next_action === 'REVIEW_VIDEO' && pendingVideo" class="review-card">
        <p>逐段播放，看人物是否稳定、动作有没有崩、场景和镜头是否合理。</p>
        <div class="video-grid">
          <article v-for="clip in pendingVideo.content.clips" :key="clip.generation_segment_id">
            <strong>第 {{ clip.episode_order }} 集 · 片段 {{ clip.segment_number }}</strong>
            <video :src="clip.media_url" controls preload="metadata" />
          </article>
        </div>
        <div class="actions">
          <button type="button" class="primary" :disabled="busy" @click="reviewVideo(true)">画面可以，继续成片</button>
          <button type="button" class="secondary" :disabled="busy" @click="reviewVideo(false)">这版不行，重新生成</button>
        </div>
      </div>

      <button v-else-if="workflow.next_action === 'BUILD_FINAL'" type="button" class="primary large" :disabled="busy" @click="buildFinal">制作最终成片</button>

      <div v-else-if="workflow.next_action === 'REVIEW_FINAL' && pendingFinal" class="review-card">
        <div class="final-grid">
          <article v-for="episode in pendingFinal.content.episodes" :key="episode.episode_id">
            <strong>第 {{ episode.episode_order }} 集</strong>
            <video :src="episode.video_url" controls preload="metadata" />
            <a :href="episode.subtitle_url" target="_blank" rel="noreferrer">查看字幕文件</a>
          </article>
        </div>
        <div class="actions">
          <button type="button" class="primary" :disabled="busy" @click="reviewFinal(true)">成片可以，完成</button>
          <button type="button" class="secondary" :disabled="busy" @click="reviewFinal(false)">还需要调整</button>
        </div>
      </div>

      <div v-else-if="workflow.next_action === 'COMPLETE'" class="review-card complete-card">
        <div class="final-grid">
          <article v-for="episode in finalOutput?.content?.episodes ?? []" :key="episode.episode_id">
            <strong>第 {{ episode.episode_order }} 集 · 最终成片</strong>
            <video :src="episode.video_url" controls preload="metadata" />
            <a :href="episode.subtitle_url" target="_blank" rel="noreferrer">字幕</a>
          </article>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.replica-product-workspace{display:grid;gap:16px;max-width:1180px;margin:24px auto;padding:0 4px}.hero{display:flex;justify-content:space-between;gap:20px;padding:26px;border:1px solid #dddcd5;border-radius:22px;background:linear-gradient(135deg,#fff 0%,#f7f6ff 100%)}.hero h2{margin:4px 0 8px;font-size:28px}.hero p:last-child{max-width:720px;margin:0;color:#6f6e68;line-height:1.7}.eyebrow{margin:0;color:#6757e8;font-size:11px;font-weight:800;letter-spacing:.14em}.quiet{align-self:flex-start;padding:8px 12px;border:1px solid #d7d6cf;border-radius:9px;background:#fff;cursor:pointer}.step-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.step{display:flex;gap:11px;align-items:center;padding:14px 16px;border:1px solid #dfded7;border-radius:14px;background:#fff}.step-number{display:grid;place-items:center;width:30px;height:30px;border-radius:50%;background:#efeee9;font-weight:800}.step strong,.step small{display:block}.step small{margin-top:3px;color:#85847e}.step.complete .step-number{background:#e5f4e8;color:#29713d}.step.needs_action{border-color:#b7b0ff;background:#faf9ff}.step.needs_action .step-number{background:#6b5be7;color:#fff}.step.working .step-number{background:#fff0c8;color:#8d6411}.next-card{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:22px 24px;border-radius:18px;background:#282824;color:#fff}.next-label{color:#bdb9ff;font-size:11px;font-weight:800;letter-spacing:.12em}.next-card h3{margin:5px 0 4px;font-size:22px}.next-card p{margin:0;color:#cbc9c0}.progress-block{min-width:220px}.progress-track{height:7px;overflow:hidden;border-radius:99px;background:#4d4d47}.progress-track span{display:block;height:100%;border-radius:99px;background:#a99fff;transition:width .25s}.progress-block small{display:block;margin-top:5px;text-align:right;color:#cfcfc8}.action-zone{padding:22px;border:1px solid #dfded7;border-radius:18px;background:#fff}.primary,.secondary{min-height:40px;padding:0 18px;border-radius:10px;font-weight:800;cursor:pointer}.primary{border:1px solid #292925;background:#292925;color:#fff}.primary.large{min-width:220px;min-height:48px;font-size:15px}.secondary{border:1px solid #d7d6cf;background:#fff;color:#444}.primary:disabled,.secondary:disabled{cursor:not-allowed;opacity:.5}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:16px}.review-card{display:grid;gap:14px}.summary-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.summary-grid>div{padding:14px;border-radius:12px;background:#f6f5f1}.summary-grid strong{display:block;font-size:22px}.summary-grid span{color:#777;font-size:12px}.adaptation-summary{margin:0;padding:12px 14px;border-left:3px solid #7668eb;background:#f8f7ff;line-height:1.7}.entity-list{display:flex;gap:7px;flex-wrap:wrap}.entity-list span,.rewrite-tag{padding:5px 9px;border-radius:999px;background:#f0efea;font-size:12px}.dialogue-line{margin:5px 0;padding:8px 10px;border-radius:8px;background:#fafaf8}.voice-row{display:grid;grid-template-columns:minmax(180px,1fr) minmax(180px,260px) minmax(180px,280px);gap:12px;align-items:center;padding:12px;border:1px solid #e6e5df;border-radius:12px}.voice-row strong,.voice-row small{display:block}.voice-row small{margin-top:4px;color:#777}.voice-row select{min-height:38px;border:1px solid #d7d6cf;border-radius:9px;background:#fff;padding:0 9px}.voice-row audio{width:100%}.audio-list{display:grid;gap:9px;max-height:620px;overflow:auto}.audio-list article{display:grid;grid-template-columns:minmax(0,1fr) 310px;gap:12px;align-items:center;padding:11px;border-radius:11px;background:#f8f8f5}.audio-list strong,.audio-list small{display:block}.audio-list small{margin-top:3px;color:#666}.audio-list audio{width:100%}.fit-result{padding:18px;border-radius:12px;background:#ecf7ef;color:#256b39;font-weight:800}.overflow-row{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:13px;border:1px solid #eadfcf;border-radius:12px;background:#fffaf2}.overflow-row strong,.overflow-row small,.overflow-row span{display:block}.overflow-row small{margin:4px 0;color:#555}.overflow-row div>span{color:#9a6233;font-size:11px}.rewrite-tag{white-space:nowrap;background:#fff0db;color:#8e572b}.video-grid,.final-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.video-grid article,.final-grid article{display:grid;gap:8px;padding:11px;border:1px solid #e1e0da;border-radius:12px;background:#fafaf8}.video-grid video,.final-grid video{width:100%;max-height:560px;background:#111}.final-grid a{color:#584bd7;font-size:12px}.handoff-note,.warning{padding:13px 15px;border-radius:11px;background:#f6f5f1;color:#666}.warning{background:#fff7e7;color:#865d20}.error{padding:11px 13px;border-radius:10px;background:#fff0ee;color:#9d352e}.success{padding:11px 13px;border-radius:10px;background:#edf8ef;color:#256b39}@media(max-width:850px){.hero,.next-card{flex-direction:column}.step-strip{grid-template-columns:1fr}.voice-row,.audio-list article{grid-template-columns:1fr}.video-grid,.final-grid{grid-template-columns:1fr}.progress-block{width:100%;min-width:0}}
</style>
