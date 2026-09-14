<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import {
  getLocalizedStoryboard,
  listLocalizedStoryboardCandidates,
  reviewLocalizedStoryboard,
  startLocalizedStoryboard,
  type LocalizedStoryboardCandidate,
  type LocalizedStoryboardContent,
  type LocalizedStoryboardRead,
} from '@/features/projects/replicaFiveStep'
import type { TaskRead, TaskStatus } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const current = ref<LocalizedStoryboardRead | null>(null)
const candidates = ref<LocalizedStoryboardCandidate[]>([])
const localizedTask = ref<TaskRead | null>(null)
const action = ref('')
const error = ref('')
const message = ref('')
const reason = ref('已逐镜检查中文描述、本土语言对白和中文翻译，确认可进入资产生成')
let refreshTimer: number | undefined
let taskTimer: number | undefined

const pending = computed(() => candidates.value.find(item => item.review_status === 'NEEDS_REVIEW') ?? null)
const content = computed<LocalizedStoryboardContent | null>(() => pending.value?.content ?? current.value?.content ?? null)
const taskRunning = computed(() => localizedTask.value?.status === 'queued' || localizedTask.value?.status === 'running')
const taskFailed = computed(() => localizedTask.value?.status === 'failed' || localizedTask.value?.status === 'cancelled' || localizedTask.value?.status === 'interrupted')
const showTaskProgress = computed(() => taskRunning.value || taskFailed.value)
const progressPercent = computed(() => Math.max(0, Math.min(100, localizedTask.value?.progress_percent ?? 0)))

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
    <header><div><p class="eyebrow">步骤 2 / 5</p><h2>本土化改写分镜表</h2><p>画面与镜头说明统一用中文审核；真正说出口的对白使用目标地区语言，并同时保留一份中文翻译供理解。</p></div><button type="button" :disabled="Boolean(action) || Boolean(pending) || taskRunning" @click="generate">{{ generateButtonText }}</button></header>
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
    <label v-if="pending" class="review"><span>审核备注</span><input v-model="reason" maxlength="800" /></label>
    <div v-if="!content" class="empty">先完成步骤 1 的正式原片分镜表，再生成本土化分镜。</div>
    <template v-else>
      <div class="metrics"><span>{{ content.shots.length }} 镜</span><span>目标语言 {{ content.target_language }}</span><span>目标地区 {{ content.target_region }}</span><span>{{ pending ? '待人工确认' : current?.status === 'CURRENT' ? '正式 CURRENT' : '历史结果' }}</span></div>
      <div class="shots">
        <article v-for="shot in content.shots" :key="shot.storyboard_shot_id">
          <div class="shot-head"><strong>第 {{ shot.episode_order }} 集 · Shot {{ shot.shot_number }}</strong><small>{{ seconds(shot.duration_us) }} · {{ shot.output_ratio }}</small></div>
          <div class="fact"><b>中文画面描述</b><p>{{ shot.localized_visual_description_zh }}</p></div>
          <div class="fact"><b>中文镜头说明</b><p>{{ shot.camera_description_zh }}</p></div>
          <div v-for="line in shot.dialogue" :key="line.utterance_id" class="dialogue"><div><b>本土对白</b><p lang="auto">{{ line.target_dialogue }}</p></div><div><b>中文理解</b><p>{{ line.target_dialogue_zh }}</p></div></div>
        </article>
      </div>
      <div v-if="pending" class="actions"><button type="button" :disabled="Boolean(action) || !reason.trim()" @click="review(pending, true)">确认本土化分镜</button><button type="button" class="secondary" :disabled="Boolean(action) || !reason.trim()" @click="review(pending, false)">拒绝重做</button></div>
    </template>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:16px;max-width:1360px;margin:20px auto}.workspace>header{display:flex;justify-content:space-between;gap:16px;padding:22px;border:1px solid #deded8;border-radius:18px;background:#fff}.workspace h2{margin:3px 0}.workspace header p:last-child{color:#706d67}.eyebrow{margin:0;color:#5a4ed8;font-size:11px;font-weight:850}.workspace button{min-height:38px;padding:0 15px;border:0;border-radius:9px;background:#292925;color:#fff;font-weight:750}.workspace button:disabled{opacity:.5}.task-progress{display:grid;gap:10px;padding:15px 17px;border:1px solid #dedbe9;border-radius:14px;background:#fff}.task-progress-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.task-progress-heading>div{display:grid;gap:4px}.task-progress-heading strong{font-size:13px}.task-progress-heading span{color:#706d67;font-size:12px;line-height:1.5}.task-progress-heading>b{font-size:15px;font-variant-numeric:tabular-nums}.progress-track{height:8px;overflow:hidden;border-radius:999px;background:#e7e5ee}.progress-value{height:100%;border-radius:inherit;background:#6558e8;transition:width .25s ease}.progress-value.active{position:relative;overflow:hidden}.progress-value.active::after{position:absolute;inset:0;content:"";background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);animation:progress-shimmer 1.4s linear infinite}.metrics,.actions{display:flex;gap:8px;flex-wrap:wrap}.metrics span{padding:7px 10px;border-radius:999px;background:#efeee9;font-size:12px}.shots{display:grid;gap:10px}.shots article{display:grid;gap:10px;padding:16px;border:1px solid #e2e0da;border-radius:14px;background:#fff}.shot-head{display:flex;justify-content:space-between}.shot-head small{color:#817c74}.fact{display:grid;grid-template-columns:110px 1fr;gap:12px}.fact p,.dialogue p{margin:0;line-height:1.6}.dialogue{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px;border-radius:10px;background:#f8f7ff}.dialogue>div{display:grid;gap:4px}.dialogue b,.fact b{font-size:11px;color:#68635c}.review{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center}.review input{min-height:36px;padding:0 10px;border:1px solid #d7d3cc;border-radius:8px}.secondary{background:#fff!important;color:#333!important;border:1px solid #d4d0c9!important}.empty{padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@keyframes progress-shimmer{from{transform:translateX(-100%)}to{transform:translateX(100%)}}@media(max-width:800px){.workspace>header,.shot-head,.task-progress-heading{flex-direction:column}.dialogue,.fact{grid-template-columns:1fr}}
</style>
