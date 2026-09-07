<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import SourceShotReviewWorkspaceV2 from './SourceShotReviewWorkspaceV2.vue'
import { nextReviewKey } from '../utils/continuousReviewQueue'
import type { Episode, Shot } from '../types/studio'

type Evidence = { id: string; revision: string; status: string; start_us: number; end_us: number; asr_text?: string; subtitle_text: string; utterance_id?: string; requires_full_text?: boolean }
const props = defineProps<{ projectId: string; episode: Episode; focusShotOrdinal?: number | null; focusDialogueStartUs?: number | null; sourceReady: boolean; blockingReason: string }>()
const emit = defineEmits<{ changed: []; busy: [boolean]; people: [] }>()
const rows = ref<Evidence[]>([])
const shots = ref<Shot[]>([])
const activeId = ref('')
const edits = ref<Record<string, string>>({})
const loading = ref(true)
const readFailed = ref(false)
const saving = ref(false)
const error = ref('')
const speakerReady = ref(false)
const savedCount = ref(0)
const pending = computed(() => rows.value.filter(row => row.status === 'OPEN').sort((a, b) => a.start_us - b.start_us || a.id.localeCompare(b.id)))
const active = computed(() => pending.value.find(row => row.id === activeId.value) || pending.value[0])
const linkedShots = computed(() => active.value ? shots.value.filter(shot => Math.min(shot.end_us, active.value!.end_us) > Math.max(shot.start_us, active.value!.start_us)) : [])
const previewShotId = ref('')
const previewShot = computed(() => linkedShots.value.find(shot => shot.id === previewShotId.value) || linkedShots.value[0])
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}
async function load(): Promise<boolean> {
  loading.value = true
  error.value = ''
  try {
    const [evidence, shotRows] = await Promise.all([
      request<Evidence[]>(`/api/episodes/${encodeURIComponent(props.episode.id)}/dialogue-evidence`),
      api.listShots(props.episode.id),
    ])
    rows.value = evidence
    shots.value = shotRows
    for (const row of evidence) if (!(row.id in edits.value)) edits.value[row.id] = (row.requires_full_text ? row.asr_text : row.subtitle_text) || ''
    if (!activeId.value) {
      const shot = shots.value.find(shot => shot.ordinal === props.focusShotOrdinal)
      activeId.value = pending.value.find(row => props.focusDialogueStartUs != null && row.start_us <= props.focusDialogueStartUs && row.end_us > props.focusDialogueStartUs)?.id
        || pending.value.find(row => shot && Math.min(shot.end_us, row.end_us) > Math.max(shot.start_us, row.start_us))?.id || ''
    }
    readFailed.value = false
    return true
  } catch (err) { readFailed.value = true; error.value = err instanceof Error ? err.message : '对白读取失败'; return false }
  finally { loading.value = false }
}
function next(): void {
  if (saving.value || loading.value || readFailed.value) return
  activeId.value = nextReviewKey(pending.value.map(row => row.id), active.value?.id || '', pending.value.map(row => row.id))
  previewShotId.value = ''
}
async function decide(choice: string): Promise<void> {
  const row = active.value
  if (!row || saving.value || loading.value || readFailed.value) return
  const before = pending.value.map(row => row.id)
  saving.value = true; emit('busy', true); error.value = ''
  try {
    await request(`/api/episodes/${encodeURIComponent(props.episode.id)}/dialogue-evidence/${encodeURIComponent(row.id)}/decide`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ revision: row.revision, choice, text: edits.value[row.id] }),
    })
    savedCount.value += 1
    if (await load()) {
      activeId.value = nextReviewKey(before, row.id, pending.value.map(row => row.id))
      previewShotId.value = ''
    }
    window.dispatchEvent(new CustomEvent('studio-project-truth-changed', { detail: { project_id: props.projectId } }))
    emit('changed')
  } catch (err) { error.value = err instanceof Error ? err.message : '保存失败，已保留当前输入' }
  finally { saving.value = false; emit('busy', false) }
}
async function prepareSpeakers(): Promise<void> {
  if (saving.value || loading.value || readFailed.value || pending.value.length) return
  saving.value = true; emit('busy', true); error.value = ''
  try {
    await request(`/api/projects/${encodeURIComponent(props.projectId)}/episodes/${encodeURIComponent(props.episode.id)}/speaker-reviews/prepare`, { method: 'POST' })
    speakerReady.value = true
  } catch (err) { error.value = err instanceof Error ? err.message : '说话人审核准备失败' }
  finally { saving.value = false; emit('busy', false) }
}
function time(us: number): string { return `${(us / 1e6).toFixed(2)} 秒` }
onMounted(() => { void load() })
</script>

<template>
  <section class="dialogue-review-queue" aria-label="对白连续确认">
    <p v-if="error" class="queue-error" role="alert">{{ error }} <button :disabled="saving || loading" @click="load">重新读取</button></p>
    <p v-if="loading" role="status">正在读取本集对白与字幕证据…</p>
    <template v-else-if="active">
      <header class="queue-head"><div><strong>先核对台词，再确认说话人</strong><span aria-live="polite">本次已确认 {{ savedCount }} 项 · 台词还剩 {{ pending.length }} 项</span><small>语音与字幕存在差异；保存后自动展示下一条，同一句对白的关联分镜同步更新。</small></div><button :disabled="saving || readFailed || pending.length < 2" @click="next">暂看下一条 →</button></header>
      <main class="text-review-body" :inert="saving || readFailed">
        <section class="text-preview">
          <video v-if="previewShot?.reference_url" :key="previewShot.id" :src="previewShot.reference_url" controls preload="metadata" />
          <img v-else-if="previewShot?.thumbnail_url" :src="previewShot.thumbnail_url" alt="对白所在分镜" />
          <p v-else>这条对白暂缺可播放片段，请先检查原片。</p>
          <div class="related-shots"><span>关联分镜</span><button v-for="shot in linkedShots" :key="shot.id" :class="{ selected: previewShot?.id === shot.id }" @click="previewShotId = shot.id">镜头 {{ shot.ordinal }}</button></div>
        </section>
        <article :key="active.id" class="text-decision">
          <small>{{ episode.title }} · {{ time(active.start_us) }} → {{ time(active.end_us) }}</small>
          <dl><dt>语音识别</dt><dd>{{ active.asr_text || '未获得可靠对白' }}</dd><dt>字幕识别</dt><dd>{{ active.subtitle_text }}</dd></dl>
          <p v-if="active.requires_full_text">字幕只覆盖部分对白，请听完整台词后填写整句。</p>
          <label>完整台词<textarea v-model="edits[active.id]" maxlength="4000" /></label>
          <div class="decision-actions">
            <button :disabled="saving || !edits[active.id]?.trim()" class="primary" @click="decide('EDIT')">{{ saving ? '保存中…' : '确认台词并继续 →' }}</button>
            <button :disabled="saving || active.requires_full_text" @click="decide('SUBTITLE')">采用字幕并继续</button>
            <button v-if="active.asr_text" :disabled="saving" @click="decide('ASR')">保留语音识别并继续</button>
            <button v-if="!active.utterance_id" :disabled="saving" @click="decide('NOT_DIALOGUE')">这是画面文字，继续</button>
          </div>
        </article>
      </main>
    </template>
    <SourceShotReviewWorkspaceV2 v-else-if="speakerReady && !error" :project-id="projectId" :episodes="[episode]" :focus-episode-id="episode.id" :focus-shot-ordinal="focusShotOrdinal" :focus-dialogue-start-us="focusDialogueStartUs" review-kind="speakers" :source-ready="sourceReady" :blocking-reason="blockingReason" @changed="emit('changed')" @busy="emit('busy', $event)" @people="emit('people')" />
    <section v-else-if="!error" class="prepare-speakers"><strong>本集没有待核对的语音／字幕冲突</strong><p>接下来逐条确认说话人，确认一条后自动展示下一条。</p><button class="primary" :disabled="saving" @click="prepareSpeakers">{{ saving ? '正在准备说话人审核…' : '开始连续确认说话人 →' }}</button><small>人物身份未确定时会显示具体阻塞原因。</small></section>
  </section>
</template>

<style scoped>
.dialogue-review-queue{display:flex;flex-direction:column;flex:1;min-height:0;gap:10px;color:#273b58}.dialogue-review-queue>.source-shot-review-v2{flex:1;min-height:0}.queue-error{margin:0;padding:12px;color:#9d3838;background:#fff1f1;border-radius:8px}.queue-head{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:12px 16px;background:white;border-radius:9px}.queue-head>div{display:grid;gap:5px}.queue-head span{font-size:13px;color:#42638b}.queue-head small,.prepare-speakers small{font-size:12px;color:#738398}.text-review-body{flex:1;min-height:0;display:grid;grid-template-columns:minmax(0,44%) minmax(0,56%);gap:16px;padding:12px;overflow:auto}.text-preview{min-width:0}.text-preview video,.text-preview img{width:100%;max-height:55vh;object-fit:contain;background:#111a27;border-radius:10px}.related-shots{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px;font-size:12px}.text-decision{align-self:start;padding:20px;background:#fff;border-radius:10px;min-width:0}.text-decision small{color:#738398}.text-decision dt{font-size:12px;color:#738398;margin-bottom:7px}.text-decision dd{margin:0 0 20px;font-size:17px;line-height:1.6;overflow-wrap:anywhere}.text-decision p{color:#996a20;font-size:13px}.text-decision label{display:grid;gap:8px;font-size:13px}.text-decision textarea{box-sizing:border-box;width:100%;min-height:120px;padding:12px;border:1px solid #ced8e5;border-radius:7px;font:inherit;resize:vertical}.decision-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}button{border:1px solid #ced8e5;border-radius:7px;padding:10px 13px;background:white;color:#405977;cursor:pointer;font:inherit;font-size:12px}button:disabled{opacity:.5;cursor:not-allowed}.primary,.selected{background:#1769ff;color:white;border-color:#1769ff}.prepare-speakers{display:grid;place-items:center;align-content:center;gap:12px;flex:1;background:#fff;border-radius:10px}.prepare-speakers p{font-size:13px;margin:0}@media(max-width:900px){.text-review-body{grid-template-columns:1fr}.queue-head{flex-wrap:wrap}}
</style>
