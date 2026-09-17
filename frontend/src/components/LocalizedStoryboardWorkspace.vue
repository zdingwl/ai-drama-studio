<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import {
  getLocalizedStoryboard,
  listLocalizedStoryboardCandidates,
  reviewLocalizedStoryboard,
  startLocalizedStoryboard,
  updateLocalizedStoryboardShot,
  type LocalizedStoryboardCandidate,
  type LocalizedStoryboardContent,
  type LocalizedStoryboardRead,
} from '@/features/projects/replicaFiveStep'
import type { TaskRead, TaskStatus } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const episodeId = computed(() => String(route.query.episode ?? ''))
const episodeOrder = computed(() => Number(route.query.ep ?? 1) || 1)
const current = ref<LocalizedStoryboardRead | null>(null)
const candidates = ref<LocalizedStoryboardCandidate[]>([])
const localizedTask = ref<TaskRead | null>(null)
const action = ref('')
const error = ref('')
const message = ref('')
const reason = ref('已逐镜检查中文描述、本土语言对白和中文翻译，确认可进入资产生成')
const query = ref('')
const selectedShotId = ref('')
const activeEditor = ref('')
const autoSaving = ref(false)
const editDraft = ref({ localized_visual_description_zh: '', camera_description_zh: '', dialogue: [] as Array<{ utterance_id: string; target_dialogue: string; target_dialogue_zh: string }> })
let savedDraftFingerprint = ''
let queuedDraftFingerprint = ''
let saveQueue: Promise<void> = Promise.resolve()
let refreshTimer: number | undefined
let taskTimer: number | undefined

const pending = computed(() => candidates.value.find(item => item.review_status === 'NEEDS_REVIEW') ?? null)
const content = computed<LocalizedStoryboardContent | null>(() => pending.value?.content ?? current.value?.content ?? null)
const taskRunning = computed(() => localizedTask.value?.status === 'queued' || localizedTask.value?.status === 'running')
const taskFailed = computed(() => localizedTask.value?.status === 'failed' || localizedTask.value?.status === 'cancelled' || localizedTask.value?.status === 'interrupted')
const showTaskProgress = computed(() => taskRunning.value || taskFailed.value)
const progressPercent = computed(() => Math.max(0, Math.min(100, localizedTask.value?.progress_percent ?? 0)))
const episodeShots = computed(() => (content.value?.shots ?? []).filter(shot => !episodeId.value || shot.episode_id === episodeId.value))
const filteredShots = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  return episodeShots.value.filter(shot => {
    if (!keyword) return true
    return [String(shot.shot_number), shot.localized_visual_description_zh, shot.camera_description_zh, ...shot.dialogue.flatMap(line => [line.target_dialogue, line.target_dialogue_zh])].some(value => value.toLocaleLowerCase().includes(keyword))
  })
})
const selectedShot = computed(() => (
  filteredShots.value.find(shot => shot.storyboard_shot_id === selectedShotId.value)
  ?? filteredShots.value[0]
  ?? null
))

const taskStatusText: Record<TaskStatus, string> = {
  queued: '排队中',
  running: '正在生成',
  succeeded: '已完成',
  failed: '生成失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

const taskStageText = computed(() => {
  const task = localizedTask.value
  if (!task) return ''
  if (task.status === 'queued') return '任务已进入队列，等待火山引擎 Doubao 开始执行。'
  if (task.status === 'failed') return task.last_error || '本土化分镜生成失败，请检查任务错误后重试。'
  if (task.status === 'cancelled') return '本土化分镜任务已取消。'
  if (task.status === 'interrupted') return task.last_error || '本土化分镜任务已中断。'
  if (task.progress_percent >= 95) return '正在保存候选分镜并完成一致性检查。'
  if (task.progress_percent >= 70) return '火山引擎结果已返回，正在绑定人物、场景、道具并组装正式候选分镜。'
  return '正在调用火山引擎 Doubao，逐镜改写中文画面说明、目标语言对白和中文翻译。'
})

const generateButtonText = computed(() => {
  if (action.value === 'generate') return '启动中…'
  if (localizedTask.value?.status === 'queued') return `本土化排队中 ${progressPercent.value}%`
  if (localizedTask.value?.status === 'running') return `本土化中 ${progressPercent.value}%`
  return current.value?.status === 'CURRENT' ? '重新本土化' : '生成本土化分镜'
})

function seconds(us: number) { return `${(us / 1_000_000).toFixed(2)}s` }

function latestLocalizedTask(rows: TaskRead[]): TaskRead | null {
  const relevant = rows.filter(item => item.task_type === 'replica.localized-storyboard')
  if (!relevant.length) return null
  return [...relevant].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0] ?? null
}

function stopTaskPolling() {
  if (taskTimer !== undefined) {
    window.clearInterval(taskTimer)
    taskTimer = undefined
  }
}

function startTaskPolling() {
  if (taskTimer !== undefined) return
  taskTimer = window.setInterval(() => void refreshTask(true), 1000)
}

async function refresh(silent = false) {
  try {
    const [read, rows] = await Promise.all([getLocalizedStoryboard(projectId.value), listLocalizedStoryboardCandidates(projectId.value)])
    current.value = read
    candidates.value = rows
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '读取本土化分镜失败'
  }
}

async function refreshTask(silent = false) {
  try {
    const rows = await listProjectTasks(projectId.value)
    const tracked = localizedTask.value ? rows.find(item => item.id === localizedTask.value?.id) ?? null : null
    localizedTask.value = tracked ?? latestLocalizedTask(rows)
    if (taskRunning.value) {
      startTaskPolling()
    } else {
      stopTaskPolling()
      if (localizedTask.value?.status === 'succeeded') await refresh(true)
    }
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '读取本土化任务进度失败'
  }
}

async function run(name: string, work: () => Promise<unknown>, success: string) {
  action.value = name; error.value = ''; message.value = ''
  try { await work(); message.value = success; await refresh() }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '操作失败' }
  finally { action.value = '' }
}

async function generate() {
  action.value = 'generate'; error.value = ''; message.value = ''
  try {
    localizedTask.value = await startLocalizedStoryboard(projectId.value)
    message.value = '本土化分镜任务已启动，可在下方查看实时进度。'
    if (taskRunning.value) startTaskPolling()
    await refresh(true)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '本土化分镜任务启动失败'
  } finally {
    action.value = ''
  }
}

function selectShot(shotId: string) {
  selectedShotId.value = shotId
  activeEditor.value = ''
  syncDraft()
}

function draftFingerprint() {
  return JSON.stringify(editDraft.value)
}

function syncDraft() {
  const shot = selectedShot.value
  if (!shot) return
  editDraft.value = {
    localized_visual_description_zh: shot.localized_visual_description_zh,
    camera_description_zh: shot.camera_description_zh,
    dialogue: shot.dialogue.map(line => ({ utterance_id: line.utterance_id, target_dialogue: line.target_dialogue, target_dialogue_zh: line.target_dialogue_zh })),
  }
  savedDraftFingerprint = draftFingerprint()
  queuedDraftFingerprint = savedDraftFingerprint
}

function beginInlineEdit(field: string) {
  activeEditor.value = field
  error.value = ''
  message.value = ''
}

function queueAutoSave() {
  activeEditor.value = ''
  const fingerprint = draftFingerprint()
  if (fingerprint === savedDraftFingerprint || fingerprint === queuedDraftFingerprint) return
  if (!editDraft.value.localized_visual_description_zh.trim() || !editDraft.value.camera_description_zh.trim() || editDraft.value.dialogue.some(line => !line.target_dialogue.trim() || !line.target_dialogue_zh.trim())) {
    error.value = '画面描述、镜头说明和已有对白都不能为空。'
    return
  }
  const shotId = selectedShot.value?.storyboard_shot_id
  const snapshot = JSON.parse(fingerprint) as typeof editDraft.value
  if (!shotId) return
  queuedDraftFingerprint = fingerprint
  saveQueue = saveQueue.then(() => persistAutoSave(shotId, snapshot, fingerprint))
}

async function persistAutoSave(shotId: string, snapshot: typeof editDraft.value, fingerprint: string) {
  const sourceSnapshotId = content.value?.source_snapshot_artifact_id
  if (!sourceSnapshotId) return
  autoSaving.value = true; error.value = ''; message.value = ''
  try {
    const saved = await updateLocalizedStoryboardShot(projectId.value, {
      candidate_id: pending.value?.id ?? null,
      expected_current_artifact_id: current.value?.artifact_id ?? null,
      expected_source_snapshot_artifact_id: sourceSnapshotId,
      storyboard_shot_id: shotId,
      localized_visual_description_zh: snapshot.localized_visual_description_zh.trim(),
      camera_description_zh: snapshot.camera_description_zh.trim(),
      dialogue: snapshot.dialogue.map(line => ({ utterance_id: line.utterance_id, target_dialogue: line.target_dialogue.trim(), target_dialogue_zh: line.target_dialogue_zh.trim() })),
    })
    candidates.value = [saved, ...candidates.value.filter(item => item.id !== saved.id)]
    savedDraftFingerprint = fingerprint
    message.value = '已自动保存为待确认版本。'
  } catch (exc) {
    queuedDraftFingerprint = savedDraftFingerprint
    error.value = exc instanceof Error ? exc.message : '保存本镜修改失败'
  } finally {
    autoSaving.value = false
  }
}

watch(selectedShot, () => {
  if (!activeEditor.value && !autoSaving.value) syncDraft()
}, { immediate: true })

const review = (candidate: LocalizedStoryboardCandidate, accept: boolean) => run('review', () => reviewLocalizedStoryboard(projectId.value, candidate, accept, reason.value), accept ? '本土化分镜已正式确认。' : '已拒绝当前本土化分镜。')

onMounted(() => {
  void Promise.all([refresh(), refreshTask()])
  refreshTimer = window.setInterval(() => void refresh(true), 4000)
})
onBeforeUnmount(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
  stopTaskPolling()
})
</script>

<template>
  <section class="workspace" data-testid="localized-storyboard-workspace">
    <header class="stage-header"><div class="stage-title"><h2>本土化分镜</h2><div v-if="content" class="header-meta"><span><b>{{ episodeShots.length }}</b> 镜</span><span>{{ content.target_language }} · {{ content.target_region }}</span><span :class="{ attention: pending }">{{ pending ? '待人工确认' : current?.status === 'CURRENT' ? '已正式确认' : '历史结果' }}</span></div></div><div class="stage-actions"><label v-if="content" class="search"><span>⌕</span><input v-model="query" type="search" placeholder="搜索镜号、画面或对白" /></label><button type="button" :disabled="Boolean(action) || Boolean(pending) || taskRunning" @click="generate">{{ generateButtonText }}</button></div></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
    <div v-if="showTaskProgress && localizedTask" class="task-progress" data-testid="localized-storyboard-progress" role="status" aria-live="polite">
      <div class="task-progress-heading">
        <div><strong>{{ taskStatusText[localizedTask.status] }}</strong><span>{{ taskStageText }}</span></div>
        <b>{{ progressPercent }}%</b>
      </div>
      <div class="progress-track" role="progressbar" aria-label="本土化分镜生成进度" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="progressPercent">
        <div class="progress-value" :class="{ active: taskRunning }" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </div>
    <div v-if="!content" class="empty">先完成步骤 1 的正式原片分镜表，再生成本土化分镜。</div>
    <template v-else>
      <div class="review-shell">
        <aside class="shot-browser" aria-label="本土化镜头列表">
          <div class="browser-heading"><strong>本集镜头</strong><span>{{ filteredShots.length }} / {{ episodeShots.length }}</span></div>
          <button v-for="shot in filteredShots" :key="shot.storyboard_shot_id" type="button" class="shot-row" :class="{ active: selectedShot?.storyboard_shot_id === shot.storyboard_shot_id }" @click="selectShot(shot.storyboard_shot_id)">
            <span class="shot-index">{{ String(shot.shot_number).padStart(2, '0') }}</span>
            <span class="row-copy"><strong>第 {{ shot.episode_order }} 集 · Shot {{ shot.shot_number }}</strong><small>{{ shot.dialogue[0]?.target_dialogue_zh || shot.localized_visual_description_zh }}</small><em>{{ seconds(shot.duration_us) }} · {{ shot.output_ratio }}</em></span>
            <span v-if="shot.dialogue.length" class="line-count">{{ shot.dialogue.length }} 句</span>
          </button>
          <div v-if="!filteredShots.length" class="browser-empty">当前筛选没有匹配镜头</div>
        </aside>

        <article v-if="selectedShot" class="shot-inspector">
          <div class="shot-head"><div><span>本土化镜头</span><strong>第 {{ selectedShot.episode_order }} 集 · Shot {{ selectedShot.shot_number }}</strong></div><div class="shot-head-actions"><small>{{ seconds(selectedShot.duration_us) }} · {{ selectedShot.output_ratio }}</small><em :class="{ saving: autoSaving }">{{ autoSaving ? '正在自动保存…' : '点击内容即可修改' }}</em></div></div>
          <div class="fact-grid">
            <section class="fact"><b>中文画面描述</b><textarea v-model="editDraft.localized_visual_description_zh" aria-label="中文画面描述" rows="5" maxlength="8000" @focus="beginInlineEdit('visual')" @blur="queueAutoSave" /></section>
            <section class="fact camera"><b>中文镜头说明</b><textarea v-model="editDraft.camera_description_zh" aria-label="中文镜头说明" rows="5" maxlength="4000" @focus="beginInlineEdit('camera')" @blur="queueAutoSave" /></section>
          </div>
          <section class="dialogue-section">
            <div class="section-title"><strong>对白审核</strong><span>{{ selectedShot.dialogue.length }} 句</span></div>
            <div v-if="selectedShot.dialogue.length" class="dialogue-list">
              <article v-for="(line, index) in selectedShot.dialogue" :key="line.utterance_id" class="dialogue"><div><b>本土对白</b><textarea v-model="editDraft.dialogue[index].target_dialogue" :aria-label="`本土对白 ${index + 1}`" rows="3" maxlength="2000" lang="auto" @focus="beginInlineEdit(`dialogue-${index}`)" @blur="queueAutoSave" /></div><div><b>中文理解</b><textarea v-model="editDraft.dialogue[index].target_dialogue_zh" :aria-label="`中文理解 ${index + 1}`" rows="3" maxlength="2000" @focus="beginInlineEdit(`translation-${index}`)" @blur="queueAutoSave" /></div></article>
            </div>
            <p v-else class="no-dialogue">本镜头无对白</p>
          </section>
          <details class="source-reference"><summary>查看原片画面描述</summary><p>{{ selectedShot.source_visual_description }}</p></details>
        </article>
      </div>

      <div v-if="pending" class="review-bar"><label class="review"><span>审核备注</span><input v-model="reason" maxlength="800" /></label><div class="actions"><button type="button" :disabled="Boolean(action) || !reason.trim()" @click="review(pending, true)">确认本土化分镜</button><button type="button" class="secondary" :disabled="Boolean(action) || !reason.trim()" @click="review(pending, false)">拒绝重做</button></div></div>
    </template>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:8px;min-width:0;margin:0}.stage-header{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:46px;padding:0 2px 6px;border-bottom:1px solid #e8eaf0}.stage-title{display:flex;align-items:center;gap:10px;min-width:0}.stage-title h2{margin:0;color:#142647;font-size:20px;letter-spacing:-.015em}.header-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.header-meta span{padding:4px 7px;border:1px solid #e5e2dc;border-radius:999px;background:#fff;color:#6b665f;font-size:10px}.header-meta .attention{border-color:#ead9b0;background:#fff9ec;color:#805d18}.stage-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;min-width:0}.stage-actions>button,.review-bar .actions>button{min-height:32px;padding:0 13px;border:0;border-radius:8px;background:linear-gradient(135deg,#704cf4,#5a38e6);color:#fff;font-size:12px;font-weight:750;cursor:pointer;box-shadow:0 5px 12px rgba(91,59,227,.14)}.stage-actions>button:disabled,.review-bar .actions>button:disabled{opacity:.5}.task-progress{display:grid;gap:10px;padding:15px 17px;border:1px solid #dedbe9;border-radius:14px;background:#fff}.task-progress-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.task-progress-heading>div{display:grid;gap:4px}.task-progress-heading strong{font-size:13px}.task-progress-heading span{color:#706d67;font-size:12px;line-height:1.5}.task-progress-heading>b{font-size:15px;font-variant-numeric:tabular-nums}.progress-track{height:8px;overflow:hidden;border-radius:999px;background:#e7e5ee}.progress-value{height:100%;border-radius:inherit;background:#6558e8;transition:width .25s ease}.progress-value.active{position:relative;overflow:hidden}.progress-value.active::after{position:absolute;inset:0;content:"";background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);animation:progress-shimmer 1.4s linear infinite}.actions{display:flex;gap:5px;flex-wrap:wrap}.search{display:flex;align-items:center;gap:6px;min-width:260px;padding:0 9px;border:1px solid #dedbd4;border-radius:8px;background:#fff;color:#918b83}.search input{width:100%;height:30px;border:0;outline:0;background:transparent;font-size:12px}.review-shell{display:grid;grid-template-columns:310px minmax(0,1fr);height:clamp(540px,calc(100dvh - 230px),860px);min-height:540px;overflow:hidden;border:1px solid #e0e3eb;border-radius:12px;background:#fff;box-shadow:0 5px 18px rgba(31,43,69,.035)}.shot-browser{min-height:0;overflow:auto;border-right:1px solid #e5e7ee;background:#fbfcfe}.browser-heading{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #ebe8e2;background:rgba(250,249,246,.96);font-size:12px;backdrop-filter:blur(8px)}.browser-heading span{color:#918c85}.shot-row{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:10px;width:100%;min-height:72px;padding:8px 11px;border:0;border-bottom:1px solid #eceef3;background:#fff;color:#33435f;text-align:left;cursor:pointer}.shot-row:hover{background:#f7f8fc}.shot-row.active{background:#f2efff;box-shadow:inset 3px 0 #674cf0}.shot-index{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:#ebe9e4;color:#69645e;font-size:11px;font-weight:850}.active .shot-index{background:#6152e8;color:#fff}.row-copy{display:grid;min-width:0;gap:2px}.row-copy strong{font-size:13px}.row-copy small,.row-copy em{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.row-copy small{color:#5d6d87;font-size:12px}.row-copy em{color:#7f899b;font-size:11px;font-style:normal}.line-count{padding:3px 5px;border-radius:6px;background:#fff;color:#6f69a7;font-size:10px}.browser-empty{padding:28px;color:#89847d;font-size:12px;text-align:center}.shot-inspector{display:grid;align-content:start;gap:12px;min-width:0;overflow:auto;padding:14px 16px 18px}.shot-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding-bottom:12px;border-bottom:1px solid #eeeae4}.shot-head>div{display:grid;gap:3px}.shot-head span{color:#7469da;font-size:10px;font-weight:850;letter-spacing:.08em}.shot-head strong{font-size:18px}.shot-head small{padding:5px 7px;border-radius:7px;background:#f2f1ed;color:#77716a;font-size:11px}.fact-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.fact{display:grid;align-content:start;gap:7px;min-height:132px;padding:13px 14px;border:1px solid #e8e5df;border-radius:10px;background:#fbfaf8}.fact.camera{background:#f8f7ff}.fact b,.dialogue b{color:#675e9f;font-size:11px}.fact p,.dialogue p{margin:0;color:#45413d;font-size:14px;line-height:1.75}.dialogue-section{display:grid;gap:10px}.section-title{display:flex;justify-content:space-between}.section-title strong{font-size:14px}.section-title span{color:#7d776f;font-size:11px}.dialogue-list{display:grid;gap:8px}.dialogue{display:grid;grid-template-columns:1fr 1fr;gap:0;overflow:hidden;border:1px solid #e6e2ee;border-radius:11px;background:#fff}.dialogue>div{display:grid;align-content:start;gap:5px;padding:11px 12px}.dialogue>div+div{border-left:1px solid #e6e2ee;background:#f8f7ff}.no-dialogue{margin:0;padding:18px;border-radius:10px;background:#f7f6f2;color:#7d7871;font-size:13px}.source-reference{padding-top:10px;border-top:1px solid #eeeae4;color:#625e58;font-size:12px}.source-reference summary{cursor:pointer;font-weight:750}.source-reference p{line-height:1.65}.review-bar{position:sticky;bottom:12px;z-index:8;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;padding:10px 12px;border:1px solid #ddd8cf;border-radius:14px;background:rgba(255,255,255,.96);box-shadow:0 12px 32px rgba(36,31,26,.12);backdrop-filter:blur(12px)}.review{display:grid;grid-template-columns:auto minmax(0,1fr);gap:9px;align-items:center}.review span{font-size:11px;font-weight:800;color:#706b64}.review input{min-height:36px;padding:0 10px;border:1px solid #d7d3cc;border-radius:8px}.secondary{background:#fff!important;color:#333!important;border:1px solid #d4d0c9!important}.empty{padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@keyframes progress-shimmer{from{transform:translateX(-100%)}to{transform:translateX(100%)}}@media(max-width:900px){.stage-header,.task-progress-heading{align-items:stretch;flex-direction:column}.stage-title{align-items:flex-start;flex-direction:column;gap:5px}.stage-actions{width:100%}.search{min-width:0;flex:1}.review-shell{grid-template-columns:1fr;height:auto;min-height:0;overflow:visible}.shot-browser{display:flex;max-height:none;overflow-x:auto;border-right:0;border-bottom:1px solid #ebe8e2}.browser-heading{display:none}.shot-row{flex:0 0 230px;border-right:1px solid #eeeae4;border-bottom:0}.shot-row.active{box-shadow:inset 0 -3px #6152e8}.fact-grid{grid-template-columns:1fr}.review-bar{position:static;grid-template-columns:1fr}.actions{justify-content:flex-end}}@media(max-width:620px){.shot-inspector{padding:15px}.shot-head{flex-direction:column}.dialogue{grid-template-columns:1fr}.dialogue>div+div{border-top:1px solid #e6e2ee;border-left:0}.review{grid-template-columns:1fr}.actions button{flex:1}}
.shot-head-actions{display:flex;align-items:center;gap:8px}.shot-head-actions em{color:#847d96;font-size:10px;font-style:normal}.shot-head-actions em.saving{color:#6552dc}.fact textarea,.dialogue textarea{box-sizing:border-box;width:100%;resize:vertical;padding:7px 8px;border:1px solid transparent;border-radius:8px;background:transparent;color:#45413d;font:inherit;line-height:1.75;outline:none;transition:border-color .16s ease,background .16s ease,box-shadow .16s ease}.fact textarea:hover,.dialogue textarea:hover{border-color:#ddd7fa;background:rgba(255,255,255,.72)}.fact textarea:focus,.dialogue textarea:focus{border-color:#7057ec;background:#fff;box-shadow:0 0 0 3px rgba(112,87,236,.12)}
</style>
