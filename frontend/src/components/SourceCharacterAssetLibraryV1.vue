<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import CharacterAssetsWorkbenchV1 from './CharacterAssetsWorkbenchV1.vue'

const props = defineProps<{
  projectId: string
}>()

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
const busyKey = ref('')
const error = ref('')
const search = ref('')
const showAdvanced = ref(false)
const selectedCharacterId = ref<string | null>(null)

const charactersById = computed(() => new Map((workspace.value?.characters || []).map((item) => [item.id, item])))
const summary = computed<CharacterSummary>(() => workspace.value?.summary || {
  character_count: workspace.value?.characters.length || 0,
  bound_shot_count: new Set((workspace.value?.characters || []).flatMap((item) => item.shot_ids || [])).size,
  observation_count: workspace.value?.observations.length || 0,
  confirmed_observation_count: (workspace.value?.observations || []).filter((item) => item.character_id).length,
  suggested_observation_count: (workspace.value?.observations || []).filter((item) => !item.character_id && item.suggested_character_id).length,
  unresolved_observation_count: (workspace.value?.observations || []).filter((item) => !item.character_id && !item.suggested_character_id).length,
})

const filteredCharacters = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return workspace.value?.characters || []
  return (workspace.value?.characters || []).filter((item) => item.name.toLowerCase().includes(keyword))
})

const suggestions = computed(() => (workspace.value?.observations || []).filter(
  (item) => !item.character_id && item.suggested_character_id,
))
const unresolved = computed(() => (workspace.value?.observations || []).filter(
  (item) => !item.character_id && !item.suggested_character_id,
))
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
      const payload = await response.json()
      if (typeof payload?.detail === 'string') message = payload.detail
    } catch {
      // 保留默认错误文案。
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
    if (selectedCharacterId.value && !charactersById.value.has(selectedCharacterId.value)) {
      selectedCharacterId.value = null
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物资产读取失败'
  } finally {
    loading.value = false
  }
}

async function acceptSuggestion(item: Observation): Promise<void> {
  if (!workspace.value || !item.suggested_character_id || busyKey.value) return
  busyKey.value = item.key
  error.value = ''
  try {
    workspace.value = await request<Workspace>(
      `/api/projects/${encodeURIComponent(props.projectId)}/character-assets/assign`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          keys: [item.key],
          name: '',
          character_id: item.suggested_character_id,
          expected_revision: workspace.value.revision,
          localizations: {},
        }),
      },
    )
    // character-assets route 会附加目标人物字段；这里再次读取，保证 summary 也是最新版本。
    await load()
    window.dispatchEvent(new CustomEvent('studio-project-truth-changed', {
      detail: { project_id: props.projectId },
    }))
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物归并失败'
  } finally {
    busyKey.value = ''
  }
}

function confidenceLabel(value?: number | null): string {
  if (value == null || !Number.isFinite(Number(value))) return '已形成正式人物'
  return `识别可信度 ${Math.round(Number(value) * 100)}%`
}

function openCharacter(character: SourceCharacter): void {
  selectedCharacterId.value = selectedCharacterId.value === character.id ? null : character.id
}

function onAdvancedChanged(): void {
  void load()
}

onMounted(load)
</script>

<template>
  <section class="source-character-library">
    <header class="library-header">
      <div>
        <small>原片人物资产库</small>
        <h2>把分镜里识别到的人，整理成可长期复用的人物资产</h2>
        <p>系统自动使用跨镜身份结果和 Final Shot Binding。只有无法唯一判断的人物才进入人工处理。</p>
      </div>
      <button type="button" :disabled="loading || Boolean(busyKey)" @click="load">刷新</button>
    </header>

    <div v-if="error" class="error" role="alert">{{ error }}</div>

    <div class="metrics" aria-label="人物资产统计">
      <article>
        <small>正式人物资产</small>
        <strong>{{ summary.character_count }}</strong>
        <span>已经跨分镜归并</span>
      </article>
      <article>
        <small>已绑定分镜</small>
        <strong>{{ summary.bound_shot_count }}</strong>
        <span>后续 H3 直接使用</span>
      </article>
      <article class="suggested">
        <small>可直接确认</small>
        <strong>{{ summary.suggested_observation_count }}</strong>
        <span>Final Binding 唯一匹配</span>
      </article>
      <article :class="{ warning: summary.unresolved_observation_count > 0 }">
        <small>真正待人工</small>
        <strong>{{ summary.unresolved_observation_count }}</strong>
        <span>同框多人或身份不唯一</span>
      </article>
    </div>

    <section class="asset-section">
      <div class="section-title">
        <div>
          <h3>正式人物资产</h3>
          <p>这些人物已经拥有稳定项目级 ID，并绑定回出现的分镜。</p>
        </div>
        <input v-model="search" type="search" placeholder="搜索人物" aria-label="搜索正式人物资产" />
      </div>

      <div v-if="loading" class="empty">正在读取人物资产…</div>
      <div v-else-if="!filteredCharacters.length" class="empty">还没有正式人物资产。请先完成 Character V10.1 资产提取。</div>
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
        <div>
          <small>当前人物资产</small>
          <h4>{{ selectedCharacter.name }}</h4>
          <p>
            已绑定 {{ selectedCharacter.shot_count ?? selectedCharacter.shot_ids.length }} 个分镜，
            来源身份类 {{ selectedCharacter.source_candidate_ids?.length || 0 }} 组。
          </p>
        </div>
        <div class="detail-observations">
          <strong>已人工确认的拉片人物观察 {{ selectedObservations.length }} 组</strong>
          <span v-for="item in selectedObservations.slice(0, 8)" :key="item.key">
            {{ item.episode_title }} · {{ item.scene }} · {{ item.shots.length }} 镜
          </span>
          <small v-if="selectedObservations.length > 8">另有 {{ selectedObservations.length - 8 }} 组</small>
        </div>
      </div>
    </section>

    <section v-if="suggestions.length" class="asset-section suggestion-section">
      <div class="section-title">
        <div>
          <h3>系统已经能唯一判断</h3>
          <p>这些拉片人物在其所有出现分镜中的 Final Character 交集只有一个，可以直接确认，不需要重新框人。</p>
        </div>
      </div>
      <div class="observation-list">
        <article v-for="item in suggestions" :key="item.key" class="observation-row">
          <img v-if="item.shots[0]?.thumbnail_url" :src="item.shots[0].thumbnail_url" alt="人物出现镜头" />
          <div>
            <strong>{{ item.name }}</strong>
            <span>{{ item.episode_title }} · {{ item.scene }} · {{ item.shots.length }} 个分镜</span>
            <small v-if="item.appearance">{{ item.appearance }}</small>
          </div>
          <div class="suggestion-target">
            <small>建议归并到</small>
            <strong>{{ charactersById.get(item.suggested_character_id || '')?.name || '正式人物' }}</strong>
          </div>
          <button
            type="button"
            class="primary"
            :disabled="Boolean(busyKey)"
            @click="acceptSuggestion(item)"
          >
            {{ busyKey === item.key ? '正在确认…' : '确认归并' }}
          </button>
        </article>
      </div>
    </section>

    <section class="asset-section manual-section">
      <div class="section-title">
        <div>
          <h3>需要人工判断 {{ unresolved.length }}</h3>
          <p>只有同框多人、绑定交集不唯一或缺少可靠身份结果的观察才需要进入人工工具。</p>
        </div>
        <button v-if="unresolved.length" type="button" @click="showAdvanced = !showAdvanced">
          {{ showAdvanced ? '收起人工工具' : `处理 ${unresolved.length} 个问题` }}
        </button>
      </div>
      <div v-if="!unresolved.length" class="success">✓ 当前没有需要人工判断的人物归并问题。</div>
      <div v-else class="unresolved-preview">
        <span v-for="item in unresolved.slice(0, 6)" :key="item.key">
          {{ item.episode_title }} · {{ item.name }}
        </span>
        <small v-if="unresolved.length > 6">另有 {{ unresolved.length - 6 }} 组</small>
      </div>
    </section>

    <section v-if="showAdvanced" class="advanced-workbench">
      <div class="advanced-note">
        <strong>高级人工归并</strong>
        <span>这里保留原来的画面框选能力，只处理系统无法唯一确定的情况。</span>
      </div>
      <CharacterAssetsWorkbenchV1 :project-id="props.projectId" @changed="onAdvancedChanged" />
    </section>
  </section>
</template>

<style scoped>
.source-character-library {
  display: grid;
  gap: 12px;
}

.library-header,
.section-title,
.observation-row,
.character-detail,
.advanced-note {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.library-header {
  padding: 16px 18px;
  border: 1px solid #dce4ef;
  border-radius: 14px;
  background: #fff;
}
.library-header small { color: #70809a; font-size: 10px; font-weight: 850; letter-spacing: .05em; }
.library-header h2 { margin: 3px 0 5px; color: #253a58; font-size: 18px; }
.library-header p, .section-title p, .character-detail p { margin: 0; color: #758398; font-size: 11px; line-height: 1.6; }
button { border: 1px solid #d6dfeb; border-radius: 8px; padding: 8px 11px; background: #fff; color: #43536b; font: inherit; cursor: pointer; }
button:disabled { opacity: .55; cursor: wait; }
button.primary { border-color: #426fd2; background: #426fd2; color: #fff; font-weight: 800; }
.error { padding: 10px 12px; border: 1px solid #f0c7c7; border-radius: 9px; background: #fff3f3; color: #a83a3a; font-size: 12px; }

.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; }
.metrics article { display: grid; gap: 2px; padding: 12px 14px; border: 1px solid #dfe5ed; border-radius: 11px; background: #fff; }
.metrics small { color: #8793a5; font-size: 10px; }
.metrics strong { color: #2f435f; font-size: 22px; }
.metrics span { color: #8a96a6; font-size: 10px; }
.metrics article.suggested { border-color: #cbdaf8; background: #f6f9ff; }
.metrics article.warning { border-color: #efcf9b; background: #fff8eb; }

.asset-section { padding: 15px; border: 1px solid #dfe5ed; border-radius: 12px; background: #fff; }
.section-title { margin-bottom: 12px; align-items: flex-start; }
.section-title h3 { margin: 0 0 3px; color: #344a68; font-size: 14px; }
.section-title input { width: 220px; min-height: 34px; border: 1px solid #d8e0eb; border-radius: 8px; padding: 0 10px; outline: none; }
.section-title input:focus { border-color: #7898d6; box-shadow: 0 0 0 3px rgba(66,111,210,.09); }
.empty, .success { padding: 18px; border-radius: 9px; background: #f7f9fc; color: #758398; font-size: 12px; text-align: center; }
.success { background: #f1faf5; color: #3e785d; }

.character-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 9px; }
.character-card { position: relative; display: grid; grid-template-columns: 62px 1fr; gap: 10px; min-height: 86px; padding: 10px; text-align: left; }
.character-card:hover, .character-card.active { border-color: #8da7dc; background: #f7faff; }
.cover { width: 62px; height: 66px; display: grid; place-items: center; overflow: hidden; border-radius: 8px; background: #edf1f6; color: #667891; font-size: 24px; font-weight: 800; }
.cover img { width: 100%; height: 100%; object-fit: cover; }
.character-copy { min-width: 0; display: grid; align-content: center; gap: 3px; }
.character-copy > strong { color: #2f425e; font-size: 14px; }
.character-copy > small { color: #8490a2; font-size: 9px; }
.character-stats { display: flex; gap: 7px; flex-wrap: wrap; }
.character-stats span { padding: 2px 5px; border-radius: 5px; background: #eef3f9; color: #65758c; font-size: 9px; }
.state { position: absolute; top: 8px; right: 8px; color: #4e8a69; font-size: 9px; font-weight: 800; }
.character-detail { margin-top: 10px; padding: 12px; border-radius: 10px; background: #f7f9fc; align-items: flex-start; }
.character-detail h4 { margin: 3px 0; color: #30445f; }
.detail-observations { min-width: min(460px, 50%); display: grid; gap: 3px; color: #6f7e91; font-size: 10px; }
.detail-observations strong { color: #485a72; }

.suggestion-section { border-color: #d7e2f7; }
.observation-list { display: grid; gap: 7px; }
.observation-row { padding: 8px; border: 1px solid #e0e6ef; border-radius: 9px; }
.observation-row > img { width: 74px; height: 52px; border-radius: 7px; object-fit: cover; background: #edf1f5; }
.observation-row > div:nth-child(2) { min-width: 0; flex: 1; display: grid; gap: 2px; }
.observation-row > div:nth-child(2) strong { color: #354861; font-size: 12px; }
.observation-row > div:nth-child(2) span, .observation-row > div:nth-child(2) small { color: #7f8b9c; font-size: 10px; }
.suggestion-target { min-width: 130px; display: grid; gap: 2px; }
.suggestion-target small { color: #8b96a5; font-size: 9px; }
.suggestion-target strong { color: #3f6298; font-size: 11px; }
.unresolved-preview { display: flex; flex-wrap: wrap; gap: 6px; }
.unresolved-preview span, .unresolved-preview small { padding: 5px 7px; border-radius: 6px; background: #fff4e2; color: #8a6a36; font-size: 10px; }

.advanced-workbench { overflow: hidden; border: 1px solid #dce3ed; border-radius: 12px; background: #fff; }
.advanced-note { padding: 10px 14px; border-bottom: 1px solid #e4e9f0; background: #f7f9fc; justify-content: flex-start; }
.advanced-note strong { color: #40536d; font-size: 11px; }
.advanced-note span { color: #7d8999; font-size: 10px; }

@media (max-width: 1000px) {
  .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .library-header, .character-detail { align-items: flex-start; flex-direction: column; }
  .detail-observations { min-width: 0; width: 100%; }
  .observation-row { align-items: flex-start; flex-wrap: wrap; }
}
</style>
