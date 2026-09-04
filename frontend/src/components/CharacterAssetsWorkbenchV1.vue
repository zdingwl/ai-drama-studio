<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()
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
  shot_ids: string[]
  shot_count?: number
  episode_count?: number
}

type Workspace = {
  revision: string
  observations: Observation[]
  characters: SourceCharacter[]
}

const data = ref<Workspace | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const search = ref('')
const focusKey = ref('')
const shotIndex = ref(0)
const destinationCharacterId = ref('')
const creatingNew = ref(false)
const sourceName = ref('')
const showLocator = ref(false)
const mark = ref<Mark | null>(null)
let dragStart: [number, number] | null = null

const pending = computed(() => (data.value?.observations || []).filter((item) => !item.character_id))
const completedCount = computed(() => (data.value?.observations || []).filter((item) => Boolean(item.character_id)).length)
const filteredPending = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  if (!keyword) return pending.value
  return pending.value.filter((item) =>
    `${item.name} ${item.appearance || ''} ${item.scene} ${item.episode_title}`.toLowerCase().includes(keyword),
  )
})
const charactersById = computed(() => new Map((data.value?.characters || []).map((item) => [item.id, item])))
const focused = computed(() => pending.value.find((item) => item.key === focusKey.value) || null)
const currentShot = computed(() => focused.value?.shots[shotIndex.value] || null)
const shownMark = computed(() => {
  if (!mark.value || !currentShot.value) return null
  return mark.value.shot_id === currentShot.value.id ? mark.value : null
})
const selectedCharacter = computed(() => destinationCharacterId.value
  ? charactersById.value.get(destinationCharacterId.value) || null
  : null)
const canSave = computed(() => Boolean(
  focused.value
  && !busy.value
  && (
    (!creatingNew.value && destinationCharacterId.value)
    || (creatingNew.value && sourceName.value.trim())
  ),
))
const progressLabel = computed(() => {
  const total = data.value?.observations.length || 0
  if (!total) return '0 / 0'
  return `${completedCount.value} / ${total}`
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

function selectObservation(item: Observation): void {
  focusKey.value = item.key
  shotIndex.value = 0
  sourceName.value = ''
  creatingNew.value = false
  showLocator.value = false
  mark.value = item.localization ? {
    shot_id: item.localization.shot_id,
    image_url: item.localization.image_url,
    box: [...item.localization.box],
  } : null
  dragStart = null

  if (item.suggested_character_id && charactersById.value.has(item.suggested_character_id)) {
    destinationCharacterId.value = item.suggested_character_id
  } else {
    destinationCharacterId.value = ''
  }
}

function ensureFocus(): void {
  if (focused.value) return
  const next = filteredPending.value[0] || pending.value[0]
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

function chooseCharacter(characterId: string): void {
  destinationCharacterId.value = characterId
  creatingNew.value = false
  sourceName.value = ''
}

function chooseNewCharacter(): void {
  destinationCharacterId.value = ''
  creatingNew.value = true
  sourceName.value = focused.value?.name && !/^人物\d*$/u.test(focused.value.name)
    ? focused.value.name
    : ''
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
  if (!showLocator.value || busy.value || !currentShot.value?.thumbnail_url) return
  dragStart = point(event)
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}

function moveMark(event: PointerEvent): void {
  if (!dragStart || !focused.value || !currentShot.value?.thumbnail_url) return
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
  if (mark.value && (mark.value.box[2]! < 0.02 || mark.value.box[3]! < 0.02)) {
    mark.value = null
  }
}

function clearMark(): void {
  mark.value = null
}

function changeShot(index: number): void {
  shotIndex.value = index
  dragStart = null
}

async function saveAssignment(): Promise<void> {
  if (!data.value || !focused.value || !canSave.value) return
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
          name: creatingNew.value ? sourceName.value.trim() : '',
          character_id: creatingNew.value ? null : destinationCharacterId.value,
          expected_revision: data.value.revision,
          // 明确选择 Local Person 后不强制重新框人；用户主动框选时才保存定位证据。
          localizations: mark.value ? { [savingKey]: mark.value } : null,
        }),
      },
    )
    data.value = result
    const next = result.observations.find((item) => !item.character_id && item.key !== savingKey)
    if (next) selectObservation(next)
    else focusKey.value = ''
    window.dispatchEvent(new CustomEvent('studio-project-truth-changed', {
      detail: { project_id: props.projectId },
    }))
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物归并失败'
  } finally {
    busy.value = false
  }
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
    <header class="review-header">
      <div>
        <small>人物归并</small>
        <h2>只判断一件事：画面里这个人是谁？</h2>
        <p>选择已有原片人物，或新建一个人物。普通情况不需要重新框选画面。</p>
      </div>
      <div class="review-header__status">
        <span><b>{{ pending.length }}</b> 待处理</span>
        <span><b>{{ progressLabel }}</b> 已完成</span>
        <button type="button" :disabled="loading || busy" @click="load">刷新</button>
      </div>
    </header>

    <div v-if="error" class="error" role="alert">{{ error }}</div>
    <div v-if="loading && !data" class="loading">正在读取人物归并任务…</div>

    <section v-else-if="data && !pending.length" class="all-done">
      <span>✓</span>
      <div>
        <strong>人物归并已经处理完成</strong>
        <p>当前没有需要人工确认的拉片人物观察。</p>
      </div>
    </section>

    <div v-else-if="data" class="review-layout">
      <aside class="review-queue">
        <div class="queue-head">
          <div>
            <strong>待处理 {{ pending.length }}</strong>
            <small>完成一个自动进入下一个</small>
          </div>
          <input v-model="search" type="search" placeholder="搜索人物或场景" aria-label="搜索待处理人物" />
        </div>

        <div class="queue-list">
          <button
            v-for="item in filteredPending"
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
            <em v-if="item.suggested_character_id">有建议</em>
          </button>
          <p v-if="!filteredPending.length" class="queue-empty">没有匹配的待处理人物。</p>
        </div>
      </aside>

      <main v-if="focused" class="review-card">
        <div class="identity-title">
          <div>
            <small>{{ focused.episode_title }} · {{ focused.scene }}</small>
            <h3>{{ focused.name }}</h3>
            <p>{{ focused.appearance || '暂无稳定外观描述，请以画面证据为准。' }}</p>
          </div>
          <button type="button" class="text-button" @click="openBreakdown">查看完整分镜 ↗</button>
        </div>

        <div class="decision-layout">
          <section class="evidence-panel">
            <div
              class="frame-stage"
              :class="{ locating: showLocator }"
              @pointerdown.prevent="startMark"
              @pointermove="moveMark"
              @pointerup="endMark"
              @pointercancel="dragStart = null"
            >
              <img
                v-if="currentShot?.thumbnail_url"
                :src="currentShot.thumbnail_url"
                alt="当前人物证据画面"
                draggable="false"
              />
              <div v-else class="no-frame">当前分镜没有可用画面</div>
              <div v-if="shownMark" class="person-box" :style="markStyle(shownMark)">
                <span>人物定位</span>
              </div>
              <div v-if="showLocator && currentShot?.thumbnail_url" class="locator-tip">
                在人物身上拖动框选
              </div>
            </div>

            <div v-if="focused.shots.length > 1" class="shot-picker">
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

            <div class="locator-row">
              <div>
                <strong>{{ shownMark ? '已记录人物位置' : '普通归并无需框人' }}</strong>
                <span>只有同框多人、画面容易认错时才需要定位。</span>
              </div>
              <div>
                <button v-if="shownMark" type="button" @click="clearMark">清除定位</button>
                <button type="button" @click="showLocator = !showLocator">
                  {{ showLocator ? '结束框选' : '需要框选人物' }}
                </button>
              </div>
            </div>
          </section>

          <section class="decision-panel">
            <div class="decision-head">
              <small>确认身份</small>
              <h3>这个人是谁？</h3>
              <p>优先选择已有原片人物；确定是新角色时再创建。</p>
            </div>

            <div
              v-if="focused.suggested_character_id && charactersById.get(focused.suggested_character_id)"
              class="suggestion"
            >
              <div>
                <small>系统建议</small>
                <strong>{{ charactersById.get(focused.suggested_character_id)!.name }}</strong>
              </div>
              <span>多个分镜的 Final Binding 唯一一致</span>
            </div>

            <div class="candidate-list">
              <button
                v-for="character in data.characters"
                :key="character.id"
                type="button"
                class="candidate"
                :class="{ selected: !creatingNew && destinationCharacterId === character.id }"
                @click="chooseCharacter(character.id)"
              >
                <div class="candidate-cover">
                  <img v-if="character.cover_url" :src="character.cover_url" :alt="`${character.name} 人物参考`" />
                  <span v-else>{{ character.name.slice(0, 1) }}</span>
                </div>
                <div>
                  <strong>{{ character.name }}</strong>
                  <small>{{ character.shot_count ?? character.shot_ids.length }} 个分镜 · {{ character.episode_count ?? 0 }} 集</small>
                </div>
                <span class="radio">{{ !creatingNew && destinationCharacterId === character.id ? '✓' : '' }}</span>
              </button>

              <button
                type="button"
                class="candidate new-character"
                :class="{ selected: creatingNew }"
                @click="chooseNewCharacter"
              >
                <span class="new-icon">＋</span>
                <div>
                  <strong>这是一个新人物</strong>
                  <small>创建新的原片人物资产</small>
                </div>
                <span class="radio">{{ creatingNew ? '✓' : '' }}</span>
              </button>
            </div>

            <label v-if="creatingNew" class="new-name">
              <span>人物名称</span>
              <input v-model="sourceName" maxlength="200" placeholder="例如：邻居大妈、司机、Emma" />
            </label>

            <div class="decision-result">
              <template v-if="creatingNew">
                <small>将创建并绑定</small>
                <strong>{{ sourceName.trim() || '请输入新人物名称' }}</strong>
              </template>
              <template v-else-if="selectedCharacter">
                <small>将归并到</small>
                <strong>{{ selectedCharacter.name }}</strong>
              </template>
              <template v-else>
                <small>尚未选择</small>
                <strong>请选择已有人物或新建人物</strong>
              </template>
            </div>

            <button
              type="button"
              class="primary-action"
              :disabled="!canSave"
              @click="saveAssignment"
            >
              {{ busy ? '正在保存…' : creatingNew ? '创建人物并确认 →' : selectedCharacter ? `确认是 ${selectedCharacter.name} →` : '请选择人物' }}
            </button>
          </section>
        </div>
      </main>
    </div>
  </section>
</template>

<style scoped>
.identity-review {
  display: grid;
  gap: 12px;
  min-height: 100%;
  color: #263850;
}

.review-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 14px 16px;
  border: 1px solid #dfe5ed;
  border-radius: 12px;
  background: #fff;
}
.review-header > div:first-child { min-width: 0; }
.review-header small { color: #6f7f95; font-size: 10px; font-weight: 800; letter-spacing: .04em; }
.review-header h2 { margin: 2px 0 4px; color: #273b58; font-size: 18px; }
.review-header p { margin: 0; color: #76849a; font-size: 11px; line-height: 1.55; }
.review-header__status { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.review-header__status > span { padding: 7px 9px; border-radius: 8px; background: #f4f7fb; color: #738197; font-size: 10px; }
.review-header__status b { color: #334967; font-size: 12px; }

button, input {
  box-sizing: border-box;
  border: 1px solid #d7e0eb;
  border-radius: 8px;
  background: #fff;
  color: #40516a;
  font: inherit;
  font-size: 11px;
}
button { padding: 8px 10px; cursor: pointer; }
button:disabled { opacity: .52; cursor: not-allowed; }
input { padding: 9px 10px; }

.error { margin: 0; padding: 9px 11px; border: 1px solid #efc7c7; border-radius: 8px; background: #fff3f3; color: #a93c3c; font-size: 11px; }
.loading { padding: 28px; border: 1px dashed #dbe2eb; border-radius: 10px; background: #fff; color: #7b899b; text-align: center; }
.all-done { min-height: 160px; display: flex; align-items: center; justify-content: center; gap: 12px; border: 1px solid #cae4d6; border-radius: 12px; background: #f3fbf7; }
.all-done > span { width: 38px; height: 38px; display: grid; place-items: center; border-radius: 50%; background: #dff3e8; color: #2e8051; font-size: 20px; font-weight: 900; }
.all-done strong { color: #315b45; font-size: 15px; }.all-done p { margin: 3px 0 0; color: #72907f; font-size: 11px; }

.review-layout {
  min-height: 560px;
  display: grid;
  grid-template-columns: 270px minmax(0, 1fr);
  gap: 10px;
}
.review-queue, .review-card { min-width: 0; border: 1px solid #dfe5ed; border-radius: 12px; background: #fff; overflow: hidden; }
.review-queue { display: grid; grid-template-rows: auto minmax(0, 1fr); }
.queue-head { display: grid; gap: 8px; padding: 12px; border-bottom: 1px solid #e7ebf1; background: #fbfcfe; }
.queue-head > div { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.queue-head strong { color: #334966; font-size: 12px; }.queue-head small { color: #8b96a6; font-size: 9px; }
.queue-head input { width: 100%; }
.queue-list { min-height: 0; max-height: 680px; overflow-y: auto; padding: 7px; }
.queue-item { width: 100%; display: grid; grid-template-columns: 48px minmax(0, 1fr) auto; gap: 8px; align-items: center; margin-bottom: 5px; padding: 7px; border-color: transparent; text-align: left; }
.queue-item:hover { background: #f7f9fc; }
.queue-item.active { border-color: #8fb0f4; background: #eef4ff; box-shadow: inset 3px 0 0 #4d79db; }
.queue-thumb { width: 48px; height: 56px; display: grid; place-items: center; overflow: hidden; border-radius: 7px; background: #edf1f6; color: #5d6f87; font-size: 17px; font-weight: 800; }
.queue-thumb img { width: 100%; height: 100%; object-fit: cover; }
.queue-copy { min-width: 0; display: grid; gap: 2px; }
.queue-copy strong { overflow: hidden; color: #334966; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.queue-copy span, .queue-copy small { overflow: hidden; color: #7f8b9d; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.queue-item em { padding: 3px 5px; border-radius: 5px; background: #edf4ff; color: #4d72bc; font-size: 8px; font-style: normal; white-space: nowrap; }
.queue-empty { padding: 20px 8px; color: #8a96a6; font-size: 10px; text-align: center; }

.review-card { padding: 14px; overflow: visible; }
.identity-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.identity-title > div { min-width: 0; }.identity-title small { color: #8490a2; font-size: 9px; }.identity-title h3 { margin: 3px 0 2px; color: #283e5d; font-size: 18px; }.identity-title p { margin: 0; color: #6f7f94; font-size: 11px; }
.text-button { border-color: transparent; color: #5471a1; background: transparent; }

.decision-layout { display: grid; grid-template-columns: minmax(0, 1.12fr) minmax(330px, .88fr); gap: 14px; align-items: start; }
.evidence-panel, .decision-panel { min-width: 0; }
.frame-stage { position: relative; min-height: 360px; max-height: 520px; display: grid; place-items: center; overflow: hidden; border-radius: 10px; background: #101923; user-select: none; }
.frame-stage.locating { cursor: crosshair; box-shadow: 0 0 0 2px #6f9bf4 inset; touch-action: none; }
.frame-stage > img { width: 100%; height: 100%; max-height: 520px; object-fit: contain; pointer-events: none; }
.no-frame { color: #aeb8c6; font-size: 11px; }
.person-box { position: absolute; border: 2px solid #6da1ff; border-radius: 4px; box-shadow: 0 0 0 9999px rgba(15, 25, 38, .18); pointer-events: none; }
.person-box span { position: absolute; left: 0; top: -24px; padding: 3px 6px; border-radius: 4px; background: #3e73d9; color: #fff; font-size: 9px; white-space: nowrap; }
.locator-tip { position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%); padding: 6px 10px; border-radius: 999px; background: rgba(21, 37, 58, .84); color: #fff; font-size: 10px; pointer-events: none; }
.shot-picker { display: flex; gap: 5px; overflow-x: auto; padding-top: 7px; }
.shot-picker button { white-space: nowrap; }.shot-picker button.active { border-color: #7295db; background: #edf4ff; color: #4269b5; }
.locator-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 8px; padding: 10px 11px; border-radius: 9px; background: #f6f8fb; }
.locator-row > div:first-child { display: grid; gap: 2px; }.locator-row strong { color: #465a75; font-size: 10px; }.locator-row span { color: #8793a4; font-size: 9px; }.locator-row > div:last-child { display: flex; gap: 5px; }

.decision-panel { display: grid; gap: 10px; align-content: start; padding: 13px; border: 1px solid #e1e7ef; border-radius: 10px; background: #fbfcfe; }
.decision-head small { color: #6c7d95; font-size: 9px; font-weight: 800; }.decision-head h3 { margin: 2px 0 3px; color: #2d425f; font-size: 17px; }.decision-head p { margin: 0; color: #7f8b9c; font-size: 10px; line-height: 1.5; }
.suggestion { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 8px 9px; border: 1px solid #cbdcfb; border-radius: 8px; background: #f1f6ff; }
.suggestion > div { display: grid; gap: 1px; }.suggestion small { color: #7188ad; font-size: 8px; }.suggestion strong { color: #3b5f9e; font-size: 11px; }.suggestion > span { color: #7589a9; font-size: 8px; text-align: right; }
.candidate-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 7px; max-height: 330px; overflow-y: auto; padding-right: 2px; }
.candidate { min-width: 0; display: grid; grid-template-columns: 42px minmax(0, 1fr) 20px; gap: 7px; align-items: center; padding: 7px; border-color: #dfe5ed; text-align: left; }
.candidate:hover { border-color: #b9c9e2; background: #fff; }.candidate.selected { border-color: #78a0ee; background: #edf4ff; box-shadow: inset 0 0 0 1px #78a0ee; }
.candidate-cover { width: 42px; height: 48px; display: grid; place-items: center; overflow: hidden; border-radius: 7px; background: #edf1f5; color: #61728a; font-size: 16px; font-weight: 800; }.candidate-cover img { width: 100%; height: 100%; object-fit: cover; }
.candidate > div:nth-child(2) { min-width: 0; display: grid; gap: 2px; }.candidate strong { overflow: hidden; color: #344a68; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }.candidate small { overflow: hidden; color: #8490a1; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.candidate .radio { width: 18px; height: 18px; display: grid; place-items: center; border: 1px solid #cbd5e2; border-radius: 50%; color: #356bc8; font-size: 10px; }
.new-character { grid-column: 1 / -1; }.new-icon { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 7px; background: #eef2f7; color: #65758b; font-size: 20px; }
.new-name { display: grid; gap: 4px; }.new-name span { color: #687990; font-size: 9px; font-weight: 750; }.new-name input { width: 100%; }
.decision-result { display: grid; gap: 2px; padding: 9px 10px; border-radius: 8px; background: #fff; }.decision-result small { color: #8a95a5; font-size: 8px; }.decision-result strong { color: #354b69; font-size: 11px; }
.primary-action { min-height: 42px; border-color: #3f71dc; background: #3f71dc; color: #fff; font-size: 11px; font-weight: 850; }

@media (max-width: 1100px) {
  .review-layout { grid-template-columns: 230px minmax(0, 1fr); }
  .decision-layout { grid-template-columns: 1fr; }
  .frame-stage { min-height: 300px; }
  .candidate-list { max-height: none; }
}

@media (max-width: 760px) {
  .review-header { align-items: flex-start; flex-direction: column; }
  .review-header__status { width: 100%; flex-wrap: wrap; }
  .review-layout { grid-template-columns: 1fr; }
  .review-queue { max-height: 260px; }
  .queue-list { max-height: 200px; }
  .candidate-list { grid-template-columns: 1fr; }
  .new-character { grid-column: auto; }
  .locator-row { align-items: flex-start; flex-direction: column; }
}
</style>
