<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import CharacterAssetsWorkbenchV1 from './CharacterAssetsWorkbenchV1.vue'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ 'next-stage': [] }>()
const route = useRoute()

type SourceCharacter = {
  id: string
  name: string
  status?: string
  cover_url?: string | null
  source_candidate_ids?: string[]
  confidence?: number | null
  shot_ids: string[]
  shot_count?: number
  episode_count?: number
}

type ObservationShot = {
  id: string
  ordinal: number
  thumbnail_url: string | null
}

type Observation = {
  key: string
  name: string
  appearance: string | null
  episode_id: string
  episode_title: string
  scene: string
  character_id: string | null
  suggested_character_id?: string | null
  suggestion_source?: string | null
  shots: ObservationShot[]
}

type CharacterSummary = {
  character_count: number
  bound_shot_count: number
  observation_count: number
  confirmed_observation_count: number
  suggested_observation_count: number
  unresolved_observation_count: number
}

type Workspace = {
  project_id: string
  revision: string
  observations: Observation[]
  characters: SourceCharacter[]
  summary?: CharacterSummary
}

const workspace = ref<Workspace | null>(null)
const loading = ref(true)
const error = ref('')
const search = ref('')
const showReview = ref(false)
const showLibrary = ref(false)
const selectedCharacterId = ref<string | null>(null)

const sourceConfirmMode = computed(() => String(route.query.mode || '') === 'confirm')
const pending = computed(() => (workspace.value?.observations || []).filter((item) => !item.character_id))
const assigned = computed(() => (workspace.value?.observations || []).filter((item) => Boolean(item.character_id)))
const charactersById = computed(() => new Map((workspace.value?.characters || []).map((item) => [item.id, item])))
const summary = computed<CharacterSummary>(() => workspace.value?.summary || {
  character_count: workspace.value?.characters.length || 0,
  bound_shot_count: new Set((workspace.value?.characters || []).flatMap((item) => item.shot_ids || [])).size,
  observation_count: workspace.value?.observations.length || 0,
  confirmed_observation_count: assigned.value.length,
  suggested_observation_count: pending.value.filter((item) => item.suggested_character_id).length,
  unresolved_observation_count: pending.value.filter((item) => !item.suggested_character_id).length,
})
const completionPercent = computed(() => summary.value.observation_count
  ? Math.round(summary.value.confirmed_observation_count / summary.value.observation_count * 100)
  : 100)
const filteredCharacters = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return workspace.value?.characters || []
  return (workspace.value?.characters || []).filter((item) => item.name.toLowerCase().includes(keyword))
})
const selectedCharacter = computed(() => selectedCharacterId.value ? charactersById.value.get(selectedCharacterId.value) || null : null)
const selectedObservations = computed(() => {
  if (!selectedCharacterId.value) return []
  return (workspace.value?.observations || []).filter((item) => item.character_id === selectedCharacterId.value)
})

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json() as { detail?: unknown }
      if (typeof payload.detail === 'string') message = payload.detail
    } catch {
      // 保留默认错误信息。
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    workspace.value = await request<Workspace>(`/api/projects/${encodeURIComponent(props.projectId)}/character-assets`)
    if (selectedCharacterId.value && !charactersById.value.has(selectedCharacterId.value)) selectedCharacterId.value = null
    if (!sourceConfirmMode.value) showLibrary.value = true
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物资产读取失败'
  } finally {
    loading.value = false
  }
}

function startReview(): void {
  showLibrary.value = false
  showReview.value = true
}

async function backToOverview(): Promise<void> {
  showReview.value = false
  await load()
}

async function onReviewChanged(): Promise<void> {
  await load()
}

async function goNextStage(): Promise<void> {
  showReview.value = false
  await load()
  emit('next-stage')
}

function openCharacter(character: SourceCharacter): void {
  selectedCharacterId.value = selectedCharacterId.value === character.id ? null : character.id
}

function confidenceLabel(value?: number | null): string {
  if (value == null || !Number.isFinite(Number(value))) return '正式人物资产'
  return `身份可信度 ${Math.round(Number(value) * 100)}%`
}

onMounted(load)
</script>

<template>
  <section class="source-character-library">
    <CharacterAssetsWorkbenchV1
      v-if="showReview"
      :project-id="props.projectId"
      @changed="onReviewChanged"
      @back-to-library="backToOverview"
      @next-stage="goNextStage"
    />

    <template v-else>
      <div v-if="error" class="error" role="alert">{{ error }}</div>
      <div v-if="loading && !workspace" class="loading">正在读取原片人物状态…</div>

      <template v-else-if="workspace">
        <section v-if="sourceConfirmMode && !showLibrary" class="confirm-overview">
          <header class="overview-head">
            <div>
              <small>原片人物确认</small>
              <h2>确认人物身份，生成稳定的人物资产库</h2>
              <p>系统已经自动归并能确定的人物。你只需要处理剩余不确定项，每次确认一个即可。</p>
            </div>
            <span :class="['status-chip', { done: !pending.length }]">
              {{ pending.length ? `${pending.length} 个待确认` : '人物确认完成' }}
            </span>
          </header>

          <div class="progress-card">
            <div class="progress-copy">
              <div class="progress-icon">人</div>
              <div>
                <small>人物</small>
                <strong>{{ summary.character_count }} 个正式人物</strong>
                <span>{{ pending.length ? `还有 ${pending.length} 个人物观察需要判断` : '全部人物观察已完成确认' }}</span>
              </div>
            </div>
            <div class="progress-visual">
              <div class="progress-label"><span>确认进度</span><b>{{ completionPercent }}%</b></div>
              <div class="progress-track"><i :style="{ width: `${completionPercent}%` }" /></div>
            </div>
          </div>

          <div class="overview-metrics">
            <article>
              <small>原片人物</small>
              <strong>{{ summary.character_count }}</strong>
              <span>项目级人物资产</span>
            </article>
            <article :class="{ warning: pending.length }">
              <small>待确认</small>
              <strong>{{ pending.length }}</strong>
              <span>需要人工判断</span>
            </article>
            <article>
              <small>已确认观察</small>
              <strong>{{ summary.confirmed_observation_count }}</strong>
              <span>跨场景人物观察</span>
            </article>
            <article>
              <small>已绑定镜头</small>
              <strong>{{ summary.bound_shot_count }}</strong>
              <span>后续生成直接使用</span>
            </article>
          </div>

          <section v-if="pending.length" class="pending-preview">
            <div class="pending-preview__head">
              <div>
                <strong>下一步：处理待确认人物</strong>
                <span>有系统推荐的会优先显示；多人同框时才需要框选人物。</span>
              </div>
              <button type="button" class="primary" @click="startReview">开始处理人物 →</button>
            </div>
            <div class="pending-thumbs">
              <article v-for="item in pending.slice(0, 6)" :key="item.key">
                <div class="pending-thumb">
                  <img v-if="item.shots[0]?.thumbnail_url" :src="item.shots[0].thumbnail_url" alt="待确认人物" />
                  <span v-else>{{ item.name.slice(0, 1) }}</span>
                </div>
                <div>
                  <strong>{{ item.name }}</strong>
                  <span>{{ item.episode_title }} · {{ item.shots.length }} 镜</span>
                </div>
                <em>{{ item.suggested_character_id ? '有推荐' : '待判断' }}</em>
              </article>
              <small v-if="pending.length > 6" class="more-pending">还有 {{ pending.length - 6 }} 个待处理</small>
            </div>
          </section>

          <section v-else class="overview-complete">
            <div class="complete-check">✓</div>
            <div>
              <strong>人物确认已经完成</strong>
              <span>正式人物资产和 Shot Character Binding 已更新，可以继续场景 / 道具确认。</span>
            </div>
            <div class="complete-actions">
              <button type="button" @click="showLibrary = true">查看人物资产库</button>
              <button type="button" class="primary" @click="emit('next-stage')">继续场景 / 道具确认 →</button>
            </div>
          </section>
        </section>

        <section v-else class="asset-library-view">
          <header class="library-head">
            <div>
              <small>人物资产库</small>
              <h2>{{ workspace.characters.length }} 个原片人物资产</h2>
              <p>这里查看已经归并完成的人物、出现分镜和身份素材。替换人物与四视图在后续本土化阶段处理。</p>
            </div>
            <div class="library-actions">
              <button v-if="sourceConfirmMode" type="button" @click="showLibrary = false">← 返回人物确认</button>
              <button v-if="pending.length" type="button" class="primary" @click="startReview">继续处理 {{ pending.length }} 个待确认</button>
              <button type="button" :disabled="loading" @click="load">刷新</button>
            </div>
          </header>

          <div class="library-toolbar">
            <div class="library-stats">
              <span><b>{{ workspace.characters.length }}</b> 人物</span>
              <span><b>{{ summary.bound_shot_count }}</b> 已绑定镜头</span>
              <span :class="{ warning: pending.length }"><b>{{ pending.length }}</b> 待确认</span>
            </div>
            <input v-model="search" type="search" placeholder="搜索人物" aria-label="搜索正式人物资产" />
          </div>

          <div v-if="!filteredCharacters.length" class="empty">还没有正式人物资产。</div>
          <div v-else class="character-grid">
            <button
              v-for="character in filteredCharacters"
              :key="character.id"
              type="button"
              class="character-card"
              :class="{ active: selectedCharacterId === character.id }"
              @click="openCharacter(character)"
            >
              <div class="cover">
                <img v-if="character.cover_url" :src="character.cover_url" :alt="`${character.name} 人物参考`" />
                <span v-else>{{ character.name.slice(0, 1) }}</span>
              </div>
              <div class="character-copy">
                <strong>{{ character.name }}</strong>
                <small>{{ confidenceLabel(character.confidence) }}</small>
                <div class="character-stats">
                  <span>{{ character.shot_count ?? character.shot_ids.length }} 个分镜</span>
                  <span>{{ character.episode_count ?? 0 }} 集</span>
                </div>
              </div>
              <span class="state">✓ 已资产化</span>
            </button>
          </div>

          <div v-if="selectedCharacter" class="character-detail">
            <div class="detail-title">
              <div class="cover large">
                <img v-if="selectedCharacter.cover_url" :src="selectedCharacter.cover_url" :alt="`${selectedCharacter.name} 人物参考`" />
                <span v-else>{{ selectedCharacter.name.slice(0, 1) }}</span>
              </div>
              <div>
                <small>当前人物资产</small>
                <h3>{{ selectedCharacter.name }}</h3>
                <p>已绑定 {{ selectedCharacter.shot_count ?? selectedCharacter.shot_ids.length }} 个分镜，出现于 {{ selectedCharacter.episode_count ?? 0 }} 集。</p>
              </div>
            </div>
            <div class="detail-observations">
              <strong>已确认的人物观察 {{ selectedObservations.length }} 组</strong>
              <span v-for="item in selectedObservations.slice(0, 10)" :key="item.key">
                {{ item.episode_title }} · {{ item.scene }} · {{ item.shots.length }} 镜
              </span>
              <small v-if="selectedObservations.length > 10">另有 {{ selectedObservations.length - 10 }} 组</small>
            </div>
          </div>
        </section>
      </template>
    </template>
  </section>
</template>

<style scoped>
.source-character-library { min-height: 100%; color: #263850; }
button,
input { box-sizing: border-box; border: 1px solid #d9e1ec; border-radius: 9px; background: #fff; color: #40516a; font: inherit; font-size: 11px; }
button { padding: 8px 11px; cursor: pointer; }
button:hover:not(:disabled) { border-color: #adc0df; background: #f9fbff; }
button:disabled { opacity: .55; cursor: wait; }
button.primary { border-color: #1769ff; background: #1769ff; color: #fff; font-weight: 800; }
input { min-height: 36px; padding: 0 10px; outline: none; }
input:focus { border-color: #7ba3f5; box-shadow: 0 0 0 3px rgba(23,105,255,.08); }
.error { margin-bottom: 9px; padding: 9px 11px; border: 1px solid #efc7c7; border-radius: 8px; background: #fff3f3; color: #a93c3c; font-size: 11px; }
.loading,
.empty { padding: 28px; border: 1px dashed #dbe2eb; border-radius: 10px; background: #fff; color: #7b899b; text-align: center; }

.confirm-overview,
.asset-library-view { display: grid; gap: 10px; }
.overview-head,
.library-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 16px; border: 1px solid #e0e5ed; border-radius: 12px; background: #fff; }
.overview-head > div,
.library-head > div:first-child { min-width: 0; display: grid; gap: 2px; }
.overview-head small,
.library-head small { color: #1769ff; font-size: 9px; font-weight: 850; letter-spacing: .04em; }
.overview-head h2,
.library-head h2 { margin: 1px 0 2px; color: #273d59; font-size: 17px; }
.overview-head p,
.library-head p { margin: 0; color: #7d899b; font-size: 10px; line-height: 1.5; }
.status-chip { flex: 0 0 auto; padding: 6px 9px; border-radius: 999px; background: #fff3e3; color: #a96e19; font-size: 9px; font-weight: 800; }
.status-chip.done { background: #eaf8f0; color: #3f875f; }

.progress-card { display: grid; grid-template-columns: minmax(260px, 1fr) minmax(260px, .8fr); gap: 20px; align-items: center; padding: 15px 16px; border: 1px solid #dbe4f3; border-radius: 12px; background: linear-gradient(135deg, #f8fbff, #fff); }
.progress-copy { display: flex; align-items: center; gap: 11px; }
.progress-icon { width: 48px; height: 48px; display: grid; place-items: center; border-radius: 12px; background: #eaf2ff; color: #1769ff; font-size: 15px; font-weight: 900; }
.progress-copy > div:last-child { display: grid; gap: 2px; }
.progress-copy small { color: #7c899a; font-size: 8px; }
.progress-copy strong { color: #2e4561; font-size: 14px; }
.progress-copy span { color: #8591a2; font-size: 9px; }
.progress-visual { display: grid; gap: 6px; }
.progress-label { display: flex; justify-content: space-between; color: #7d899b; font-size: 9px; }
.progress-label b { color: #1769ff; }
.progress-track { height: 7px; overflow: hidden; border-radius: 999px; background: #e7edf6; }
.progress-track i { display: block; height: 100%; border-radius: inherit; background: #1769ff; transition: width .2s ease; }

.overview-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.overview-metrics article { display: grid; gap: 2px; padding: 12px 13px; border: 1px solid #e0e5ed; border-radius: 10px; background: #fff; }
.overview-metrics article.warning { border-color: #eed0a1; background: #fff9ef; }
.overview-metrics small { color: #8894a4; font-size: 8px; }
.overview-metrics strong { color: #2f4662; font-size: 20px; }
.overview-metrics article.warning strong { color: #b27420; }
.overview-metrics span { color: #929cab; font-size: 8px; }

.pending-preview { padding: 14px; border: 1px solid #dfe5ed; border-radius: 12px; background: #fff; }
.pending-preview__head { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.pending-preview__head > div { display: grid; gap: 2px; }
.pending-preview__head strong { color: #30465f; font-size: 12px; }
.pending-preview__head span { color: #8591a2; font-size: 9px; }
.pending-thumbs { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 7px; margin-top: 11px; }
.pending-thumbs article { position: relative; min-width: 0; display: grid; grid-template-columns: 42px minmax(0, 1fr); gap: 7px; align-items: center; padding: 6px; border: 1px solid #e6eaf0; border-radius: 8px; background: #fbfcfd; }
.pending-thumb { width: 42px; height: 50px; display: grid; place-items: center; overflow: hidden; border-radius: 6px; background: #edf1f6; color: #63748b; font-weight: 800; }
.pending-thumb img { width: 100%; height: 100%; object-fit: cover; }
.pending-thumbs article > div:nth-child(2) { min-width: 0; display: grid; gap: 2px; }
.pending-thumbs strong { overflow: hidden; color: #3a4e67; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.pending-thumbs span { overflow: hidden; color: #8a95a5; font-size: 7px; text-overflow: ellipsis; white-space: nowrap; }
.pending-thumbs em { position: absolute; right: 5px; top: 5px; padding: 2px 4px; border-radius: 4px; background: #fff2df; color: #9f6d25; font-size: 7px; font-style: normal; }
.more-pending { display: grid; place-items: center; border: 1px dashed #d7dfeb; border-radius: 8px; color: #8490a1; font-size: 8px; }

.overview-complete { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 16px; border: 1px solid #cbe6d7; border-radius: 12px; background: #f5fbf7; }
.complete-check { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 50%; background: #2fc36b; color: #fff; font-size: 21px; font-weight: 900; }
.overview-complete > div:nth-child(2) { display: grid; gap: 2px; }
.overview-complete strong { color: #315b45; font-size: 13px; }
.overview-complete span { color: #71917f; font-size: 9px; }
.complete-actions,
.library-actions { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }

.library-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 11px; border: 1px solid #e0e5ed; border-radius: 10px; background: #fff; }
.library-stats { display: flex; gap: 6px; flex-wrap: wrap; }
.library-stats span { padding: 5px 7px; border-radius: 6px; background: #f4f7fb; color: #7d899a; font-size: 8px; }
.library-stats span.warning { background: #fff3e3; color: #a96f20; }
.library-stats b { color: #3e536d; }
.library-toolbar input { width: 210px; }
.character-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
.character-card { position: relative; display: grid; grid-template-columns: 58px minmax(0, 1fr); gap: 9px; min-height: 82px; padding: 9px; border-color: #e0e5ed; text-align: left; }
.character-card.active { border-color: #1769ff; background: #f3f7ff; }
.cover { width: 58px; height: 62px; display: grid; place-items: center; overflow: hidden; border-radius: 8px; background: #edf1f6; color: #63748b; font-size: 20px; font-weight: 800; }
.cover.large { width: 70px; height: 78px; }
.cover img { width: 100%; height: 100%; object-fit: cover; }
.character-copy { min-width: 0; display: grid; align-content: center; gap: 3px; }
.character-copy > strong { color: #334963; font-size: 12px; }
.character-copy > small { color: #8894a4; font-size: 8px; }
.character-stats { display: flex; gap: 5px; flex-wrap: wrap; }
.character-stats span { padding: 2px 5px; border-radius: 5px; background: #f0f4f8; color: #6d7c91; font-size: 8px; }
.state { position: absolute; top: 7px; right: 7px; color: #4b8964; font-size: 8px; font-weight: 800; }
.character-detail { display: grid; grid-template-columns: minmax(260px, .8fr) minmax(300px, 1.2fr); gap: 14px; padding: 12px; border: 1px solid #dfe5ed; border-radius: 11px; background: #fff; }
.detail-title { display: flex; gap: 10px; align-items: center; }
.detail-title > div:last-child { display: grid; gap: 2px; }
.detail-title small { color: #8a96a5; font-size: 8px; }
.detail-title h3 { margin: 0; color: #334963; font-size: 14px; }
.detail-title p { margin: 0; color: #7d899a; font-size: 9px; line-height: 1.5; }
.detail-observations { display: grid; gap: 3px; align-content: start; padding: 8px 10px; border-radius: 8px; background: #f6f8fb; color: #718096; font-size: 8px; }
.detail-observations strong { color: #455b73; font-size: 9px; }

@media (max-width: 1050px) {
  .pending-thumbs { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .overview-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  .overview-head,
  .library-head,
  .pending-preview__head,
  .overview-complete,
  .library-toolbar { align-items: flex-start; flex-direction: column; display: flex; }
  .progress-card { grid-template-columns: 1fr; }
  .pending-thumbs { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .library-toolbar input { width: 100%; }
  .character-detail { grid-template-columns: 1fr; }
}
</style>
