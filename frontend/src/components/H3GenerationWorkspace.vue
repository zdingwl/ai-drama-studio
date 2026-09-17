<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { cancelProjectTask, listProjectTasks, resumeProjectTask, retryProjectTask } from '@/features/projects/api'
import {
  getGeneratedVideo,
  getVideoGenerationRuntimeReadiness,
  listGenerationAttempts,
  regenerateVideoSegment,
  startVideoGeneration,
  type GeneratedVideoRead,
  type GenerationAttempt,
  type H3RuntimeReadinessRead,
  type SelectedClip,
} from '@/features/projects/production'
import { getH3Prompts, type H3PromptsRead } from '@/features/projects/replicaFiveStep'
import type { TaskRead } from '@/features/projects/types'

const FULL_TASK_TYPE = 'P16_MINIMAX_H3_GENERATION'
const SEGMENT_TASK_TYPE = 'P16_MINIMAX_H3_SEGMENT_REGENERATE'
const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const episodeId = computed(() => String(route.query.episode ?? ''))
const episodeOrder = computed(() => Number(route.query.ep ?? 1) || 1)

const prompts = ref<H3PromptsRead | null>(null)
const runtime = ref<H3RuntimeReadinessRead | null>(null)
const generated = ref<GeneratedVideoRead | null>(null)
const tasks = ref<TaskRead[]>([])
const attempts = ref<GenerationAttempt[]>([])
const action = ref(false)
const error = ref('')
const message = ref('')
const selectedClipId = ref('')
let timer: number | undefined

const relevantTasks = computed(() => tasks.value
  .filter(item => item.task_type === FULL_TASK_TYPE || item.task_type === SEGMENT_TASK_TYPE)
  .sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime()))
const activeTask = computed(() => relevantTasks.value.find(item => item.status === 'queued' || item.status === 'running') ?? null)
const fullTask = computed(() => relevantTasks.value.find(item => item.task_type === FULL_TASK_TYPE) ?? null)
const busy = computed(() => action.value || Boolean(activeTask.value))
const currentVideo = computed(() => generated.value?.status === 'CURRENT' && Boolean(generated.value.content))
const needsFullGeneration = computed(() => generated.value?.status !== 'CURRENT')
const canStartFull = computed(() => prompts.value?.status === 'CURRENT' && runtime.value?.ready === true && !busy.value && needsFullGeneration.value)
const canRegenerate = computed(() => currentVideo.value && prompts.value?.status === 'CURRENT' && runtime.value?.ready === true && !busy.value)
const headerButtonText = computed(() => {
  if (activeTask.value?.status === 'running') return `MiniMax H3 生成中 ${activeTask.value.progress_percent}%`
  if (activeTask.value?.status === 'queued') return '排队中…'
  if (fullTask.value?.status === 'failed' && fullTask.value.can_retry) return '重试整批生成'
  if (fullTask.value?.status === 'interrupted' && fullTask.value.can_resume) return '继续整批生成'
  return generated.value?.status === 'STALE' ? '按最新输入重新生成' : '用 MiniMax H3 生成视频'
})

const allClips = computed(() => generated.value?.content?.clips ?? [])
const clips = computed(() => allClips.value.filter(clip => !episodeId.value || clip.episode_id === episodeId.value))
const selectedClip = computed(() => clips.value.find(clip => clip.generation_segment_id === selectedClipId.value) ?? clips.value[0] ?? null)
const selectedPromptSegment = computed(() => prompts.value?.content?.segments.find(segment => segment.generation_segment_id === selectedClip.value?.generation_segment_id) ?? null)
const selectedDurationDelta = computed(() => selectedClip.value ? selectedClip.value.actual_duration_us - selectedClip.value.planned_duration_us : 0)

function seconds(us: number) {
  return `${(us / 1_000_000).toFixed(2)}s`
}

async function refresh(silent = false) {
  try {
    const [p, r, t, a, g] = await Promise.all([
      getH3Prompts(projectId.value),
      getVideoGenerationRuntimeReadiness(projectId.value),
      listProjectTasks(projectId.value),
      listGenerationAttempts(projectId.value),
      getGeneratedVideo(projectId.value),
    ])
    prompts.value = p
    runtime.value = r
    tasks.value = t
    attempts.value = a
    generated.value = g
    if (!clips.value.some(item => item.generation_segment_id === selectedClipId.value)) {
      selectedClipId.value = clips.value[0]?.generation_segment_id ?? ''
    }
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '读取视频生成状态失败'
  }
}

async function generateAll() {
  if (!canStartFull.value && !(fullTask.value?.status === 'failed' && fullTask.value.can_retry) && !(fullTask.value?.status === 'interrupted' && fullTask.value.can_resume)) return
  action.value = true
  error.value = ''
  message.value = ''
  try {
    const current = fullTask.value
    if (current?.status === 'failed' && current.can_retry) {
      await retryProjectTask(projectId.value, current.id)
    } else if (current?.status === 'interrupted' && current.can_resume) {
      await resumeProjectTask(projectId.value, current.id)
    } else {
      await startVideoGeneration(projectId.value)
    }
    message.value = 'MiniMax H3 音画生成任务已进入持久化队列。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '启动视频生成失败'
  } finally {
    action.value = false
  }
}

async function regenerate(clip: SelectedClip) {
  if (!canRegenerate.value) return
  action.value = true
  error.value = ''
  message.value = ''
  try {
    await regenerateVideoSegment(projectId.value, clip.generation_segment_id)
    message.value = `Segment ${clip.segment_number} 已进入重做队列；其他分镜保持当前版本不变。`
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '重做该分镜失败'
  } finally {
    action.value = false
  }
}

async function cancelGeneration() {
  const current = activeTask.value
  if (!current) return
  action.value = true
  error.value = ''
  message.value = ''
  try {
    await cancelProjectTask(projectId.value, current.id)
    message.value = '已请求停止当前 MiniMax H3 任务。正在执行的单次模型调用结束后，系统会在下一个检查点停止。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '停止视频生成失败'
  } finally {
    action.value = false
  }
}

onMounted(() => {
  void refresh()
  timer = window.setInterval(() => void refresh(true), 3500)
})
onBeforeUnmount(() => {
  if (timer !== undefined) window.clearInterval(timer)
})
</script>

<template>
  <section class="workspace" data-testid="h3-generation-workspace">
    <header class="stage-header">
      <div>
        <h2>视频生成</h2>
        <p>生成成功即作为当前版本；不再额外确认或拒绝。不满意哪个分镜，直接重做哪个分镜。</p>
      </div>
      <div class="header-actions">
        <div class="status-row">
          <span :class="runtime?.ready ? 'ready' : 'blocked'">Runtime {{ runtime?.ready ? '就绪' : '未就绪' }}</span>
          <span :class="prompts?.status === 'CURRENT' ? 'ready' : 'blocked'">Prompt {{ prompts?.status === 'CURRENT' ? '就绪' : '未就绪' }}</span>
          <span :class="currentVideo ? 'ready' : 'neutral'">当前视频 {{ currentVideo ? `v${generated?.revision ?? ''}` : '未生成' }}</span>
        </div>
        <div class="buttons">
          <button v-if="needsFullGeneration || fullTask?.status === 'failed' || fullTask?.status === 'interrupted'" type="button" :disabled="!canStartFull && !(fullTask?.status === 'failed' && fullTask.can_retry) && !(fullTask?.status === 'interrupted' && fullTask.can_resume)" @click="generateAll">
            {{ headerButtonText }}
          </button>
          <button v-if="activeTask" type="button" class="cancel" :disabled="action" @click="cancelGeneration">停止生成</button>
        </div>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="message" class="success">{{ message }}</p>
    <p v-if="activeTask" class="task-state">
      {{ activeTask.task_name }} · {{ activeTask.status === 'queued' ? '排队中' : `处理中 ${activeTask.progress_percent}%` }}
    </p>
    <p v-if="activeTask?.last_error" class="error">{{ activeTask.last_error }}</p>

    <div v-if="generated?.status === 'STALE'" class="notice warning">
      上游资产或 H3 Prompt 已更新，旧视频只保留历史回看，不能继续当当前版本。请按最新输入重新生成。
    </div>
    <div v-else-if="currentVideo" class="notice">
      这里展示的是当前采用版本。技术 QC 只保证媒体可播放和基础参数有效；人物、场景、动作、对白或音画同步有问题时，直接点对应分镜的“重做该分镜”。
    </div>

    <template v-if="currentVideo && clips.length">
      <div class="toolbar">
        <div><strong>{{ clips.length }}</strong><span> 个本集 Segment</span></div>
        <span>第 {{ episodeOrder }} 集</span>
      </div>

      <div class="workbench">
        <aside class="clip-browser">
          <div class="browser-heading"><strong>当前分镜</strong><span>{{ clips.length }}</span></div>
          <button
            v-for="clip in clips"
            :key="clip.generation_segment_id"
            type="button"
            class="clip-row"
            :class="{ active: selectedClip?.generation_segment_id === clip.generation_segment_id }"
            @click="selectedClipId = clip.generation_segment_id"
          >
            <span class="segment-number">{{ String(clip.segment_number).padStart(2, '0') }}</span>
            <span class="row-copy">
              <strong>Segment {{ clip.segment_number }}</strong>
              <small>计划 {{ seconds(clip.planned_duration_us) }} · 输出 {{ seconds(clip.actual_duration_us) }}</small>
              <em>{{ clip.width }} × {{ clip.height }}</em>
            </span>
            <span class="current-badge">当前</span>
          </button>
        </aside>

        <article v-if="selectedClip" class="inspector">
          <div class="inspector-head">
            <div>
              <span>当前采用 · Attempt {{ selectedClip.selected_attempt_id.slice(0, 8) }}</span>
              <h3>第 {{ selectedClip.episode_order }} 集 · Segment {{ selectedClip.segment_number }}</h3>
            </div>
            <div class="duration-meta">
              <span>计划 {{ seconds(selectedClip.planned_duration_us) }}</span>
              <span>输出 {{ seconds(selectedClip.actual_duration_us) }}</span>
              <span :class="{ over: selectedDurationDelta > 0 }">差值 {{ selectedDurationDelta >= 0 ? '+' : '' }}{{ seconds(selectedDurationDelta) }}</span>
            </div>
          </div>

          <div class="player"><video :src="selectedClip.media_url" controls preload="metadata" /></div>

          <div class="segment-action">
            <div>
              <strong>这个分镜不满意？</strong>
              <span>只会重新生成当前 Segment，其他已采用分镜不会重跑，也不会覆盖旧历史媒体。</span>
            </div>
            <button type="button" :disabled="!canRegenerate" @click="regenerate(selectedClip)">
              {{ busy ? '任务执行中…' : '重做该分镜' }}
            </button>
          </div>

          <section v-if="selectedPromptSegment" class="generation-basis">
            <div class="section-title"><strong>本段生成依据</strong><span>{{ selectedPromptSegment.reference_conditions.length }} 张参考图</span></div>
            <div v-if="selectedPromptSegment.reference_conditions.length" class="refs">
              <figure v-for="refItem in selectedPromptSegment.reference_conditions" :key="refItem.reference_id">
                <img :src="refItem.reference_uri" :alt="`Picture ${refItem.picture_index}`" loading="lazy" />
                <figcaption>&lt;Picture {{ refItem.picture_index }}&gt; · {{ refItem.asset_type }}</figcaption>
              </figure>
            </div>
            <div class="review-prompt"><span>中文审核说明</span><p>{{ selectedPromptSegment.review_prompt_zh }}</p></div>
            <details><summary>查看 MiniMax H3 execution prompt</summary><pre>{{ selectedPromptSegment.generation_prompt }}</pre></details>
          </section>
        </article>
      </div>
    </template>

    <div v-else-if="prompts?.status !== 'CURRENT'" class="empty">先完成步骤 4，生成 CURRENT MiniMax H3 模型专属提示词。</div>
    <div v-else-if="!currentVideo && !activeTask" class="empty">还没有当前视频。Runtime 就绪后启动一次整批生成即可。</div>

    <details v-if="attempts.length" class="attempts">
      <summary>生成历史与媒体技术 QC（{{ attempts.length }}）</summary>
      <div><p v-for="item in attempts" :key="item.id"><span>{{ item.generation_segment_id }} · Attempt #{{ item.attempt_number }}</span><b :class="item.technical_qc_status === 'PASS' ? 'pass' : 'fail'">{{ item.technical_qc_status }}</b></p></div>
    </details>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:10px;min-width:0}.stage-header{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding:2px 2px 12px;border-bottom:1px solid #e6e9f0}.stage-header h2{margin:0;color:#142647;font-size:22px}.stage-header p{margin:5px 0 0;color:#74706a;font-size:12px;line-height:1.6}.header-actions{display:grid;justify-items:end;gap:8px}.status-row,.buttons,.duration-meta{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.status-row span{padding:4px 8px;border:1px solid #e5e2dc;border-radius:999px;background:#fff;color:#6b665f;font-size:10px;font-weight:750}.status-row .ready{border-color:#d4ead9;background:#f4fbf6;color:#28633a}.status-row .blocked{border-color:#efd0cb;background:#fff7f5;color:#9b4036}.status-row .neutral{color:#777169}.buttons button,.segment-action button{min-height:36px;padding:0 15px;border:0;border-radius:9px;background:#6042e8;color:#fff;font-size:12px;font-weight:800;cursor:pointer}.buttons button:disabled,.segment-action button:disabled{opacity:.5;cursor:not-allowed}.buttons .cancel{border:1px solid #ebc8c4;background:#fff8f7;color:#9c3e35}.error,.success,.task-state,.notice{margin:0;padding:10px 12px;border-radius:9px;font-size:12px;line-height:1.55}.error{border:1px solid #efc8c4;background:#fff7f6;color:#9a3d35}.success{border:1px solid #cfe7d4;background:#f5fbf6;color:#2f6a3d}.task-state{border:1px solid #d9d3f7;background:#f8f7ff;color:#584d8d}.notice{border:1px solid #dce6df;background:#f7fbf8;color:#536158}.notice.warning{border-color:#eadbc0;background:#fffaf0;color:#805f2a}.toolbar{display:flex;align-items:center;justify-content:space-between;padding:0 2px;color:#6e6962;font-size:11px}.toolbar strong{color:#182742;font-size:18px;margin-right:4px}.workbench{display:grid;grid-template-columns:320px minmax(0,1fr);min-height:590px;overflow:hidden;border:1px solid #dfe3eb;border-radius:12px;background:#fff}.clip-browser{overflow:auto;border-right:1px solid #e6e8ee;background:#fbfcfe}.browser-heading{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;padding:12px;border-bottom:1px solid #e8eaf0;background:#fbfcfe}.browser-heading span{color:#89837b;font-size:11px}.clip-row{display:grid;width:100%;grid-template-columns:34px minmax(0,1fr) auto;gap:9px;align-items:center;padding:11px;border:0;border-bottom:1px solid #eceef3;background:transparent;text-align:left;cursor:pointer}.clip-row.active{background:#f3f1ff}.segment-number{display:grid;width:30px;height:30px;place-items:center;border-radius:8px;background:#ece9ff;color:#6042e8;font-size:11px;font-weight:850}.row-copy{display:grid;gap:2px;min-width:0}.row-copy strong{color:#25334d;font-size:12px}.row-copy small,.row-copy em{overflow:hidden;color:#7d776f;font-size:10px;font-style:normal;text-overflow:ellipsis;white-space:nowrap}.current-badge{padding:3px 6px;border-radius:999px;background:#e9f7ed;color:#347342;font-size:9px;font-weight:850}.inspector{display:grid;align-content:start;gap:12px;min-width:0;padding:14px;overflow:auto}.inspector-head{display:flex;justify-content:space-between;gap:12px}.inspector-head>div:first-child span{color:#347342;font-size:10px;font-weight:800}.inspector-head h3{margin:4px 0 0;color:#172842;font-size:18px}.duration-meta span{padding:4px 7px;border-radius:7px;background:#f5f6f8;color:#6e6962;font-size:10px}.duration-meta .over{background:#fff1ee;color:#9b4238}.player{display:grid;place-items:center;min-height:330px;overflow:hidden;border-radius:11px;background:#111722}.player video{display:block;max-width:100%;max-height:520px}.segment-action{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px;border:1px solid #dedaf7;border-radius:10px;background:#faf9ff}.segment-action>div{display:grid;gap:3px}.segment-action strong{color:#2d2850;font-size:12px}.segment-action span{color:#736e78;font-size:11px;line-height:1.5}.generation-basis{display:grid;gap:10px;padding-top:4px}.section-title{display:flex;justify-content:space-between;align-items:center}.section-title strong{color:#23314a;font-size:13px}.section-title span{color:#857f77;font-size:10px}.refs{display:flex;gap:8px;overflow:auto}.refs figure{flex:0 0 112px;margin:0}.refs img{display:block;width:112px;height:112px;object-fit:cover;border:1px solid #e0e2e8;border-radius:8px}.refs figcaption{margin-top:4px;color:#777169;font-size:9px}.review-prompt{padding:10px;border-radius:8px;background:#f7f8fa}.review-prompt span{color:#746e67;font-size:10px;font-weight:800}.review-prompt p{margin:5px 0 0;color:#4f4b46;font-size:11px;line-height:1.6}details summary{cursor:pointer;color:#6358a5;font-size:11px;font-weight:750}pre{overflow:auto;padding:10px;border-radius:8px;background:#111722;color:#e8ecf5;font-size:10px;white-space:pre-wrap}.empty{padding:36px 20px;border:1px dashed #d8dbe3;border-radius:11px;color:#7b756e;text-align:center;font-size:12px}.attempts{padding:8px 10px;border-top:1px solid #e7e9ee}.attempts div{display:grid;gap:5px;margin-top:8px}.attempts p{display:flex;justify-content:space-between;gap:10px;margin:0;padding:6px 8px;border-radius:7px;background:#f7f8fa;font-size:10px}.attempts b.pass{color:#347342}.attempts b.fail{color:#9b4238}@media(max-width:920px){.stage-header{display:grid}.header-actions{justify-items:start}.status-row,.buttons{justify-content:flex-start}.workbench{grid-template-columns:1fr}.clip-browser{max-height:250px;border-right:0;border-bottom:1px solid #e6e8ee}.inspector-head,.segment-action{display:grid}.duration-meta{justify-content:flex-start}}
</style>
