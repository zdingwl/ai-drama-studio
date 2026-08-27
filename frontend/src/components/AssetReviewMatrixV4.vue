<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type {
  AssetEntityType,
  AssetEvidenceItem,
  AssetWorkspace,
  CharacterGalleryImage,
  CharacterGalleryPayload,
  Episode,
  FinalAssetEntity,
  Shot,
  ShotAssetBindings,
  ShotAssetEvidence,
} from '../types/studio'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

type FilterKey = 'all' | 'pending' | 'conflict' | 'unbound' | 'low'
type PickerKind = 'character' | 'prop'
type CharacterCompareStatus = 'matched' | 'evidence_only' | 'final_only'

type ReviewState = {
  key: 'ok' | 'conflict' | 'unbound' | 'low'
  label: string
  conflict: boolean
  unbound: boolean
  low: boolean
}

type CharacterShotComparison = {
  shotId: string
  shot: Shot | null
  shotOrdinal: number | null
  episodeOrder: number | null
  evidenceImages: CharacterGalleryImage[]
  finalBound: boolean
  status: CharacterCompareStatus
}

const workspace = ref<AssetWorkspace | null>(null)
const selectedEpisodeId = ref('')
const shots = ref<Shot[]>([])
const allShots = ref<Shot[]>([])
const loading = ref(true)
const busy = ref('')
const error = ref('')
const filter = ref<FilterKey>('all')
const search = ref('')
const page = ref(1)
const pageSize = ref(10)
const selectedShotIds = ref<string[]>([])
const picker = ref<{ shotId: string; kind: PickerKind } | null>(null)
const detailShotId = ref<string | null>(null)
const revisionOpen = ref(false)
const libraryOpen = ref(false)
const libraryType = ref<AssetEntityType>('character')
const librarySearch = ref('')
const librarySelectedIds = ref<string[]>([])
const libraryFocusId = ref<string | null>(null)
const librarySplitShotIds = ref<string[]>([])
const libraryCharacterGalleries = ref<CharacterGalleryPayload[]>([])
const libraryGalleryLoading = ref(false)
const libraryGalleryError = ref('')
let libraryGalleryRequestId = 0
const batchType = ref<AssetEntityType | null>(null)
const batchCharacterIds = ref<string[]>([])
const batchSceneId = ref<string | null>(null)
const batchPropIds = ref<string[]>([])
const drawerCharacterIds = ref<string[]>([])
const drawerSceneId = ref<string | null>(null)
const drawerPropIds = ref<string[]>([])

const selectedEpisode = computed(() => props.episodes.find((item) => item.id === selectedEpisodeId.value) ?? null)
const detailShot = computed(() => shots.value.find((item) => item.id === detailShotId.value) ?? null)
const charactersById = computed(() => new Map((workspace.value?.characters ?? []).map((item) => [item.id, item])))
const scenesById = computed(() => new Map((workspace.value?.scenes ?? []).map((item) => [item.id, item])))
const propsById = computed(() => new Map((workspace.value?.props ?? []).map((item) => [item.id, item])))
const currentRevision = computed(() => workspace.value?.revision ?? null)
const allShotsById = computed(() => new Map(allShots.value.map((shot) => [shot.id, shot])))
const episodeOrderById = computed(() => new Map(props.episodes.map((episode) => [episode.id, episode.sort_order])))

function emptyBindings(): ShotAssetBindings {
  return { character_ids: [], scene_id: null, prop_ids: [] }
}

function emptyEvidence(): ShotAssetEvidence {
  return { characters: [], scene: null, props: [] }
}

function bindingsFor(shotId: string): ShotAssetBindings {
  return workspace.value?.bindings_by_shot[shotId] ?? emptyBindings()
}

function evidenceFor(shotId: string): ShotAssetEvidence {
  return workspace.value?.evidence_by_shot[shotId] ?? emptyEvidence()
}

function assetName(type: AssetEntityType, id: string): string {
  if (type === 'character') return charactersById.value.get(id)?.name ?? '未知人物'
  if (type === 'scene') return scenesById.value.get(id)?.name ?? '未知场景'
  return propsById.value.get(id)?.name ?? '未知道具'
}

function timecode(us: number): string {
  const ms = Math.max(0, Math.round(us / 1000))
  const minutes = Math.floor(ms / 60_000)
  const seconds = Math.floor((ms % 60_000) / 1000)
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`
}

function thumbnailUrl(shot: Shot): string {
  return shot.thumbnail_url ? `${shot.thumbnail_url}?v=${shot.start_us}-${shot.end_us}` : ''
}

function confidenceLabel(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

function highConfidence(item: AssetEvidenceItem | null | undefined, threshold = 0.75): boolean {
  return Boolean(item && item.confidence !== null && item.confidence >= threshold)
}

/**
 * 职责：根据 Final Binding 与 AI Evidence 计算 Shot 是否真的需要人看。
 * 输入：一个 Shot；输出：自动一致 / AI 冲突 / 未绑定 / 低置信度。
 * 为什么：资产页只应把异常主动推给用户，而不是要求逐镜确认全部结果。
 */
function reviewState(shot: Shot): ReviewState {
  const binding = bindingsFor(shot.id)
  const evidence = evidenceFor(shot.id)
  const strongCharacters = evidence.characters.filter((item) => highConfidence(item) && item.final_asset_id)
  const strongProps = evidence.props.filter((item) => highConfidence(item, 0.8) && item.final_asset_id)

  const characterUnbound = binding.character_ids.length === 0 && strongCharacters.length > 0
  const sceneUnbound = !binding.scene_id && highConfidence(evidence.scene) && Boolean(evidence.scene?.final_asset_id)
  const unbound = characterUnbound || sceneUnbound

  const characterConflict = binding.character_ids.length > 0 && strongCharacters.some((item) => item.final_asset_id && !binding.character_ids.includes(item.final_asset_id))
  const sceneConflict = Boolean(
    binding.scene_id
      && highConfidence(evidence.scene)
      && evidence.scene?.final_asset_id
      && evidence.scene.final_asset_id !== binding.scene_id,
  )
  const propConflict = binding.prop_ids.length > 0 && strongProps.some((item) => item.final_asset_id && !binding.prop_ids.includes(item.final_asset_id))
  const conflict = characterConflict || sceneConflict || propConflict

  const confidenceValues = [
    ...evidence.characters.map((item) => item.confidence),
    evidence.scene?.confidence ?? null,
    ...evidence.props.map((item) => item.confidence),
  ].filter((value): value is number => value !== null)
  const low = confidenceValues.some((value) => value < 0.75)

  if (conflict) return { key: 'conflict', label: 'AI 冲突', conflict, unbound, low }
  if (unbound) return { key: 'unbound', label: '未绑定', conflict, unbound, low }
  if (low) return { key: 'low', label: '低置信度', conflict, unbound, low }
  return { key: 'ok', label: '自动一致', conflict, unbound, low }
}

function shotSearchText(shot: Shot): string {
  const binding = bindingsFor(shot.id)
  const evidence = evidenceFor(shot.id)
  return [
    `shot ${shot.ordinal}`,
    ...binding.character_ids.map((id) => assetName('character', id)),
    binding.scene_id ? assetName('scene', binding.scene_id) : '',
    ...binding.prop_ids.map((id) => assetName('prop', id)),
    ...evidence.characters.map((item) => item.label),
    evidence.scene?.label ?? '',
    ...evidence.props.map((item) => item.label),
  ].join(' ').toLowerCase()
}

const filteredShots = computed(() => {
  const query = search.value.trim().toLowerCase()
  return shots.value.filter((shot) => {
    const state = reviewState(shot)
    const filterMatches = filter.value === 'all'
      || (filter.value === 'pending' && state.key !== 'ok')
      || (filter.value === 'conflict' && state.conflict)
      || (filter.value === 'unbound' && state.unbound)
      || (filter.value === 'low' && state.low)
    return filterMatches && (!query || shotSearchText(shot).includes(query))
  })
})

const filterCounts = computed(() => ({
  all: shots.value.length,
  pending: shots.value.filter((shot) => reviewState(shot).key !== 'ok').length,
  conflict: shots.value.filter((shot) => reviewState(shot).conflict).length,
  unbound: shots.value.filter((shot) => reviewState(shot).unbound).length,
  low: shots.value.filter((shot) => reviewState(shot).low).length,
}))

const pageCount = computed(() => Math.max(1, Math.ceil(filteredShots.value.length / pageSize.value)))
const pageShots = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredShots.value.slice(start, start + pageSize.value)
})
const pageAllSelected = computed(() => pageShots.value.length > 0 && pageShots.value.every((shot) => selectedShotIds.value.includes(shot.id)))

const libraryAssets = computed<FinalAssetEntity[]>(() => {
  if (!workspace.value) return []
  const source = libraryType.value === 'character' ? workspace.value.characters : libraryType.value === 'scene' ? workspace.value.scenes : workspace.value.props
  const query = librarySearch.value.trim().toLowerCase()
  return query ? source.filter((item) => item.name.toLowerCase().includes(query)) : source
})
const libraryFocus = computed(() => libraryAssets.value.find((item) => item.id === libraryFocusId.value) ?? null)
const libraryFocusShots = computed(() => {
  const ids = new Set(libraryFocus.value?.shot_ids ?? [])
  return allShots.value.filter((shot) => ids.has(shot.id))
})
const libraryGalleryKey = computed(() => {
  if (!libraryOpen.value || libraryType.value !== 'character' || !libraryFocus.value) return ''
  return `${libraryFocus.value.id}:${[...new Set(libraryFocus.value.source_candidate_ids ?? [])].sort().join(',')}`
})
const libraryCharacterEvidenceByShot = computed(() => {
  const result = new Map<string, CharacterGalleryImage[]>()
  for (const gallery of libraryCharacterGalleries.value) {
    for (const image of gallery.images) {
      if (!image.shot_id) continue
      const values = result.get(image.shot_id) ?? []
      values.push(image)
      result.set(image.shot_id, values)
    }
  }
  for (const values of result.values()) {
    values.sort((left, right) => (left.source_time_us ?? 0) - (right.source_time_us ?? 0))
  }
  return result
})
const libraryCharacterComparison = computed<CharacterShotComparison[]>(() => {
  if (libraryType.value !== 'character' || !libraryFocus.value) return []
  const finalIds = new Set(libraryFocus.value.shot_ids ?? [])
  const evidence = libraryCharacterEvidenceByShot.value
  const shotIds = new Set([...finalIds, ...evidence.keys()])

  return [...shotIds].map((shotId) => {
    const shot = allShotsById.value.get(shotId) ?? null
    const images = evidence.get(shotId) ?? []
    const first = images[0]
    const finalBound = finalIds.has(shotId)
    const status: CharacterCompareStatus = finalBound && images.length
      ? 'matched'
      : images.length
        ? 'evidence_only'
        : 'final_only'
    return {
      shotId,
      shot,
      shotOrdinal: shot?.ordinal ?? first?.shot_ordinal ?? null,
      episodeOrder: (shot ? episodeOrderById.value.get(shot.episode_id) : undefined) ?? first?.episode_order ?? null,
      evidenceImages: images,
      finalBound,
      status,
    }
  }).sort((left, right) => {
    const episode = (left.episodeOrder ?? 999999) - (right.episodeOrder ?? 999999)
    if (episode) return episode
    return (left.shotOrdinal ?? 999999) - (right.shotOrdinal ?? 999999)
  })
})
const libraryCharacterEvidenceShotCount = computed(() => libraryCharacterEvidenceByShot.value.size)
const libraryCharacterImageCount = computed(() => libraryCharacterGalleries.value.reduce((total, item) => total + item.images.length, 0))
const libraryCharacterMismatchCount = computed(() => libraryCharacterComparison.value.filter((item) => item.status !== 'matched').length)

function comparisonShotLabel(item: CharacterShotComparison): string {
  const shot = item.shotOrdinal === null ? item.shotId : `SHOT ${String(item.shotOrdinal).padStart(4, '0')}`
  if (props.episodes.length > 1 && item.episodeOrder !== null) return `E${String(item.episodeOrder).padStart(2, '0')} · ${shot}`
  return shot
}

function comparisonStatusLabel(status: CharacterCompareStatus): string {
  if (status === 'matched') return 'Evidence + Final'
  if (status === 'evidence_only') return 'AI ONLY'
  return 'FINAL ONLY'
}

function revisionKind(kind: string): string {
  return ({ AUTO: '自动资产', MANUAL: '人工修正', RESTORE: '历史恢复' } as Record<string, string>)[kind] || kind
}

async function loadEpisodeShots(episodeId: string): Promise<void> {
  if (!episodeId) {
    shots.value = []
    return
  }
  shots.value = await api.listShots(episodeId)
  page.value = 1
  selectedShotIds.value = []
  detailShotId.value = null
  picker.value = null
}

async function refreshWorkspace(): Promise<void> {
  workspace.value = await api.getAssetWorkspace(props.projectId)
}

async function refreshAll(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    await refreshWorkspace()
    const groups = await Promise.all(props.episodes.map((episode) => api.listShots(episode.id)))
    allShots.value = groups.flat()
    if (!selectedEpisodeId.value && props.episodes.length) selectedEpisodeId.value = props.episodes[0].id
    const index = props.episodes.findIndex((episode) => episode.id === selectedEpisodeId.value)
    shots.value = index >= 0 ? groups[index] : []
  } catch (err) {
    error.value = err instanceof Error ? err.message : '资产工作台读取失败'
  } finally {
    loading.value = false
  }
}

async function write(label: string, action: () => Promise<AssetWorkspace>): Promise<void> {
  busy.value = label
  error.value = ''
  try {
    workspace.value = await action()
    syncDrawerDraft()
  } catch (err) {
    error.value = err instanceof Error ? err.message : `${label}失败`
  } finally {
    busy.value = ''
  }
}

async function startExtraction(): Promise<void> {
  busy.value = '正在启动资产提取'
  error.value = ''
  try {
    await api.startFullAssetExtractionTask(props.projectId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '启动资产提取失败'
  } finally {
    busy.value = ''
  }
}

async function applyLatestEvidence(): Promise<void> {
  if (!window.confirm('基于最新 AI Evidence 创建新的资产版本？当前人工版本会保留在历史中。')) return
  await write('正在应用最新 Evidence', () => api.applyLatestAssetAnalysis(props.projectId))
}

function toggleSelected(shotId: string): void {
  selectedShotIds.value = selectedShotIds.value.includes(shotId)
    ? selectedShotIds.value.filter((id) => id !== shotId)
    : [...selectedShotIds.value, shotId]
}

function togglePageSelection(): void {
  const ids = pageShots.value.map((shot) => shot.id)
  if (pageAllSelected.value) {
    selectedShotIds.value = selectedShotIds.value.filter((id) => !ids.includes(id))
  } else {
    selectedShotIds.value = Array.from(new Set([...selectedShotIds.value, ...ids]))
  }
}

async function saveShotBindings(shot: Shot, binding: ShotAssetBindings): Promise<void> {
  await write(`正在保存 SHOT ${String(shot.ordinal).padStart(4, '0')}`, () => api.setShotAssetBindings(props.projectId, shot.id, binding))
}

async function toggleRowEntity(shot: Shot, kind: PickerKind, entityId: string): Promise<void> {
  const current = bindingsFor(shot.id)
  if (kind === 'character') {
    const next = current.character_ids.includes(entityId)
      ? current.character_ids.filter((id) => id !== entityId)
      : [...current.character_ids, entityId]
    await saveShotBindings(shot, { ...current, character_ids: next })
  } else {
    const next = current.prop_ids.includes(entityId)
      ? current.prop_ids.filter((id) => id !== entityId)
      : [...current.prop_ids, entityId]
    await saveShotBindings(shot, { ...current, prop_ids: next })
  }
}

async function setScene(shot: Shot, event: Event): Promise<void> {
  const target = event.target as HTMLSelectElement
  const current = bindingsFor(shot.id)
  await saveShotBindings(shot, { ...current, scene_id: target.value || null })
}

function togglePicker(shotId: string, kind: PickerKind): void {
  picker.value = picker.value?.shotId === shotId && picker.value.kind === kind ? null : { shotId, kind }
}

function syncDrawerDraft(): void {
  const shot = detailShot.value
  if (!shot) {
    drawerCharacterIds.value = []
    drawerSceneId.value = null
    drawerPropIds.value = []
    return
  }
  const binding = bindingsFor(shot.id)
  drawerCharacterIds.value = [...binding.character_ids]
  drawerSceneId.value = binding.scene_id
  drawerPropIds.value = [...binding.prop_ids]
}

function openDetail(shot: Shot): void {
  detailShotId.value = shot.id
  syncDrawerDraft()
}

function toggleDrawerEntity(kind: PickerKind, entityId: string): void {
  const target = kind === 'character' ? drawerCharacterIds : drawerPropIds
  target.value = target.value.includes(entityId)
    ? target.value.filter((id) => id !== entityId)
    : [...target.value, entityId]
}

async function saveDrawer(): Promise<void> {
  const shot = detailShot.value
  if (!shot) return
  await saveShotBindings(shot, {
    character_ids: [...drawerCharacterIds.value],
    scene_id: drawerSceneId.value,
    prop_ids: [...drawerPropIds.value],
  })
}

async function adoptDrawerEvidence(): Promise<void> {
  const shot = detailShot.value
  if (!shot) return
  const evidence = evidenceFor(shot.id)
  drawerCharacterIds.value = evidence.characters.map((item) => item.final_asset_id).filter((id): id is string => Boolean(id))
  drawerSceneId.value = evidence.scene?.final_asset_id ?? null
  drawerPropIds.value = evidence.props.map((item) => item.final_asset_id).filter((id): id is string => Boolean(id))
  await saveDrawer()
}

function openBatch(type: AssetEntityType): void {
  if (!selectedShotIds.value.length) return
  batchType.value = batchType.value === type ? null : type
  batchCharacterIds.value = []
  batchSceneId.value = null
  batchPropIds.value = []
}

function toggleBatchEntity(type: 'character' | 'prop', entityId: string): void {
  const target = type === 'character' ? batchCharacterIds : batchPropIds
  target.value = target.value.includes(entityId)
    ? target.value.filter((id) => id !== entityId)
    : [...target.value, entityId]
}

async function applyBatch(): Promise<void> {
  if (!batchType.value || !selectedShotIds.value.length) return
  const type = batchType.value
  await write(`正在批量修改${type === 'character' ? '人物' : type === 'scene' ? '场景' : '道具'}`, () => api.batchSetShotAssetBindings(props.projectId, {
    shot_ids: [...selectedShotIds.value],
    apply_characters: type === 'character',
    character_ids: type === 'character' ? [...batchCharacterIds.value] : [],
    apply_scene: type === 'scene',
    scene_id: type === 'scene' ? batchSceneId.value : null,
    apply_props: type === 'prop',
    prop_ids: type === 'prop' ? [...batchPropIds.value] : [],
  }))
  batchType.value = null
}

async function restoreRevision(revisionId: string, revision: number): Promise<void> {
  if (!window.confirm(`恢复资产 R${revision}？系统会创建新的 RESTORE Revision，当前版本不会删除。`)) return
  await write(`正在恢复 R${revision}`, () => api.restoreAssetRevision(revisionId))
  revisionOpen.value = false
}

function openLibrary(): void {
  libraryOpen.value = true
  libraryType.value = 'character'
  librarySelectedIds.value = []
  librarySplitShotIds.value = []
  libraryFocusId.value = workspace.value?.characters[0]?.id ?? null
}

function switchLibraryType(type: AssetEntityType): void {
  libraryType.value = type
  librarySelectedIds.value = []
  librarySplitShotIds.value = []
  const source = type === 'character' ? workspace.value?.characters : type === 'scene' ? workspace.value?.scenes : workspace.value?.props
  libraryFocusId.value = source?.[0]?.id ?? null
}

function focusLibraryAsset(id: string): void {
  libraryFocusId.value = id
  librarySplitShotIds.value = []
}

async function loadLibraryCharacterGallery(): Promise<void> {
  const requestId = ++libraryGalleryRequestId
  libraryCharacterGalleries.value = []
  libraryGalleryError.value = ''
  if (!libraryOpen.value || libraryType.value !== 'character' || !libraryFocus.value) {
    libraryGalleryLoading.value = false
    return
  }

  const candidateIds = [...new Set(libraryFocus.value.source_candidate_ids ?? [])]
  if (!candidateIds.length) {
    libraryGalleryLoading.value = false
    return
  }

  libraryGalleryLoading.value = true
  const settled = await Promise.allSettled(candidateIds.map((candidateId) => api.getCharacterGallery(candidateId)))
  if (requestId !== libraryGalleryRequestId) return

  libraryCharacterGalleries.value = settled
    .filter((item): item is PromiseFulfilledResult<CharacterGalleryPayload> => item.status === 'fulfilled')
    .map((item) => item.value)
  const failed = settled.filter((item) => item.status === 'rejected').length
  if (failed) libraryGalleryError.value = `${failed} 个历史 Candidate Gallery 无法读取；已展示其余 Evidence。`
  libraryGalleryLoading.value = false
}

function toggleLibrarySelected(id: string): void {
  librarySelectedIds.value = librarySelectedIds.value.includes(id)
    ? librarySelectedIds.value.filter((item) => item !== id)
    : [...librarySelectedIds.value, id]
}

async function createLibraryAsset(): Promise<void> {
  const label = libraryType.value === 'character' ? '人物' : libraryType.value === 'scene' ? '场景' : '道具'
  const name = window.prompt(`新建${label}名称`)
  if (!name?.trim()) return
  await write(`正在新建${label}`, () => api.createFinalAsset(props.projectId, libraryType.value, name.trim()))
  const source = libraryType.value === 'character' ? workspace.value?.characters : libraryType.value === 'scene' ? workspace.value?.scenes : workspace.value?.props
  libraryFocusId.value = source?.at(-1)?.id ?? libraryFocusId.value
}

async function renameLibraryAsset(): Promise<void> {
  const asset = libraryFocus.value
  if (!asset) return
  const name = window.prompt('修改资产名称', asset.name)
  if (!name?.trim() || name.trim() === asset.name) return
  await write('正在重命名资产', () => api.renameFinalAsset(props.projectId, libraryType.value, asset.id, name.trim()))
}

async function deleteLibraryAsset(): Promise<void> {
  const asset = libraryFocus.value
  if (!asset || !window.confirm(`删除「${asset.name}」并移除它的全部 Shot Binding？`)) return
  await write('正在删除资产', () => api.deleteFinalAsset(props.projectId, libraryType.value, asset.id))
  const source = libraryType.value === 'character' ? workspace.value?.characters : libraryType.value === 'scene' ? workspace.value?.scenes : workspace.value?.props
  libraryFocusId.value = source?.[0]?.id ?? null
}

async function mergeLibraryAssets(): Promise<void> {
  if (librarySelectedIds.value.length < 2) return
  const targetId = libraryFocusId.value && librarySelectedIds.value.includes(libraryFocusId.value)
    ? libraryFocusId.value
    : librarySelectedIds.value[0]
  if (!window.confirm(`合并选中的 ${librarySelectedIds.value.length} 个资产？`)) return
  await write('正在合并资产', () => api.mergeFinalAssets(props.projectId, libraryType.value, [...librarySelectedIds.value], targetId))
  libraryFocusId.value = targetId
  librarySelectedIds.value = []
}

function toggleLibrarySplitShot(shotId: string): void {
  librarySplitShotIds.value = librarySplitShotIds.value.includes(shotId)
    ? librarySplitShotIds.value.filter((id) => id !== shotId)
    : [...librarySplitShotIds.value, shotId]
}

async function splitLibraryAsset(): Promise<void> {
  const asset = libraryFocus.value
  if (!asset || !librarySplitShotIds.value.length) return
  const name = window.prompt('拆分后的新资产名称', `${asset.name} · 拆分`)
  if (!name?.trim()) return
  await write('正在拆分资产', () => api.splitFinalAsset(props.projectId, libraryType.value, asset.id, [...librarySplitShotIds.value], name.trim()))
  librarySplitShotIds.value = []
}

function onTaskFinished(event: Event): void {
  const detail = (event as CustomEvent).detail as { task_type?: string } | undefined
  if (detail?.task_type === 'ASSET_EXTRACTION_V3') void refreshAll()
}

watch([filter, search, selectedEpisodeId], () => { page.value = 1 })
watch(pageCount, (count) => { if (page.value > count) page.value = count })
watch(detailShotId, syncDrawerDraft)
watch(libraryGalleryKey, () => { void loadLibraryCharacterGallery() })

onMounted(async () => {
  if (props.episodes.length) selectedEpisodeId.value = props.episodes[0].id
  await refreshAll()
  window.addEventListener('studio-task-finished', onTaskFinished)
})

onUnmounted(() => window.removeEventListener('studio-task-finished', onTaskFinished))
</script>

<template>
  <section class="asset-matrix-v4">
    <header class="asset-matrix-header">
      <div class="asset-matrix-title">
        <div class="asset-matrix-title-line">
          <h1>资产</h1>
          <span v-if="currentRevision" class="asset-revision-pill">Current R{{ currentRevision.revision }} · {{ revisionKind(currentRevision.kind) }}</span>
          <span v-if="workspace?.stale" class="asset-stale-pill">STALE</span>
        </div>
        <p>{{ workspace?.characters.length ?? 0 }} 人物 · {{ workspace?.scenes.length ?? 0 }} Final 场景 · {{ workspace?.props.length ?? 0 }} 道具 · {{ episodes.length }} 集</p>
      </div>
      <div class="asset-matrix-header-actions">
        <button class="matrix-button secondary" @click="openLibrary">资产库</button>
        <button v-if="workspace?.revisions.length" class="matrix-button secondary" @click="revisionOpen = !revisionOpen">版本历史 {{ revisionOpen ? '▴' : '▾' }}</button>
        <button v-if="workspace?.stale && workspace.analysis" class="matrix-button warning" :disabled="!!busy" @click="applyLatestEvidence">采用新 Evidence</button>
        <button class="matrix-button primary" :disabled="!!busy || !episodes.length" @click="startExtraction">{{ workspace?.analysis ? '重新提取资产' : '提取资产' }}</button>
      </div>
    </header>

    <div v-if="revisionOpen" class="matrix-revision-popover">
      <div class="matrix-popover-head"><strong>资产版本历史</strong><span>恢复会创建新版本</span></div>
      <button v-for="item in workspace?.revisions ?? []" :key="item.id" :disabled="item.is_current" @click="restoreRevision(item.id, item.revision)">
        <b>R{{ item.revision }}</b><span>{{ revisionKind(item.kind) }}</span><small>{{ item.note || '—' }}</small><em>{{ item.is_current ? 'CURRENT' : '恢复' }}</em>
      </button>
    </div>

    <p v-if="error" class="matrix-error">{{ error }}</p>
    <div v-if="workspace?.stale" class="matrix-stale-banner">
      <strong>最新 AI Evidence 已变化，但当前人工资产没有被覆盖。</strong>
      <span>继续使用当前版本，或点击“采用新 Evidence”创建新的 AUTO Revision。</span>
    </div>

    <div class="asset-matrix-toolbar">
      <select v-model="selectedEpisodeId" @change="loadEpisodeShots(selectedEpisodeId)">
        <option v-for="episode in episodes" :key="episode.id" :value="episode.id">第{{ String(episode.sort_order).padStart(2, '0') }}集 · {{ episode.title }}</option>
      </select>
      <span class="shot-count-pill">{{ shots.length }} Shots</span>
      <div class="matrix-filters">
        <button :class="{ active: filter === 'all' }" @click="filter = 'all'">全部 <span>{{ filterCounts.all }}</span></button>
        <button :class="{ active: filter === 'pending' }" @click="filter = 'pending'">待处理 <span>{{ filterCounts.pending }}</span></button>
        <button :class="{ active: filter === 'conflict' }" @click="filter = 'conflict'">AI 冲突 <span>{{ filterCounts.conflict }}</span></button>
        <button :class="{ active: filter === 'unbound' }" @click="filter = 'unbound'">未绑定 <span>{{ filterCounts.unbound }}</span></button>
        <button :class="{ active: filter === 'low' }" @click="filter = 'low'">低置信度 <span>{{ filterCounts.low }}</span></button>
      </div>
      <input v-model="search" class="matrix-search" type="search" placeholder="搜索 Shot / 人物 / 场景 / 道具" />
    </div>

    <div v-if="selectedShotIds.length" class="matrix-batch-bar">
      <strong>已选择 {{ selectedShotIds.length }} 个 Shots</strong>
      <div class="matrix-batch-actions">
        <button @click="openBatch('character')">批量人物</button>
        <button @click="openBatch('scene')">批量场景</button>
        <button @click="openBatch('prop')">批量道具</button>
        <button class="clear" @click="selectedShotIds = []; batchType = null">清除选择</button>
      </div>
      <div v-if="batchType" class="matrix-batch-editor">
        <div class="matrix-popover-head">
          <strong>{{ batchType === 'character' ? '统一人物' : batchType === 'scene' ? '统一场景' : '统一关键道具' }}</strong>
          <span>只修改该维度；其他 Binding 保持不变</span>
        </div>
        <div v-if="batchType === 'character'" class="matrix-option-list">
          <label v-for="item in workspace?.characters ?? []" :key="item.id"><input type="checkbox" :checked="batchCharacterIds.includes(item.id)" @change="toggleBatchEntity('character', item.id)" />{{ item.name }}</label>
        </div>
        <select v-else-if="batchType === 'scene'" v-model="batchSceneId"><option :value="null">清空场景</option><option v-for="item in workspace?.scenes ?? []" :key="item.id" :value="item.id">{{ item.name }}</option></select>
        <div v-else class="matrix-option-list">
          <label v-for="item in workspace?.props ?? []" :key="item.id"><input type="checkbox" :checked="batchPropIds.includes(item.id)" @change="toggleBatchEntity('prop', item.id)" />{{ item.name }}</label>
        </div>
        <div class="matrix-batch-editor-actions"><button class="matrix-button secondary" @click="batchType = null">取消</button><button class="matrix-button primary" :disabled="!!busy" @click="applyBatch">应用到 {{ selectedShotIds.length }} 个 Shots</button></div>
      </div>
    </div>

    <div v-if="loading" class="matrix-loading">正在读取 Final Asset / Shot Binding…</div>

    <div v-else class="matrix-work-area" :class="{ 'drawer-open': detailShot }">
      <div class="matrix-table-wrap">
        <table class="shot-review-table">
          <thead>
            <tr>
              <th class="select-col"><input type="checkbox" :checked="pageAllSelected" @change="togglePageSelection" /></th>
              <th class="shot-col">Shot</th>
              <th class="visual-col">画面 / 时间</th>
              <th>人物</th>
              <th class="scene-col">场景</th>
              <th>关键道具</th>
              <th class="status-col">状态</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="shot in pageShots" :key="shot.id" :class="{ focused: detailShotId === shot.id }">
              <td class="select-col"><input type="checkbox" :checked="selectedShotIds.includes(shot.id)" @change="toggleSelected(shot.id)" /></td>
              <td class="shot-col"><button class="shot-id-button" @click="openDetail(shot)">SHOT {{ String(shot.ordinal).padStart(4, '0') }}</button></td>
              <td class="visual-col">
                <button class="matrix-thumb" @click="openDetail(shot)"><img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" alt="" /></button>
                <div class="matrix-time"><span>{{ timecode(shot.start_us) }}</span><span>{{ timecode(shot.end_us) }}</span></div>
              </td>
              <td>
                <div class="matrix-entity-cell">
                  <div class="matrix-chips">
                    <button v-for="id in bindingsFor(shot.id).character_ids" :key="id" class="matrix-chip" title="点击移除" @click.stop="toggleRowEntity(shot, 'character', id)">{{ assetName('character', id) }} <span>×</span></button>
                    <button class="matrix-add" @click.stop="togglePicker(shot.id, 'character')">+</button>
                  </div>
                  <small class="matrix-ai-line">AI: {{ evidenceFor(shot.id).characters.length ? evidenceFor(shot.id).characters.map((item) => `${item.label} ${confidenceLabel(item.confidence)}`).join(' · ') : '—' }}</small>
                  <div v-if="picker?.shotId === shot.id && picker.kind === 'character'" class="matrix-picker">
                    <strong>人物</strong>
                    <label v-for="item in workspace?.characters ?? []" :key="item.id"><input type="checkbox" :checked="bindingsFor(shot.id).character_ids.includes(item.id)" @change="toggleRowEntity(shot, 'character', item.id)" />{{ item.name }}</label>
                  </div>
                </div>
              </td>
              <td class="scene-col">
                <select :value="bindingsFor(shot.id).scene_id ?? ''" @change="setScene(shot, $event)"><option value="">未绑定</option><option v-for="item in workspace?.scenes ?? []" :key="item.id" :value="item.id">{{ item.name }}</option></select>
                <small class="matrix-ai-line">AI: {{ evidenceFor(shot.id).scene ? `${evidenceFor(shot.id).scene?.label} ${confidenceLabel(evidenceFor(shot.id).scene?.confidence ?? null)}` : '—' }}</small>
              </td>
              <td>
                <div class="matrix-entity-cell">
                  <div class="matrix-chips">
                    <button v-for="id in bindingsFor(shot.id).prop_ids" :key="id" class="matrix-chip" title="点击移除" @click.stop="toggleRowEntity(shot, 'prop', id)">{{ assetName('prop', id) }} <span>×</span></button>
                    <button class="matrix-add wide" @click.stop="togglePicker(shot.id, 'prop')">{{ bindingsFor(shot.id).prop_ids.length ? '+' : '+ 添加' }}</button>
                  </div>
                  <small class="matrix-ai-line">AI: {{ evidenceFor(shot.id).props.length ? evidenceFor(shot.id).props.map((item) => `${item.label} ${confidenceLabel(item.confidence)}`).join(' · ') : '—' }}</small>
                  <div v-if="picker?.shotId === shot.id && picker.kind === 'prop'" class="matrix-picker">
                    <strong>关键道具</strong>
                    <label v-for="item in workspace?.props ?? []" :key="item.id"><input type="checkbox" :checked="bindingsFor(shot.id).prop_ids.includes(item.id)" @change="toggleRowEntity(shot, 'prop', item.id)" />{{ item.name }}</label>
                    <span v-if="!workspace?.props.length">还没有道具资产，请到“资产库”新建。</span>
                  </div>
                </div>
              </td>
              <td class="status-col"><button :class="['matrix-status', reviewState(shot).key]" @click="openDetail(shot)">{{ reviewState(shot).key === 'ok' ? '✓' : reviewState(shot).key === 'conflict' ? '⚠' : '○' }} {{ reviewState(shot).label }}</button></td>
            </tr>
          </tbody>
        </table>

        <div v-if="!pageShots.length" class="matrix-empty">当前筛选没有 Shot。</div>
        <footer class="matrix-pagination">
          <span>共 {{ filteredShots.length }} 个 Shots</span>
          <div><button :disabled="page <= 1" @click="page--">‹</button><span>{{ page }} / {{ pageCount }}</span><button :disabled="page >= pageCount" @click="page++">›</button><select v-model.number="pageSize"><option :value="8">8 条/页</option><option :value="10">10 条/页</option><option :value="15">15 条/页</option></select></div>
        </footer>
      </div>

      <aside v-if="detailShot" class="matrix-drawer">
        <header><div><strong>SHOT {{ String(detailShot.ordinal).padStart(4, '0') }} · 详情</strong><small>{{ timecode(detailShot.start_us) }} → {{ timecode(detailShot.end_us) }}</small></div><button @click="detailShotId = null">×</button></header>
        <video :key="detailShot.id" :src="`${detailShot.reference_url}?v=${detailShot.start_us}-${detailShot.end_us}`" controls preload="metadata"></video>

        <section>
          <div class="drawer-section-title"><strong>Final Binding</strong><span>可编辑</span></div>
          <label class="drawer-field"><span>人物</span><div class="drawer-options"><label v-for="item in workspace?.characters ?? []" :key="item.id"><input type="checkbox" :checked="drawerCharacterIds.includes(item.id)" @change="toggleDrawerEntity('character', item.id)" />{{ item.name }}</label></div></label>
          <label class="drawer-field"><span>场景</span><select v-model="drawerSceneId"><option :value="null">未绑定</option><option v-for="item in workspace?.scenes ?? []" :key="item.id" :value="item.id">{{ item.name }}</option></select></label>
          <label class="drawer-field"><span>关键道具</span><div class="drawer-options compact"><label v-for="item in workspace?.props ?? []" :key="item.id"><input type="checkbox" :checked="drawerPropIds.includes(item.id)" @change="toggleDrawerEntity('prop', item.id)" />{{ item.name }}</label><small v-if="!workspace?.props.length">暂无道具资产</small></div></label>
        </section>

        <section class="drawer-evidence">
          <div class="drawer-section-title"><strong>AI Evidence</strong><span>只作建议</span></div>
          <div v-for="item in evidenceFor(detailShot.id).characters" :key="item.candidate_id" class="drawer-evidence-row"><img v-if="item.cover_url" :src="item.cover_url" alt="" /><div><b>{{ item.label }}</b><small>人物 · {{ confidenceLabel(item.confidence) }}</small></div><em v-if="item.final_asset_id">可采用</em></div>
          <div v-if="evidenceFor(detailShot.id).scene" class="drawer-evidence-row"><img v-if="evidenceFor(detailShot.id).scene?.cover_url" :src="evidenceFor(detailShot.id).scene?.cover_url ?? ''" alt="" /><div><b>{{ evidenceFor(detailShot.id).scene?.label }}</b><small>场景 · {{ confidenceLabel(evidenceFor(detailShot.id).scene?.confidence ?? null) }}</small></div><em v-if="evidenceFor(detailShot.id).scene?.final_asset_id">可采用</em></div>
          <div v-for="item in evidenceFor(detailShot.id).props" :key="item.candidate_id" class="drawer-evidence-row"><span class="drawer-prop-icon">物</span><div><b>{{ item.label }}</b><small>道具 · {{ confidenceLabel(item.confidence) }}</small></div><em v-if="item.final_asset_id">可采用</em></div>
          <p v-if="!evidenceFor(detailShot.id).characters.length && !evidenceFor(detailShot.id).scene && !evidenceFor(detailShot.id).props.length">当前 Shot 没有自动 Evidence。</p>
        </section>

        <footer><button class="matrix-button secondary" :disabled="!!busy" @click="adoptDrawerEvidence">采用 AI 建议</button><button class="matrix-button primary" :disabled="!!busy" @click="saveDrawer">保存修改</button></footer>
      </aside>
    </div>

    <div v-if="libraryOpen" class="asset-library-modal" @click.self="libraryOpen = false">
      <div class="asset-library-dialog">
        <header><div><strong>资产库</strong><span>项目级 Final Asset · 合并 / 拆分 / 改名 / 删除</span></div><button @click="libraryOpen = false">×</button></header>
        <nav><button :class="{ active: libraryType === 'character' }" @click="switchLibraryType('character')">人物 {{ workspace?.characters.length ?? 0 }}</button><button :class="{ active: libraryType === 'scene' }" @click="switchLibraryType('scene')">场景 {{ workspace?.scenes.length ?? 0 }}</button><button :class="{ active: libraryType === 'prop' }" @click="switchLibraryType('prop')">道具 {{ workspace?.props.length ?? 0 }}</button></nav>
        <div class="asset-library-toolbar"><input v-model="librarySearch" type="search" placeholder="搜索资产" /><button class="matrix-button secondary" @click="createLibraryAsset">+ 新建</button><button class="matrix-button secondary" :disabled="librarySelectedIds.length < 2" @click="mergeLibraryAssets">合并选中 {{ librarySelectedIds.length }}</button></div>
        <div class="asset-library-body">
          <div class="asset-library-list">
            <button v-for="item in libraryAssets" :key="item.id" :class="{ active: item.id === libraryFocusId }" @click="focusLibraryAsset(item.id)"><input type="checkbox" :checked="librarySelectedIds.includes(item.id)" @click.stop @change="toggleLibrarySelected(item.id)" /><img v-if="item.cover_url" :src="item.cover_url" alt="" /><span><strong>{{ item.name }}</strong><small>{{ item.shot_count }} Shots · {{ item.status }}</small></span></button>
          </div>
          <div v-if="libraryFocus" class="asset-library-detail">
            <div class="asset-library-detail-head"><div><strong>{{ libraryFocus.name }}</strong><span>{{ libraryType === 'character' ? `${libraryFocus.shot_count} Final Binding Shots` : `${libraryFocus.shot_count} Shots` }}</span></div><div><button @click="renameLibraryAsset">改名</button><button class="danger" @click="deleteLibraryAsset">删除</button></div></div>

            <template v-if="libraryType === 'character'">
              <div class="asset-library-character-summary">
                <div><strong>{{ libraryFocus.shot_count }}</strong><span>Final Binding Shots</span></div>
                <div><strong>{{ libraryCharacterEvidenceShotCount }}</strong><span>Evidence Shots</span></div>
                <div><strong>{{ libraryCharacterImageCount }}</strong><span>人物 crop</span></div>
                <div :class="{ warning: libraryCharacterMismatchCount > 0 }"><strong>{{ libraryCharacterMismatchCount }}</strong><span>不一致 Shots</span></div>
              </div>
              <p class="asset-library-character-help">每张卡片上方是 Shot 整帧上下文，下方是模型真正分类到该人物的 Person crop。绿色表示 Evidence 与 Final Binding 同时存在；AI ONLY / FINAL ONLY 就是需要继续检查的差异。</p>
              <div v-if="libraryGalleryLoading" class="asset-library-gallery-state">正在读取人物 Evidence Gallery…</div>
              <p v-if="libraryGalleryError" class="asset-library-gallery-warning">{{ libraryGalleryError }}</p>
              <div v-if="!libraryGalleryLoading && !libraryFocus.source_candidate_ids.length" class="asset-library-gallery-state">这个人物没有关联 AI Candidate，属于人工 Final Asset，因此没有可对照的 Gallery Evidence。</div>
              <div v-else-if="!libraryGalleryLoading && !libraryCharacterComparison.length" class="asset-library-gallery-state">当前人物没有可对照的 Shot Evidence / Final Binding。</div>
              <div v-else class="asset-library-character-grid">
                <article v-for="item in libraryCharacterComparison" :key="item.shotId" :class="['asset-library-character-shot', item.status]">
                  <div class="asset-library-character-shot-head">
                    <label v-if="item.finalBound" title="勾选后可从当前 Final Asset 拆分"><input type="checkbox" :checked="librarySplitShotIds.includes(item.shotId)" @change="toggleLibrarySplitShot(item.shotId)" /></label>
                    <b>{{ comparisonShotLabel(item) }}</b>
                    <em :class="item.status">{{ comparisonStatusLabel(item.status) }}</em>
                  </div>
                  <div class="asset-library-context-frame">
                    <img v-if="item.shot?.thumbnail_url" :src="thumbnailUrl(item.shot)" alt="Shot 整帧" />
                    <span v-else>无 Shot 整帧缩略图</span>
                    <small>SHOT 整帧</small>
                  </div>
                  <div v-if="item.evidenceImages.length" class="asset-library-evidence-strip">
                    <img v-for="image in item.evidenceImages.slice(0, 3)" :key="`${image.index}-${image.url}`" :src="image.url" alt="人物 Evidence crop" loading="lazy" />
                    <span v-if="item.evidenceImages.length > 3">+{{ item.evidenceImages.length - 3 }}</span>
                  </div>
                  <div v-else class="asset-library-no-evidence">没有 AI 人物 crop</div>
                  <small class="asset-library-evidence-caption">{{ item.evidenceImages.length }} 张 Evidence crop</small>
                </article>
              </div>
              <button class="matrix-button primary" :disabled="!librarySplitShotIds.length || librarySplitShotIds.length >= libraryFocusShots.length" @click="splitLibraryAsset">拆分所选 {{ librarySplitShotIds.length }} 个 Final Shots</button>
            </template>

            <template v-else>
              <p>选择其中部分 Shot，可以把它们拆成新的独立资产。</p>
              <div class="asset-library-shot-grid"><label v-for="shot in libraryFocusShots" :key="shot.id"><input type="checkbox" :checked="librarySplitShotIds.includes(shot.id)" @change="toggleLibrarySplitShot(shot.id)" /><img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" alt="" /><span>SHOT {{ String(shot.ordinal).padStart(4, '0') }}</span></label></div>
              <button class="matrix-button primary" :disabled="!librarySplitShotIds.length || librarySplitShotIds.length >= libraryFocusShots.length" @click="splitLibraryAsset">拆分所选 {{ librarySplitShotIds.length }} 个 Shots</button>
            </template>
          </div>
        </div>
      </div>
    </div>

    <div v-if="busy" class="matrix-busy-toast"><span></span>{{ busy }}…</div>
  </section>
</template>