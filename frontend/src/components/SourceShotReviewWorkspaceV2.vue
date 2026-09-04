<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

import { api } from '../api/client'
import { remakeApi } from '../api/remake'
import { resolveSourcePersonChoiceV1 } from '../utils/sourcePersonChoiceV1'
import VisualCharacterPickerV1 from './VisualCharacterPickerV1.vue'
import PersonLocalizationReview from './PersonLocalizationReview.vue'
import MissingPersonReview from './MissingPersonReview.vue'
import { shotSpeakerCandidates } from '../utils/shotSpeakerCandidates'
import { personConfirmationMark } from '../utils/personConfirmationMark'
import type {
  AssetEvidenceItem,
  AssetWorkspace,
  Episode,
  Shot,
  ShotAssetBindings,
  ShotAssetEvidence,
} from '../types/studio'
import type { ReviewIssue } from '../types/remake'

const props = withDefaults(defineProps<{
  projectId: string
  episodes: Episode[]
  focusEpisodeId?: string
  focusShotOrdinal?: number | null
  sourceReady?: boolean
  blockingReason?: string
}>(), {
  focusEpisodeId: '',
  focusShotOrdinal: null,
  sourceReady: false,
  blockingReason: '',
})
const emit = defineEmits<{ changed: []; completed: [] }>()

type Mark = {
  shot_id: string
  image_url: string
  box: number[]
  source?: string | null
  track_id?: string | null
  candidate_id?: string | null
}

type CharacterObservationShot = { id: string; ordinal: number; thumbnail_url: string | null }
type CharacterObservation = {
  localization?: Mark | null
  key: string
  name: string
  appearance: string | null
  identity_issue?: string | null
  episode_id: string
  episode_title: string
  scene: string
  character_id: string | null
  suggested_character_id?: string | null
  suggestion_source?: string | null
  shots: CharacterObservationShot[]
}
type SourceCharacter = {
  id: string
  name: string
  cover_url?: string | null
  confidence?: number | null
  shot_ids: string[]
  shot_count?: number
  episode_count?: number
}
type CharacterWorkspace = { revision: string; observations: CharacterObservation[]; characters: SourceCharacter[] }
type AutoProposal = {
  decision: 'AUTO' | 'REVIEW'
  source: string
  character_id?: string | null
  candidate_id?: string | null
  shot_ids: string[]
  localization?: Mark | null
  localizations?: Mark[]
  reason?: string | null
}
type AutoResolveResponse = {
  changed: boolean
  auto_bound_count: number
  review_count: number
  review_proposals: Record<string, AutoProposal>
  workspace: CharacterWorkspace
}
type ReviewEntry = { episode: Episode; shot: Shot }
type SpeakerCandidate = {
  person_key: string
  display_name?: string | null
  appearance?: string | null
  character_id?: string | null
  character_name?: string | null
  cover_url?: string | null
  visible_in_shot?: boolean
  in_performance?: boolean
}
type SpeakerSuggestion = {
  dialogue_key: string
  source_text: string
  dialogue_start_us?: number
  dialogue_end_us?: number
  current_speakers?: Array<{ person_key: string; display_name?: string | null; character_id?: string | null; character_name?: string | null }>
  candidate_people?: SpeakerCandidate[]
  shot_id?: string
  shot_ordinal?: number
}

const assetWorkspace = ref<AssetWorkspace | null>(null)
const characterWorkspace = ref<CharacterWorkspace | null>(null)
const reviewProposals = ref<Record<string, AutoProposal>>({})
const issues = ref<ReviewIssue[]>([])
const entries = ref<ReviewEntry[]>([])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const selectedShotId = ref('')
const search = ref('')
const draftCharacterIds = ref<string[]>([])
const draftSceneId = ref<string | null>(null)
const draftPropIds = ref<string[]>([])
const personChoice = ref<Record<string, string>>({})
const newPersonName = ref<Record<string, string>>({})
const personMarks = ref<Record<string, Mark>>({})
function updatePersonMark(key: string, mark: Mark | null): void {
  if (mark) personMarks.value[key] = mark
  else delete personMarks.value[key]
}
const activePersonKey = ref('')
const activePerson = computed(() => selectedObservations.value.find(item => item.key === activePersonKey.value) || selectedObservations.value[0])
function observationFrame(observation: CharacterObservation): CharacterObservationShot | null {
  return observation.shots.find(shot => shot.id === selectedEntry.value?.shot.id) || null
}
const speakerChoice = ref<Record<string, string>>({})
const supplementShotId = ref('')
async function presenceSaved(): Promise<void> {
  const shotId = supplementShotId.value || selectedEntry.value?.shot.id || ''
  supplementShotId.value = ''
  await afterChange(shotId)
}
const offscreenSpeaker = ref<Record<string, boolean>>({})
function setSpeakerMode(issueId: string, offscreen: boolean): void {
  offscreenSpeaker.value[issueId] = offscreen
  delete speakerChoice.value[issueId]
  error.value = ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
function emptyBindings(): ShotAssetBindings { return { character_ids: [], scene_id: null, prop_ids: [] } }
function emptyEvidence(): ShotAssetEvidence { return { characters: [], scene: null, props: [] } }
function bindingsFor(shotId: string): ShotAssetBindings { return assetWorkspace.value?.bindings_by_shot[shotId] ?? emptyBindings() }
function evidenceFor(shotId: string): ShotAssetEvidence { return assetWorkspace.value?.evidence_by_shot[shotId] ?? emptyEvidence() }
function highConfidence(item: AssetEvidenceItem | null | undefined, threshold = 0.75): boolean {
  return Boolean(item && item.confidence !== null && item.confidence >= threshold)
}
function assetNeedsReview(shot: Shot): boolean {
  const binding = bindingsFor(shot.id)
  const evidence = evidenceFor(shot.id)
  const strongCharacters = evidence.characters.filter((item) => highConfidence(item) && item.final_asset_id)
  const strongProps = evidence.props.filter((item) => highConfidence(item, 0.8) && item.final_asset_id)
  if ((binding.character_ids.length === 0 && strongCharacters.length > 0) || (!binding.scene_id && highConfidence(evidence.scene) && Boolean(evidence.scene?.final_asset_id))) return true
  if ((binding.character_ids.length > 0 && strongCharacters.some((item) => item.final_asset_id && !binding.character_ids.includes(item.final_asset_id))) || Boolean(binding.scene_id && highConfidence(evidence.scene) && evidence.scene?.final_asset_id && evidence.scene.final_asset_id !== binding.scene_id) || (binding.prop_ids.length > 0 && strongProps.some((item) => item.final_asset_id && !binding.prop_ids.includes(item.final_asset_id)))) return true
  const lowCharacter = evidence.characters.some((item) => item.confidence !== null && item.confidence < 0.75 && Boolean(item.final_asset_id) && !binding.character_ids.includes(item.final_asset_id as string))
  const lowScene = Boolean(evidence.scene && evidence.scene.confidence !== null && evidence.scene.confidence < 0.75 && evidence.scene.final_asset_id && evidence.scene.final_asset_id !== binding.scene_id)
  const lowProp = evidence.props.some((item) => item.confidence !== null && item.confidence < 0.75 && Boolean(item.final_asset_id) && !binding.prop_ids.includes(item.final_asset_id as string))
  return lowCharacter || lowScene || lowProp
}

const unresolvedObservations = computed(() => (characterWorkspace.value?.observations || []).filter((item) => !item.character_id))
function representativeShotId(item: CharacterObservation): string {
  const proposal = reviewProposals.value[item.key]
  return proposal?.localization?.shot_id || proposal?.localizations?.[0]?.shot_id || item.localization?.shot_id || item.shots[0]?.id || ''
}
function observationsForShot(shotId: string): CharacterObservation[] {
  return unresolvedObservations.value.filter((item) => representativeShotId(item) === shotId)
}
function speakerSuggestion(issue: ReviewIssue): SpeakerSuggestion | null {
  if (issue.issue_type !== 'SPEAKER' || !isRecord(issue.ai_suggestion)) return null
  const value = issue.ai_suggestion
  if (typeof value.dialogue_key !== 'string' || typeof value.source_text !== 'string') return null
  return value as unknown as SpeakerSuggestion
}
function speakerIssuesForShot(shotId: string): ReviewIssue[] {
  return issues.value.filter((issue) => issue.issue_type === 'SPEAKER' && (issue.shot_id === shotId || speakerSuggestion(issue)?.shot_id === shotId))
}
function shotNeedsReview(entry: ReviewEntry): boolean {
  return presenceIssuesForShot(entry.shot.id).length > 0 || assetNeedsReview(entry.shot) || observationsForShot(entry.shot.id).length > 0 || speakerIssuesForShot(entry.shot.id).length > 0
}
function presenceIssuesForShot(shotId: string): ReviewIssue[] {
  return issues.value.filter(issue => issue.issue_type === 'PERSON_PRESENCE' && issue.shot_id === shotId)
}
function compareReviewEntries(a: ReviewEntry, b: ReviewEntry): number {
  const episodeOrder = Number(a.episode.sort_order || 0) - Number(b.episode.sort_order || 0)
  if (episodeOrder !== 0) return episodeOrder
  const shotOrder = Number(a.shot.ordinal || 0) - Number(b.shot.ordinal || 0)
  if (shotOrder !== 0) return shotOrder
  const startOrder = Number(a.shot.start_us || 0) - Number(b.shot.start_us || 0)
  if (startOrder !== 0) return startOrder
  return String(a.shot.id).localeCompare(String(b.shot.id))
}
const pendingEntries = computed(() => entries.value.filter(shotNeedsReview).sort(compareReviewEntries))
function focusedPendingEntry(): ReviewEntry | null {
  const ordinal = Number(props.focusShotOrdinal || 0)
  if (!Number.isInteger(ordinal) || ordinal <= 0) return null
  return pendingEntries.value.find((entry) => (
    (!props.focusEpisodeId || entry.episode.id === props.focusEpisodeId)
    && entry.shot.ordinal === ordinal
  )) || null
}
const visibleEntries = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return pendingEntries.value
  return pendingEntries.value.filter((entry) => {
    const observationText = observationsForShot(entry.shot.id).map((item) => `${item.name} ${item.appearance || ''}`).join(' ')
    const speakerText = speakerIssuesForShot(entry.shot.id).map((issue) => speakerSuggestion(issue)?.source_text || '').join(' ')
    return `${entry.episode.title} ${entry.shot.ordinal} ${entry.shot.short_description || ''} ${observationText} ${speakerText}`.toLowerCase().includes(keyword)
  })
})
const selectedEntry = computed(() => pendingEntries.value.find((entry) => entry.shot.id === selectedShotId.value) || pendingEntries.value[0] || null)
const selectedObservations = computed(() => selectedEntry.value ? observationsForShot(selectedEntry.value.shot.id) : [])
const selectedSpeakerIssues = computed(() => selectedEntry.value ? speakerIssuesForShot(selectedEntry.value.shot.id) : [])
const selectedHasAssetIssue = computed(() => Boolean(selectedEntry.value && assetNeedsReview(selectedEntry.value.shot)))
const selectedHasPendingPeople = computed(() => selectedObservations.value.length > 0 || Boolean(selectedEntry.value && presenceIssuesForShot(selectedEntry.value.shot.id).length))
const finalCharacters = computed<SourceCharacter[]>(() => characterWorkspace.value?.characters.length
  ? characterWorkspace.value.characters
  : (assetWorkspace.value?.characters || []).map((item) => ({ id: item.id, name: item.name, cover_url: item.cover_url, confidence: item.confidence, shot_ids: item.shot_ids, shot_count: item.shot_count })))

function formatTime(us: number | undefined): string {
  const totalMs = Math.max(0, Math.round(Number(us || 0) / 1000))
  const minutes = Math.floor(totalMs / 60000)
  const seconds = Math.floor((totalMs % 60000) / 1000)
  const millis = totalMs % 1000
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
}
function thumbnailUrl(shot: Shot): string { return shot.thumbnail_url ? `${shot.thumbnail_url}?v=${shot.start_us}-${shot.end_us}` : '' }
function shotIssueSummary(entry: ReviewEntry): string[] {
  const labels: string[] = []
  const personCount = observationsForShot(entry.shot.id).length
  const speakerCount = speakerIssuesForShot(entry.shot.id).length
  if (personCount) labels.push(`人物 ${personCount}`)
  if (assetNeedsReview(entry.shot)) labels.push('场景 / 道具')
  if (speakerCount) labels.push(`对白 ${speakerCount}`)
  return labels
}
function selectedPersonId(observation: CharacterObservation): string {
  if (observation.identity_issue) return ''
  return resolveSourcePersonChoiceV1({
    explicitCharacterId: personChoice.value[observation.key],
    suggestedCharacterId: observation.suggested_character_id,
    proposalCharacterId: reviewProposals.value[observation.key]?.character_id,
    newPersonName: newPersonName.value[observation.key],
  }).characterId
}
function setPersonChoice(observationKey: string, characterId: string): void {
  personChoice.value = { ...personChoice.value, [observationKey]: characterId }
  if (characterId) newPersonName.value = { ...newPersonName.value, [observationKey]: '' }
  error.value = ''
}
function setNewPersonName(observationKey: string, value: string): void {
  newPersonName.value = { ...newPersonName.value, [observationKey]: value }
  if (value.trim()) personChoice.value = { ...personChoice.value, [observationKey]: '' }
}
function chooseSpeaker(issueId: string, personKey: string): void { speakerChoice.value = { ...speakerChoice.value, [issueId]: personKey }; error.value = '' }
function initSelectedShot(entry: ReviewEntry | null): void {
  if (!entry) return
  selectedShotId.value = entry.shot.id
  activePersonKey.value = observationsForShot(entry.shot.id)[0]?.key || ''
  const binding = bindingsFor(entry.shot.id)
  draftCharacterIds.value = [...binding.character_ids]
  draftSceneId.value = binding.scene_id
  draftPropIds.value = [...binding.prop_ids]
  const nextPersonChoice = { ...personChoice.value }
  for (const item of observationsForShot(entry.shot.id)) if (!nextPersonChoice[item.key]) nextPersonChoice[item.key] = item.suggested_character_id || reviewProposals.value[item.key]?.character_id || ''
  personChoice.value = nextPersonChoice
  const nextSpeakerChoice = { ...speakerChoice.value }
  for (const issue of speakerIssuesForShot(entry.shot.id)) {
    const current = speakerSuggestion(issue)?.current_speakers || []
    if (!nextSpeakerChoice[issue.id] && current.length === 1) nextSpeakerChoice[issue.id] = current[0]?.person_key || ''
  }
  speakerChoice.value = nextSpeakerChoice
}
function selectShot(entry: ReviewEntry): void { initSelectedShot(entry) }
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try { const payload = await response.json() as { detail?: unknown }; if (typeof payload.detail === 'string') message = payload.detail } catch { /* keep default */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
async function loadCharacterWorkspace(runAuto = false): Promise<void> {
  const initial = await request<CharacterWorkspace>(`/api/projects/${encodeURIComponent(props.projectId)}/character-assets`)
  if (!runAuto) {
    if (characterWorkspace.value?.revision !== initial.revision) personMarks.value = {}
    characterWorkspace.value = initial; return
  }
  try {
    const result = await request<AutoResolveResponse>(`/api/projects/${encodeURIComponent(props.projectId)}/character-assets/auto-resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ expected_revision: initial.revision }) })
    characterWorkspace.value = result.workspace
    reviewProposals.value = result.review_proposals || {}
  } catch { characterWorkspace.value = initial; reviewProposals.value = {} }
}
async function load(runAuto = false): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [nextAssetWorkspace, shotGroups, nextIssues] = await Promise.all([
      api.getAssetWorkspace(props.projectId),
      Promise.all(props.episodes.map((episode) => api.listShots(episode.id))),
      remakeApi.listReviewIssues(props.projectId, 'OPEN'),
    ])
    assetWorkspace.value = nextAssetWorkspace
    entries.value = props.episodes.flatMap((episode, index) => (shotGroups[index] || []).map((shot) => ({ episode, shot })))
    issues.value = nextIssues
    await loadCharacterWorkspace(runAuto)
    initSelectedShot(
      pendingEntries.value.find((entry) => entry.shot.id === selectedShotId.value)
      || focusedPendingEntry()
      || pendingEntries.value[0]
      || null,
    )
    if (!pendingEntries.value.length) emit('completed')
  } catch (err) { error.value = err instanceof Error ? err.message : '原片待确认分镜读取失败' } finally { loading.value = false }
}
async function saveAssetBinding(): Promise<void> {
  const entry = selectedEntry.value
  if (!entry || saving.value) return
  saving.value = true; error.value = ''
  try {
    assetWorkspace.value = await api.setShotAssetBindings(props.projectId, entry.shot.id, { character_ids: [...draftCharacterIds.value], scene_id: draftSceneId.value, prop_ids: [...draftPropIds.value] })
    await afterChange(entry.shot.id)
  } catch (err) { error.value = err instanceof Error ? err.message : '镜头资产保存失败' } finally { saving.value = false }
}
async function assignObservation(observation: CharacterObservation, confirmSinglePerson = false): Promise<void> {
  if (!characterWorkspace.value || saving.value) return
  if (observation.identity_issue) { error.value = observation.identity_issue; return }
  const localization = personConfirmationMark(observationFrame(observation), personMarks.value[observation.key], confirmSinglePerson)
  if (!localization) { error.value = '请先在多人画面中框出此人，或使用单人确认。'; return }
  const characterId = selectedPersonId(observation)
  const createName = (newPersonName.value[observation.key] || '').trim()
  if (!characterId && !createName) { error.value = '请选择已有正式人物，或输入新人物名称。'; return }
  saving.value = true; error.value = ''
  try {
    characterWorkspace.value = await request<CharacterWorkspace>(`/api/projects/${encodeURIComponent(props.projectId)}/character-assets/assign`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ keys: [observation.key], name: characterId ? '' : createName, character_id: characterId || null, expected_revision: characterWorkspace.value.revision, localizations: localization ? { [observation.key]: localization } : null }),
    })
    const nextProposals = { ...reviewProposals.value }; delete nextProposals[observation.key]; reviewProposals.value = nextProposals
    await afterChange(selectedEntry.value?.shot.id || '')
  } catch (err) { error.value = err instanceof Error ? err.message : '人物身份保存失败' } finally { saving.value = false }
}
function candidatePeople(issue: ReviewIssue): SpeakerCandidate[] { return speakerSuggestion(issue)?.candidate_people?.filter((item) => item?.person_key) || [] }
function confirmedCandidatePeople(issue: ReviewIssue): SpeakerCandidate[] {
  const shotId = issue.shot_id || speakerSuggestion(issue)?.shot_id || selectedEntry.value?.shot.id || ''
  return shotSpeakerCandidates(candidatePeople(issue), bindingsFor(shotId).character_ids, Boolean(offscreenSpeaker.value[issue.id]))
}
function speakerDependsOnPendingPeople(issue: ReviewIssue): boolean {
  if (supplementShotId.value === selectedEntry.value?.shot.id) return true
  if (selectedHasPendingPeople.value) return true
  return candidatePeople(issue).some((person) => !person.character_id && Boolean(person.visible_in_shot || person.in_performance))
}
function speakerPersonTitle(person: SpeakerCandidate): string { return person.character_name || person.display_name || '未命名人物' }
async function saveSpeaker(issue: ReviewIssue): Promise<void> {
  if (speakerDependsOnPendingPeople(issue)) {
    error.value = '请先确认当前镜头人物身份，再确认对白说话人。'
    return
  }
  const personKey = speakerChoice.value[issue.id] || ''
  const selectedPerson = confirmedCandidatePeople(issue).find((person) => person.person_key === personKey)
  if (!personKey || !selectedPerson || saving.value) { error.value = '请选择已经绑定正式人物的说话人。'; return }
  saving.value = true; error.value = ''
  try { await remakeApi.resolveSpeakerReviewIssue(issue.id, personKey); await afterChange(selectedEntry.value?.shot.id || '') }
  catch (err) { error.value = err instanceof Error ? err.message : '对白说话人保存失败' } finally { saving.value = false }
}
function toggleDraftCharacter(id: string): void { draftCharacterIds.value = draftCharacterIds.value.includes(id) ? draftCharacterIds.value.filter((item) => item !== id) : [...draftCharacterIds.value, id] }
function toggleDraftProp(id: string): void { draftPropIds.value = draftPropIds.value.includes(id) ? draftPropIds.value.filter((item) => item !== id) : [...draftPropIds.value, id] }
function fillAiSuggestion(): void {
  const entry = selectedEntry.value; if (!entry) return
  const evidence = evidenceFor(entry.shot.id)
  draftCharacterIds.value = Array.from(new Set(evidence.characters.map((item) => item.final_asset_id).filter((id): id is string => Boolean(id))))
  draftSceneId.value = evidence.scene?.final_asset_id ?? null
  draftPropIds.value = Array.from(new Set(evidence.props.map((item) => item.final_asset_id).filter((id): id is string => Boolean(id))))
}
function evidenceLabel(items: AssetEvidenceItem[]): string { return items.length ? items.map((item) => `${item.label}${item.confidence === null ? '' : ` ${Math.round(item.confidence * 100)}%`}`).join('、') : '无建议' }
async function afterChange(previousShotId: string): Promise<void> {
  window.dispatchEvent(new CustomEvent('studio-project-truth-changed', { detail: { project_id: props.projectId } }))
  emit('changed')
  await load(false)
  if (!pendingEntries.value.length) { emit('completed'); return }
  initSelectedShot(pendingEntries.value.find((entry) => entry.shot.id === previousShotId) || pendingEntries.value[0] || null)
}
function onTruthChanged(event: Event): void {
  const detail = (event as CustomEvent<{ project_id?: string }>).detail
  if (detail?.project_id && detail.project_id !== props.projectId) return
  if (!saving.value) void load(false)
}
onMounted(() => { window.addEventListener('studio-project-truth-changed', onTruthChanged); void load(false) })
onUnmounted(() => window.removeEventListener('studio-project-truth-changed', onTruthChanged))
</script>

<template>
  <section class="source-shot-review-v2">
    <div v-if="error" class="review-error">{{ error }}</div>
    <div v-if="loading && !assetWorkspace" class="review-loading">正在整理真正需要你确认的分镜…</div>
    <section v-else-if="!pendingEntries.length" class="review-complete"><div class="check">{{ sourceReady && !error ? '✓' : 'i' }}</div><strong>{{ sourceReady && !error ? '原片确认完成' : '当前审核队列为空，原片尚未就绪' }}</strong><span>{{ sourceReady && !error ? '原片资产与快照均已满足下游条件。' : blockingReason || '请返回拉片检查内容完整性及上游状态；没有审核任务不代表全部完成。' }}</span></section>

    <div v-else class="review-shell">
      <aside class="shot-queue">
        <header><div><strong>待确认分镜</strong><span>{{ pendingEntries.length }} 个</span></div><input v-model="search" type="search" placeholder="搜索分镜 / 人物 / 台词" /></header>
        <div class="shot-list">
          <button v-for="entry in visibleEntries" :key="entry.shot.id" type="button" :class="['shot-row', { active: selectedEntry?.shot.id === entry.shot.id }]" @click="selectShot(entry)">
            <div class="thumb"><img v-if="entry.shot.thumbnail_url" :src="thumbnailUrl(entry.shot)" alt="" /><span v-else>无画面</span></div>
            <div class="copy"><strong>第{{ String(entry.episode.sort_order).padStart(2, '0') }}集 · 镜头 {{ String(entry.shot.ordinal).padStart(2, '0') }}</strong><span>{{ entry.shot.short_description || '待确认原片事实' }}</span><div class="badges"><i v-for="label in shotIssueSummary(entry)" :key="label">{{ label }}</i></div></div>
          </button>
        </div>
      </aside>

      <main v-if="selectedEntry" class="shot-editor">
        <header class="editor-head"><div><small>当前分镜</small><strong>第{{ String(selectedEntry.episode.sort_order).padStart(2, '0') }}集 · 镜头 {{ String(selectedEntry.shot.ordinal).padStart(2, '0') }}</strong><span>{{ formatTime(selectedEntry.shot.start_us) }} – {{ formatTime(selectedEntry.shot.end_us) }}</span></div><div class="editor-progress">按顺序处理：人物 → 场景 / 道具 → 对白</div></header>
        <div class="editor-body">
          <section class="preview-panel">
            <PersonLocalizationReview v-if="activePerson" :key="`${selectedEntry.shot.id}:${activePerson.key}:${observationFrame(activePerson)?.thumbnail_url}`" :image-url="observationFrame(activePerson)?.thumbnail_url || ''" :shot-id="selectedEntry.shot.id" :label="`${activePerson.name} · ${activePerson.appearance || '请核对人物位置'}`" :model-value="personMarks[activePerson.key]" :disabled="saving || Boolean(activePerson.identity_issue)" @update:model-value="updatePersonMark(activePerson.key, $event)" />
            <video v-else-if="selectedEntry.shot.reference_url" :src="selectedEntry.shot.reference_url" :poster="selectedEntry.shot.thumbnail_url || undefined" controls preload="metadata" />
            <img v-else-if="selectedEntry.shot.thumbnail_url" :src="thumbnailUrl(selectedEntry.shot)" alt="当前分镜" />
            <div v-else class="no-preview">暂无分镜画面</div>
            <details v-if="activePerson && selectedEntry.shot.reference_url" style="width:100%;color:#fff;padding:8px;box-sizing:border-box"><summary>查看原视频（定位框仅对应上方静态帧）</summary><video :src="selectedEntry.shot.reference_url" controls preload="none" /></details>
          </section>

          <section class="facts-panel">
            <button type="button" class="ghost" @click="supplementShotId = selectedEntry.shot.id">漏了一个人？补充本镜头出镜人物</button>
            <MissingPersonReview v-if="supplementShotId === selectedEntry.shot.id || presenceIssuesForShot(selectedEntry.shot.id).length" :key="selectedEntry.shot.id" :project-id="projectId" :shot-id="selectedEntry.shot.id" @close="supplementShotId = ''" @saved="presenceSaved" />
            <section v-if="selectedObservations.length" class="fact-card person-card">
              <header><div><small>1 · 人物身份</small><strong>先确认这个镜头里的人是谁</strong></div><span>{{ selectedObservations.length }} 项</span></header>
              <article v-for="observation in selectedObservations" :key="observation.key" class="person-row">
                <div class="person-info"><strong>{{ observation.name }}</strong><span>{{ observation.appearance || '暂无稳定外观描述' }}</span><button type="button" class="ghost" @click="activePersonKey = observation.key">{{ activePerson?.key === observation.key ? '正在左侧核对' : '在左侧核对此人' }} · {{ personMarks[observation.key]?.source === 'MANUAL_SINGLE_PERSON' ? '单人，无需框选' : personMarks[observation.key] ? '已框选，可调整' : '待核对画面' }}</button></div>

                <div v-if="observation.identity_issue" class="review-error" role="alert">
                  <strong>原片人物识别需修正</strong>
                  <p>{{ observation.identity_issue }}</p>
                  <span>这不是一个可确认的单人人物条目。原始对白与动作暂不分配给任何一个人。</span>
                </div>

                <VisualCharacterPickerV1
                  v-if="!observation.identity_issue"
                  :model-value="selectedPersonId(observation)"
                  :characters="finalCharacters"
                  :suggested-character-id="observation.suggested_character_id || reviewProposals[observation.key]?.character_id || null"
                  :disabled="saving"
                  @update:model-value="setPersonChoice(observation.key, $event)"
                />

                <div v-if="!observation.identity_issue" class="new-person-divider"><span>找不到这个人？</span></div>
                <div v-if="!observation.identity_issue" class="new-person">
                  <input :value="newPersonName[observation.key] || ''" type="text" placeholder="这是新人物：输入人物名称" @input="setNewPersonName(observation.key, ($event.target as HTMLInputElement).value)" />
                  <button type="button" :disabled="saving || !observationFrame(observation)?.thumbnail_url || (!selectedPersonId(observation) && !(newPersonName[observation.key] || '').trim())" @click="assignObservation(observation, !personMarks[observation.key])">{{ saving ? '保存中…' : personMarks[observation.key] ? '确认人物' : '单人画面，确认人物' }}</button>
                </div>
                <small v-if="!observation.identity_issue && !personMarks[observation.key]" style="color:#63748b">只有画面中仅有此人时才直接确认；有其他人时，请先在左侧框出目标。</small>
              </article>
            </section>

            <section v-if="selectedHasAssetIssue" class="fact-card asset-card">
              <header><div><small>2 · 场景 / 道具</small><strong>确认这个镜头真正出现的资产</strong></div><button type="button" class="ghost" @click="fillAiSuggestion">采用 AI 建议到表单</button></header>
              <div class="field-block"><label>人物 Final Binding</label><div class="option-grid visual-binding"><button v-for="item in assetWorkspace?.characters || []" :key="item.id" type="button" :class="{ selected: draftCharacterIds.includes(item.id) }" @click="toggleDraftCharacter(item.id)"><img v-if="item.cover_url" :src="item.cover_url" alt="" /><span>{{ item.name }}</span></button></div></div>
              <div class="field-block two-col"><div><label>场景</label><select v-model="draftSceneId"><option :value="null">未绑定场景</option><option v-for="item in assetWorkspace?.scenes || []" :key="item.id" :value="item.id">{{ item.name }}</option></select></div><div><label>关键道具</label><div class="option-grid compact"><button v-for="item in assetWorkspace?.props || []" :key="item.id" type="button" :class="{ selected: draftPropIds.includes(item.id) }" @click="toggleDraftProp(item.id)">{{ item.name }}</button></div></div></div>
              <details class="ai-details"><summary>查看 AI 识别依据</summary><p>人物：{{ evidenceLabel(evidenceFor(selectedEntry.shot.id).characters) }}</p><p>场景：{{ evidenceFor(selectedEntry.shot.id).scene?.label || '无建议' }}</p><p>道具：{{ evidenceLabel(evidenceFor(selectedEntry.shot.id).props) }}</p></details>
              <div class="save-line"><span>只修改当前分镜，不跳页面。</span><button type="button" class="primary" :disabled="saving" @click="saveAssetBinding">保存镜头资产</button></div>
            </section>

            <section v-if="selectedSpeakerIssues.length" class="fact-card speaker-card">
              <header><div><small>3 · 对白说话人</small><strong>人物确认完成后，再确认这句台词是谁说的</strong></div><span>{{ selectedSpeakerIssues.length }} 条</span></header>
              <article v-for="issue in selectedSpeakerIssues" :key="issue.id" class="speaker-row">
                <div v-if="speakerSuggestion(issue)" class="speaker-content">
                  <div class="dialogue-copy"><strong>“{{ speakerSuggestion(issue)?.source_text || '（无文本）' }}”</strong><span>{{ formatTime(speakerSuggestion(issue)?.dialogue_start_us) }} – {{ formatTime(speakerSuggestion(issue)?.dialogue_end_us) }}</span></div>
                  <div v-if="speakerDependsOnPendingPeople(issue)" class="speaker-lock">
                    <strong>先确认人物，才能确认对白</strong>
                    <span>当前镜头仍有人物身份未确定。确认人物后，这条对白会自动解锁并只显示已绑定的正式人物。</span>
                  </div>
                  <template v-else>
                    <div class="speaker-options" aria-label="说话人候选范围"><button type="button" :disabled="saving" :class="{selected:!offscreenSpeaker[issue.id]}" @click="setSpeakerMode(issue.id, false)">当前镜头人物</button><button type="button" :disabled="saving" :class="{selected:offscreenSpeaker[issue.id]}" @click="setSpeakerMode(issue.id, true)">画外说话人</button></div>
                    <div class="speaker-options"><button v-for="person in confirmedCandidatePeople(issue)" :key="person.person_key" type="button" :class="{ selected: speakerChoice[issue.id] === person.person_key }" @click="chooseSpeaker(issue.id, person.person_key)"><img v-if="person.cover_url" :src="person.cover_url" alt="" /><span>{{ speakerPersonTitle(person) }}</span></button></div>
                    <div class="save-line"><span v-if="!confirmedCandidatePeople(issue).length">{{ offscreenSpeaker[issue.id] ? '当前场景没有其他已确认人物可选，请先补齐人物身份。' : '当前镜头没有可选的绑定人物；声音来自画外时，请选择“画外说话人”。' }}</span><span v-else>{{ offscreenSpeaker[issue.id] ? '画外候选：当前场景其他已确认人物。此选择不添加镜头出镜绑定。' : '仅显示当前镜头绑定人物，同一正式身份只显示一次。' }}</span><button type="button" class="primary" :disabled="saving || !confirmedCandidatePeople(issue).some((person) => person.person_key === speakerChoice[issue.id])" @click="saveSpeaker(issue)">确认说话人</button></div>
                  </template>
                </div>
              </article>
            </section>
          </section>
        </div>
      </main>
    </div>
  </section>
</template>

<style scoped>
.source-shot-review-v2{height:100%;min-height:0;color:#273b58}.review-error{margin:0 0 8px;padding:9px 12px;border:1px solid #efcaca;border-radius:8px;background:#fff2f2;color:#a34848;font-size:11px}.review-loading,.review-complete{height:100%;min-height:360px;display:grid;place-items:center;align-content:center;gap:8px;background:#fff}.review-complete .check{width:52px;height:52px;display:grid;place-items:center;border-radius:50%;background:#eaf8ef;color:#29a85d;font-size:26px;font-weight:900}.review-complete strong{font-size:18px}.review-complete span{color:#7c899b;font-size:11px}.review-shell{height:100%;min-height:0;display:grid;grid-template-columns:300px minmax(0,1fr);background:#f5f7fa}.shot-queue{min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);border-right:1px solid #e1e6ed;background:#fff}.shot-queue>header{display:grid;gap:9px;padding:13px;border-bottom:1px solid #e8ecf1}.shot-queue>header>div{display:flex;justify-content:space-between;align-items:center}.shot-queue strong{font-size:13px}.shot-queue header span{padding:3px 7px;border-radius:99px;background:#fff1d8;color:#986519;font-size:9px;font-weight:800}.shot-queue input{height:34px;border:1px solid #dbe2eb;border-radius:8px;padding:0 10px;font-size:10px;outline:none}.shot-list{min-height:0;overflow:auto;padding:8px}.shot-row{width:100%;display:grid;grid-template-columns:70px minmax(0,1fr);gap:9px;margin-bottom:7px;padding:7px;border:1px solid transparent;border-radius:9px;background:#fff;text-align:left;cursor:pointer}.shot-row:hover{background:#f7f9fc}.shot-row.active{border-color:#8caff0;background:#f1f6ff}.thumb{height:76px;overflow:hidden;display:grid;place-items:center;border-radius:7px;background:#111a27;color:#7e8997;font-size:9px}.thumb img{width:100%;height:100%;object-fit:cover}.copy{min-width:0;display:grid;align-content:center;gap:3px}.copy strong{font-size:10px;color:#344b69}.copy>span{overflow:hidden;color:#7d899a;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.badges{display:flex;gap:4px;flex-wrap:wrap}.badges i{padding:2px 5px;border-radius:99px;background:#eef3fa;color:#58739a;font-size:8px;font-style:normal}.shot-editor{min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden}.editor-head{min-height:58px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:10px 15px;border-bottom:1px solid #e2e7ee;background:#fff}.editor-head>div:first-child{display:grid;gap:1px}.editor-head small{font-size:8px;color:#8b97a8}.editor-head strong{font-size:13px}.editor-head span,.editor-progress{font-size:9px;color:#7d899b}.editor-progress{padding:5px 8px;border-radius:99px;background:#edf4ff;color:#5072a5}.editor-body{min-height:0;overflow:auto;display:grid;grid-template-columns:minmax(360px,46%) minmax(480px,54%);gap:12px;padding:12px}.preview-panel{position:sticky;top:0;align-self:start;min-height:320px;display:grid;place-items:center;overflow:hidden;border-radius:11px;background:#101824}.preview-panel video,.preview-panel img{display:block;width:100%;max-height:calc(100vh - 220px);object-fit:contain;background:#101824}.no-preview{color:#7e8998;font-size:10px}.facts-panel{display:grid;align-content:start;gap:10px}.fact-card{overflow:hidden;border:1px solid #dfe5ed;border-radius:11px;background:#fff}.fact-card>header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border-bottom:1px solid #ebeff4}.fact-card>header>div{display:grid;gap:2px}.fact-card header small{font-size:8px;color:#8492a5}.fact-card header strong{font-size:12px}.fact-card header>span{font-size:9px;color:#7a899c}.person-row,.speaker-row{display:grid;gap:10px;padding:11px 12px;border-bottom:1px solid #eef1f5}.person-row:last-child,.speaker-row:last-child{border-bottom:0}.person-info{display:grid;gap:2px}.person-info strong{font-size:11px}.person-info span{color:#7d8999;font-size:9px;line-height:1.5}.person-info small{color:#3f77c8;font-size:8px}.new-person-divider{display:flex;align-items:center;gap:8px;color:#8a96a6;font-size:8px}.new-person-divider:before,.new-person-divider:after{content:"";height:1px;flex:1;background:#e8ecf1}.new-person{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:7px}.new-person input,.field-block select{width:100%;height:34px;box-sizing:border-box;border:1px solid #d9e1eb;border-radius:7px;padding:0 9px;background:#fff;color:#40516b;font-size:10px}.new-person button,.ghost,.primary{min-height:34px;border-radius:7px;padding:0 11px;font-size:9px;font-weight:800;cursor:pointer}.new-person button{border:1px solid #a9bfe3;background:#f7faff;color:#496b9f}.new-person button:disabled,.primary:disabled{opacity:.45;cursor:not-allowed}.asset-card{padding-bottom:11px}.asset-card>header{margin-bottom:10px}.ghost{border:1px solid #d5dfec;background:#fff;color:#5b6f8d}.field-block{display:grid;gap:6px;padding:0 12px 10px}.field-block>label,.field-block>div>label{color:#65748a;font-size:9px;font-weight:800}.two-col{grid-template-columns:1fr 1fr;gap:10px}.two-col>div{display:grid;gap:6px}.option-grid{display:flex;flex-wrap:wrap;gap:5px}.option-grid button{min-height:29px;border:1px solid #dbe2eb;border-radius:7px;padding:0 8px;background:#fff;color:#596a80;font-size:9px;cursor:pointer}.option-grid button.selected{border-color:#5d89dc;background:#edf4ff;color:#315d9f}.visual-binding button{display:grid;grid-template-columns:28px auto;gap:6px;align-items:center;padding:4px 8px 4px 4px}.visual-binding img{width:28px;height:34px;border-radius:5px;object-fit:cover}.ai-details{margin:0 12px 10px;border:1px solid #e3e8ef;border-radius:7px;background:#fafbfd}.ai-details summary{padding:7px 9px;color:#6e7e93;font-size:9px;cursor:pointer}.ai-details p{margin:0;padding:3px 9px;color:#78879a;font-size:8px}.save-line{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px}.save-line>span{color:#8491a2;font-size:8px}.primary{border:0;background:#1769ff;color:#fff}.speaker-content{display:grid;gap:10px}.dialogue-copy{display:flex;align-items:baseline;justify-content:space-between;gap:10px}.dialogue-copy strong{font-size:12px;line-height:1.45}.dialogue-copy span{flex:none;color:#8995a5;font-size:8px}.speaker-lock{display:grid;gap:4px;padding:10px 12px;border:1px solid #f0d7a3;border-radius:8px;background:#fff8e8}.speaker-lock strong{color:#8a5c14;font-size:10px}.speaker-lock span{color:#927441;font-size:9px;line-height:1.55}.speaker-options{display:flex;flex-wrap:wrap;gap:6px}.speaker-options button{display:grid;grid-template-columns:30px auto;gap:6px;align-items:center;border:1px solid #dce3ec;border-radius:8px;padding:5px 8px 5px 5px;background:#fff;color:#40536e;font-size:9px;cursor:pointer}.speaker-options button.selected{border-color:#5c87d9;background:#eef4ff}.speaker-options img{width:30px;height:38px;border-radius:6px;object-fit:cover}@media(max-width:1000px){.review-shell{grid-template-columns:240px minmax(0,1fr)}.editor-body{grid-template-columns:1fr}.preview-panel{position:static;min-height:260px}.two-col{grid-template-columns:1fr}}@media(max-width:760px){.review-shell{grid-template-columns:1fr;grid-template-rows:210px minmax(0,1fr)}.shot-queue{border-right:0;border-bottom:1px solid #e1e6ed}.shot-list{display:flex;overflow:auto}.shot-row{min-width:230px}.editor-body{padding:8px}.new-person,.two-col{grid-template-columns:1fr}.save-line,.dialogue-copy{align-items:stretch;flex-direction:column}}
</style>
