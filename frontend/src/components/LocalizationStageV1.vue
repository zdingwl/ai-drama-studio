<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { localizationApi } from '../api/localization'
import type {
  LocalizationDraftDecision,
  LocalizationDraftEditPayload,
  LocalizationDraftEntry,
  LocalizationDraftView,
  LocalizationRevisionSummary,
} from '../types/localization'
import type { Project } from '../types/studio'

const props = defineProps<{ project: Project }>()
const route = useRoute()
const router = useRouter()

interface EditableEntry {
  decision: LocalizationDraftDecision
  translated_text: string
  localized_text: string
  final_text: string
}

const draft = ref<LocalizationDraftView | null>(null)
const revisions = ref<LocalizationRevisionSummary[]>([])
const editor = ref<Record<string, EditableEntry>>({})
const dirtyKeys = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)
const error = ref('')
const success = ref('')

const selectedEpisodeId = computed(() => {
  const requested = String(route.query.episode || '')
  return props.project.episodes.find((episode) => episode.id === requested)?.id
    ?? props.project.episodes[0]?.id
    ?? ''
})

const selectedEpisode = computed(() => props.project.episodes.find((episode) => episode.id === selectedEpisodeId.value) ?? null)
const canEdit = computed(() => Boolean(draft.value && draft.value.status === 'DRAFT' && !draft.value.stale))
const hasDirty = computed(() => dirtyKeys.value.length > 0)
const unresolvedFinalCount = computed(() => {
  if (!draft.value) return 0
  let count = 0
  for (const scene of draft.value.scenes) {
    for (const shot of scene.shots) {
      for (const entry of shot.entries) {
        const item = editor.value[entry.source_key]
        if (!item) continue
        if (item.decision === 'PENDING') count += 1
        if (item.decision === 'LOCALIZE' && !item.final_text.trim()) count += 1
      }
    }
  }
  return count
})
const reviewReady = computed(() => Boolean(
  draft.value
  && draft.value.status === 'DRAFT'
  && !draft.value.stale
  && !hasDirty.value
  && unresolvedFinalCount.value === 0,
))

const statusLabel = computed(() => {
  if (!draft.value) return '未创建'
  if (draft.value.stale) return '源版本已变化'
  if (draft.value.status === 'FINAL') return '已定稿'
  if (draft.value.status === 'IN_REVIEW') return '待复核'
  return '编辑中'
})

function hydrate(next: LocalizationDraftView | null): void {
  draft.value = next
  const nextEditor: Record<string, EditableEntry> = {}
  if (next) {
    for (const scene of next.scenes) {
      for (const shot of scene.shots) {
        for (const entry of shot.entries) {
          nextEditor[entry.source_key] = {
            decision: entry.decision,
            translated_text: entry.translated_text ?? '',
            localized_text: entry.localized_text ?? '',
            final_text: entry.final_text ?? '',
          }
        }
      }
    }
  }
  editor.value = nextEditor
  dirtyKeys.value = []
}

function markDirty(sourceKey: string): void {
  if (!dirtyKeys.value.includes(sourceKey)) dirtyKeys.value = [...dirtyKeys.value, sourceKey]
  success.value = ''
}

function changeDecision(sourceKey: string, decision: LocalizationDraftDecision): void {
  const item = editor.value[sourceKey]
  if (!item) return
  item.decision = decision
  if (decision === 'KEEP_SOURCE' || decision === 'OMIT') item.final_text = ''
  markDirty(sourceKey)
}

function formatTime(us: number): string {
  const total = Math.max(0, us) / 1_000_000
  const minutes = Math.floor(total / 60)
  const seconds = total - minutes * 60
  return `${String(minutes).padStart(2, '0')}:${seconds.toFixed(1).padStart(4, '0')}`
}

function speakerLabel(entry: LocalizationDraftEntry): string {
  if (!entry.speakers.length) return entry.kind === 'dialogue' ? '说话人未确认' : '画面文字'
  return entry.speakers.map((item) => item.display_name).join('、')
}

async function load(): Promise<void> {
  if (!selectedEpisodeId.value) {
    hydrate(null)
    revisions.value = []
    return
  }
  loading.value = true
  error.value = ''
  try {
    const [draftResult, revisionResult] = await Promise.allSettled([
      localizationApi.getCurrentDraft(selectedEpisodeId.value),
      localizationApi.listRevisions(selectedEpisodeId.value),
    ])
    if (draftResult.status === 'fulfilled') hydrate(draftResult.value)
    else throw draftResult.reason
    revisions.value = revisionResult.status === 'fulfilled' ? revisionResult.value : []
  } catch (err) {
    hydrate(null)
    error.value = err instanceof Error ? err.message : '本土化稿读取失败'
  } finally {
    loading.value = false
  }
}

async function createDraft(): Promise<void> {
  if (!selectedEpisodeId.value) return
  saving.value = true
  error.value = ''
  try {
    const next = await localizationApi.createDraft(selectedEpisodeId.value)
    hydrate(next)
    revisions.value = await localizationApi.listRevisions(selectedEpisodeId.value)
    success.value = '已创建本土化草稿。源对白和画面文字保持只读。'
  } catch (err) {
    error.value = err instanceof Error ? err.message : '创建本土化草稿失败'
  } finally {
    saving.value = false
  }
}

async function saveDraft(): Promise<void> {
  if (!draft.value || !canEdit.value || !dirtyKeys.value.length) return
  const entries: LocalizationDraftEditPayload[] = dirtyKeys.value.map((sourceKey) => {
    const item = editor.value[sourceKey]
    return {
      source_key: sourceKey,
      decision: item.decision,
      translated_text: item.translated_text.trim() || null,
      localized_text: item.localized_text.trim() || null,
      final_text: item.final_text.trim() || null,
    }
  })
  saving.value = true
  error.value = ''
  try {
    const next = await localizationApi.editDraft(
      draft.value.episode_id,
      draft.value.revision_id,
      entries,
      `保存 ${entries.length} 条本土化修改`,
    )
    hydrate(next)
    revisions.value = await localizationApi.listRevisions(next.episode_id)
    success.value = `已保存，新版本为 R${next.revision}。`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '保存本土化草稿失败'
  } finally {
    saving.value = false
  }
}

async function setStatus(status: 'DRAFT' | 'IN_REVIEW' | 'FINAL'): Promise<void> {
  if (!draft.value || hasDirty.value) return
  saving.value = true
  error.value = ''
  try {
    const next = await localizationApi.setStatus(draft.value.episode_id, draft.value.revision_id, status)
    hydrate(next)
    revisions.value = await localizationApi.listRevisions(next.episode_id)
    success.value = status === 'IN_REVIEW' ? '已送审。' : status === 'FINAL' ? '本集本土化稿已定稿。' : '已退回编辑。'
  } catch (err) {
    error.value = err instanceof Error ? err.message : '状态更新失败'
  } finally {
    saving.value = false
  }
}

async function rebaseDraft(): Promise<void> {
  if (!draft.value) return
  saving.value = true
  error.value = ''
  try {
    const next = await localizationApi.rebaseDraft(draft.value.episode_id)
    hydrate(next)
    revisions.value = await localizationApi.listRevisions(next.episode_id)
    success.value = next.note || '已重建到最新源版本。'
  } catch (err) {
    error.value = err instanceof Error ? err.message : '重建本土化草稿失败'
  } finally {
    saving.value = false
  }
}

function selectEpisode(episodeId: string): void {
  void router.replace({ query: { ...route.query, stage: '4', episode: episodeId } })
}

function openReference(url: string | null): void {
  if (!url || typeof window === 'undefined') return
  window.open(url, '_blank', 'noopener,noreferrer')
}

watch(selectedEpisodeId, () => void load())
onMounted(() => void load())
</script>

<template>
  <section class="localization-stage">
    <header class="localization-head">
      <div>
        <small>04 · 本土化剧本</small>
        <h1>先保留原文，再完成目标语言版本</h1>
        <p>原对白 / OCR 永远只读；这里保存的只有翻译、本土化改写和最终文案。</p>
      </div>
      <div class="target-card">
        <small>目标</small>
        <strong>{{ project.target_language }}</strong>
        <span>{{ project.target_region }}</span>
      </div>
    </header>

    <div v-if="project.episodes.length" class="episode-tabs">
      <button
        v-for="episode in project.episodes"
        :key="episode.id"
        :class="{ active: episode.id === selectedEpisodeId }"
        @click="selectEpisode(episode.id)"
      >
        {{ episode.title }}
      </button>
    </div>

    <div v-if="error" class="message error-message">{{ error }}</div>
    <div v-if="success" class="message success-message">{{ success }}</div>

    <div v-if="loading" class="empty-state">正在读取本土化稿…</div>
    <div v-else-if="!selectedEpisode" class="empty-state">
      <strong>还没有剧集</strong>
      <span>先在 01 导入源片。</span>
    </div>
    <div v-else-if="!draft" class="empty-state create-state">
      <strong>{{ selectedEpisode.title }} 还没有本土化草稿</strong>
      <span>创建时会读取当前 02 拉片 + 03 最终资产结果；不会复制旧 Dialogue 表作为真相。</span>
      <button class="primary-button" :disabled="saving" @click="createDraft">
        {{ saving ? '正在创建…' : '创建本土化草稿' }}
      </button>
    </div>

    <template v-else>
      <section class="draft-summary">
        <div class="summary-main">
          <div>
            <small>{{ selectedEpisode?.title }}</small>
            <strong>{{ statusLabel }} · R{{ draft.revision }}</strong>
          </div>
          <div class="progress-copy">
            <strong>{{ draft.progress.total - draft.progress.pending }} / {{ draft.progress.total }}</strong>
            <span>已做处理决定</span>
          </div>
          <div class="progress-copy">
            <strong>{{ unresolvedFinalCount }}</strong>
            <span>送审前待完成</span>
          </div>
        </div>

        <div class="draft-actions">
          <button v-if="draft.stale" class="primary-button" :disabled="saving" @click="rebaseDraft">重建到最新源版本</button>
          <button v-else-if="draft.status === 'DRAFT'" class="ghost-button" :disabled="saving || !hasDirty" @click="saveDraft">保存修改</button>
          <button v-if="draft.status === 'DRAFT' && !draft.stale" class="primary-button" :disabled="saving || !reviewReady" @click="setStatus('IN_REVIEW')">送审</button>
          <button v-if="draft.status === 'IN_REVIEW'" class="ghost-button" :disabled="saving" @click="setStatus('DRAFT')">退回修改</button>
          <button v-if="draft.status === 'IN_REVIEW'" class="primary-button" :disabled="saving" @click="setStatus('FINAL')">确认定稿</button>
        </div>
      </section>

      <div v-if="draft.stale" class="source-warning">
        <strong>这份稿件绑定的是旧源版本</strong>
        <span>为防止台词写到错误镜头，当前稿件已只读。重建时只会继承原文、时间和 source_key 完全一致的编辑。</span>
      </div>

      <div v-for="warning in draft.warnings" :key="warning" class="message warning-message">{{ warning }}</div>

      <section v-for="scene in draft.scenes" :key="scene.ordinal" class="scene-card">
        <header class="scene-head">
          <div>
            <small>场景 {{ String(scene.ordinal).padStart(2, '0') }}</small>
            <h2>{{ scene.title }}</h2>
          </div>
          <p v-if="scene.story_summary">{{ scene.story_summary }}</p>
        </header>

        <article v-for="shot in scene.shots" :key="shot.ordinal" class="shot-card">
          <div class="shot-context">
            <div class="shot-cover">
              <img v-if="shot.thumbnail_url" :src="shot.thumbnail_url" alt="镜头缩略图" />
              <div v-else class="shot-placeholder">镜头 {{ shot.ordinal }}</div>
            </div>
            <div class="shot-copy">
              <small>镜头 {{ String(shot.ordinal).padStart(2, '0') }} · {{ formatTime(shot.start_us) }}–{{ formatTime(shot.end_us) }}</small>
              <p>{{ shot.visual_description || '暂无画面描述' }}</p>
              <div v-if="shot.people.length" class="people-row">
                <span v-for="person in shot.people" :key="person.character?.id || person.display_name">{{ person.display_name }}</span>
              </div>
              <button v-if="shot.reference_url" class="link-button" @click="openReference(shot.reference_url)">查看参考片段 ↗</button>
            </div>
          </div>

          <div v-if="!shot.entries.length" class="shot-no-copy">这个镜头没有对白或需要处理的画面文字。</div>

          <div v-for="entry in shot.entries" :key="entry.source_key" class="copy-editor">
            <div class="source-column">
              <div class="entry-meta">
                <span>{{ entry.kind === 'dialogue' ? '对白' : '画面文字' }}</span>
                <small>{{ speakerLabel(entry) }} · {{ formatTime(entry.start_us) }}–{{ formatTime(entry.end_us) }}</small>
              </div>
              <strong>{{ entry.source_text }}</strong>
              <small class="source-lock">源文本 · 只读</small>
            </div>

            <div class="target-column">
              <label>
                <span>处理方式</span>
                <select
                  :value="editor[entry.source_key]?.decision"
                  :disabled="!canEdit"
                  @change="changeDecision(entry.source_key, ($event.target as HTMLSelectElement).value as LocalizationDraftDecision)"
                >
                  <option value="PENDING">待处理</option>
                  <option value="LOCALIZE">本土化改写</option>
                  <option value="KEEP_SOURCE">保留原文</option>
                  <option value="OMIT">重制版不显示 / 不说</option>
                </select>
              </label>

              <template v-if="editor[entry.source_key]?.decision === 'LOCALIZE'">
                <label>
                  <span>直译参考</span>
                  <textarea
                    v-model="editor[entry.source_key].translated_text"
                    :disabled="!canEdit"
                    rows="2"
                    placeholder="先保留语义，不必追求口语化"
                    @input="markDirty(entry.source_key)"
                  ></textarea>
                </label>
                <label>
                  <span>本土化改写</span>
                  <textarea
                    v-model="editor[entry.source_key].localized_text"
                    :disabled="!canEdit"
                    rows="2"
                    placeholder="按目标地区表达习惯改写"
                    @input="markDirty(entry.source_key)"
                  ></textarea>
                </label>
                <label>
                  <span>最终台词 / 文字</span>
                  <textarea
                    v-model="editor[entry.source_key].final_text"
                    :disabled="!canEdit"
                    rows="2"
                    placeholder="送审前必须确定最终版本"
                    @input="markDirty(entry.source_key)"
                  ></textarea>
                </label>
              </template>
              <div v-else-if="editor[entry.source_key]?.decision === 'KEEP_SOURCE'" class="decision-preview">最终使用原文：{{ entry.source_text }}</div>
              <div v-else-if="editor[entry.source_key]?.decision === 'OMIT'" class="decision-preview muted">此内容不会进入后续重制脚本。</div>
            </div>
          </div>
        </article>
      </section>

      <details class="revision-history">
        <summary>版本记录 · {{ revisions.length }} 个 Revision</summary>
        <div class="revision-row" v-for="item in revisions" :key="item.id">
          <strong>R{{ item.revision }} · {{ item.status }}</strong>
          <span>{{ item.note || item.kind }}</span>
          <small>{{ new Date(item.created_at).toLocaleString() }}</small>
        </div>
      </details>
    </template>
  </section>
</template>

<style scoped>
.localization-stage { height: 100%; overflow: auto; padding: 24px 28px 80px; background: #f6f7f9; color: #172033; }
.localization-head { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 18px; }
.localization-head small { color: #718096; font-weight: 800; letter-spacing: .04em; }
.localization-head h1 { margin: 5px 0 6px; font-size: 24px; }
.localization-head p { margin: 0; color: #69768a; }
.target-card { min-width: 150px; padding: 12px 14px; border: 1px solid #dfe4eb; border-radius: 12px; background: #fff; display: grid; gap: 2px; }
.target-card strong { font-size: 16px; }
.target-card span { color: #6f7b8d; font-size: 12px; }
.episode-tabs { display: flex; gap: 8px; overflow-x: auto; margin-bottom: 16px; }
.episode-tabs button { border: 1px solid #dde3eb; background: #fff; border-radius: 9px; padding: 8px 12px; cursor: pointer; white-space: nowrap; }
.episode-tabs button.active { border-color: #345fc7; color: #234da9; background: #edf3ff; font-weight: 800; }
.empty-state { min-height: 260px; border: 1px dashed #ccd4df; border-radius: 14px; display: grid; place-content: center; gap: 8px; text-align: center; background: #fff; color: #6d7889; padding: 28px; }
.empty-state strong { color: #1d2738; font-size: 18px; }
.create-state .primary-button { justify-self: center; margin-top: 8px; }
.message { margin: 10px 0; border-radius: 10px; padding: 10px 12px; font-size: 13px; }
.error-message { background: #fff0f0; color: #a13a3a; border: 1px solid #f0cccc; }
.success-message { background: #edf9f2; color: #28704b; border: 1px solid #ccebd9; }
.warning-message { background: #fff8e8; color: #875e16; border: 1px solid #f1dfb6; }
.draft-summary { position: sticky; top: 0; z-index: 3; display: flex; justify-content: space-between; gap: 16px; align-items: center; padding: 13px 15px; margin-bottom: 14px; border: 1px solid #dfe4eb; border-radius: 12px; background: rgba(255,255,255,.96); backdrop-filter: blur(8px); }
.summary-main { display: flex; gap: 28px; align-items: center; }
.summary-main > div:first-child { display: grid; gap: 2px; }
.summary-main small, .progress-copy span { color: #788498; font-size: 11px; }
.progress-copy { display: grid; gap: 1px; }
.progress-copy strong { font-size: 17px; }
.draft-actions { display: flex; gap: 8px; }
.primary-button, .ghost-button { border-radius: 9px; padding: 9px 13px; font-weight: 800; cursor: pointer; }
.primary-button { border: 1px solid #2857bd; background: #315fc5; color: #fff; }
.ghost-button { border: 1px solid #d8dee8; background: #fff; color: #334056; }
.primary-button:disabled, .ghost-button:disabled { opacity: .45; cursor: not-allowed; }
.source-warning { display: grid; gap: 4px; margin: 10px 0 14px; padding: 12px 14px; border: 1px solid #efcaca; border-radius: 10px; background: #fff4f4; color: #874040; }
.source-warning span { font-size: 12px; }
.scene-card { margin: 16px 0 22px; }
.scene-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 28px; margin-bottom: 9px; }
.scene-head small { color: #8490a2; font-weight: 800; }
.scene-head h2 { margin: 3px 0 0; font-size: 18px; }
.scene-head p { margin: 0; max-width: 55%; color: #707c8f; font-size: 12px; text-align: right; }
.shot-card { margin-bottom: 12px; border: 1px solid #dfe4eb; border-radius: 13px; background: #fff; overflow: hidden; }
.shot-context { display: grid; grid-template-columns: 150px 1fr; gap: 14px; padding: 13px; background: #fafbfc; border-bottom: 1px solid #e7ebf0; }
.shot-cover { height: 84px; border-radius: 9px; overflow: hidden; background: #e7ebf0; }
.shot-cover img { width: 100%; height: 100%; object-fit: cover; display: block; }
.shot-placeholder { height: 100%; display: grid; place-content: center; color: #798598; font-size: 12px; }
.shot-copy { display: grid; align-content: center; gap: 6px; }
.shot-copy small { color: #7f8a9b; }
.shot-copy p { margin: 0; font-size: 13px; line-height: 1.55; }
.people-row { display: flex; gap: 5px; flex-wrap: wrap; }
.people-row span { padding: 3px 7px; border-radius: 999px; background: #eef2f8; color: #566378; font-size: 11px; }
.link-button { justify-self: start; border: 0; padding: 0; background: transparent; color: #315fc5; cursor: pointer; font-size: 12px; }
.shot-no-copy { padding: 14px; color: #8a95a5; font-size: 12px; }
.copy-editor { display: grid; grid-template-columns: minmax(260px, .8fr) minmax(420px, 1.2fr); border-top: 1px solid #edf0f4; }
.copy-editor:first-of-type { border-top: 0; }
.source-column, .target-column { padding: 14px 16px; }
.source-column { border-right: 1px solid #edf0f4; display: grid; align-content: start; gap: 9px; }
.source-column > strong { font-size: 15px; line-height: 1.6; }
.entry-meta { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.entry-meta span { padding: 3px 7px; border-radius: 6px; background: #eef2f8; color: #536075; font-size: 11px; font-weight: 800; }
.entry-meta small, .source-lock { color: #8a95a6; font-size: 10px; }
.target-column { display: grid; gap: 10px; }
.target-column label { display: grid; gap: 5px; }
.target-column label > span { color: #69768a; font-size: 11px; font-weight: 800; }
.target-column select, .target-column textarea { width: 100%; box-sizing: border-box; border: 1px solid #d9dfe8; border-radius: 8px; background: #fff; padding: 8px 9px; color: #243047; font: inherit; font-size: 12px; }
.target-column textarea { resize: vertical; line-height: 1.5; }
.target-column select:disabled, .target-column textarea:disabled { background: #f5f6f8; color: #6e798a; }
.decision-preview { border-radius: 8px; padding: 10px; background: #eff7f2; color: #35694d; font-size: 12px; }
.decision-preview.muted { background: #f3f4f6; color: #7c8593; }
.revision-history { margin-top: 18px; border: 1px solid #dde3eb; border-radius: 11px; background: #fff; padding: 11px 13px; }
.revision-history summary { cursor: pointer; font-weight: 800; font-size: 12px; }
.revision-row { display: grid; grid-template-columns: 120px 1fr auto; gap: 10px; align-items: center; padding: 9px 0; border-top: 1px solid #edf0f4; font-size: 11px; }
.revision-row:first-of-type { margin-top: 8px; }
.revision-row span, .revision-row small { color: #7b8798; }
@media (max-width: 1000px) {
  .copy-editor { grid-template-columns: 1fr; }
  .source-column { border-right: 0; border-bottom: 1px solid #edf0f4; }
  .draft-summary, .localization-head, .scene-head { align-items: stretch; flex-direction: column; }
  .summary-main { flex-wrap: wrap; }
  .shot-context { grid-template-columns: 110px 1fr; }
  .scene-head p { max-width: none; text-align: left; }
}
</style>
