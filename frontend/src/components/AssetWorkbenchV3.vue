<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type {
  AssetEntityType,
  AssetEvidenceItem,
  AssetSemanticModelStatus,
  AssetWorkspace,
  Episode,
  F05ModelStatus,
  FinalAssetEntity,
  Shot,
  ShotAssetBindings,
} from '../types/studio'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

const workspace = ref<AssetWorkspace | null>(null)
const faceModels = ref<F05ModelStatus | null>(null)
const semanticModel = ref<AssetSemanticModelStatus | null>(null)
const selectedEpisodeId = ref('')
const shots = ref<Shot[]>([])
const allShots = ref<Shot[]>([])
const selectedShot = ref<Shot | null>(null)
const view = ref<'shot' | AssetEntityType>('shot')
const busy = ref('')
const error = ref('')
const revisionOpen = ref(false)
const assetSearch = ref('')
const selectedAssetId = ref<string | null>(null)
const selectedMergeIds = ref<string[]>([])
const splitShotIds = ref<string[]>([])
const draftCharacterIds = ref<string[]>([])
const draftSceneId = ref<string | null>(null)
const draftPropIds = ref<string[]>([])

const selectedEpisode = computed(() => props.episodes.find((item) => item.id === selectedEpisodeId.value) ?? null)
const selectedBindings = computed(() => selectedShot.value ? workspace.value?.bindings_by_shot[selectedShot.value.id] ?? emptyBindings() : emptyBindings())
const selectedEvidence = computed(() => selectedShot.value ? workspace.value?.evidence_by_shot[selectedShot.value.id] ?? { characters: [], scene: null, props: [] } : { characters: [], scene: null, props: [] })
const currentRevision = computed(() => workspace.value?.revision ?? null)
const activeAssets = computed<FinalAssetEntity[]>(() => {
  if (!workspace.value || view.value === 'shot') return []
  const items = view.value === 'character' ? workspace.value.characters : view.value === 'scene' ? workspace.value.scenes : workspace.value.props
  const query = assetSearch.value.trim().toLowerCase()
  return query ? items.filter((item) => item.name.toLowerCase().includes(query)) : items
})
const selectedAsset = computed(() => activeAssets.value.find((item) => item.id === selectedAssetId.value) ?? null)
const selectedAssetShots = computed(() => {
  const ids = new Set(selectedAsset.value?.shot_ids ?? [])
  return allShots.value.filter((shot) => ids.has(shot.id))
})

function emptyBindings(): ShotAssetBindings {
  return { character_ids: [], scene_id: null, prop_ids: [] }
}

function timecode(us: number): string {
  const ms = Math.max(0, Math.round(us / 1000))
  const minutes = Math.floor(ms / 60_000)
  const seconds = Math.floor((ms % 60_000) / 1000)
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`
}

function confidence(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

function thumbnailUrl(shot: Shot): string {
  return shot.thumbnail_url ? `${shot.thumbnail_url}?v=${shot.start_us}-${shot.end_us}` : ''
}

function assetLabel(type: AssetEntityType): string {
  return type === 'character' ? '人物' : type === 'scene' ? '场景' : '道具'
}

function revisionKind(kind: string): string {
  return ({ AUTO: '自动资产', MANUAL: '人工修正', RESTORE: '历史恢复' } as Record<string, string>)[kind] || kind
}

/**
 * 职责：把 Final Binding 复制到右侧编辑草稿。
 * 输入：当前 Shot；输出：人物 / 场景 / 道具三个草稿字段。
 * 为什么：用户可以同时修改三类绑定，最后一次原子保存，避免产生半完成状态。
 */
function syncBindingDraft(): void {
  const value = selectedBindings.value
  draftCharacterIds.value = [...value.character_ids]
  draftSceneId.value = value.scene_id
  draftPropIds.value = [...value.prop_ids]
}

function selectShot(shot: Shot): void {
  selectedShot.value = shot
  syncBindingDraft()
}

async function loadEpisodeShots(episodeId: string): Promise<void> {
  const next = await api.listShots(episodeId)
  shots.value = next
  const previous = selectedShot.value?.id
  selectShot(next.find((item) => item.id === previous) ?? next[0] ?? null as unknown as Shot)
  if (!next.length) selectedShot.value = null
}

async function chooseEpisode(episodeId: string): Promise<void> {
  selectedEpisodeId.value = episodeId
  error.value = ''
  try {
    await loadEpisodeShots(episodeId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '剧集 Shot 读取失败'
  }
}

/**
 * 职责：刷新 Final Asset、模型状态与全项目 Shot 索引。
 * 输入：Project ID；输出：更新页面所有可编辑数据。
 * 为什么：任务完成、Revision 恢复、人工写操作后都必须从同一个 Final Asset Source of Truth 重载。
 */
async function refreshAll(): Promise<void> {
  const [nextWorkspace, nextFaceModels, nextSemantic] = await Promise.all([
    api.getAssetWorkspace(props.projectId),
    api.getF05ModelStatus(),
    api.getAssetSemanticModelStatus(),
  ])
  workspace.value = nextWorkspace
  faceModels.value = nextFaceModels
  semanticModel.value = nextSemantic

  const shotGroups = await Promise.all(props.episodes.map((episode) => api.listShots(episode.id)))
  allShots.value = shotGroups.flat()
  if (!selectedEpisodeId.value && props.episodes.length) selectedEpisodeId.value = props.episodes[0].id
  const currentGroup = shotGroups[props.episodes.findIndex((item) => item.id === selectedEpisodeId.value)] ?? []
  shots.value = currentGroup
  const selectedId = selectedShot.value?.id
  const nextSelected = currentGroup.find((item) => item.id === selectedId) ?? currentGroup[0] ?? null
  selectedShot.value = nextSelected
  syncBindingDraft()
}

async function write(label: string, action: () => Promise<AssetWorkspace>): Promise<void> {
  busy.value = label
  error.value = ''
  try {
    workspace.value = await action()
    syncBindingDraft()
  } catch (err) {
    error.value = err instanceof Error ? err.message : `${label}失败`
  } finally {
    busy.value = ''
  }
}

async function prepareFaceModels(): Promise<void> {
  busy.value = '正在准备人物识别模型'
  error.value = ''
  try {
    faceModels.value = await api.prepareF05Models()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '模型准备失败'
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

async function saveBindings(): Promise<void> {
  if (!selectedShot.value) return
  await write('正在保存 Shot Binding', () => api.setShotAssetBindings(props.projectId, selectedShot.value!.id, {
    character_ids: [...draftCharacterIds.value],
    scene_id: draftSceneId.value || null,
    prop_ids: [...draftPropIds.value],
  }))
}

function toggleId(bucket: 'character' | 'prop', id: string): void {
  const target = bucket === 'character' ? draftCharacterIds : draftPropIds
  target.value = target.value.includes(id) ? target.value.filter((item) => item !== id) : [...target.value, id]
}

async function createAsset(type: AssetEntityType, bindToShot = false, suggestedName = ''): Promise<void> {
  const name = window.prompt(`新建${assetLabel(type)}名称`, suggestedName)
  if (!name?.trim()) return
  await write(`正在新建${assetLabel(type)}`, () => api.createFinalAsset(props.projectId, type, name.trim(), bindToShot ? selectedShot.value?.id : null))
}

async function adoptEvidence(type: AssetEntityType, item: AssetEvidenceItem): Promise<void> {
  if (item.final_asset_id) {
    if (type === 'character' && !draftCharacterIds.value.includes(item.final_asset_id)) draftCharacterIds.value.push(item.final_asset_id)
    if (type === 'scene') draftSceneId.value = item.final_asset_id
    if (type === 'prop' && !draftPropIds.value.includes(item.final_asset_id)) draftPropIds.value.push(item.final_asset_id)
    return
  }
  await createAsset(type, true, item.label)
}

function switchView(next: 'shot' | AssetEntityType): void {
  view.value = next
  selectedMergeIds.value = []
  splitShotIds.value = []
  assetSearch.value = ''
  if (next !== 'shot') {
    const source = next === 'character' ? workspace.value?.characters : next === 'scene' ? workspace.value?.scenes : workspace.value?.props
    selectedAssetId.value = source?.[0]?.id ?? null
  }
}

function selectAsset(asset: FinalAssetEntity): void {
  selectedAssetId.value = asset.id
  splitShotIds.value = []
}

async function renameSelectedAsset(): Promise<void> {
  const asset = selectedAsset.value
  if (!asset || view.value === 'shot') return
  const name = window.prompt(`修改${assetLabel(view.value)}名称`, asset.name)
  if (!name?.trim() || name.trim() === asset.name) return
  await write('正在重命名资产', () => api.renameFinalAsset(props.projectId, view.value as AssetEntityType, asset.id, name.trim()))
}

async function deleteSelectedAsset(): Promise<void> {
  const asset = selectedAsset.value
  if (!asset || view.value === 'shot') return
  if (!window.confirm(`删除「${asset.name}」并移除所有 Shot Binding？`)) return
  const entityType = view.value as AssetEntityType
  await write('正在删除资产', () => api.deleteFinalAsset(props.projectId, entityType, asset.id))
  const next = entityType === 'character' ? workspace.value?.characters : entityType === 'scene' ? workspace.value?.scenes : workspace.value?.props
  selectedAssetId.value = next?.[0]?.id ?? null
}

function toggleMerge(assetId: string): void {
  selectedMergeIds.value = selectedMergeIds.value.includes(assetId)
    ? selectedMergeIds.value.filter((item) => item !== assetId)
    : [...selectedMergeIds.value, assetId]
}

async function mergeSelectedAssets(): Promise<void> {
  if (view.value === 'shot' || selectedMergeIds.value.length < 2) return
  const selected = [...selectedMergeIds.value]
  const targetId = selectedAssetId.value && selected.includes(selectedAssetId.value) ? selectedAssetId.value : selected[0]
  if (!window.confirm(`把选中的 ${selected.length} 个${assetLabel(view.value)}合并？将保留当前选中的资产身份。`)) return
  await write('正在合并资产', () => api.mergeFinalAssets(props.projectId, view.value as AssetEntityType, selected, targetId))
  selectedMergeIds.value = []
  selectedAssetId.value = targetId
}

function toggleSplitShot(shotId: string): void {
  splitShotIds.value = splitShotIds.value.includes(shotId)
    ? splitShotIds.value.filter((item) => item !== shotId)
    : [...splitShotIds.value, shotId]
}

async function splitSelectedAsset(): Promise<void> {
  const asset = selectedAsset.value
  if (!asset || view.value === 'shot' || !splitShotIds.value.length) return
  const name = window.prompt(`拆分后的新${assetLabel(view.value)}名称`, `${asset.name} · 拆分`)
  if (!name?.trim()) return
  await write('正在拆分资产', () => api.splitFinalAsset(props.projectId, view.value as AssetEntityType, asset.id, [...splitShotIds.value], name.trim()))
  splitShotIds.value = []
}

async function restoreRevision(revisionId: string, revision: number): Promise<void> {
  if (!window.confirm(`恢复资产 R${revision}？系统会创建新的 RESTORE Revision，当前版本不会被删除。`)) return
  await write(`正在恢复 R${revision}`, () => api.restoreAssetRevision(revisionId))
  revisionOpen.value = false
}

function onTaskFinished(event: Event): void {
  const detail = (event as CustomEvent).detail as { task_type?: string } | undefined
  if (detail?.task_type === 'ASSET_EXTRACTION_V3') void refreshAll()
}

watch(selectedBindings, syncBindingDraft)

onMounted(async () => {
  try {
    if (props.episodes.length) selectedEpisodeId.value = props.episodes[0].id
    await refreshAll()
    window.addEventListener('studio-task-finished', onTaskFinished)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '资产工作台读取失败'
  }
})

onUnmounted(() => window.removeEventListener('studio-task-finished', onTaskFinished))
</script>

<template>
  <section class="asset-v3">
    <header class="asset-v3-header">
      <div>
        <div class="asset-v3-title-row">
          <h1>资产</h1>
          <span v-if="workspace?.revision" class="asset-v3-revision">Current R{{ workspace.revision.revision }} · {{ revisionKind(workspace.revision.kind) }}</span>
          <span v-if="workspace?.stale" class="asset-v3-stale">STALE</span>
        </div>
        <div class="asset-v3-stats">
          <span>{{ workspace?.characters.length ?? 0 }} 人物</span><i>·</i>
          <span>{{ workspace?.scenes.length ?? 0 }} 场景</span><i>·</i>
          <span>{{ workspace?.props.length ?? 0 }} 道具</span><i>·</i>
          <span>{{ episodes.length }} 集</span>
        </div>
      </div>
      <div class="asset-v3-actions">
        <button v-if="!faceModels?.ready" class="asset-v3-secondary" :disabled="!!busy" @click="prepareFaceModels">准备人物模型</button>
        <button v-if="workspace?.stale && workspace.analysis" class="asset-v3-warning-button" :disabled="!!busy" @click="applyLatestEvidence">基于新 Evidence 创建版本</button>
        <button v-if="workspace?.revisions.length" class="asset-v3-secondary" @click="revisionOpen = !revisionOpen">版本历史 {{ revisionOpen ? '▴' : '▾' }}</button>
        <button class="asset-v3-primary" :disabled="!episodes.length || !!busy" @click="startExtraction">{{ workspace?.analysis ? '重新提取资产' : '提取资产' }}</button>
      </div>
    </header>

    <p v-if="error" class="asset-v3-error">{{ error }}</p>
    <div v-if="busy" class="asset-v3-busy"><span></span>{{ busy }}…</div>

    <div v-if="workspace?.stale" class="asset-v3-stale-banner">
      <div><strong>当前 Final Asset 与最新 AI Evidence 不一致</strong><span>人工版本没有被覆盖。你可以继续使用当前版本，也可以基于最新 Evidence 创建新的 AUTO Revision。</span></div>
      <button @click="applyLatestEvidence">查看并采用最新 Evidence</button>
    </div>

    <div class="asset-v3-model-strip">
      <span :class="faceModels?.ready ? 'ready' : 'warning'">人物身份：{{ faceModels?.ready ? 'Face/SFace + Body/服装辅助' : '模型未准备' }}</span>
      <span :class="semanticModel?.ready ? 'ready' : 'muted'">Qwen3-VL：{{ semanticModel?.ready ? semanticModel.model : '未配置 · 场景语义/道具可人工维护' }}</span>
      <span>Detection ≠ Identity · Evidence ≠ Final Asset</span>
    </div>

    <div v-if="revisionOpen" class="asset-v3-history">
      <div class="asset-v3-history-head"><strong>资产版本历史</strong><span>恢复会创建新版本，不覆盖历史</span></div>
      <div v-for="item in workspace?.revisions ?? []" :key="item.id" :class="['asset-v3-history-row', { current: item.is_current }]">
        <b>R{{ item.revision }}</b>
        <div><strong>{{ revisionKind(item.kind) }}</strong><small>{{ item.note || '—' }}</small></div>
        <span>{{ item.counts.characters }} 人物 · {{ item.counts.scenes }} 场景 · {{ item.counts.props }} 道具</span>
        <em>{{ item.is_current ? 'CURRENT' : 'HISTORY' }}</em>
        <button v-if="!item.is_current" @click="restoreRevision(item.id, item.revision)">恢复</button>
      </div>
    </div>

    <nav class="asset-v3-tabs">
      <button :class="{ active: view === 'shot' }" @click="switchView('shot')">按 Shot 检查</button>
      <button :class="{ active: view === 'character' }" @click="switchView('character')">人物库 <span>{{ workspace?.characters.length ?? 0 }}</span></button>
      <button :class="{ active: view === 'scene' }" @click="switchView('scene')">场景库 <span>{{ workspace?.scenes.length ?? 0 }}</span></button>
      <button :class="{ active: view === 'prop' }" @click="switchView('prop')">道具库 <span>{{ workspace?.props.length ?? 0 }}</span></button>
    </nav>

    <div v-if="view === 'shot'" class="asset-v3-shot-layout">
      <aside class="asset-v3-episodes">
        <div class="asset-v3-panel-head"><strong>剧集</strong><span>{{ episodes.length }}</span></div>
        <div class="asset-v3-episode-scroll">
          <button v-for="episode in episodes" :key="episode.id" :class="{ active: episode.id === selectedEpisodeId }" @click="chooseEpisode(episode.id)">
            <b>E{{ String(episode.sort_order).padStart(2, '0') }}</b><span>{{ episode.shot_count }} Shots</span><i>{{ episode.shot_count ? '✓' : '○' }}</i>
          </button>
        </div>
      </aside>

      <main class="asset-v3-shot-main">
        <div class="asset-v3-shot-head">
          <div><strong>{{ selectedEpisode?.title || '请选择剧集' }}</strong><span>{{ shots.length }} Shots</span></div>
          <span>选择镜头后直接修改右侧 Final Binding</span>
        </div>
        <div v-if="selectedShot" class="asset-v3-video">
          <video :key="selectedShot.id" :src="`${selectedShot.reference_url}?v=${selectedShot.start_us}-${selectedShot.end_us}`" controls preload="metadata"></video>
          <div><b>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</b><span>{{ timecode(selectedShot.start_us) }} → {{ timecode(selectedShot.end_us) }}</span></div>
        </div>
        <div v-else class="asset-v3-empty">当前剧集没有 Shot。</div>

        <div class="asset-v3-shot-list-head"><strong>Shots</strong><span>人物 / 场景 / 道具绑定直接显示在卡片上</span></div>
        <div class="asset-v3-shot-grid">
          <button v-for="shot in shots" :key="shot.id" :class="['asset-v3-shot-card', { active: selectedShot?.id === shot.id }]" @click="selectShot(shot)">
            <img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" alt="" />
            <div><b>{{ String(shot.ordinal).padStart(4, '0') }}</b><small>{{ timecode(shot.start_us) }}</small></div>
            <p>
              <span>人 {{ workspace?.bindings_by_shot[shot.id]?.character_ids.length ?? 0 }}</span>
              <span>{{ workspace?.bindings_by_shot[shot.id]?.scene_id ? '场 ✓' : '场 —' }}</span>
              <span>道 {{ workspace?.bindings_by_shot[shot.id]?.prop_ids.length ?? 0 }}</span>
            </p>
          </button>
        </div>
      </main>

      <aside v-if="selectedShot" class="asset-v3-inspector">
        <div class="asset-v3-inspector-head"><strong>SHOT {{ String(selectedShot.ordinal).padStart(4, '0') }}</strong><span>FINAL BINDING</span></div>

        <section class="asset-v3-binding-section">
          <div class="asset-v3-binding-title"><strong>人物</strong><button @click="createAsset('character', true)">+ 新建</button></div>
          <div class="asset-v3-check-list">
            <label v-for="item in workspace?.characters ?? []" :key="item.id">
              <input type="checkbox" :checked="draftCharacterIds.includes(item.id)" @change="toggleId('character', item.id)" />
              <img v-if="item.cover_url" :src="item.cover_url" alt="" /><span>{{ item.name }}</span><small>{{ item.shot_count }} Shots</small>
            </label>
            <p v-if="!workspace?.characters.length">还没有人物资产</p>
          </div>
        </section>

        <section class="asset-v3-binding-section">
          <div class="asset-v3-binding-title"><strong>场景</strong><button @click="createAsset('scene', true)">+ 新建</button></div>
          <select v-model="draftSceneId">
            <option :value="null">未绑定场景</option>
            <option v-for="item in workspace?.scenes ?? []" :key="item.id" :value="item.id">{{ item.name }}</option>
          </select>
        </section>

        <section class="asset-v3-binding-section">
          <div class="asset-v3-binding-title"><strong>关键道具</strong><button @click="createAsset('prop', true)">+ 新建</button></div>
          <div class="asset-v3-check-list compact">
            <label v-for="item in workspace?.props ?? []" :key="item.id">
              <input type="checkbox" :checked="draftPropIds.includes(item.id)" @change="toggleId('prop', item.id)" /><span>{{ item.name }}</span><small>{{ item.shot_count }} Shots</small>
            </label>
            <p v-if="!workspace?.props.length">暂无关键道具，可人工新建；配置 Qwen3-VL 后可自动给出 Evidence。</p>
          </div>
        </section>

        <button class="asset-v3-primary asset-v3-save" :disabled="!!busy" @click="saveBindings">保存当前 Shot Binding</button>

        <section class="asset-v3-evidence">
          <div class="asset-v3-evidence-head"><strong>AI EVIDENCE</strong><span>只作为建议，不会覆盖 Final</span></div>
          <div v-for="item in selectedEvidence.characters" :key="item.candidate_id" class="asset-v3-evidence-row">
            <img v-if="item.cover_url" :src="item.cover_url" alt="" /><div><b>{{ item.label }}</b><small>人物 · {{ confidence(item.confidence) }}</small></div><button @click="adoptEvidence('character', item)">采用</button>
          </div>
          <div v-if="selectedEvidence.scene" class="asset-v3-evidence-row">
            <img v-if="selectedEvidence.scene.cover_url" :src="selectedEvidence.scene.cover_url" alt="" /><div><b>{{ selectedEvidence.scene.label }}</b><small>场景 · {{ confidence(selectedEvidence.scene.confidence) }}</small></div><button @click="adoptEvidence('scene', selectedEvidence.scene)">采用</button>
          </div>
          <div v-for="item in selectedEvidence.props" :key="item.candidate_id" class="asset-v3-evidence-row">
            <div class="asset-v3-evidence-icon">物</div><div><b>{{ item.label }}</b><small>关键道具 · {{ confidence(item.confidence) }}</small></div><button @click="adoptEvidence('prop', item)">采用</button>
          </div>
          <p v-if="!selectedEvidence.characters.length && !selectedEvidence.scene && !selectedEvidence.props.length">当前 Shot 没有自动 Evidence；仍可直接人工绑定。</p>
        </section>
      </aside>
    </div>

    <div v-else class="asset-v3-library-layout">
      <aside class="asset-v3-library-list">
        <div class="asset-v3-library-tools">
          <input v-model="assetSearch" type="search" :placeholder="`搜索${assetLabel(view as AssetEntityType)}`" />
          <button @click="createAsset(view as AssetEntityType)">+ 新建</button>
        </div>
        <div class="asset-v3-library-scroll">
          <article v-for="asset in activeAssets" :key="asset.id" :class="{ active: selectedAssetId === asset.id }" @click="selectAsset(asset)">
            <input type="checkbox" :checked="selectedMergeIds.includes(asset.id)" @click.stop @change="toggleMerge(asset.id)" />
            <img v-if="asset.cover_url" :src="asset.cover_url" alt="" /><div v-else class="asset-v3-placeholder">{{ assetLabel(view as AssetEntityType).slice(0, 1) }}</div>
            <div><strong>{{ asset.name }}</strong><small>{{ asset.shot_count }} Shots · {{ asset.status }}</small></div>
            <span v-if="asset.confidence !== null">{{ confidence(asset.confidence) }}</span>
          </article>
        </div>
        <button class="asset-v3-secondary asset-v3-merge" :disabled="selectedMergeIds.length < 2 || !!busy" @click="mergeSelectedAssets">合并选中（{{ selectedMergeIds.length }}）</button>
      </aside>

      <main class="asset-v3-library-main">
        <div v-if="selectedAsset" class="asset-v3-library-header">
          <div class="asset-v3-library-identity">
            <img v-if="selectedAsset.cover_url" :src="selectedAsset.cover_url" alt="" />
            <div><span>{{ assetLabel(view as AssetEntityType).toUpperCase() }} ASSET</span><h2>{{ selectedAsset.name }}</h2><p>{{ selectedAsset.shot_count }} 个绑定 Shot · {{ selectedAsset.status }}</p></div>
          </div>
          <div><button @click="renameSelectedAsset">改名</button><button class="danger" @click="deleteSelectedAsset">删除</button></div>
        </div>
        <div v-if="selectedAsset" class="asset-v3-split-help">勾选下面一部分 Shot，可以把误合并的{{ assetLabel(view as AssetEntityType) }}拆成一个新资产。</div>
        <div class="asset-v3-bound-shots">
          <label v-for="shot in selectedAssetShots" :key="shot.id" :class="{ checked: splitShotIds.includes(shot.id) }">
            <input type="checkbox" :checked="splitShotIds.includes(shot.id)" @change="toggleSplitShot(shot.id)" />
            <img v-if="shot.thumbnail_url" :src="thumbnailUrl(shot)" alt="" />
            <div><b>SHOT {{ String(shot.ordinal).padStart(4, '0') }}</b><small>{{ timecode(shot.start_us) }}</small></div>
          </label>
          <div v-if="selectedAsset && !selectedAssetShots.length" class="asset-v3-empty">这个资产目前没有绑定 Shot。</div>
        </div>
      </main>

      <aside class="asset-v3-library-inspector">
        <template v-if="selectedAsset">
          <strong>资产操作</strong>
          <p>Final Asset 是后续内容剧本与重制设计消费的稳定身份。AI Candidate 只作为 Evidence。</p>
          <dl><div><dt>名称</dt><dd>{{ selectedAsset.name }}</dd></div><div><dt>绑定</dt><dd>{{ selectedAsset.shot_count }} Shots</dd></div><div><dt>来源</dt><dd>{{ selectedAsset.status }}</dd></div><div><dt>置信</dt><dd>{{ confidence(selectedAsset.confidence) }}</dd></div></dl>
          <button class="asset-v3-primary" :disabled="!splitShotIds.length || splitShotIds.length >= selectedAsset.shot_count || !!busy" @click="splitSelectedAsset">拆分所选 Shot（{{ splitShotIds.length }}）</button>
          <button class="asset-v3-secondary" @click="renameSelectedAsset">修改名称</button>
          <button class="asset-v3-danger" @click="deleteSelectedAsset">删除这个资产</button>
          <div class="asset-v3-note">合并：在左侧勾选两个以上资产。拆分：在中间勾选该资产的一部分 Shot。</div>
        </template>
      </aside>
    </div>
  </section>
</template>