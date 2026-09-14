<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getProject, listProjectTasks, resumeProjectTask, retryProjectTask } from '@/features/projects/api'
import type { TaskRead } from '@/features/projects/types'
import {
  getFinalOutput,
  getGenerationSegments,
  getGenerationSelection,
  getTargetStoryboard,
  getVideoGenerationRuntimeReadiness,
  listGenerationAttempts,
  listGenerationCandidates,
  listPostCandidates,
  listStoryboardCandidates,
  reviewGeneration,
  reviewPost,
  reviewStoryboard,
  startPostProduction,
  startStoryboard,
  startVideoGeneration,
  type FinalOutputRead,
  type GenerationAttempt,
  type GenerationCandidate,
  type GenerationSegmentsRead,
  type GenerationSelectionRead,
  type H3RuntimeReadinessRead,
  type PostCandidate,
  type StoryboardCandidate,
  type TargetStoryboardRead,
} from '@/features/projects/production'

const props = withDefaults(defineProps<{ workspace?: 'all' | 'storyboard' | 'generation' | 'final' }>(), { workspace: 'all' })

const P16_TASK_TYPE = 'P16_MINIMAX_H3_GENERATION'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const replicaProject = ref<boolean | null>(null)
const loading = ref(false)
const action = ref('')
const error = ref('')
const message = ref('')
const reason = ref('已逐项检查当前候选，确认可以进入下一生产阶段')
const storyboard = ref<TargetStoryboardRead | null>(null)
const segments = ref<GenerationSegmentsRead | null>(null)
const storyboardCandidates = ref<StoryboardCandidate[]>([])
const attempts = ref<GenerationAttempt[]>([])
const generationCandidates = ref<GenerationCandidate[]>([])
const selection = ref<GenerationSelectionRead | null>(null)
const postCandidates = ref<PostCandidate[]>([])
const finalOutput = ref<FinalOutputRead | null>(null)
const projectTasks = ref<TaskRead[]>([])
const runtimeReadiness = ref<H3RuntimeReadinessRead | null>(null)
let pollTimer: number | undefined

const pendingStoryboard = computed(() => storyboardCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const pendingGeneration = computed(() => generationCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const latestGenerationCandidate = computed(() => generationCandidates.value[0] ?? null)
const generationTask = computed(() => projectTasks.value.find((item) => item.task_type === P16_TASK_TYPE) ?? null)
const legacyRuntimeFailure = computed(() => Boolean(
  generationTask.value?.status === 'failed'
  && runtimeReadiness.value?.ready === true
  && runtimeReadiness.value.runtime_mode === 'LOCAL_COMFYUI'
  && generationTask.value.last_error?.includes('P16_LOCAL_RUNTIME_CREATE_FAILED'),
))
const generationTaskActive = computed(() => generationTask.value?.status === 'queued' || generationTask.value?.status === 'running')
const generationTaskFinalizing = computed(() => Boolean(
  generationTask.value?.status === 'succeeded'
  && selection.value?.status !== 'CURRENT'
  && !pendingGeneration.value
  && latestGenerationCandidate.value?.review_status !== 'REJECTED',
))
const generationBusy = computed(() => generationTaskActive.value || generationTaskFinalizing.value)
const generationStateLabel = computed(() => {
  if (selection.value?.status === 'CURRENT') return '已确认'
  if (pendingGeneration.value) return '待确认'
  if (latestGenerationCandidate.value?.review_status === 'REJECTED') return '已拒绝'
  if (generationTask.value?.status === 'queued') return '排队中'
  if (generationTask.value?.status === 'running') return `生成中 ${generationTask.value.progress_percent}%`
  if (legacyRuntimeFailure.value) return '可重试'
  if (generationTask.value?.status === 'failed') return '生成失败'
  if (generationTask.value?.status === 'interrupted') return '已中断'
  if (generationTask.value?.status === 'cancelled') return '已取消'
  if (generationTaskFinalizing.value) return '整理结果中'
  return '未生成'
})
const generationTaskNote = computed(() => {
  if (runtimeReadiness.value && !runtimeReadiness.value.ready) return runtimeReadiness.value.message
  const task = generationTask.value
  if (!task || pendingGeneration.value || selection.value?.status === 'CURRENT') return ''
  if (task.status === 'queued') return '音画生成任务已提交，正在等待本地 H3 Runtime 执行。'
  if (task.status === 'running') return `本地 H3 正在生成，当前进度 ${task.progress_percent}%（任务尝试 ${task.attempt}/${task.max_attempts}）。`
  if (legacyRuntimeFailure.value) return '当前 ComfyUI 已就绪。这里显示的是切换运行时之前的失败记录；点击“重试生成”会基于当前正式分镜与 Generation Segments 创建新的 ComfyUI 生成任务。'
  if (task.status === 'failed') return task.last_error || '音画生成失败。请确认本地 H3 Runtime 已启动后重试。'
  if (task.status === 'interrupted') return '音画生成任务被中断，可以继续执行。'
  if (task.status === 'cancelled') return '音画生成任务已取消。'
  if (generationTaskFinalizing.value) return '视频生成已完成，正在整理待确认候选。'
  return ''
})
const generationButtonText = computed(() => {
  if (action.value === 'p16-start') return '处理中…'
  if (runtimeReadiness.value && !runtimeReadiness.value.ready) return '等待生成服务'
  const task = generationTask.value
  if (task?.status === 'queued') return '排队中…'
  if (task?.status === 'running') return `生成中 ${task.progress_percent}%`
  if (task?.status === 'failed' && task.can_retry) return '重试生成'
  if (task?.status === 'interrupted' && task.can_resume) return '继续生成'
  if (generationTaskFinalizing.value) return '整理结果中…'
  if (pendingGeneration.value) return '请先确认当前候选'
  return selection.value?.status === 'CURRENT' || latestGenerationCandidate.value?.review_status === 'REJECTED' ? '重新生成本集' : '生成本集'
})
const generationButtonDisabled = computed(() => Boolean(
  action.value
  || segments.value?.status !== 'CURRENT'
  || generationBusy.value
  || pendingGeneration.value
  || runtimeReadiness.value?.ready !== true
  || (generationTask.value?.status === 'failed' && !generationTask.value.can_retry)
  || (generationTask.value?.status === 'interrupted' && !generationTask.value.can_resume),
))
const pendingPost = computed(() => postCandidates.value.find((item) => item.review_status === 'NEEDS_REVIEW') ?? null)
const recentAttempts = computed(() => attempts.value.slice().sort((a, b) => b.attempt_number - a.attempt_number).slice(0, 24))
const workspaceTitle = computed(() => props.workspace === 'storyboard' ? '分镜' : props.workspace === 'generation' ? '音画生成' : props.workspace === 'final' ? '最终成片' : '分镜 → 视频生成 → 最终成片')
const workspaceSubtitle = computed(() => props.workspace === 'storyboard'
  ? '确定每个镜头如何生成，并在开始生成前确认镜头计划。'
  : props.workspace === 'generation'
    ? '默认按集音画联合生成，只把需要处理的异常镜头交给你。'
    : props.workspace === 'final'
      ? '自动组合已确认镜头、声音与字幕，检查问题后导出成片。'
      : '系统自动完成制作，你只需要在需要判断画面和声音质量时确认。')

function seconds(us: number): string {
  return `${(us / 1_000_000).toFixed(2)}s`
}

async function refresh(silent = false) {
  if (!projectId.value || loading.value) return
  if (!silent) loading.value = true
  if (!silent) error.value = ''
  try {
    if (replicaProject.value === null) {
      const project = await getProject(projectId.value)
      replicaProject.value = project.project_type === 'REPLICA'
    }
    if (!replicaProject.value) return
    const [storyboardRead, segmentRead, sbCandidates, attemptRows, generationRows, selectionRead, postRows, finalRead, taskRows, runtimeRead] = await Promise.all([
      getTargetStoryboard(projectId.value),
      getGenerationSegments(projectId.value),
      listStoryboardCandidates(projectId.value),
      listGenerationAttempts(projectId.value),
      listGenerationCandidates(projectId.value),
      getGenerationSelection(projectId.value),
      listPostCandidates(projectId.value),
      getFinalOutput(projectId.value),
      listProjectTasks(projectId.value),
      getVideoGenerationRuntimeReadiness(projectId.value),
    ])
    storyboard.value = storyboardRead
    segments.value = segmentRead
    storyboardCandidates.value = sbCandidates
    attempts.value = attemptRows
    generationCandidates.value = generationRows
    selection.value = selectionRead
    postCandidates.value = postRows
    finalOutput.value = finalRead
    projectTasks.value = [...taskRows]
    runtimeReadiness.value = runtimeRead
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '加载生产工作区失败'
  } finally {
    if (!silent) loading.value = false
  }
}

async function run(name: string, callback: () => Promise<unknown>, success: string) {
  action.value = name
  error.value = ''
  message.value = ''
  try {
    await callback()
    message.value = success
    await refresh(true)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '操作失败'
  } finally {
    action.value = ''
  }
}

const startP15 = () => run('p15-start', () => startStoryboard(projectId.value), '分镜编译任务已启动。完成后会出现待确认分镜。')
const reviewP15 = (candidate: StoryboardCandidate, accept: boolean) => run('p15-review', () => reviewStoryboard(projectId.value, candidate, accept, reason.value), accept ? '分镜与生成分段已确认。' : '已拒绝当前分镜候选。')
function rememberTask(task: TaskRead) {
  projectTasks.value = [task, ...projectTasks.value.filter((item) => item.id !== task.id)]
}

async function startP16() {
  if (!projectId.value || generationButtonDisabled.value) return
  action.value = 'p16-start'
  error.value = ''
  message.value = ''
  try {
    const current = generationTask.value
    let task: TaskRead
    if (current?.status === 'failed' && current.can_retry) {
      task = await retryProjectTask(projectId.value, current.id)
    } else if (current?.status === 'interrupted' && current.can_resume) {
      task = await resumeProjectTask(projectId.value, current.id)
    } else {
      task = await startVideoGeneration(projectId.value)
    }
    rememberTask(task)
    if (task.status === 'failed') {
      error.value = task.last_error || '音画生成任务启动后立即失败。'
    }
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '启动音画生成失败'
  } finally {
    action.value = ''
  }
}
const reviewP16 = (candidate: GenerationCandidate, accept: boolean) => run('p16-review', () => reviewGeneration(projectId.value, candidate, accept, reason.value), accept ? '正式视频选片已确认。' : '已拒绝当前视频候选。')
const startP17 = () => run('p17-start', () => startPostProduction(projectId.value), '成片任务已启动。需要口型的段会进入 Lip Sync，随后完成正式音频、字幕和剪辑。')
const reviewP17 = (candidate: PostCandidate, accept: boolean) => run('p17-review', () => reviewPost(projectId.value, candidate, accept, reason.value), accept ? '最终成片已确认并发布。' : '已拒绝当前成片候选。')

onMounted(() => {
  void refresh()
  pollTimer = window.setInterval(() => { void refresh(true) }, 6000)
})

onBeforeUnmount(() => {
  if (pollTimer !== undefined) window.clearInterval(pollTimer)
})
</script>

<template>
  <section v-if="replicaProject" class="production-workspace">
    <header class="workspace-head">
      <div>
        <p class="eyebrow">{{ props.workspace === 'generation' ? '生成' : props.workspace === 'final' ? '成片' : '分镜' }}</p>
        <h2>{{ workspaceTitle }}</h2>
        <p>{{ workspaceSubtitle }}</p>
      </div>
      <button type="button" :disabled="loading" @click="refresh()">{{ loading ? '刷新中…' : '刷新' }}</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="success">{{ message }}</p>
    <label class="review-reason">
      <span>本轮备注</span>
      <input v-model="reason" maxlength="800" />
    </label>

    <article v-if="props.workspace === 'all' || props.workspace === 'storyboard'" class="stage-card">
      <div class="stage-head">
        <div><span class="stage-index">1</span><div><h3>复刻分镜</h3><p>按照原片的镜头顺序和节奏，自动组合已确认的人物、场景、道具、对白与配音。</p></div></div>
        <span class="state">{{ storyboard?.status === 'CURRENT' && segments?.status === 'CURRENT' ? '已确认' : pendingStoryboard ? '待确认' : '未生成' }}</span>
      </div>
      <div class="actions">
        <button type="button" :disabled="Boolean(action)" @click="startP15">{{ action === 'p15-start' ? '启动中…' : storyboard?.status === 'CURRENT' ? '重新编译候选' : '生成分镜候选' }}</button>
      </div>
      <template v-if="pendingStoryboard">
        <div class="metrics">
          <span><strong>{{ pendingStoryboard.content.storyboard.shots.length }}</strong> 个镜头</span>
          <span><strong>{{ pendingStoryboard.content.generation_segments.segments.length }}</strong> 个生成分段</span>
          <span><strong>{{ pendingStoryboard.content.generation_segments.segments.filter((item) => item.requires_lip_sync).length }}</strong> 个需口型段</span>
        </div>
        <div class="shot-preview">
          <article v-for="shot in pendingStoryboard.content.storyboard.shots.slice(0, 12)" :key="shot.storyboard_shot_id">
            <strong>第 {{ shot.episode_order }} 集 · Shot {{ shot.shot_number }}</strong>
            <small>{{ seconds(shot.duration_us) }}</small>
            <p>{{ shot.target_visual_description }}</p>
          </article>
        </div>
        <div class="review-actions">
          <button type="button" :disabled="Boolean(action) || !reason.trim()" @click="reviewP15(pendingStoryboard, true)">确认分镜</button>
          <button type="button" :disabled="Boolean(action) || !reason.trim()" class="secondary" @click="reviewP15(pendingStoryboard, false)">拒绝</button>
        </div>
      </template>
      <p v-else-if="storyboard?.status === 'CURRENT'" class="current-note">当前正式分镜包含 {{ storyboard.content?.shots.length ?? 0 }} 个镜头，生成计划包含 {{ segments?.content?.segments.length ?? 0 }} 个分段。</p>
    </article>

    <article v-if="props.workspace === 'all' || props.workspace === 'generation'" class="stage-card">
      <div class="stage-head">
        <div><span class="stage-index">2</span><div><h3>视频生成与选片</h3><p>系统逐段生成视频并自动排除损坏结果，你只需播放检查并确认最合适的版本。</p></div></div>
        <span class="state">{{ generationStateLabel }}</span>
      </div>
      <div class="actions">
        <button type="button" :disabled="generationButtonDisabled" @click="startP16">{{ generationButtonText }}</button>
      </div>
      <p v-if="generationTaskNote" class="generation-task-note" :class="{ failed: (generationTask?.status === 'failed' && !legacyRuntimeFailure) || runtimeReadiness?.ready === false }">{{ generationTaskNote }}</p>
      <template v-if="pendingGeneration">
        <p class="guidance">请逐段播放检查人物、场景、动作、构图、连续性和明显生成崩坏。系统的 PASS 只代表媒体技术可用，不代表语义质量通过。</p>
        <div class="video-grid">
          <article v-for="clip in pendingGeneration.content.clips" :key="clip.generation_segment_id">
            <div class="clip-title"><strong>第 {{ clip.episode_order }} 集 · Segment {{ clip.segment_number }}</strong><span>技术 QC PASS</span></div>
            <video :src="clip.media_url" controls preload="metadata" />
            <small>计划 {{ seconds(clip.planned_duration_us) }} · H3 输出 {{ seconds(clip.actual_duration_us) }}<template v-if="clip.requires_lip_sync"> · 后续需口型</template></small>
          </article>
        </div>
        <div class="review-actions">
          <button type="button" :disabled="Boolean(action) || !reason.trim()" @click="reviewP16(pendingGeneration, true)">确认正式选片</button>
          <button type="button" :disabled="Boolean(action) || !reason.trim()" class="secondary" @click="reviewP16(pendingGeneration, false)">拒绝并重新生成</button>
        </div>
      </template>
      <details v-if="recentAttempts.length" class="attempts">
        <summary>查看最近生成尝试与技术质检（{{ recentAttempts.length }}）</summary>
        <div class="attempt-list">
          <div v-for="attempt in recentAttempts" :key="attempt.id" :class="attempt.technical_qc_status === 'PASS' ? 'pass' : 'fail'">
            <span>{{ attempt.generation_segment_id }} · #{{ attempt.attempt_number }}</span>
            <strong>{{ attempt.technical_qc_status }}</strong>
            <small v-if="attempt.technical_qc_issues.length">{{ attempt.technical_qc_issues.join('；') }}</small>
          </div>
        </div>
      </details>
    </article>

    <article v-if="props.workspace === 'all' || props.workspace === 'final'" class="stage-card">
      <div class="stage-head">
        <div><span class="stage-index">3</span><div><h3>口型、字幕与最终成片</h3><p>系统自动完成口型、剪辑、配音混合和字幕，生成可以完整播放的成片候选。</p></div></div>
        <span class="state">{{ finalOutput?.status === 'CURRENT' ? '已发布' : pendingPost ? '待确认' : '未生成' }}</span>
      </div>
      <div class="actions">
        <button type="button" :disabled="Boolean(action) || selection?.status !== 'CURRENT'" @click="startP17">{{ action === 'p17-start' ? '启动中…' : finalOutput?.status === 'CURRENT' ? '重新制作候选' : '制作最终成片' }}</button>
      </div>
      <template v-if="pendingPost">
        <div class="final-list">
          <article v-for="episode in pendingPost.content.episodes" :key="episode.episode_id">
            <div><strong>第 {{ episode.episode_order }} 集成片候选</strong><small>{{ seconds(episode.duration_us) }} · {{ episode.segment_count }} 段 · {{ episode.lip_synced_segment_count }} 段已口型同步</small></div>
            <video :src="episode.video_url" controls preload="metadata" />
            <a :href="episode.subtitle_url" target="_blank" rel="noreferrer">查看 SRT 字幕</a>
          </article>
        </div>
        <div class="review-actions">
          <button type="button" :disabled="Boolean(action) || !reason.trim()" @click="reviewP17(pendingPost, true)">确认最终成片</button>
          <button type="button" :disabled="Boolean(action) || !reason.trim()" class="secondary" @click="reviewP17(pendingPost, false)">拒绝</button>
        </div>
      </template>
      <div v-else-if="finalOutput?.status === 'CURRENT'" class="final-list">
        <article v-for="episode in finalOutput.content?.episodes ?? []" :key="episode.episode_id">
          <div><strong>第 {{ episode.episode_order }} 集 · 正式成片</strong><small>{{ seconds(episode.duration_us) }}</small></div>
          <video :src="episode.video_url" controls preload="metadata" />
          <a :href="episode.subtitle_url" target="_blank" rel="noreferrer">查看 SRT 字幕</a>
        </article>
      </div>
    </article>
  </section>
</template>

<style scoped>
.production-workspace{display:grid;gap:16px;max-width:1330px;margin:24px auto;padding:0 4px}.workspace-head,.stage-head,.stage-head>div,.actions,.review-actions,.clip-title,.final-list article>div{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.workspace-head{padding:22px;border:1px solid #deded8;border-radius:18px;background:#fff}.workspace-head h2{margin:3px 0;font-size:24px}.workspace-head p:last-child,.stage-head p,.guidance,.current-note{margin:5px 0 0;color:#70706a;line-height:1.6}.eyebrow{margin:0;color:#6b5ce7;font-size:11px;font-weight:800;letter-spacing:.1em}.stage-card{padding:20px;border:1px solid #deded8;border-radius:16px;background:#fff}.stage-head>div{justify-content:flex-start}.stage-head h3{margin:0}.stage-index{display:grid;place-items:center;flex:0 0 32px;width:32px;height:32px;border-radius:9px;background:#eeecff;color:#5d4fe0;font-weight:800}.state{white-space:nowrap;padding:4px 9px;border-radius:999px;background:#f1f1ed;font-size:12px;font-weight:700}.actions,.review-actions{justify-content:flex-start;margin-top:14px}.actions button,.review-actions button,.workspace-head button{min-height:36px;padding:0 14px;border:1px solid #292925;border-radius:9px;background:#292925;color:#fff;font-weight:700;cursor:pointer}.secondary{border-color:#d4d4ce!important;background:#fff!important;color:#444!important}button:disabled{cursor:not-allowed;opacity:.5}.review-reason{display:grid;grid-template-columns:auto minmax(240px,1fr);gap:10px;align-items:center;padding:12px 16px;border:1px solid #e1e1dc;border-radius:12px;background:#fafaf8}.review-reason span{font-size:12px;font-weight:700}.review-reason input{min-height:34px;padding:0 10px;border:1px solid #d4d4ce;border-radius:8px}.metrics{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.metrics span{padding:8px 10px;border-radius:9px;background:#f5f5f1;font-size:12px}.shot-preview{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:12px}.shot-preview article{padding:11px;border:1px solid #e5e5df;border-radius:10px;background:#fafaf8}.shot-preview strong,.shot-preview small{display:block}.shot-preview small{margin-top:3px;color:#888}.shot-preview p{display:-webkit-box;overflow:hidden;margin:8px 0 0;color:#666;font-size:12px;line-height:1.5;-webkit-box-orient:vertical;-webkit-line-clamp:4}.video-grid,.final-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:14px}.video-grid article,.final-list article{display:grid;gap:8px;padding:12px;border:1px solid #e2e2dc;border-radius:12px;background:#fafaf8}.video-grid video,.final-list video{width:100%;max-height:520px;background:#111}.clip-title span{color:#2f6f3e;font-size:11px;font-weight:800}.video-grid small,.final-list small{color:#777}.final-list article>div{align-items:baseline}.final-list a{justify-self:start;color:#5749d8;font-size:12px}.attempts{margin-top:14px;padding-top:12px;border-top:1px solid #ecece7}.attempts summary{cursor:pointer;font-size:12px;font-weight:700}.attempt-list{display:grid;gap:6px;margin-top:9px}.attempt-list>div{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:4px;padding:8px 10px;border-radius:8px;background:#f6f6f3;font-size:11px}.attempt-list small{grid-column:1/-1}.attempt-list .pass strong{color:#2f6f3e}.attempt-list .fail strong,.error{color:#a33b32}.success{color:#2f6f3e}.generation-task-note{margin:12px 0 0;padding:10px 12px;border-radius:9px;background:#f5f5f1;color:#555;line-height:1.6}.generation-task-note.failed{background:#fff2f0;color:#a33b32}.guidance{padding:10px 12px;border-left:3px solid #8c83e8;background:#f8f7ff}@media(max-width:900px){.shot-preview,.video-grid,.final-list{grid-template-columns:1fr}.workspace-head,.stage-head{flex-direction:column}.review-reason{grid-template-columns:1fr}}
</style>
