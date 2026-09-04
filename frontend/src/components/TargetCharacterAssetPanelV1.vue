<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'

const props = defineProps<{ projectId: string }>()

type SourceCharacter = {
  id: string
  name: string
  cover_url?: string | null
  shot_ids: string[]
  shot_count?: number
  episode_count?: number
}

type ViewImage = { view: string; url: string }
type FourViewVersion = {
  id: string
  status: string
  error: string | null
  current: boolean
  accepted: boolean
  view_schema?: string
  images: ViewImage[]
}

type TargetCharacter = {
  id: string
  source_character_id: string
  source_character_name?: string
  target_name: string
  appearance_profile: string
  generation_prompt: string
  current: boolean
  fingerprint: string
  versions: FourViewVersion[]
}

type Workspace = {
  revision: string
  characters: SourceCharacter[]
  targets: TargetCharacter[]
  designable_ids: string[]
  snapshot_error: string | null
  target_region: string
  target_language?: string
}

type Draft = {
  target_name: string
  appearance_profile: string
  generation_prompt: string
}

const workspace = ref<Workspace | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const opened = ref('')
const preview = ref('')
const drafts = reactive<Record<string, Draft>>({})
const editRevisions = reactive<Record<string, string>>({})
const editFingerprints = reactive<Record<string, string | null>>({})
let timer: ReturnType<typeof setInterval> | undefined
let reading = false

const targetBySource = computed(() => new Map((workspace.value?.targets || []).map((item) => [item.source_character_id, item])))
const activeGeneration = computed(() => (workspace.value?.targets || []).some((target) =>
  target.versions.some((version) => ['QUEUED', 'PROCESSING'].includes(version.status)),
))
const designedCount = computed(() => (workspace.value?.targets || []).filter((item) => item.current).length)
const acceptedCount = computed(() => (workspace.value?.targets || []).filter((item) =>
  item.current && item.versions.some((version) => version.current && version.accepted),
).length)

async function request<T>(path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
  const options: RequestInit | undefined = body === undefined
    ? undefined
    : {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
        },
        body: JSON.stringify(body),
      }
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    try {
      const payload = await response.json() as { detail?: unknown }
      if (typeof payload.detail === 'string') message = payload.detail
    } catch {
      // 保留默认错误文案。
    }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

async function load(): Promise<void> {
  if (reading) return
  reading = true
  try {
    workspace.value = await request<Workspace>(`/api/projects/${encodeURIComponent(props.projectId)}/character-assets`)
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '替换人物资产读取失败'
  } finally {
    reading = false
    loading.value = false
  }
}

function target(sourceId: string): TargetCharacter | undefined {
  return targetBySource.value.get(sourceId)
}

function edit(sourceId: string): void {
  if (!workspace.value) return
  const current = target(sourceId)
  editRevisions[sourceId] = workspace.value.revision
  editFingerprints[sourceId] = current?.fingerprint || null
  drafts[sourceId] = {
    target_name: current?.target_name || '',
    appearance_profile: current?.appearance_profile || '',
    generation_prompt: current?.generation_prompt || '',
  }
  opened.value = sourceId
}

async function act(action: () => Promise<unknown>): Promise<void> {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    await action()
    await load()
    window.dispatchEvent(new CustomEvent('studio-project-truth-changed', {
      detail: { project_id: props.projectId },
    }))
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

async function save(sourceId: string): Promise<void> {
  const draft = drafts[sourceId]
  if (!draft) return
  await act(async () => {
    await request(
      `/api/projects/${encodeURIComponent(props.projectId)}/character-assets/design`,
      {
        source_character_id: sourceId,
        expected_revision: editRevisions[sourceId],
        expected_target_fingerprint: editFingerprints[sourceId],
        target_name: draft.target_name,
        appearance_profile: draft.appearance_profile,
        generation_prompt: draft.generation_prompt,
      },
    )
    opened.value = ''
  })
}

async function generate(item: TargetCharacter): Promise<void> {
  await act(() => request(
    `/api/target-characters/${encodeURIComponent(item.id)}/four-views`,
    { fingerprint: item.fingerprint },
    crypto.randomUUID(),
  ))
}

async function accept(item: TargetCharacter, version: FourViewVersion): Promise<void> {
  await act(() => request(
    `/api/character-view-versions/${encodeURIComponent(version.id)}/accept`,
    { fingerprint: item.fingerprint },
  ))
}

function viewName(view: string): string {
  return ({
    front: '正面',
    three_quarter: '45°',
    side: '侧面',
    back: '背面',
    left: '左侧（历史）',
    right: '右侧（历史）',
  } as Record<string, string>)[view] || view
}

function acceptedVersion(item?: TargetCharacter): FourViewVersion | undefined {
  return item?.versions.find((version) => version.current && version.accepted)
}

function latestCurrentVersion(item?: TargetCharacter): FourViewVersion | undefined {
  return item?.versions.find((version) => version.current)
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Escape') preview.value = ''
}

onMounted(() => {
  void load()
  timer = setInterval(() => {
    if (activeGeneration.value && !busy.value) void load()
  }, 4000)
  window.addEventListener('keydown', onKey)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  window.removeEventListener('keydown', onKey)
})
</script>

<template>
  <section class="target-character-panel">
    <header class="panel-header">
      <div>
        <small>替换人物资产</small>
        <h2>为每个原片人物建立本土化替换人物和四视图</h2>
        <p>
          四视图使用同一次连续 H3 身份转台生成，再抽取正面、45°、侧面、背面，
          避免四次独立生成造成脸、发型和服装漂移。
        </p>
      </div>
      <button type="button" :disabled="loading || busy" @click="load">刷新</button>
    </header>

    <div v-if="error" class="error" role="alert">{{ error }}</div>

    <div v-if="workspace" class="metrics">
      <article>
        <small>原片人物</small>
        <strong>{{ workspace.characters.length }}</strong>
        <span>已形成项目级人物资产</span>
      </article>
      <article>
        <small>已设计替换人物</small>
        <strong>{{ designedCount }}</strong>
        <span>{{ workspace.target_region || '目标地区' }} · {{ workspace.target_language || '目标语言' }}</span>
      </article>
      <article :class="{ warning: designedCount < workspace.characters.length }">
        <small>待设计</small>
        <strong>{{ Math.max(0, workspace.characters.length - designedCount) }}</strong>
        <span>需要确定新的本土化人物</span>
      </article>
      <article :class="{ ready: acceptedCount === workspace.characters.length && workspace.characters.length > 0 }">
        <small>四视图已采用</small>
        <strong>{{ acceptedCount }}</strong>
        <span>可作为 H3 人物 Reference</span>
      </article>
    </div>

    <div v-if="loading" class="empty">正在读取替换人物…</div>
    <div v-else-if="!workspace?.characters.length" class="empty">请先完成原片人物归并和分镜绑定。</div>

    <p v-if="workspace?.snapshot_error" class="notice">
      当前原片快照尚不能提供稳定人物上下文：{{ workspace.snapshot_error }}
    </p>

    <div v-if="workspace?.characters.length" class="target-list">
      <article v-for="source in workspace.characters" :key="source.id" class="target-card">
        <div class="source-side">
          <div class="source-cover">
            <img v-if="source.cover_url" :src="source.cover_url" :alt="`${source.name} 原片人物`" />
            <span v-else>{{ source.name.slice(0, 1) }}</span>
          </div>
          <div>
            <small>原片人物</small>
            <strong>{{ source.name }}</strong>
            <span>{{ source.shot_count ?? source.shot_ids.length }} 个分镜 · {{ source.episode_count ?? 0 }} 集</span>
          </div>
        </div>

        <div class="replace-arrow">→</div>

        <div class="target-side">
          <template v-if="target(source.id)">
            <div class="target-heading">
              <div>
                <small>替换人物</small>
                <strong>{{ target(source.id)!.target_name }}</strong>
                <span v-if="target(source.id)!.current">✓ 当前设计</span>
                <span v-else class="stale">原片人物或地区已变化</span>
              </div>
              <button
                type="button"
                :disabled="busy || !workspace.designable_ids.includes(source.id)"
                @click="edit(source.id)"
              >编辑设计</button>
            </div>
            <p>{{ target(source.id)!.appearance_profile }}</p>
          </template>
          <template v-else>
            <div class="target-empty">
              <div>
                <small>替换人物</small>
                <strong>尚未设计</strong>
                <span>先定义目标地区中的新人物身份与外观</span>
              </div>
              <button
                type="button"
                class="primary"
                :disabled="busy || !workspace.designable_ids.includes(source.id)"
                @click="edit(source.id)"
              >设计替换人物</button>
            </div>
          </template>

          <form v-if="opened === source.id" class="design-form" @submit.prevent="save(source.id)">
            <label>
              <span>目标人物名称</span>
              <input v-model="drafts[source.id]!.target_name" maxlength="200" required placeholder="例如：Emma Carter" />
            </label>
            <label>
              <span>固定身份与外观</span>
              <textarea
                v-model="drafts[source.id]!.appearance_profile"
                rows="4"
                required
                placeholder="年龄、肤色、脸型、五官、发型、体型、服装、鞋、角色气质。这里写需要跨镜保持一致的属性。"
              />
            </label>
            <label>
              <span>生成要求</span>
              <textarea
                v-model="drafts[source.id]!.generation_prompt"
                rows="3"
                required
                placeholder="补充目标地区、人物风格和必须保持的细节；不要写单个镜头动作。"
              />
            </label>
            <div class="form-actions">
              <button type="button" @click="opened = ''">取消</button>
              <button type="submit" class="primary" :disabled="busy">保存人物设计</button>
            </div>
          </form>

          <section v-if="target(source.id)?.current" class="reference-set">
            <div class="reference-heading">
              <div>
                <strong>人物四视图</strong>
                <span v-if="acceptedVersion(target(source.id))">✓ 已采用，可供 H3 使用</span>
                <span v-else-if="latestCurrentVersion(target(source.id))">候选版本待确认</span>
                <span v-else>尚未生成</span>
              </div>
              <button
                type="button"
                :disabled="busy || activeGeneration"
                @click="generate(target(source.id)!)"
              >
                {{ activeGeneration ? '生成任务进行中…' : latestCurrentVersion(target(source.id)) ? '重新生成四视图' : '生成四视图' }}
              </button>
            </div>

            <article
              v-for="version in target(source.id)!.versions"
              :key="version.id"
              class="version"
              :class="{ accepted: version.accepted && version.current }"
            >
              <div class="version-title">
                <strong>{{ version.accepted && version.current ? '当前采用版本' : version.current ? '当前候选版本' : '历史版本' }}</strong>
                <span>{{ version.view_schema === 'character-reference-v2' ? '正面 / 45° / 侧面 / 背面' : '历史角度标准' }}</span>
              </div>
              <p v-if="version.error" class="error">{{ version.error }}</p>
              <p v-else-if="!version.images.length" class="version-state">
                {{ version.status === 'QUEUED' ? '排队中…' : version.status === 'PROCESSING' ? '正在生成并抽取四视图…' : version.status }}
              </p>
              <div v-if="version.images.length" class="four-views">
                <button
                  v-for="image in version.images"
                  :key="image.view"
                  type="button"
                  @click="preview = image.url"
                >
                  <img :src="image.url" :alt="`${target(source.id)!.target_name} ${viewName(image.view)}`" />
                  <span>{{ viewName(image.view) }}</span>
                </button>
              </div>
              <button
                v-if="version.images.length && version.current && !version.accepted"
                type="button"
                class="accept-button"
                :disabled="busy"
                @click="accept(target(source.id)!, version)"
              >确认脸、发型、体型、服装与四个角度一致，采用此版本</button>
            </article>
          </section>
        </div>
      </article>
    </div>

    <div v-if="preview" class="preview" @click.self="preview = ''">
      <div role="dialog" aria-modal="true" aria-label="人物四视图预览">
        <button type="button" @click="preview = ''">关闭 ×</button>
        <img :src="preview" alt="人物参考图大图" />
      </div>
    </div>
  </section>
</template>

<style scoped>
.target-character-panel { display: grid; gap: 12px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 16px 18px; border: 1px solid #dce4ef; border-radius: 14px; background: #fff; }
.panel-header small { color: #70809a; font-size: 10px; font-weight: 850; letter-spacing: .05em; }
.panel-header h2 { margin: 3px 0 5px; color: #253a58; font-size: 18px; }
.panel-header p { max-width: 820px; margin: 0; color: #758398; font-size: 11px; line-height: 1.65; }
button, input, textarea { box-sizing: border-box; border: 1px solid #d6dfeb; border-radius: 8px; padding: 8px 10px; background: #fff; color: #43536b; font: inherit; font-size: 11px; }
button { cursor: pointer; } button:disabled { opacity: .55; cursor: not-allowed; } button.primary { border-color: #426fd2; background: #426fd2; color: #fff; font-weight: 800; }
.error { padding: 9px 11px; border: 1px solid #f0c7c7; border-radius: 8px; background: #fff3f3; color: #a83a3a; font-size: 11px; }
.notice { margin: 0; padding: 10px 12px; border: 1px solid #ecd29f; border-radius: 9px; background: #fff8ea; color: #7b642f; font-size: 11px; }
.empty { padding: 24px; border: 1px dashed #d8e0ea; border-radius: 10px; background: #fff; color: #78869a; font-size: 12px; text-align: center; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 9px; }
.metrics article { display: grid; gap: 2px; padding: 12px 14px; border: 1px solid #dfe5ed; border-radius: 11px; background: #fff; }
.metrics article.warning { border-color: #efcf9b; background: #fff8eb; }
.metrics article.ready { border-color: #c8e5d7; background: #f2faf6; }
.metrics small { color: #8793a5; font-size: 10px; }.metrics strong { color: #2f435f; font-size: 22px; }.metrics span { color: #8a96a6; font-size: 10px; }
.target-list { display: grid; gap: 10px; }
.target-card { display: grid; grid-template-columns: 235px 32px minmax(0, 1fr); gap: 10px; align-items: stretch; padding: 14px; border: 1px solid #dfe5ed; border-radius: 12px; background: #fff; }
.source-side { display: flex; align-items: center; gap: 10px; padding-right: 10px; border-right: 1px solid #edf0f4; }
.source-cover { width: 64px; height: 74px; flex: 0 0 64px; display: grid; place-items: center; overflow: hidden; border-radius: 9px; background: #edf1f6; color: #64758d; font-size: 25px; font-weight: 800; }
.source-cover img { width: 100%; height: 100%; object-fit: cover; }
.source-side > div:last-child, .target-heading > div, .target-empty > div { display: grid; gap: 3px; }
.source-side small, .target-side small { color: #8a96a7; font-size: 9px; }.source-side strong, .target-side strong { color: #344a68; font-size: 14px; }.source-side span, .target-side span { color: #758399; font-size: 10px; }
.replace-arrow { display: grid; place-items: center; color: #9aa7b9; font-size: 16px; }
.target-side { min-width: 0; display: grid; gap: 10px; align-content: start; }
.target-heading, .target-empty, .reference-heading, .version-title, .form-actions { display: flex; justify-content: space-between; align-items: flex-start; gap: 10px; }
.target-heading .stale { color: #a8663a; }.target-side > p { margin: 0; color: #6f7e92; font-size: 11px; line-height: 1.6; }
.design-form { display: grid; gap: 9px; padding: 12px; border-radius: 9px; background: #f7f9fc; }
.design-form label { display: grid; gap: 4px; }.design-form label > span { color: #5e6f86; font-size: 10px; font-weight: 750; }.design-form input, .design-form textarea { width: 100%; resize: vertical; }.form-actions { justify-content: flex-end; }
.reference-set { display: grid; gap: 8px; padding-top: 9px; border-top: 1px solid #edf0f4; }.reference-heading { align-items: center; }.reference-heading > div { display: grid; gap: 2px; }.reference-heading strong { font-size: 12px; }.reference-heading span { font-size: 9px; }
.version { display: grid; gap: 8px; padding: 10px; border: 1px solid #e2e7ee; border-radius: 9px; background: #f8fafc; }.version.accepted { border-color: #bfdcca; background: #f2faf6; }.version-title { align-items: center; }.version-title strong { font-size: 10px; }.version-title span { color: #8290a3; font-size: 9px; }.version-state { margin: 0; color: #77859a; font-size: 10px; }
.four-views { display: grid; grid-template-columns: repeat(4, minmax(0, 140px)); gap: 7px; }.four-views button { padding: 4px; display: grid; gap: 3px; }.four-views img { width: 100%; height: 170px; object-fit: contain; background: #edf1f5; }.four-views span { color: #56677e; font-size: 9px; font-weight: 750; text-align: center; }.accept-button { justify-self: start; border-color: #70a986; color: #3d7454; background: #eff8f3; font-weight: 800; }
.preview { position: fixed; inset: 0; z-index: 1400; display: grid; place-items: center; padding: 24px; background: #101722c7; }.preview > div { display: grid; gap: 8px; }.preview button { justify-self: end; }.preview img { max-width: 90vw; max-height: 84vh; border-radius: 8px; background: #fff; }
@media (max-width: 980px) { .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.target-card { grid-template-columns: 1fr; }.source-side { border-right: 0; border-bottom: 1px solid #edf0f4; padding: 0 0 10px; }.replace-arrow { transform: rotate(90deg); }.four-views { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
