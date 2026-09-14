<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks, resumeProjectTask, retryProjectTask } from '@/features/projects/api'
import {
  getGenerationSelection,
  getVideoGenerationRuntimeReadiness,
  listGenerationAttempts,
  listGenerationCandidates,
  reviewGeneration,
  startVideoGeneration,
  type GenerationAttempt,
  type GenerationCandidate,
  type GenerationSelectionRead,
  type H3RuntimeReadinessRead,
} from '@/features/projects/production'
import { getH3Prompts, type H3PromptsRead } from '@/features/projects/replicaFiveStep'
import type { TaskRead } from '@/features/projects/types'

const TASK_TYPE='P16_MINIMAX_H3_GENERATION'
const route=useRoute()
const projectId=computed(()=>String(route.params.id??''))
const prompts=ref<H3PromptsRead|null>(null)
const runtime=ref<H3RuntimeReadinessRead|null>(null)
const tasks=ref<TaskRead[]>([])
const attempts=ref<GenerationAttempt[]>([])
const candidates=ref<GenerationCandidate[]>([])
const selection=ref<GenerationSelectionRead|null>(null)
const action=ref(false)
const error=ref('')
const message=ref('')
const reason=ref('已逐段播放检查人物身份、场景、动作、口型、对白和音画同步，确认生成结果可用')
let timer:number|undefined

const task=computed(()=>tasks.value.find(item=>item.task_type===TASK_TYPE)??null)
const pending=computed(()=>candidates.value.find(item=>item.review_status==='NEEDS_REVIEW')??null)
const busy=computed(()=>action.value||task.value?.status==='queued'||task.value?.status==='running')
const canGenerate=computed(()=>prompts.value?.status==='CURRENT'&&runtime.value?.ready===true&&!busy.value&&!pending.value)
const buttonText=computed(()=>task.value?.status==='running'?`MiniMax H3 生成中 ${task.value.progress_percent}%`:task.value?.status==='queued'?'排队中…':task.value?.status==='failed'&&task.value.can_retry?'重试生成':task.value?.status==='interrupted'&&task.value.can_resume?'继续生成':selection.value?.status==='CURRENT'?'重新生成视频':'用 MiniMax H3 生成视频')

function seconds(us:number){return `${(us/1_000_000).toFixed(2)}s`}
async function refresh(silent=false){try{const [p,r,t,a,c,s]=await Promise.all([getH3Prompts(projectId.value),getVideoGenerationRuntimeReadiness(projectId.value),listProjectTasks(projectId.value),listGenerationAttempts(projectId.value),listGenerationCandidates(projectId.value),getGenerationSelection(projectId.value)]);prompts.value=p;runtime.value=r;tasks.value=t;attempts.value=a;candidates.value=c;selection.value=s}catch(exc){if(!silent)error.value=exc instanceof Error?exc.message:'读取视频生成状态失败'}}
async function generate(){if(!canGenerate.value&&!(task.value?.status==='failed'&&task.value.can_retry)&&!(task.value?.status==='interrupted'&&task.value.can_resume))return;action.value=true;error.value='';message.value='';try{const current=task.value;if(current?.status==='failed'&&current.can_retry)await retryProjectTask(projectId.value,current.id);else if(current?.status==='interrupted'&&current.can_resume)await resumeProjectTask(projectId.value,current.id);else await startVideoGeneration(projectId.value);message.value='MiniMax H3 多参考音画生成任务已启动。';await refresh()}catch(exc){error.value=exc instanceof Error?exc.message:'启动视频生成失败'}finally{action.value=false}}
async function review(candidate:GenerationCandidate,accept:boolean){action.value=true;error.value='';message.value='';try{await reviewGeneration(projectId.value,candidate,accept,reason.value);message.value=accept?'正式生成视频已确认。':'已拒绝当前生成结果，可以重新生成。';await refresh()}catch(exc){error.value=exc instanceof Error?exc.message:'审核生成结果失败'}finally{action.value=false}}

onMounted(()=>{void refresh();timer=window.setInterval(()=>void refresh(true),4500)})
onBeforeUnmount(()=>{if(timer!==undefined)window.clearInterval(timer)})
</script>

<template>
  <section class="workspace" data-testid="h3-generation-workspace">
    <header><div><p class="eyebrow">步骤 5 / 5</p><h2>用资产图 + 模型专属提示词生成视频</h2><p>MiniMax H3 Runtime 只执行步骤 4 已定稿的 Prompt Skill 输出和 reference_conditions；不在 Runtime 里重新选资产、改对白或重写提示词。</p></div><button type="button" :disabled="!canGenerate && !(task?.status==='failed'&&task.can_retry) && !(task?.status==='interrupted'&&task.can_resume)" @click="generate">{{ buttonText }}</button></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
    <div class="status"><span :class="runtime?.ready?'ready':'blocked'">Runtime：{{ runtime?.ready?'MiniMax H3 Ref2VA 已就绪':runtime?.message||'未就绪' }}</span><span>Prompt：{{ prompts?.status==='CURRENT'?'模型 Skill 输出已就绪':'等待步骤 4' }}</span><span>正式选片：{{ selection?.status==='CURRENT'?'已确认':'未确认' }}</span></div>
    <p v-if="task?.last_error && task.status==='failed'" class="error-box">{{ task.last_error }}</p>
    <template v-if="pending">
      <label class="review"><span>审核备注</span><input v-model="reason" maxlength="800" /></label>
      <p class="guidance">技术 QC PASS 只说明文件可播放。请人工检查人物是否与资产图一致、场景/道具是否正确、动作和镜头是否符合分镜、目标语言对白是否正确、口型和音画是否同步。</p>
      <div class="videos"><article v-for="clip in pending.content.clips" :key="clip.generation_segment_id"><header><strong>第 {{ clip.episode_order }} 集 · Segment {{ clip.segment_number }}</strong><span>技术 QC PASS</span></header><video :src="clip.media_url" controls preload="metadata" /><small>计划 {{ seconds(clip.planned_duration_us) }} · 输出 {{ seconds(clip.actual_duration_us) }}</small></article></div>
      <div class="actions"><button type="button" :disabled="action||!reason.trim()" @click="review(pending,true)">确认正式视频</button><button type="button" class="secondary" :disabled="action||!reason.trim()" @click="review(pending,false)">拒绝并重新生成</button></div>
    </template>
    <div v-else-if="!canGenerate && prompts?.status!=='CURRENT'" class="empty">先完成步骤 4，生成 CURRENT MiniMax H3 模型专属提示词。</div>
    <details v-if="attempts.length" class="attempts"><summary>查看生成尝试与技术 QC（{{ attempts.length }}）</summary><div><p v-for="item in attempts" :key="item.id"><span>{{ item.generation_segment_id }} · #{{ item.attempt_number }}</span><b :class="item.technical_qc_status==='PASS'?'pass':'fail'">{{ item.technical_qc_status }}</b></p></div></details>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:16px;max-width:1360px;margin:20px auto}.workspace>header{display:flex;justify-content:space-between;gap:18px;padding:22px;border:1px solid #deded8;border-radius:18px;background:#fff}.workspace h2{margin:3px 0}.workspace header p:last-child{color:#716d66}.eyebrow{margin:0;color:#5a4ed8;font-size:11px;font-weight:850}.workspace button{min-height:38px;padding:0 15px;border:0;border-radius:9px;background:#292925;color:#fff;font-weight:750}.workspace button:disabled{opacity:.5}.status,.actions{display:flex;gap:8px;flex-wrap:wrap}.status span{padding:7px 10px;border-radius:999px;background:#efeee9;font-size:12px}.status .ready{background:#e9f6ec;color:#28633a}.status .blocked{background:#fff0ed;color:#9d4036}.videos{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.videos article{display:grid;gap:8px;padding:12px;border:1px solid #e1dfd9;border-radius:14px;background:#fff}.videos article header{display:flex;justify-content:space-between}.videos header span{font-size:11px;color:#2d7140;font-weight:800}.videos video{width:100%;max-height:520px;background:#111}.videos small{color:#777}.review{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center}.review input{min-height:36px;padding:0 10px;border:1px solid #d7d3cc;border-radius:8px}.guidance{padding:11px;border-left:3px solid #7569df;background:#f8f7ff;color:#5f5b55}.secondary{background:#fff!important;color:#333!important;border:1px solid #d4d0c9!important}.attempts{padding:12px;border:1px solid #e1dfd9;border-radius:12px;background:#fff}.attempts summary{cursor:pointer;font-weight:700}.attempts p{display:flex;justify-content:space-between}.pass{color:#2d7140}.fail,.error,.error-box{color:#a33b32}.error-box{padding:10px;background:#fff1ef;border-radius:9px}.success{color:#2d7140}.empty{padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}@media(max-width:850px){.workspace>header{flex-direction:column}.videos{grid-template-columns:1fr}}
</style>
