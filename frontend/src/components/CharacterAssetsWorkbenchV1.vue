<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{
  changed: []
  'back-to-library': []
  'next-stage': []
}>()
const router = useRouter()

type Mark = {
  shot_id: string
  image_url: string
  box: number[]
}

type ObservationShot = {
  id: string
  ordinal: number
  thumbnail_url: string | null
}

type Observation = {
  localization?: Mark | null
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

type SourceCharacter = {
  id: string
  name: string
  cover_url?: string | null
  confidence?: number | null
  shot_ids: string[]
  shot_count?: number
  episode_count?: number
}

type Workspace = {
  revision: string
  observations: Observation[]
  characters: SourceCharacter[]
}

type QueueMode = 'pending' | 'assigned' | 'all'

const data = ref<Workspace | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const search = ref('')
const candidateSearch = ref('')
const queueMode = ref<QueueMode>('pending')
const focusKey = ref('')
const shotIndex = ref(0)
const destinationCharacterId = ref('')
const createModalOpen = ref(false)
const createName = ref('')
const locatorOpen = ref(false)
const mark = ref<Mark | null>(null)
let dragStart: [number, number] | null = null

const allObservations = computed(() => data.value?.observations || [])
const pending = computed(() => allObservations.value.filter((item) => !item.character_id))
const assigned = computed(() => allObservations.value.filter((item) => Boolean(item.character_id)))
const completedCount = computed(() => assigned.value.length)
const totalCount = computed(() => allObservations.value.length)
const progressPercent = computed(() => totalCount.value ? Math.round(completedCount.value / totalCount.value * 100) : 100)
const boundShotCount = computed(() => new Set((data.value?.characters || []).flatMap((item) => item.shot_ids || [])).size)
const charactersById = computed(() => new Map((data.value?.characters || []).map((item) => [item.id, item])))

const queueRows = computed(() => {
  if (queueMode.value === 'pending') return pending.value
  if (queueMode.value === 'assigned') return assigned.value
  return allObservations.value
})

const filteredRows = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return queueRows.value
  return queueRows.value.filter((item) =>
    `${item.name} ${item.appearance || ''} ${item.scene} ${item.episode_title}`.toLowerCase().includes(keyword),
  )
})

const focused = computed(() => allObservations.value.find((item) => item.key === focusKey.value) || null)
const currentShot = computed(() => focused.value?.shots[shotIndex.value] || null)
const suggestedCharacter = computed(() => {
  const id = focused.value?.suggested_character_id
  return id ? charactersById.value.get(id) || null : null
})
const selectedCharacter = computed(() => destinationCharacterId.value
  ? charactersById.value.get(destinationCharacterId.value) || null
  : null)

const candidateCharacters = computed(() => {
  const keyword = candidateSearch.value.trim().toLowerCase()
  const rows = (data.value?.characters || []).filter((character) =>
    !keyword || character.name.toLowerCase().includes(keyword),
  )
  const suggestedId = focused.value?.suggested_character_id || ''
  return [...rows].sort((a, b) => {
    if (a.id === suggestedId && b.id !== suggestedId) return -1
    if (b.id === suggestedId && a.id !== suggestedId) return 1
    return (b.shot_count ?? b.shot_ids.length) - (a.shot_count ?? a.shot_ids.length)
  })
})

const shownMark = computed(() => {
  if (!mark.value || !currentShot.value) return null
  return mark.value.shot_id === currentShot.value.id ? mark.value : null
})

const canConfirm = computed(() => Boolean(focused.value && selectedCharacter.value && !busy.value))

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

function selectObservation(item: Observation): void {
  focusKey.value = item.key
  shotIndex.value = 0
  destinationCharacterId.value = item.character_id || item.suggested_character_id || ''
  candidateSearch.value = ''
  mark.value = item.localization ? {
    shot_id: item.localization.shot_id,
    image_url: item.localization.image_url,
    box: [...item.localization.box],
  } : null
  createModalOpen.value = false
  locatorOpen.value = false
  dragStart = null
}

function ensureFocus(): void {
  if (focused.value && queueRows.value.some((item) => item.key === focused.value?.key)) return
  const next = filteredRows.value[0] || queueRows.value[0] || allObservations.value[0]
  if (next) selectObservation(next)
  else focusKey.value = ''
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    data.value = await request<Workspace>(`/api/projects/${encodeURIComponent(props.projectId)}/character-assets`)
    ensureFocus()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物归并数据读取失败'
  } finally {
    loading.value = false
  }
}

function setQueueMode(mode: QueueMode): void {
  queueMode.value = mode
  const next = mode === 'pending' ? pending.value[0] : mode === 'assigned' ? assigned.value[0] : allObservations.value[0]
  if (next) selectObservation(next)
  else focusKey.value = ''
}

function chooseCharacter(characterId: string): void {
  destinationCharacterId.value = characterId
}

function openCreateModal(): void {
  const suggestedName = focused.value?.name || ''
  createName.value = /^人物\d*$/u.test(suggestedName) ? '' : suggestedName
  createModalOpen.value = true
}

function openLocator(): void {
  if (!focused.value?.shots.length) return
  locatorOpen.value = true
  dragStart = null
}

function markStyle(value: Mark): Record<string, string> {
  const [x = 0, y = 0, width = 0, height = 0] = value.box
  return {
    left: `${x * 100}%`,
    top: `${y * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
  }
}

function point(event: PointerEvent): [number, number] {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  return [
    Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
    Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
  ]
}

function startMark(event: PointerEvent): void {
  if (!locatorOpen.value || busy.value || !currentShot.value?.thumbnail_url) return
  dragStart = point(event)
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function moveMark(event: PointerEvent): void {
  if (!dragStart || !currentShot.value?.thumbnail_url) return
  const [x, y] = point(event)
  const [startX, startY] = dragStart
  mark.value = {
    shot_id: currentShot.value.id,
    image_url: currentShot.value.thumbnail_url,
    box: [
      Math.min(x, startX),
      Math.min(y, startY),
      Math.abs(x - startX),
      Math.abs(y - startY),
    ],
  }
}

function endMark(event: PointerEvent): void {
  if (!dragStart) return
  moveMark(event)
  dragStart = null
  if (mark.value && (mark.value.box[2]! < 0.02 || mark.value.box[3]! < 0.02)) mark.value = null
}

function clearMark(): void {
  mark.value = null
}

function changeShot(index: number): void {
  shotIndex.value = index
  dragStart = null
}

function nextPendingAfter(key: string): Observation | null {
  const rows = pending.value
  if (!rows.length) return null
  const currentIndex = rows.findIndex((item) => item.key === key)
  if (currentIndex >= 0 && rows[currentIndex + 1]) return rows[currentIndex + 1]!
  return rows.find((item) => item.key !== key) || null
}

function skipCurrent(): void {
  if (!focused.value) return
  const next = nextPendingAfter(focused.value.key)
  if (next) {
    selectObservation(next)
    return
  }
  error.value = '当前已经是最后一个待处理人物。可以先确认身份，或返回人物资产库。'
}

async function submitAssignment(characterId: string | null, name: string): Promise<void> {
  if (!data.value || !focused.value || busy.value) return
  const savingKey = focused.value.key
  busy.value = true
  error.value = ''
  try {
    const result = await request<Workspace>(
      `/api/projects/${encodeURIComponent(props.projectId)}/character-assets/assign`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          keys: [savingKey],
          name,
          character_id: characterId,
          expected_revision: data.value.revision,
          // 只有多人同框时用户主动框选，普通身份确认不重复要求定位。
          localizations: mark.value ? { [savingKey]: mark.value } : null,
        }),
      },
    )
    data.value = result
    createModalOpen.value = false
    locatorOpen.value = false
    mark.value = null
    queueMode.value = 'pending'
    const next = result.observations.find((item) => !item.character_id && item.key !== savingKey)
    if (next) selectObservation(next)
    else focusKey.value = ''
    window.dispatchEvent(new CustomEvent('studio-project-truth-changed', {
      detail: { project_id: props.projectId },
    }))
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物身份确认失败'
  } finally {
    busy.value = false
  }
}

async function confirmSelected(): Promise<void> {
  if (!selectedCharacter.value) return
  await submitAssignment(selectedCharacter.value.id, '')
}

async function createAndConfirm(): Promise<void> {
  const name = createName.value.trim()
  if (!name) return
  await submitAssignment(null, name)
}

function openBreakdown(): void {
  if (!focused.value) return
  void router.push({
    name: 'breakdown',
    params: { projectId: props.projectId },
    query: {
      episode: focused.value.episode_id,
      ...(currentShot.value?.ordinal ? { shot: currentShot.value.ordinal } : {}),
    },
  })
}

onMounted(load)
</script>

<template>
  <section class="identity-review">
    <header class="review-topbar">
      <button type="button" class="back-button" @click="emit('back-to-library')">← 返回</button>
      <div class="topbar-title">
        <strong>原片人物确认</strong>
        <span>每次只判断一个人物，确认后自动进入下一条</span>
      </div>
      <div class="progress-box">
        <span>{{ completedCount }} / {{ totalCount }}</span>
        <div class="progress-track"><i :style="{ width: `${progressPercent}%` }" /></div>
        <b>{{ progressPercent }}%</b>
      </div>
    </header>

    <div v-if="error" class="error" role="alert">{{ error }}</div>
    <div v-if="loading && !data" class="loading">正在读取人物确认任务…</div>

    <section v-else-if="data && !pending.length && queueMode === 'pending'" class="completion-screen">
      <div class="completion-check">✓</div>
      <h2>人物确认完成！</h2>
      <p>所有需要人工判断的人物都已完成归并，人物资产和分镜绑定已经更新。</p>

      <div class="completion-metrics">
        <article><strong>{{ data.characters.length }}</strong><span>原片人物</span></article>
        <article><strong>0</strong><span>待确认</span></article>
        <article><strong>{{ boundShotCount }}</strong><span>已绑定镜头</span></article>
        <article><strong>100%</strong><span>确认完成</span></article>
      </div>

      <div class="completion-actions">
        <button type="button" @click="emit('back-to-library')">查看人物资产库</button>
        <button type="button" class="primary" @click="emit('next-stage')">继续场景 / 道具确认 →</button>
      </div>
    </section>

    <template v-else-if="data">
      <nav class="queue-tabs" aria-label="人物确认筛选">
        <button type="button" :class="{ active: queueMode === 'pending' }" @click="setQueueMode('pending')">
          待处理 <b>{{ pending.length }}</b>
        </button>
        <button type="button" :class="{ active: queueMode === 'assigned' }" @click="setQueueMode('assigned')">
          已确认 <b>{{ assigned.length }}</b>
        </button>
        <button type="button" :class="{ active: queueMode === 'all' }" @click="setQueueMode('all')">
          全部 <b>{{ totalCount }}</b>
        </button>
      </nav>

      <div class="review-layout">
        <aside class="review-queue">
          <div class="queue-search">
            <input v-model="search" type="search" placeholder="搜索人物、外观或场景" aria-label="搜索人物" />
          </div>

          <div class="queue-list">
            <button
              v-for="item in filteredRows"
              :key="item.key"
              type="button"
              class="queue-item"
              :class="{ active: item.key === focusKey }"
              @click="selectObservation(item)"
            >
              <div class="queue-thumb">
                <img v-if="item.shots[0]?.thumbnail_url" :src="item.shots[0].thumbnail_url" alt="人物观察缩略图" />
                <span v-else>{{ item.name.slice(0, 1) }}</span>
              </div>
              <div class="queue-copy">
                <strong>{{ item.name }}</strong>
                <span>{{ item.episode_title }} · {{ item.scene }}</span>
                <small>{{ item.shots.length }} 个分镜</small>
              </div>
              <em v-if="item.character_id">已确认</em>
              <em v-else-if="item.suggested_character_id" class="suggested">有推荐</em>
              <em v-else class="pending">待确认</em>
            </button>
            <p v-if="!filteredRows.length" class="queue-empty">没有匹配的人物。</p>
          </div>
        </aside>

        <main v-if="focused" class="review-main">
          <section class="evidence-column">
            <div class="current-context">
              <div>
                <small>当前镜头</small>
                <strong>{{ focused.episode_title }} · 镜头 {{ currentShot?.ordinal || '-' }}</strong>
              </div>
              <span>{{ focused.scene }}</span>
            </div>

            <div class="frame-stage">
              <img
                v-if="currentShot?.thumbnail_url"
                :src="currentShot.thumbnail_url"
                alt="当前人物证据画面"
                draggable="false"
              />
              <div v-else class="no-frame">当前分镜没有可用画面</div>
              <div v-if="shownMark" class="person-box" :style="markStyle(shownMark)"><span>已定位人物</span></div>
            </div>

            <div v-if="focused.shots.length > 1" class="shot-strip">
              <button
                v-for="(shot, index) in focused.shots"
                :key="shot.id"
                type="button"
                :class="{ active: shotIndex === index }"
                @click="changeShot(index)"
              >
                <img v-if="shot.thumbnail_url" :src="shot.thumbnail_url" alt="分镜缩略图" />
                <span>镜头 {{ shot.ordinal }}</span>
              </button>
            </div>

            <div class="evidence-meta">
              <div>
                <strong>{{ focused.name }}</strong>
                <span>{{ focused.appearance || '暂无稳定外观描述，请以画面为准。' }}</span>
              </div>
              <div class="evidence-actions">
                <button type="button" @click="openBreakdown">查看完整分镜 ↗</button>
                <button type="button" :class="{ marked: Boolean(mark) }" @click="openLocator">
                  {{ mark ? '已框选人物 · 修改' : '需要框选人物' }}
                </button>
              </div>
            </div>
            <p class="locator-help">只有多人同框、容易认错时才需要框选。普通人物确认直接选择身份即可。</p>
          </section>

          <aside class="decision-panel">
            <div class="decision-head">
              <small>确认人物身份</small>
              <h2>这个人是谁？</h2>
              <p>优先选择已有原片人物；确认是新角色时再创建。</p>
            </div>

            <button
              v-if="suggestedCharacter"
              type="button"
              class="recommended-card"
              :class="{ selected: destinationCharacterId === suggestedCharacter.id }"
              @click="chooseCharacter(suggestedCharacter.id)"
            >
              <div class="candidate-cover large">
                <img v-if="suggestedCharacter.cover_url" :src="suggestedCharacter.cover_url" :alt="`${suggestedCharacter.name} 人物参考`" />
                <span v-else>{{ suggestedCharacter.name.slice(0, 1) }}</span>
              </div>
              <div>
                <small>系统推荐 · 唯一匹配</small>
                <strong>{{ suggestedCharacter.name }}</strong>
                <span>{{ suggestedCharacter.shot_count ?? suggestedCharacter.shot_ids.length }} 个分镜 · {{ suggestedCharacter.episode_count ?? 0 }} 集</span>
              </div>
              <b>{{ destinationCharacterId === suggestedCharacter.id ? '✓' : '推荐' }}</b>
            </button>

            <div class="candidate-search">
              <span>选择已有人物</span>
              <input v-model="candidateSearch" type="search" placeholder="搜索人物" aria-label="搜索已有原片人物" />
            </div>

            <div class="candidate-grid">
              <button
                v-for="character in candidateCharacters"
                :key="character.id"
                type="button"
                class="candidate-card"
                :class="{ selected: destinationCharacterId === character.id }"
                @click="chooseCharacter(character.id)"
              >
                <div class="candidate-cover">
                  <img v-if="character.cover_url" :src="character.cover_url" :alt="`${character.name} 人物参考`" />
                  <span v-else>{{ character.name.slice(0, 1) }}</span>
                </div>
                <div>
                  <strong>{{ character.name }}</strong>
                  <small>{{ character.shot_count ?? character.shot_ids.length }} 镜</small>
                </div>
                <i>{{ destinationCharacterId === character.id ? '✓' : '' }}</i>
              </button>
            </div>

            <button type="button" class="new-character-button" @click="openCreateModal">＋ 这是新人物</button>

            <div v-if="focused.character_id" class="current-binding">
              <span>当前已绑定</span>
              <strong>{{ charactersById.get(focused.character_id)?.name || '原片人物' }}</strong>
            </div>

            <div class="decision-actions">
              <button v-if="!focused.character_id" type="button" @click="skipCurrent">跳过</button>
              <button
                type="button"
                class="primary"
                :disabled="!canConfirm"
                @click="confirmSelected"
              >
                {{ busy ? '正在保存…' : selectedCharacter ? `确认是 ${selectedCharacter.name} →` : '请选择人物' }}
              </button>
            </div>
          </aside>
        </main>
      </div>
    </template>

    <div v-if="createModalOpen" class="modal-backdrop" @click.self="createModalOpen = false">
      <section class="small-modal" role="dialog" aria-modal="true" aria-label="创建原片人物">
        <header>
          <div>
            <small>创建新人物</small>
            <h3>从当前画面创建原片人物</h3>
          </div>
          <button type="button" aria-label="关闭" @click="createModalOpen = false">×</button>
        </header>
        <div class="create-preview">
          <img v-if="currentShot?.thumbnail_url" :src="currentShot.thumbnail_url" alt="当前人物画面" />
          <div>
            <strong>{{ focused?.name || '当前人物' }}</strong>
            <span>{{ focused?.appearance || '请根据当前画面输入一个容易识别的人物名称。' }}</span>
          </div>
        </div>
        <label class="form-field">
          <span>人物名称 *</span>
          <input v-model="createName" maxlength="200" autofocus placeholder="例如：林夏、陈浩、邻居大妈" @keyup.enter="createAndConfirm" />
        </label>
        <p class="form-help">这里先建立稳定人物资产 ID，角色类型、替换人物和四视图在后续人物资产阶段处理。</p>
        <footer>
          <button type="button" @click="createModalOpen = false">取消</button>
          <button type="button" class="primary" :disabled="busy || !createName.trim()" @click="createAndConfirm">
            {{ busy ? '正在创建…' : '创建并确认' }}
          </button>
        </footer>
      </section>
    </div>

    <div v-if="locatorOpen" class="modal-backdrop" @click.self="locatorOpen = false">
      <section class="locator-modal" role="dialog" aria-modal="true" aria-label="框选人物">
        <header>
          <div>
            <small>多人镜头定位</small>
            <h3>框选画面中要确认的人物</h3>
          </div>
          <button type="button" aria-label="关闭" @click="locatorOpen = false">×</button>
        </header>

        <div
          class="locator-canvas"
          @pointerdown.prevent="startMark"
          @pointermove="moveMark"
          @pointerup="endMark"
          @pointercancel="dragStart = null"
        >
          <img v-if="currentShot?.thumbnail_url" :src="currentShot.thumbnail_url" alt="多人镜头，请框选目标人物" draggable="false" />
          <div v-else class="no-frame">当前分镜没有可用画面</div>
          <div v-if="shownMark" class="person-box" :style="markStyle(shownMark)"><span>确认对象</span></div>
          <div v-if="!shownMark && currentShot?.thumbnail_url" class="drag-tip">按住鼠标拖动框选人物</div>
        </div>

        <div v-if="focused && focused.shots.length > 1" class="locator-shots">
          <button
            v-for="(shot, index) in focused.shots"
            :key="shot.id"
            type="button"
            :class="{ active: shotIndex === index }"
            @click="changeShot(index)"
          >
            镜头 {{ shot.ordinal }}
          </button>
        </div>

        <footer>
          <button v-if="mark" type="button" @click="clearMark">清除框选</button>
          <span />
          <button type="button" @click="locatorOpen = false">取消</button>
          <button type="button" class="primary" :disabled="!mark" @click="locatorOpen = false">确认框选并继续选人物</button>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.identity-review {
  display: grid;
  gap: 10px;
  min-height: 100%;
  color: #23344d;
}

button,
input {
  box-sizing: border-box;
  border: 1px solid #d9e1ec;
  border-radius: 9px;
  background: #fff;
  color: #40516a;
  font: inherit;
  font-size: 11px;
}
button { padding: 8px 11px; cursor: pointer; }
button:hover:not(:disabled) { border-color: #adc0df; background: #f9fbff; }
button:disabled { opacity: .5; cursor: not-allowed; }
button.primary { border-color: #1769ff; background: #1769ff; color: #fff; font-weight: 800; }
button.primary:hover:not(:disabled) { border-color: #0d5be6; background: #0d5be6; }
input { min-height: 36px; padding: 0 10px; outline: none; }
input:focus { border-color: #7ba3f5; box-shadow: 0 0 0 3px rgba(23,105,255,.08); }

.review-topbar {
  min-height: 54px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid #e0e5ed;
  border-radius: 11px;
  background: #fff;
}
.back-button { color: #526985; }
.topbar-title { min-width: 0; display: grid; gap: 1px; }
.topbar-title strong { color: #263b58; font-size: 14px; }
.topbar-title span { color: #8793a5; font-size: 9px; }
.progress-box { display: grid; grid-template-columns: auto 150px auto; gap: 8px; align-items: center; color: #7c899b; font-size: 9px; }
.progress-box b { color: #2e5ec0; }
.progress-track { width: 150px; height: 6px; overflow: hidden; border-radius: 999px; background: #e9eef6; }
.progress-track i { display: block; height: 100%; border-radius: inherit; background: #1769ff; transition: width .2s ease; }

.error { margin: 0; padding: 9px 11px; border: 1px solid #efc7c7; border-radius: 8px; background: #fff3f3; color: #a93c3c; font-size: 11px; }
.loading { padding: 28px; border: 1px dashed #dbe2eb; border-radius: 10px; background: #fff; color: #7b899b; text-align: center; }

.queue-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px;
  border: 1px solid #e0e5ed;
  border-radius: 10px;
  background: #fff;
}
.queue-tabs button { border-color: transparent; padding: 7px 12px; background: transparent; color: #728096; }
.queue-tabs button b { margin-left: 4px; color: inherit; }
.queue-tabs button.active { border-color: #cbdaf7; background: #eef4ff; color: #1769ff; font-weight: 800; }

.review-layout {
  min-height: 610px;
  display: grid;
  grid-template-columns: 250px minmax(0, 1fr);
  gap: 10px;
}
.review-queue,
.review-main {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #e0e5ed;
  border-radius: 12px;
  background: #fff;
}
.review-queue { display: grid; grid-template-rows: auto minmax(0, 1fr); }
.queue-search { padding: 9px; border-bottom: 1px solid #edf0f4; background: #fbfcfe; }
.queue-search input { width: 100%; }
.queue-list { min-height: 0; max-height: 690px; overflow-y: auto; padding: 6px; }
.queue-item {
  width: 100%;
  display: grid;
  grid-template-columns: 46px minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 5px;
  padding: 7px;
  border-color: transparent;
  text-align: left;
}
.queue-item.active { border-color: #8fb1fa; background: #eef4ff; box-shadow: inset 3px 0 0 #1769ff; }
.queue-thumb { width: 46px; height: 54px; display: grid; place-items: center; overflow: hidden; border-radius: 7px; background: #edf1f6; color: #5f7088; font-size: 17px; font-weight: 800; }
.queue-thumb img { width: 100%; height: 100%; object-fit: cover; }
.queue-copy { min-width: 0; display: grid; gap: 2px; }
.queue-copy strong { overflow: hidden; color: #31465f; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.queue-copy span,
.queue-copy small { overflow: hidden; color: #8792a2; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.queue-item em { padding: 3px 5px; border-radius: 5px; background: #edf8f1; color: #4b865e; font-size: 8px; font-style: normal; white-space: nowrap; }
.queue-item em.suggested { background: #edf4ff; color: #5277bd; }
.queue-item em.pending { background: #fff3e1; color: #a56f1f; }
.queue-empty { padding: 20px 8px; color: #8b96a5; font-size: 10px; text-align: center; }

.review-main { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(330px, .65fr); }
.evidence-column { min-width: 0; padding: 12px; border-right: 1px solid #e7ebf1; }
.current-context { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
.current-context > div { display: grid; gap: 2px; }
.current-context small { color: #8a96a7; font-size: 8px; }
.current-context strong { color: #30465f; font-size: 12px; }
.current-context > span { color: #7f8b9b; font-size: 9px; }
.frame-stage,
.locator-canvas { position: relative; overflow: hidden; display: grid; place-items: center; background: #111b29; user-select: none; }
.frame-stage { min-height: 390px; max-height: 520px; border-radius: 10px; }
.frame-stage > img,
.locator-canvas > img { display: block; width: 100%; height: 100%; object-fit: contain; }
.no-frame { color: #b7c1ce; font-size: 11px; }
.person-box { position: absolute; border: 2px solid #1769ff; box-shadow: 0 0 0 9999px rgba(8,18,34,.08); pointer-events: none; }
.person-box span { position: absolute; top: -24px; left: -2px; padding: 4px 6px; border-radius: 5px; background: #1769ff; color: #fff; font-size: 9px; font-weight: 800; white-space: nowrap; }
.shot-strip { display: flex; gap: 6px; margin-top: 8px; overflow-x: auto; padding-bottom: 2px; }
.shot-strip button { min-width: 72px; display: grid; gap: 3px; padding: 4px; }
.shot-strip button.active { border-color: #1769ff; background: #eef4ff; }
.shot-strip img { width: 64px; height: 42px; border-radius: 5px; object-fit: cover; background: #edf1f6; }
.shot-strip span { color: #6f7d90; font-size: 8px; }
.evidence-meta { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 10px; }
.evidence-meta > div:first-child { min-width: 0; display: grid; gap: 2px; }
.evidence-meta strong { color: #30465f; font-size: 12px; }
.evidence-meta span { overflow: hidden; color: #7d899a; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.evidence-actions { display: flex; gap: 6px; flex: 0 0 auto; }
.evidence-actions button.marked { border-color: #7fa6f4; background: #eef4ff; color: #3767c5; }
.locator-help { margin: 7px 0 0; color: #929cab; font-size: 8px; }

.decision-panel { min-width: 0; display: flex; flex-direction: column; padding: 14px; }
.decision-head small { color: #1769ff; font-size: 9px; font-weight: 850; }
.decision-head h2 { margin: 3px 0 4px; color: #243a57; font-size: 19px; }
.decision-head p { margin: 0; color: #7c899b; font-size: 10px; line-height: 1.5; }
.recommended-card {
  width: 100%;
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) auto;
  gap: 9px;
  align-items: center;
  margin-top: 12px;
  padding: 8px;
  border-color: #a9c2f3;
  background: #f5f8ff;
  text-align: left;
}
.recommended-card.selected { border-color: #1769ff; box-shadow: 0 0 0 2px rgba(23,105,255,.08); }
.recommended-card > div:nth-child(2) { min-width: 0; display: grid; gap: 2px; }
.recommended-card small { color: #1769ff; font-size: 8px; font-weight: 850; }
.recommended-card strong { color: #294565; font-size: 12px; }
.recommended-card span { color: #7d899b; font-size: 8px; }
.recommended-card b { color: #1769ff; font-size: 9px; }
.candidate-cover { width: 44px; height: 48px; display: grid; place-items: center; overflow: hidden; border-radius: 7px; background: #edf1f6; color: #62738b; font-size: 16px; font-weight: 800; }
.candidate-cover.large { width: 58px; height: 64px; }
.candidate-cover img { width: 100%; height: 100%; object-fit: cover; }
.candidate-search { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px; align-items: center; margin-top: 12px; }
.candidate-search > span { color: #566982; font-size: 9px; font-weight: 800; }
.candidate-search input { width: 100%; min-height: 32px; }
.candidate-grid { min-height: 0; max-height: 290px; overflow-y: auto; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin-top: 8px; }
.candidate-card { min-width: 0; display: grid; grid-template-columns: 44px minmax(0, 1fr) 18px; gap: 7px; align-items: center; padding: 6px; text-align: left; }
.candidate-card.selected { border-color: #1769ff; background: #eef4ff; }
.candidate-card > div:nth-child(2) { min-width: 0; display: grid; gap: 2px; }
.candidate-card strong { overflow: hidden; color: #344a64; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.candidate-card small { color: #8994a4; font-size: 8px; }
.candidate-card i { display: grid; place-items: center; width: 18px; height: 18px; border: 1px solid #d7dfeb; border-radius: 50%; color: #1769ff; font-size: 9px; font-style: normal; font-weight: 900; }
.candidate-card.selected i { border-color: #1769ff; background: #1769ff; color: #fff; }
.new-character-button { width: 100%; margin-top: 8px; border-style: dashed; border-color: #9bb9f2; color: #1769ff; font-weight: 800; }
.current-binding { display: flex; align-items: center; gap: 6px; margin-top: 8px; padding: 7px 9px; border-radius: 7px; background: #f4f7fb; color: #738096; font-size: 9px; }
.current-binding strong { color: #3f5571; }
.decision-actions { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 7px; margin-top: auto; padding-top: 12px; }
.decision-actions .primary { min-height: 40px; }

.completion-screen {
  min-height: 520px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 36px;
  border: 1px solid #dfe6ef;
  border-radius: 14px;
  background: #fff;
  text-align: center;
}
.completion-check { width: 58px; height: 58px; display: grid; place-items: center; border-radius: 50%; background: #2fc36b; color: #fff; font-size: 30px; font-weight: 900; box-shadow: 0 10px 24px rgba(47,195,107,.2); }
.completion-screen h2 { margin: 16px 0 6px; color: #253b57; font-size: 22px; }
.completion-screen > p { margin: 0; color: #7d899a; font-size: 11px; }
.completion-metrics { width: min(680px, 100%); display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 24px; }
.completion-metrics article { display: grid; gap: 3px; padding: 14px; border: 1px solid #e1e6ed; border-radius: 10px; background: #f9fbfd; }
.completion-metrics strong { color: #29425f; font-size: 22px; }
.completion-metrics article:nth-child(2) strong { color: #d94b4b; }
.completion-metrics span { color: #8793a3; font-size: 9px; }
.completion-actions { display: flex; gap: 8px; margin-top: 20px; }
.completion-actions button { min-width: 150px; min-height: 40px; }

.modal-backdrop { position: fixed; inset: 0; z-index: 1800; display: grid; place-items: center; padding: 24px; background: rgba(20,31,48,.52); backdrop-filter: blur(2px); }
.small-modal,
.locator-modal { overflow: hidden; border: 1px solid #dfe5ed; border-radius: 14px; background: #fff; box-shadow: 0 24px 70px rgba(17,31,52,.3); }
.small-modal { width: min(520px, calc(100vw - 48px)); }
.locator-modal { width: min(920px, calc(100vw - 48px)); }
.small-modal > header,
.locator-modal > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 13px 15px; border-bottom: 1px solid #e7ebf0; }
.small-modal > header > div,
.locator-modal > header > div { display: grid; gap: 2px; }
.small-modal header small,
.locator-modal header small { color: #1769ff; font-size: 8px; font-weight: 850; }
.small-modal header h3,
.locator-modal header h3 { margin: 0; color: #2a405c; font-size: 15px; }
.small-modal > header > button,
.locator-modal > header > button { width: 32px; height: 32px; padding: 0; font-size: 18px; }
.create-preview { display: grid; grid-template-columns: 110px minmax(0, 1fr); gap: 12px; align-items: center; padding: 15px; }
.create-preview img { width: 110px; height: 94px; border-radius: 9px; object-fit: cover; background: #edf1f6; }
.create-preview > div { min-width: 0; display: grid; gap: 4px; }
.create-preview strong { color: #344a64; font-size: 13px; }
.create-preview span { color: #7d899b; font-size: 9px; line-height: 1.5; }
.form-field { display: grid; gap: 5px; padding: 0 15px; }
.form-field span { color: #566982; font-size: 9px; font-weight: 800; }
.form-field input { width: 100%; }
.form-help { margin: 8px 15px 0; color: #909aaa; font-size: 8px; line-height: 1.5; }
.small-modal > footer { display: flex; justify-content: flex-end; gap: 7px; margin-top: 14px; padding: 12px 15px; border-top: 1px solid #edf0f4; background: #fafbfc; }
.locator-canvas { height: min(62vh, 620px); margin: 12px; border-radius: 10px; cursor: crosshair; }
.drag-tip { position: absolute; left: 50%; bottom: 16px; transform: translateX(-50%); padding: 6px 9px; border-radius: 7px; background: rgba(21,35,55,.82); color: #fff; font-size: 9px; pointer-events: none; }
.locator-shots { display: flex; gap: 5px; padding: 0 12px 10px; overflow-x: auto; }
.locator-shots button.active { border-color: #1769ff; background: #eef4ff; color: #1769ff; }
.locator-modal > footer { display: grid; grid-template-columns: auto 1fr auto auto; gap: 7px; padding: 11px 12px; border-top: 1px solid #e7ebf0; background: #fafbfc; }

@media (max-width: 1050px) {
  .review-layout { grid-template-columns: 220px minmax(0, 1fr); }
  .review-main { grid-template-columns: 1fr; overflow-y: auto; }
  .evidence-column { border-right: 0; border-bottom: 1px solid #e7ebf1; }
  .decision-panel { min-height: 500px; }
  .candidate-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); max-height: none; }
}

@media (max-width: 760px) {
  .review-topbar { grid-template-columns: auto 1fr; }
  .progress-box { grid-column: 1 / -1; grid-template-columns: auto 1fr auto; }
  .progress-track { width: 100%; }
  .review-layout { grid-template-columns: 1fr; }
  .review-queue { max-height: 260px; }
  .review-main { grid-template-columns: 1fr; }
  .frame-stage { min-height: 280px; }
  .candidate-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .completion-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .completion-actions { flex-direction: column; width: 100%; }
}
</style>
