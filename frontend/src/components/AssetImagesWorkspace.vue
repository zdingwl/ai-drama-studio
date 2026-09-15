<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import {
  getAssetImages,
  listAssetImageCandidates,
  reviewAssetImages,
  startAssetImages,
  type AssetImageCandidate,
  type AssetImagesContent,
  type AssetImagesRead,
} from '@/features/projects/replicaFiveStep'
import type { TaskRead, TaskStatus } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const current = ref<AssetImagesRead | null>(null)
const candidates = ref<AssetImageCandidate[]>([])
const assetTask = ref<TaskRead | null>(null)
const action = ref('')
const error = ref('')
const message = ref('')
const reason = ref('已检查人物、场景和道具资产图，确认身份与本土化分镜一致')
let refreshTimer: number | undefined
let taskTimer: number | undefined

const pending = computed(() => candidates.value.find(item => item.review_status === 'NEEDS_REVIEW') ?? null)
const content = computed<AssetImagesContent | null>(() => pending.value?.content ?? current.value?.content ?? null)
const taskRunning = computed(() => assetTask.value?.status === 'queued' || assetTask.value?.status === 'running')
const taskFailed = computed(() => assetTask.value?.status === 'failed' || assetTask.value?.status === 'cancelled' || assetTask.value?.status === 'interrupted')
const taskSucceededWithoutResult = computed(() => assetTask.value?.status === 'succeeded' && !content.value)
const showTaskProgress = computed(() => taskRunning.value || taskFailed.value || taskSucceededWithoutResult.value)
const progressPercent = computed(() => Math.max(0, Math.min(100, assetTask.value?.progress_percent ?? 0)))

const taskStatusText: Record<TaskStatus, string> = {
  queued: '排队中',
  running: '正在生成',
  succeeded: '生成完成',
  failed: '生成失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

const taskStageText = computed(() => {
  const task = assetTask.value
  if (!task) return ''
  if (task.status === 'queued') return '任务已进入队列，等待资产图 Worker 开始执行。'
  if (task.status === 'failed') return task.last_error || '资产图生成失败，请检查 Prompt Skill、ComfyUI、Z-Image Turbo 模型和任务日志后重试。'
  if (task.status === 'cancelled') return '资产图生成任务已取消。'
  if (task.status === 'interrupted') return task.last_error || '资产图生成任务已中断，可以重新发起。'
  if (task.status === 'succeeded') return '资产图已经生成完成，正在加载待审核候选。'
  if (task.progress_percent >= 95) return '人物、场景和道具参考图已生成，正在保存候选并完成一致性检查。'
  if (task.progress_percent >= 30) return '模型专属提示词已经编译，正在通过本机 ComfyUI / Z-Image Turbo 逐项生成真实资产图。'
  if (task.progress_percent > 0) return '已从本土化分镜提取资产，正在用 Z-Image Turbo Professional Skill 分析分镜证据并生成资产提示词。'
  return '正在从本土化分镜提取实际使用的人物、场景和道具。'
})

const generateButtonText = computed(() => {
  if (action.value === 'generate') return '启动中…'
  if (assetTask.value?.status === 'queued') return `资产排队中 ${progressPercent.value}%`
  if (assetTask.value?.status === 'running') return `资产生成中 ${progressPercent.value}%`
  if (taskFailed.value) return '重试生成资产图'
  return current.value?.status === 'CURRENT' ? '重新生成资产图' : '提取并生成资产图'
})

function latestAssetTask(rows: TaskRead[]): TaskRead | null {
  const relevant = rows.filter(item => item.task_type === 'replica.asset-images')
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
    const [read, rows] = await Promise.all([getAssetImages(projectId.value), listAssetImageCandidates(projectId.value)])
    current.value = read
    candidates.value = rows
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '读取资产图失败'
  }
}

async function refreshTask(silent = false) {
  try {
    const rows = await listProjectTasks(projectId.value)
    const tracked = assetTask.value ? rows.find(item => item.id === assetTask.value?.id) ?? null : null
    assetTask.value = tracked ?? latestAssetTask(rows)
    if (taskRunning.value) {
      startTaskPolling()
    } else {
      stopTaskPolling()
      if (assetTask.value?.status === 'succeeded') await refresh(true)
    }
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '读取资产图任务进度失败'
  }
}

async function run(name: string, work: () => Promise<unknown>, success: string) {
  action.value = name
  error.value = ''
  message.value = ''
  try {
    await work()
    message.value = success
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '操作失败'
  } finally {
    action.value = ''
  }
}

async function generate() {
  action.value = 'generate'
  error.value = ''
  message.value = ''
  try {
    assetTask.value = await startAssetImages(projectId.value)
    message.value = '资产提取 → Prompt Skill 分析分镜 → Z-Image Turbo 出图任务已启动，可在下方查看实时进度；如果失败会直接显示失败原因。'
    if (taskRunning.value) startTaskPolling()
    await refresh(true)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '资产图任务启动失败'
  } finally {
    action.value = ''
  }
}

const review = (candidate: AssetImageCandidate, accept: boolean) => run('review', () => reviewAssetImages(projectId.value, candidate, accept, reason.value), accept ? '资产图已正式确认。' : '已拒绝当前资产图候选。')
const label = (type: string) => type === 'CHARACTER' ? '人物' : type === 'SCENE' ? '场景' : '道具'

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
  <section class="workspace" data-testid="asset-images-workspace">
    <header><div><p class="eyebrow">步骤 3 / 5</p><h2>提取资产 → Skill 生成提示词 → 生成资产图</h2><p>只为本土化分镜实际使用的人物、场景、道具生成正式参考图。人物固定为“正面全身 + 侧面全身 + 背面全身 + 面部特写”；整段人物小传不会直接送进图片模型。</p></div><button type="button" :disabled="Boolean(action) || Boolean(pending) || taskRunning" @click="generate">{{ generateButtonText }}</button></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
    <div v-if="showTaskProgress && assetTask" class="task-progress" :class="{ failed: taskFailed }" data-testid="asset-images-progress" role="status" aria-live="polite">
      <div class="task-progress-heading">
        <div><strong>{{ taskStatusText[assetTask.status] }}</strong><span>{{ taskStageText }}</span></div>
        <b>{{ progressPercent }}%</b>
      </div>
      <div class="progress-track" role="progressbar" aria-label="资产图生成进度" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="progressPercent">
        <div class="progress-value" :class="{ active: taskRunning }" :style="{ width: `${progressPercent}%` }"></div>
      </div>
      <p v-if="taskFailed" class="task-error">{{ assetTask.last_error || '任务没有返回更详细的错误信息，请查看后端日志后重试。' }}</p>
    </div>
    <label v-if="pending" class="review"><span>审核备注</span><input v-model="reason" maxlength="800" /></label>
    <div v-if="!content" class="empty">先确认步骤 2 的本土化分镜，再提取人物、场景和道具。</div>
    <template v-else>
      <div class="metrics"><span>{{ content.assets.length }} 个正式资产</span><span>{{ content.visual_style }}</span><span>{{ pending?'待人工确认':current?.status==='CURRENT'?'正式 CURRENT':'历史结果' }}</span></div>
      <div class="grid"><article v-for="asset in content.assets" :key="asset.target_asset_id"><div class="image"><img v-if="asset.reference_media[0]" :src="asset.reference_media[0].uri" :alt="asset.display_name" loading="lazy" /></div><div class="copy"><small>{{ label(asset.asset_type) }}</small><h3>{{ asset.display_name }}</h3><p>{{ asset.review_description_zh }}</p><p v-if="asset.prompt_review_zh" class="prompt-review">{{ asset.prompt_review_zh }}</p><details><summary>查看模型专属资产提示词</summary><p v-if="asset.prompt_skill_id" class="prompt-meta">{{ asset.prompt_skill_id }}@{{ asset.prompt_skill_version }} · {{ asset.image_model_id }}</p><p>{{ asset.image_prompt }}</p><p v-if="asset.negative_prompt"><strong>避免：</strong>{{ asset.negative_prompt }}</p></details></div></article></div>
      <div v-if="pending" class="actions"><button type="button" :disabled="Boolean(action)||!reason.trim()" @click="review(pending,true)">确认资产图</button><button type="button" class="secondary" :disabled="Boolean(action)||!reason.trim()" @click="review(pending,false)">拒绝重做</button></div>
    </template>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:16px;max-width:1360px;margin:20px auto}.workspace>header{display:flex;justify-content:space-between;gap:18px;padding:22px;border:1px solid #deded8;border-radius:18px;background:#fff}.workspace h2{margin:3px 0}.workspace header p:last-child{color:#716d66}.eyebrow{margin:0;color:#5a4ed8;font-size:11px;font-weight:850}.workspace button{min-height:38px;padding:0 15px;border:0;border-radius:9px;background:#292925;color:#fff;font-weight:750}.workspace button:disabled{opacity:.5}.task-progress{display:grid;gap:10px;padding:15px 17px;border:1px solid #dedbe9;border-radius:14px;background:#fff}.task-progress.failed{border-color:#e5b8b3;background:#fff8f7}.task-progress-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.task-progress-heading>div{display:grid;gap:4px}.task-progress-heading strong{font-size:13px}.task-progress-heading span{color:#706d67;font-size:12px;line-height:1.5}.task-progress-heading>b{font-size:15px;font-variant-numeric:tabular-nums}.progress-track{height:8px;overflow:hidden;border-radius:999px;background:#e7e5ee}.progress-value{height:100%;border-radius:inherit;background:#6558e8;transition:width .25s ease}.progress-value.active{position:relative;overflow:hidden}.progress-value.active::after{position:absolute;inset:0;content:"";background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);animation:progress-shimmer 1.4s linear infinite}.task-error{margin:0;padding:9px 10px;border-radius:9px;background:#fff0ee;color:#9a3129;font-size:12px;line-height:1.55}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.grid article{overflow:hidden;border:1px solid #e1dfd9;border-radius:14px;background:#fff}.image{aspect-ratio:1;background:#eee}.image img{width:100%;height:100%;object-fit:contain}.copy{padding:13px}.copy small{color:#6558df;font-weight:800}.copy h3{margin:3px 0}.copy p{color:#65615b;line-height:1.55}.copy details{font-size:12px}.prompt-review{padding:9px 10px;border-radius:9px;background:#f5f3fb;color:#4d4960!important;font-size:12px}.prompt-meta{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#706b80!important}.metrics,.actions{display:flex;gap:8px;flex-wrap:wrap}.metrics span{padding:7px 10px;border-radius:999px;background:#efeee9;font-size:12px}.review{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center}.review input{min-height:36px;padding:0 10px;border:1px solid #d7d3cc;border-radius:8px}.secondary{background:#fff!important;color:#333!important;border:1px solid #d4d0c9!important}.empty{padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@keyframes progress-shimmer{from{transform:translateX(-100%)}to{transform:translateX(100%)}}@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.workspace>header,.task-progress-heading{flex-direction:column}}@media(max-width:600px){.grid{grid-template-columns:1fr}}
</style>
