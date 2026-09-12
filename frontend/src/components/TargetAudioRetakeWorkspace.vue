<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
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
import {
  buildRetakeClipContexts,
  filterRetakeClipContexts,
  type RetakeClipContext,
  type RetakeFilterState,
} from '@/features/projects/p14RetakeFilters'
import { getReplicaTargetBible, type ReplicaTargetBibleContent } from '@/features/projects/targetBible'
import { getReplicaTargetScript, type ReplicaTargetScriptContent } from '@/features/projects/targetScript'

interface RetakeDraft {
  selected: boolean
  acting_direction: string
  emo_alpha: number
  duration_factor: number
}

interface CharacterGroup {
  key: string
  name: string
  rows: RetakeClipContext[]
  overflow_count: number
  selected_count: number
}

interface EpisodeGroup {
  key: string
  episode_id: string
  episode_order: number
  rows: RetakeClipContext[]
  characters: CharacterGroup[]
  overflow_count: number
  selected_count: number
}

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const loading = ref(false)
const retaking = ref(false)
const error = ref('')
const message = ref('')
const audio = ref<any>(null)
const scriptContent = ref<ReplicaTargetScriptContent | null>(null)
const bibleContent = ref<ReplicaTargetBibleContent | null>(null)
const candidates = ref<AudioCandidate[]>([])
const timingCandidates = ref<TimingCandidate[]>([])
const drafts = reactive<Record<string, RetakeDraft>>({})
const filters = reactive<RetakeFilterState>({ query: '', overflow_only: false, selected_only: false })
const expandedEpisodes = reactive<Record<string, boolean>>({})
const expandedCharacters = reactive<Record<string, boolean>>({})

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
const selectedIds = computed(() => new Set(
  Object.entries(drafts).filter(([, item]) => item.selected).map(([utteranceId]) => utteranceId),
))
const clipContexts = computed(() => buildRetakeClipContexts(
  baseCandidate.value?.content.clips ?? [],
  scriptContent.value,
  bibleContent.value,
  latestTimingCandidate.value?.content.items ?? [],
  selectedIds.value,
))
const visibleRows = computed(() => filterRetakeClipContexts(clipContexts.value, filters))
const hasActiveFilters = computed(() => Boolean(filters.query.trim() || filters.overflow_only || filters.selected_only))
const selectedVisibleCount = computed(() => visibleRows.value.filter((row) => row.selected).length)
const selectedHiddenCount = computed(() => Math.max(0, selectedCount.value - selectedVisibleCount.value))

const groupedEpisodes = computed<EpisodeGroup[]>(() => {
  const episodes = new Map<string, EpisodeGroup>()
  for (const row of visibleRows.value) {
    const episodeKey = `${row.episode_order}:${row.episode_id}`
    let episode = episodes.get(episodeKey)
    if (!episode) {
      episode = {
        key: episodeKey,
        episode_id: row.episode_id,
        episode_order: row.episode_order,
        rows: [],
        characters: [],
        overflow_count: 0,
        selected_count: 0,
      }
      episodes.set(episodeKey, episode)
    }
    episode.rows.push(row)
    if (row.is_overflow) episode.overflow_count += 1
    if (row.selected) episode.selected_count += 1
  }

  for (const episode of episodes.values()) {
    const characters = new Map<string, CharacterGroup>()
    for (const row of episode.rows) {
      const characterKey = `${episode.key}:${row.character_id ?? 'unbound'}`
      let character = characters.get(characterKey)
      if (!character) {
        character = { key: characterKey, name: row.character_name, rows: [], overflow_count: 0, selected_count: 0 }
        characters.set(characterKey, character)
      }
      character.rows.push(row)
      if (row.is_overflow) character.overflow_count += 1
      if (row.selected) character.selected_count += 1
    }
    episode.characters = [...characters.values()]
  }

  return [...episodes.values()].sort((left, right) => left.episode_order - right.episode_order)
})

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
    const [audioResult, candidateRows, timingRows, scriptResult, bibleResult] = await Promise.all([
      getTargetAudio(projectId.value),
      listAudioCandidates(projectId.value),
      listTimingCandidates(projectId.value),
      getReplicaTargetScript(projectId.value),
      getReplicaTargetBible(projectId.value),
    ])
    audio.value = audioResult
    candidates.value = candidateRows
    timingCandidates.value = timingRows
    scriptContent.value = scriptResult.content
    bibleContent.value = bibleResult.target_bible.content
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

function episodeLabel(group: EpisodeGroup): string {
  return group.episode_order >= 999999 ? '未找到所属集' : `第 ${group.episode_order} 集`
}

function isEpisodeOpen(key: string): boolean {
  return hasActiveFilters.value || expandedEpisodes[key] === true
}

function isCharacterOpen(key: string): boolean {
  return hasActiveFilters.value || expandedCharacters[key] === true
}

function toggleEpisode(key: string) {
  if (hasActiveFilters.value) return
  expandedEpisodes[key] = !isEpisodeOpen(key)
}

function toggleCharacter(key: string) {
  if (hasActiveFilters.value) return
  expandedCharacters[key] = !isCharacterOpen(key)
}

function expandAll() {
  for (const episode of groupedEpisodes.value) {
    expandedEpisodes[episode.key] = true
    for (const character of episode.characters) expandedCharacters[character.key] = true
  }
}

function collapseAll() {
  for (const episode of groupedEpisodes.value) {
    expandedEpisodes[episode.key] = false
    for (const character of episode.characters) expandedCharacters[character.key] = false
  }
}

function clearFilters() {
  filters.query = ''
  filters.overflow_only = false
  filters.selected_only = false
}

async function markOne(utteranceId: string) {
  if (drafts[utteranceId]) drafts[utteranceId].selected = true
  filters.query = ''
  filters.selected_only = false
  const row = clipContexts.value.find((item) => item.clip.utterance_id === utteranceId)
  if (row) {
    const episodeKey = `${row.episode_order}:${row.episode_id}`
    const characterKey = `${episodeKey}:${row.character_id ?? 'unbound'}`
    expandedEpisodes[episodeKey] = true
    expandedCharacters[characterKey] = true
  }
  await nextTick()
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
    <header>
      <div><p class="eyebrow">P14 · 表演与重录</p><h2>逐句语气控制与 Retake</h2></div>
      <button type="button" @click="refresh">刷新</button>
    </header>
    <p class="guidance">这里只改变表演方式，不改目标台词。默认按“集 → 角色”折叠，只有展开的分组才渲染逐句播放器和表演控件；搜索、只看 OVERFLOW、只看已选只改变展示，不会取消已经选择的 Retake。</p>
    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="ok">{{ message }}</p>
    <p v-if="loading">正在读取目标配音、目标剧本与时序…</p>

    <template v-if="baseCandidate">
      <div class="summary">
        <span>基线候选 #{{ baseCandidate.generation_sequence }}</span>
        <span>{{ baseCandidate.review_status === 'NEEDS_REVIEW' ? '待听审' : '当前正式配音对应候选' }}</span>
        <span>{{ baseCandidate.content.clips.length }} 句对白</span>
        <span v-if="baseCandidate.provenance?.retaken_utterance_ids?.length">上一轮重录 {{ baseCandidate.provenance.retaken_utterance_ids.length }} 句</span>
      </div>

      <div v-if="overflowItems.length" class="overflow-box">
        <strong>Timing 检测到 {{ overflowItems.length }} 句超时</strong>
        <p>当前会以产生正式 Timing 的已确认配音为重录基线。可直接切换“只看 OVERFLOW”，也可以从下面的超时入口定位单句。</p>
        <div class="overflow-actions">
          <button type="button" @click="filters.overflow_only = true">只看 OVERFLOW</button>
          <button type="button" @click="selectOverflow">选中全部超时对白</button>
        </div>
        <div class="overflow-list">
          <button v-for="item in overflowItems" :key="item.utterance_id" type="button" @click="markOne(item.utterance_id)">#{{ item.utterance_number }} 超时 {{ seconds(item.overflow_us) }}</button>
        </div>
      </div>

      <div class="filter-bar">
        <label class="search-field">
          <span>搜索对白</span>
          <input v-model="filters.query" type="search" placeholder="对白 / 角色 / 声线 / #序号 / 第N集" />
        </label>
        <label class="check-filter"><input v-model="filters.overflow_only" type="checkbox" :disabled="!latestTimingCandidate" /> 只看 OVERFLOW <strong>{{ overflowItems.length }}</strong></label>
        <label class="check-filter"><input v-model="filters.selected_only" type="checkbox" /> 只看已选重录 <strong>{{ selectedCount }}</strong></label>
        <div class="filter-actions">
          <button type="button" :disabled="hasActiveFilters" title="筛选生效时命中分组会自动展开" @click="expandAll">展开全部</button>
          <button type="button" :disabled="hasActiveFilters" title="筛选生效时命中分组会自动展开" @click="collapseAll">折叠全部</button>
          <button type="button" :disabled="!hasActiveFilters" @click="clearFilters">清空筛选</button>
        </div>
      </div>

      <div class="result-summary">
        <span>当前显示 <strong>{{ visibleRows.length }}</strong> / {{ baseCandidate.content.clips.length }} 句</span>
        <span v-if="selectedCount">已选 <strong>{{ selectedCount }}</strong> 句<span v-if="selectedHiddenCount">，其中 {{ selectedHiddenCount }} 句被当前筛选隐藏</span></span>
      </div>

      <p v-if="!visibleRows.length" class="empty">当前筛选没有匹配对白。已选状态不会因此丢失，可清空筛选继续查看。</p>

      <section v-for="episode in groupedEpisodes" :key="episode.key" class="episode-group">
        <button type="button" class="group-head episode-head" @click="toggleEpisode(episode.key)">
          <span><strong>{{ isEpisodeOpen(episode.key) ? '▾' : '▸' }} {{ episodeLabel(episode) }}</strong></span>
          <span class="group-metrics">{{ episode.rows.length }} 句<span v-if="episode.overflow_count"> · OVERFLOW {{ episode.overflow_count }}</span><span v-if="episode.selected_count"> · 已选 {{ episode.selected_count }}</span></span>
        </button>

        <div v-if="isEpisodeOpen(episode.key)" class="episode-body">
          <section v-for="character in episode.characters" :key="character.key" class="character-group">
            <button type="button" class="group-head character-head" @click="toggleCharacter(character.key)">
              <span><strong>{{ isCharacterOpen(character.key) ? '▾' : '▸' }} {{ character.name }}</strong></span>
              <span class="group-metrics">{{ character.rows.length }} 句<span v-if="character.overflow_count"> · OVERFLOW {{ character.overflow_count }}</span><span v-if="character.selected_count"> · 已选 {{ character.selected_count }}</span></span>
            </button>

            <div v-if="isCharacterOpen(character.key)" class="character-body">
              <article v-for="row in character.rows" :id="`retake-${row.clip.utterance_id}`" :key="row.clip.utterance_id" class="retake-row" :class="{ 'is-overflow': row.is_overflow }">
                <div class="row-head">
                  <label class="select-line"><input v-model="drafts[row.clip.utterance_id].selected" type="checkbox" /> <strong>#{{ row.clip.utterance_number }}</strong> 加入本轮重录 <span v-if="row.is_overflow" class="overflow-tag">OVERFLOW</span></label>
                  <small>{{ row.clip.voice_label || row.clip.voice_id }} · 当前 {{ seconds(row.clip.actual_speech_duration_us) }}</small>
                </div>
                <p class="dialogue">{{ row.clip.final_target_dialogue }}</p>
                <audio :src="row.clip.media_url" controls preload="none" />
                <div class="controls">
                  <label class="direction"><span>表演指令（不会被念出来）</span><textarea v-model="drafts[row.clip.utterance_id].acting_direction" maxlength="600" rows="2" placeholder="例如：克制的愤怒，压低声音；在关键否定词前短暂停顿，不要喊叫" /></label>
                  <label><span>情绪强度 {{ Number(drafts[row.clip.utterance_id].emo_alpha).toFixed(2) }}</span><input v-model.number="drafts[row.clip.utterance_id].emo_alpha" type="range" min="0" max="1" step="0.05" /></label>
                  <label><span>时长因子 {{ Number(drafts[row.clip.utterance_id].duration_factor).toFixed(2) }}</span><input v-model.number="drafts[row.clip.utterance_id].duration_factor" type="range" min="0.8" max="1.25" step="0.05" /><small>0.80 更快/更短 · 1.00 原速 · 1.25 更慢/更长</small></label>
                </div>
                <button type="button" :disabled="retaking" @click="runRetake(row.clip.utterance_id)">只重录这一句</button>
              </article>
            </div>
          </section>
        </div>
      </section>

      <div class="bulk-actions">
        <span>已选 {{ selectedCount }} 句<span v-if="selectedHiddenCount"> · 隐藏 {{ selectedHiddenCount }} 句</span></span>
        <button type="button" :disabled="retaking || selectedCount === 0" @click="runRetake()">{{ retaking ? '正在启动…' : '重录选中对白' }}</button>
      </div>
    </template>
    <p v-else>先在上方完成第一轮真实配音生成；有候选后才能做逐句表演调整和 Retake。</p>
  </section>
</template>

<style scoped>
.retake-workspace{margin:24px 0;padding:24px;border:1px solid var(--border-color,#ddd);border-radius:16px}.retake-workspace header{display:flex;justify-content:space-between;gap:16px;align-items:center}.eyebrow{margin:0;font-size:12px;opacity:.65}.guidance{padding:10px 12px;border-left:3px solid rgba(47,84,235,.45);background:rgba(47,84,235,.05)}.error{color:#b42318}.ok{color:#067647}.summary{display:flex;flex-wrap:wrap;gap:8px;margin:12px 0}.summary span{padding:4px 8px;border-radius:999px;background:rgba(127,127,127,.08);font-size:12px}.overflow-box{margin:14px 0;padding:14px;border:1px solid rgba(180,83,9,.25);border-radius:10px;background:rgba(180,83,9,.055)}.overflow-box p{margin:6px 0 10px}.overflow-actions,.overflow-list,.filter-actions{display:flex;flex-wrap:wrap;gap:7px}.overflow-list{margin-top:8px}.filter-bar{display:grid;grid-template-columns:minmax(250px,2fr) auto auto auto;gap:10px;align-items:end;margin:16px 0;padding:14px;border:1px solid rgba(127,127,127,.18);border-radius:12px;background:rgba(127,127,127,.035)}.search-field{display:grid;gap:6px;font-size:12px}.search-field input{box-sizing:border-box;width:100%;padding:8px 10px}.check-filter{display:flex;align-items:center;gap:6px;min-height:34px;white-space:nowrap}.check-filter input{width:auto}.result-summary{display:flex;flex-wrap:wrap;justify-content:space-between;gap:10px;margin:10px 0;font-size:13px}.empty{padding:14px;border:1px dashed rgba(127,127,127,.3);border-radius:10px;opacity:.7}.episode-group{margin:12px 0;border:1px solid rgba(127,127,127,.22);border-radius:12px;overflow:hidden}.group-head{width:100%;display:flex;justify-content:space-between;gap:12px;align-items:center;text-align:left;border:0;border-radius:0;padding:13px 14px;background:rgba(127,127,127,.055);cursor:pointer}.episode-head{font-size:15px}.episode-body{padding:10px}.character-group{margin:8px 0;border:1px solid rgba(127,127,127,.18);border-radius:10px;overflow:hidden}.character-head{background:rgba(127,127,127,.035)}.character-body{padding:0 10px 4px}.group-metrics{font-size:12px;opacity:.7}.retake-row{display:grid;gap:10px;margin:12px 0;padding:14px;border:1px solid rgba(127,127,127,.22);border-radius:10px}.retake-row.is-overflow{border-color:rgba(180,83,9,.45);box-shadow:inset 3px 0 rgba(180,83,9,.38)}.row-head{display:flex;justify-content:space-between;gap:12px;align-items:center}.select-line{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.select-line input{width:auto}.overflow-tag{padding:2px 6px;border-radius:999px;background:rgba(180,83,9,.12);color:#b45309;font-size:11px}.dialogue{font-size:15px;margin:0}.retake-row audio{width:100%}.controls{display:grid;grid-template-columns:2fr 1fr 1fr;gap:12px}.controls label{display:grid;gap:6px;font-size:13px}.controls textarea{box-sizing:border-box;width:100%;padding:9px 11px}.controls input[type=range]{width:100%}.bulk-actions{position:sticky;bottom:8px;display:flex;justify-content:flex-end;gap:12px;align-items:center;padding:12px;margin-top:16px;border:1px solid rgba(127,127,127,.22);border-radius:10px;background:var(--surface-color,#fff);z-index:2}@media(max-width:1050px){.filter-bar{grid-template-columns:1fr 1fr}.filter-actions{grid-column:1/-1}}@media(max-width:900px){.controls{grid-template-columns:1fr}.row-head,.group-head{align-items:flex-start;flex-direction:column}.filter-bar{grid-template-columns:1fr}}
</style>
