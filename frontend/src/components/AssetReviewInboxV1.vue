<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api } from '../api/client'
import type {
  AssetEvidenceItem,
  AssetWorkspace,
  BackgroundTask,
  Episode,
  Shot,
  ShotAssetBindings,
  ShotAssetEvidence,
} from '../types/studio'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

const emit = defineEmits<{
  (event: 'open-matrix'): void
}>()

type InboxFilter = 'pending' | 'conflict' | 'unbound' | 'low'
type ReviewKey = 'ok' | 'conflict' | 'unbound' | 'low'

type ReviewState = {
  key: ReviewKey
  label: string
  conflict: boolean
  unbound: boolean
  low: boolean
}

type ReviewEntry = {
  episode: Episode
  shot: Shot
}

const workspace = ref<AssetWorkspace | null>(null)
const entries = ref<ReviewEntry[]>([])
const loading = ref(true)
const error = ref('')
const filter = ref<InboxFilter>('pending')

const charactersById = computed(() => new Map((workspace.value?.characters ?? []).map((item) => [item.id, item.name])))
const scenesById = computed(() => new Map((workspace.value?.scenes ?? []).map((item) => [item.id, item.name])))
const propsById = computed(() => new Map((workspace.value?.props ?? []).map((item) => [item.id, item.name])))

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

function highConfidence(item: AssetEvidenceItem | null | undefined, threshold = 0.75): boolean {
  return Boolean(item && item.confidence !== null && item.confidence >= threshold)
}

/**
 * Display-only review state. This mirrors the existing AssetReviewMatrixV4 thresholds.
 * Final Binding remains authority; this component never writes asset truth.
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

  if (conflict) return { key: 'conflict', label: 'AI 与当前绑定冲突', conflict, unbound, low }
  if (unbound) return { key: 'unbound', label: '存在高置信度内容未绑定', conflict, unbound, low }
  if (low) return { key: 'low', label: '有低置信度内容建议检查', conflict, unbound, low }
  return { key: 'ok', label: '自动一致', conflict, unbound, low }
}

const counts = computed(() => {
  const states = entries.value.map((entry) => reviewState(entry.shot))
  return {
    pending: states.filter((state) => state.key !== 'ok').length,
    conflict: states.filter((state) => state.conflict).length,
    unbound: states.filter((state) => state.unbound).length,
    low: states.filter((state) => state.low).length,
  }
})

const visibleEntries = computed(() => entries.value.filter((entry) => {
  const state = reviewState(entry.shot)
  if (filter.value === 'conflict') return state.conflict
  if (filter.value === 'unbound') return state.unbound
  if (filter.value === 'low') return state.low
  return state.key !== 'ok'
}))

function assetNames(ids: string[], map: Map<string, string>): string {
  const names = ids.map((id) => map.get(id)).filter((name): name is string => Boolean(name))
  return names.length ? names.join('、') : '未绑定'
}

function finalSceneName(sceneId: string | null): string {
  return sceneId ? scenesById.value.get(sceneId) ?? '未知场景' : '未绑定'
}

function confidenceLabel(value: number | null): string {
  return value === null ? '—' : `${Math.round(value * 100)}%`
}

function evidenceLabels(items: AssetEvidenceItem[]): string {
  if (!items.length) return '无建议'
  return items.map((item) => `${item.label} ${confidenceLabel(item.confidence)}`).join('、')
}

function sceneEvidenceLabel(item: AssetEvidenceItem | null): string {
  return item ? `${item.label} ${confidenceLabel(item.confidence)}` : '无建议'
}

function timecode(us: number): string {
  const totalSeconds = Math.max(0, Math.round(us / 1_000_000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}

function thumbnailUrl(shot: Shot): string {
  return shot.thumbnail_url ? `${shot.thumbnail_url}?v=${shot.start_us}-${shot.end_us}` : ''
}

async function refresh(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const [nextWorkspace, shotGroups] = await Promise.all([
      api.getAssetWorkspace(props.projectId),
      Promise.all(props.episodes.map((episode) => api.listShots(episode.id))),
    ])
    workspace.value = nextWorkspace
    entries.value = props.episodes.flatMap((episode, index) => (
      (shotGroups[index] ?? []).map((shot) => ({ episode, shot }))
    ))
  } catch (err) {
    error.value = err instanceof Error ? err.message : '待处理资产读取失败'
  } finally {
    loading.value = false
  }
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== props.projectId) return
  if (task.task_type === 'ASSET_EXTRACTION_V3') void refresh()
}

onMounted(() => {
  window.addEventListener('studio-task-finished', onTaskFinished)
  void refresh()
})

onUnmounted(() => window.removeEventListener('studio-task-finished', onTaskFinished))
</script>

<template>
  <section class="asset-review-inbox-v1">
    <header class="inbox-header">
      <div>
        <small>人工复核收件箱</small>
        <strong v-if="loading">正在检查需要处理的镜头…</strong>
        <strong v-else-if="counts.pending">需要处理 {{ counts.pending }} 个镜头</strong>
        <strong v-else>当前没有需要人工处理的镜头</strong>
        <span>这里只显示 AI Evidence 与当前 Final Binding 不一致、未绑定或低置信度的镜头。</span>
      </div>
      <button class="inbox-matrix-button" type="button" @click="emit('open-matrix')">打开完整绑定表</button>
    </header>

    <p v-if="error" class="inbox-error">{{ error }}</p>
    <div v-if="workspace?.stale" class="inbox-stale">
      <strong>最新 AI Evidence 已变化</strong>
      <span>当前人工 Final Asset 没有被覆盖；请在完整绑定表中决定是否采用新 Evidence。</span>
    </div>

    <nav class="inbox-filters" aria-label="待处理类型">
      <button :class="{ active: filter === 'pending' }" @click="filter = 'pending'">全部待处理 <span>{{ counts.pending }}</span></button>
      <button :class="{ active: filter === 'conflict' }" @click="filter = 'conflict'">冲突 <span>{{ counts.conflict }}</span></button>
      <button :class="{ active: filter === 'unbound' }" @click="filter = 'unbound'">未绑定 <span>{{ counts.unbound }}</span></button>
      <button :class="{ active: filter === 'low' }" @click="filter = 'low'">低置信度 <span>{{ counts.low }}</span></button>
    </nav>

    <div v-if="loading" class="inbox-loading">正在读取镜头绑定与 AI Evidence…</div>

    <div v-else-if="!visibleEntries.length" class="inbox-empty">
      <strong>{{ counts.pending ? '当前筛选没有镜头' : '这一步已经清理完成' }}</strong>
      <p>{{ counts.pending ? '切换上方筛选查看其他待处理类型。' : '如果需要抽查全部结果，可以打开完整绑定表。' }}</p>
      <button type="button" @click="emit('open-matrix')">查看完整绑定</button>
    </div>

    <div v-else class="inbox-list">
      <article v-for="entry in visibleEntries" :key="entry.shot.id" class="inbox-item">
        <div class="inbox-thumb">
          <img v-if="entry.shot.thumbnail_url" :src="thumbnailUrl(entry.shot)" alt="" loading="lazy" />
          <span v-else>暂无画面</span>
        </div>

        <div class="inbox-item-main">
          <header>
            <div>
              <small>第{{ String(entry.episode.sort_order).padStart(2, '0') }}集 · 镜头 {{ String(entry.shot.ordinal).padStart(4, '0') }}</small>
              <strong>{{ reviewState(entry.shot).label }}</strong>
            </div>
            <span :class="['inbox-state-pill', `tone-${reviewState(entry.shot).key}`]">{{ reviewState(entry.shot).key === 'conflict' ? '冲突' : reviewState(entry.shot).key === 'unbound' ? '未绑定' : '低置信度' }}</span>
          </header>

          <div class="inbox-binding-compare">
            <section>
              <h4>当前最终绑定</h4>
              <p><span>人物</span><strong>{{ assetNames(bindingsFor(entry.shot.id).character_ids, charactersById) }}</strong></p>
              <p><span>场景</span><strong>{{ finalSceneName(bindingsFor(entry.shot.id).scene_id) }}</strong></p>
              <p><span>道具</span><strong>{{ assetNames(bindingsFor(entry.shot.id).prop_ids, propsById) }}</strong></p>
            </section>
            <section class="ai-suggestion">
              <h4>AI 建议 · 仅作参考</h4>
              <p><span>人物</span><strong>{{ evidenceLabels(evidenceFor(entry.shot.id).characters) }}</strong></p>
              <p><span>场景</span><strong>{{ sceneEvidenceLabel(evidenceFor(entry.shot.id).scene) }}</strong></p>
              <p><span>道具</span><strong>{{ evidenceLabels(evidenceFor(entry.shot.id).props) }}</strong></p>
            </section>
          </div>
        </div>

        <div class="inbox-item-actions">
          <small>{{ timecode(entry.shot.start_us) }} → {{ timecode(entry.shot.end_us) }}</small>
          <button type="button" @click="emit('open-matrix')">查看并修改</button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.asset-review-inbox-v1 {
  margin: 10px 22px 0;
  display: grid;
  gap: 10px;
}
.inbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 14px 16px;
  border: 1px solid #dfe5ed;
  border-radius: 12px;
  background: #fff;
}
.inbox-header > div { min-width: 0; display: grid; gap: 2px; }
.inbox-header small { color: #8491a4; font-size: 10px; font-weight: 800; }
.inbox-header strong { color: #31435d; font-size: 15px; }
.inbox-header span { color: #78869a; font-size: 11px; }
.inbox-matrix-button,
.inbox-empty button,
.inbox-item-actions button {
  flex: none;
  min-height: 34px;
  border: 1px solid #cbd7e8;
  border-radius: 8px;
  padding: 0 11px;
  background: #fff;
  color: #496386;
  font-size: 10px;
  font-weight: 800;
  cursor: pointer;
}
.inbox-matrix-button:hover,
.inbox-empty button:hover,
.inbox-item-actions button:hover { border-color: #95acd1; background: #f6f9ff; }
.inbox-error,
.inbox-stale { margin: 0; border-radius: 9px; padding: 9px 11px; font-size: 11px; }
.inbox-error { border: 1px solid #efcaca; background: #fff3f3; color: #ac4545; }
.inbox-stale { display: flex; gap: 8px; align-items: baseline; border: 1px solid #ebd79a; background: #fff9e9; color: #8b651d; }
.inbox-stale span { color: #94783e; }
.inbox-filters { display: flex; gap: 6px; flex-wrap: wrap; }
.inbox-filters button {
  min-height: 32px;
  display: inline-flex;
  gap: 6px;
  align-items: center;
  border: 1px solid #dfe4eb;
  border-radius: 8px;
  padding: 0 10px;
  background: #fff;
  color: #637188;
  font-size: 10px;
  font-weight: 750;
  cursor: pointer;
}
.inbox-filters button span { min-width: 20px; border-radius: 999px; padding: 2px 5px; background: #eff2f6; color: #758297; text-align: center; }
.inbox-filters button.active { border-color: #8da8dc; background: #eef4ff; color: #3e5f9c; }
.inbox-loading,
.inbox-empty {
  min-height: 180px;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 6px;
  border: 1px solid #dfe5ed;
  border-radius: 12px;
  background: #fff;
  color: #748196;
  font-size: 11px;
  text-align: center;
}
.inbox-empty strong { color: #40516c; font-size: 14px; }
.inbox-empty p { margin: 0 0 5px; }
.inbox-list { display: grid; gap: 8px; }
.inbox-item {
  display: grid;
  grid-template-columns: 168px minmax(0, 1fr) 120px;
  gap: 12px;
  align-items: stretch;
  padding: 10px;
  border: 1px solid #dfe5ed;
  border-radius: 12px;
  background: #fff;
}
.inbox-thumb {
  min-height: 98px;
  overflow: hidden;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: #101722;
  color: #8390a3;
  font-size: 10px;
}
.inbox-thumb img { width: 100%; height: 100%; display: block; object-fit: cover; }
.inbox-item-main { min-width: 0; display: grid; gap: 9px; }
.inbox-item-main > header { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.inbox-item-main > header > div { min-width: 0; display: grid; gap: 2px; }
.inbox-item-main header small { color: #8592a5; font-size: 9px; }
.inbox-item-main header strong { color: #374a64; font-size: 12px; }
.inbox-state-pill { flex: none; border-radius: 999px; padding: 4px 8px; font-size: 9px; font-weight: 850; }
.inbox-state-pill.tone-conflict { background: #fff0f0; color: #b44d4d; }
.inbox-state-pill.tone-unbound { background: #fff6e5; color: #9a6b19; }
.inbox-state-pill.tone-low { background: #f1f4f8; color: #69778c; }
.inbox-binding-compare { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.inbox-binding-compare section { min-width: 0; display: grid; gap: 4px; padding: 8px 10px; border-radius: 9px; background: #f8fafc; }
.inbox-binding-compare section.ai-suggestion { background: #f6f8fd; }
.inbox-binding-compare h4 { margin: 0 0 2px; color: #64738a; font-size: 9px; }
.inbox-binding-compare p { min-width: 0; display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 6px; margin: 0; }
.inbox-binding-compare p span { color: #929dad; font-size: 9px; }
.inbox-binding-compare p strong { overflow: hidden; color: #506079; font-size: 10px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.inbox-item-actions { display: grid; align-content: space-between; justify-items: stretch; gap: 8px; }
.inbox-item-actions small { color: #8a96a7; font-size: 9px; text-align: right; }
.inbox-item-actions button { width: 100%; }
@media (max-width: 1250px) {
  .inbox-item { grid-template-columns: 140px minmax(0, 1fr); }
  .inbox-item-actions { grid-column: 1 / -1; display: flex; justify-content: flex-end; align-items: center; }
  .inbox-item-actions button { width: auto; }
}
</style>
