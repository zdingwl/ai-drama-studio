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
const episodeId=computed(()=>String(route.query.episode??''))
const episodeOrder=computed(()=>Number(route.query.ep??1)||1)
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
const selectedClipId=ref('')
let timer:number|undefined

const task=computed(()=>tasks.value.find(item=>item.task_type===TASK_TYPE)??null)
function matchesCurrentInputs(candidate:GenerationCandidate){
  const current=prompts.value
  return current?.status==='CURRENT'&&Boolean(current.artifact_id)&&Boolean(current.content)
    &&candidate.content.target_storyboard_artifact_id===current.content!.target_storyboard_artifact_id
    &&candidate.content.generation_segments_artifact_id===current.artifact_id
    &&candidate.content.target_assets_artifact_id===current.content!.target_assets_artifact_id
}
const pending=computed(()=>candidates.value.find(item=>item.review_status==='NEEDS_REVIEW'&&matchesCurrentInputs(item))??null)
const stalePending=computed(()=>candidates.value.filter(item=>item.review_status==='NEEDS_REVIEW'&&!matchesCurrentInputs(item)))
const busy=computed(()=>action.value||task.value?.status==='queued'||task.value?.status==='running')
const canGenerate=computed(()=>prompts.value?.status==='CURRENT'&&runtime.value?.ready===true&&!busy.value&&!pending.value)
const hasGenerationHistory=computed(()=>candidates.value.length>0||attempts.value.length>0||selection.value?.status==='CURRENT')
const buttonText=computed(()=>task.value?.status==='running'?`MiniMax H3 生成中 ${task.value.progress_percent}%`:task.value?.status==='queued'?'排队中…':task.value?.status==='failed'&&task.value.can_retry?'重试生成':task.value?.status==='interrupted'&&task.value.can_resume?'继续生成':hasGenerationHistory.value?'重新生成视频':'用 MiniMax H3 生成视频')
const allClips=computed(()=>pending.value?.content.clips??[])
const clips=computed(()=>allClips.value.filter(clip=>!episodeId.value||clip.episode_id===episodeId.value))
const visibleClips=computed(()=>clips.value)
const selectedClip=computed(()=>visibleClips.value.find(clip=>clip.generation_segment_id===selectedClipId.value)??visibleClips.value[0]??null)
const selectedPromptSegment=computed(()=>prompts.value?.content?.segments.find(segment=>segment.generation_segment_id===selectedClip.value?.generation_segment_id)??null)
const selectedDurationDelta=computed(()=>selectedClip.value?selectedClip.value.actual_duration_us-selectedClip.value.planned_duration_us:0)

function seconds(us:number){return `${(us/1_000_000).toFixed(2)}s`}
async function refresh(silent=false){try{const [p,r,t,a,c,s]=await Promise.all([getH3Prompts(projectId.value),getVideoGenerationRuntimeReadiness(projectId.value),listProjectTasks(projectId.value),listGenerationAttempts(projectId.value),listGenerationCandidates(projectId.value),getGenerationSelection(projectId.value)]);prompts.value=p;runtime.value=r;tasks.value=t;attempts.value=a;candidates.value=c;selection.value=s}catch(exc){if(!silent)error.value=exc instanceof Error?exc.message:'读取视频生成状态失败'}}
async function generate(){if(!canGenerate.value&&!(task.value?.status==='failed'&&task.value.can_retry)&&!(task.value?.status==='interrupted'&&task.value.can_resume))return;action.value=true;error.value='';message.value='';try{const current=task.value;if(current?.status==='failed'&&current.can_retry)await retryProjectTask(projectId.value,current.id);else if(current?.status==='interrupted'&&current.can_resume)await resumeProjectTask(projectId.value,current.id);else await startVideoGeneration(projectId.value);message.value='MiniMax H3 多参考音画生成任务已启动。';await refresh()}catch(exc){error.value=exc instanceof Error?exc.message:'启动视频生成失败'}finally{action.value=false}}
async function review(candidate:GenerationCandidate,accept:boolean){
  action.value=true;error.value='';message.value=''
  try{
    await reviewGeneration(projectId.value,candidate,accept,reason.value)
    if(accept){
      message.value='正式生成视频已确认。'
    }else{
      message.value='已拒绝当前生成结果，等待重新发起生成。'
    }
    await refresh()
  }catch(exc){error.value=exc instanceof Error?exc.message:'审核生成结果失败'}finally{action.value=false}
}

onMounted(()=>{void refresh();timer=window.setInterval(()=>void refresh(true),4500)})
onBeforeUnmount(()=>{if(timer!==undefined)window.clearInterval(timer)})
</script>

<template>
  <section class="workspace" data-testid="h3-generation-workspace">
    <header class="stage-header"><div class="stage-title"><h2>视频生成</h2><div class="header-meta"><span :class="runtime?.ready?'ready':'blocked'">Runtime {{ runtime?.ready?'就绪':'未就绪' }}</span><span :class="prompts?.status==='CURRENT'?'ready':'blocked'">Prompt {{ prompts?.status==='CURRENT'?'就绪':'未就绪' }}</span><span :class="selection?.status==='CURRENT'?'ready':'neutral'">正式选片 {{ selection?.status==='CURRENT'?'已确认':'未确认' }}</span></div></div><button type="button" :disabled="!canGenerate && !(task?.status==='failed'&&task.can_retry) && !(task?.status==='interrupted'&&task.can_resume)" @click="generate">{{ buttonText }}</button></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
    <p v-if="stalePending.length" class="stale-note">检测到 {{ stalePending.length }} 个旧生成候选：其资产图或 H3 Prompt 已被更新。这些旧候选不会阻塞当前重新生成，也不能被确认成正式选片。</p>
    <p v-if="task?.last_error && task.status==='failed'" class="error-box">{{ task.last_error }}</p>
    <template v-if="pending">
      <p class="guidance">媒体技术 QC PASS 只验证文件可播放、时长/尺寸/codec 等技术条件，不代表人物一致性已经通过。人物身份、场景/道具、动作、镜头、目标语言对白、口型和音画同步当前仍是语义 QC，必须人工逐段审核。</p>
      <div class="generation-toolbar"><div><strong>{{ clips.length }}</strong><span>个本集 Segment 待逐段审核</span></div><span class="episode-label">第 {{ episodeOrder }} 集</span></div>

      <div class="generation-workbench">
        <aside class="clip-browser" aria-label="待审核视频片段">
          <div class="browser-heading"><strong>待审核片段</strong><span>{{ visibleClips.length }} / {{ clips.length }}</span></div>
          <button v-for="clip in visibleClips" :key="clip.generation_segment_id" type="button" class="clip-row" :class="{ active:selectedClip?.generation_segment_id===clip.generation_segment_id }" @click="selectedClipId=clip.generation_segment_id">
            <span class="segment-number">{{ String(clip.segment_number).padStart(2,'0') }}</span>
            <span class="row-copy"><strong>第 {{ clip.episode_order }} 集 · Segment {{ clip.segment_number }}</strong><small>计划 {{ seconds(clip.planned_duration_us) }} · 输出 {{ seconds(clip.actual_duration_us) }}</small><em>{{ clip.width }} × {{ clip.height }}</em></span>
            <span class="qc-pass">PASS</span>
          </button>
        </aside>

        <article v-if="selectedClip" class="video-inspector">
          <div class="inspector-head"><div><span>媒体技术 PASS · 人物待审</span><h3>第 {{ selectedClip.episode_order }} 集 · Segment {{ selectedClip.segment_number }}</h3></div><div class="duration-meta"><span>计划 {{ seconds(selectedClip.planned_duration_us) }}</span><span>H3 原始输出 {{ seconds(selectedClip.actual_duration_us) }}</span><span :class="{ over:selectedDurationDelta>0 }">差值 {{ selectedDurationDelta>=0?'+':'' }}{{ seconds(selectedDurationDelta) }}</span></div></div>
          <div class="player"><video :src="selectedClip.media_url" controls preload="metadata" /></div>

          <section class="human-qc">
            <div class="section-title"><strong>人工语义 QC</strong><span>技术 PASS 不等于以下项目通过</span></div>
            <div class="qc-grid"><div><b>01</b><span>人物身份与资产一致</span></div><div><b>02</b><span>场景、道具与动作正确</span></div><div><b>03</b><span>镜头构图与分镜一致</span></div><div><b>04</b><span>对白、口型、音画同步正确</span></div></div>
          </section>

          <section v-if="selectedPromptSegment" class="generation-basis">
            <div class="section-title"><strong>本段生成依据</strong><span>{{ selectedPromptSegment.reference_conditions.length }} 张参考图</span></div>
            <div v-if="selectedPromptSegment.reference_conditions.length" class="refs"><figure v-for="ref in selectedPromptSegment.reference_conditions" :key="ref.reference_id"><img :src="ref.reference_uri" :alt="`Picture ${ref.picture_index}`" loading="lazy" /><figcaption>&lt;Picture {{ ref.picture_index }}&gt; · {{ ref.asset_type }}</figcaption></figure></div>
            <div class="review-prompt"><span>中文审核说明</span><p>{{ selectedPromptSegment.review_prompt_zh }}</p></div>
            <details><summary>查看本段 MiniMax H3 execution prompt</summary><pre>{{ selectedPromptSegment.generation_prompt }}</pre></details>
          </section>
        </article>
      </div>

      <div class="review-bar"><label class="review"><span>审核备注</span><input v-model="reason" maxlength="800" /></label><div class="actions"><button type="button" :disabled="action||!reason.trim()" @click="review(pending,true)">确认正式视频</button><button type="button" class="secondary" :disabled="action||!reason.trim()" @click="review(pending,false)">拒绝并重新生成</button></div></div>
    </template>
    <div v-else-if="!canGenerate && prompts?.status!=='CURRENT'" class="empty">先完成步骤 4，生成 CURRENT MiniMax H3 模型专属提示词。</div>
    <details v-if="attempts.length" class="attempts"><summary>查看生成尝试与媒体技术 QC（{{ attempts.length }}）</summary><div><p v-for="item in attempts" :key="item.id"><span>{{ item.generation_segment_id }} · #{{ item.attempt_number }}</span><b :class="item.technical_qc_status==='PASS'?'pass':'fail'">媒体 {{ item.technical_qc_status }}</b></p></div></details>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:8px;min-width:0;margin:0}.stage-header{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:46px;padding:0 2px 6px;border-bottom:1px solid #e8eaf0}.stage-title{display:flex;align-items:center;gap:10px;min-width:0}.stage-title h2{margin:0;color:#142647;font-size:20px;letter-spacing:-.015em}.header-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.header-meta span{padding:4px 7px;border:1px solid #e5e2dc;border-radius:999px;background:#fff;color:#6b665f;font-size:10px;font-weight:750}.header-meta .ready{border-color:#d8eadb;background:#f7fbf8;color:#2b6539}.header-meta .blocked{border-color:#ecd4d0;background:#fff8f6;color:#94443b}.header-meta .neutral{color:#777169}.stage-header>button,.review-bar .actions>button{min-height:32px;padding:0 13px;border:0;border-radius:8px;background:linear-gradient(135deg,#704cf4,#5a38e6);color:#fff;font-size:12px;font-weight:750;cursor:pointer;box-shadow:0 5px 12px rgba(91,59,227,.14)}.stage-header>button:disabled,.review-bar .actions>button:disabled{opacity:.5}.actions,.duration-meta{display:flex;gap:7px;flex-wrap:wrap}.guidance{margin:0;padding:11px 13px;border:1px solid #e2def8;border-radius:10px;background:#f8f7ff;color:#56514c;font-size:12px;line-height:1.6}.generation-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:0 2px}.generation-toolbar>div{display:flex;align-items:baseline;gap:5px}.generation-toolbar strong{font-size:17px}.generation-toolbar span{color:#746e67;font-size:11px}.generation-toolbar select{min-height:34px;padding:0 28px 0 10px;border:1px solid #dedbd4;border-radius:9px;background:#fff;color:#55514b;font-size:10px}.generation-workbench{display:grid;grid-template-columns:330px minmax(0,1fr);height:clamp(580px,calc(100vh - 320px),800px);min-height:580px;overflow:hidden;border:1px solid #e0e3eb;border-radius:12px;background:#fff;box-shadow:0 5px 18px rgba(31,43,69,.035)}.clip-browser{min-height:0;overflow:auto;border-right:1px solid #e5e7ee;background:#fbfcfe}.browser-heading{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #ebe8e2;background:rgba(250,249,246,.96);font-size:12px;backdrop-filter:blur(8px)}.browser-heading span{color:#918c85}.clip-row{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:10px;width:100%;min-height:72px;padding:8px 11px;border:0;border-bottom:1px solid #eceef3;background:#fff;color:#33435f;text-align:left;cursor:pointer}.clip-row:hover{background:#f7f8fc}.clip-row.active{background:#eef8f0;box-shadow:inset 3px 0 #4a9f60}.segment-number{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:#ebe9e4;color:#69645e;font-size:11px;font-weight:850}.active .segment-number{background:#3f9856;color:#fff}.row-copy{display:grid;min-width:0;gap:2px}.row-copy strong{font-size:13px}.row-copy small,.row-copy em{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.row-copy small{color:#5d6d87;font-size:11px}.row-copy em{color:#7f899b;font-size:11px;font-style:normal}.qc-pass{padding:3px 5px;border-radius:6px;background:#e6f3e9;color:#2d7140;font-size:9px;font-weight:850}.video-inspector{display:grid;align-content:start;gap:16px;min-width:0;padding:20px 22px 26px}.inspector-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.inspector-head>div:first-child{display:grid;gap:3px}.inspector-head>div:first-child>span{color:#357646;font-size:10px;font-weight:850}.inspector-head h3{margin:0;font-size:19px}.duration-meta span{padding:5px 7px;border-radius:7px;background:#f1f0ec;color:#716b64;font-size:10px}.duration-meta .over{background:#fff4e6;color:#8a5a17}.player{display:grid;place-items:center;min-height:420px;max-height:640px;overflow:hidden;border-radius:14px;background:#0b0b0b}.player video{width:100%;height:min(62vh,640px);object-fit:contain;background:#000}.human-qc,.generation-basis{display:grid;gap:10px;padding-top:14px;border-top:1px solid #eeeae4}.section-title{display:flex;justify-content:space-between;gap:12px}.section-title strong{font-size:13px}.section-title span{color:#7c766f;font-size:10px}.qc-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px}.qc-grid>div{display:flex;align-items:center;gap:8px;min-height:48px;padding:8px 9px;border:1px solid #e7e3dc;border-radius:9px;background:#faf9f6}.qc-grid b{display:grid;place-items:center;flex:0 0 23px;width:23px;height:23px;border-radius:7px;background:#eeeae3;color:#777169;font-size:9px}.qc-grid span{font-size:11px;line-height:1.4}.refs{display:flex;gap:8px;overflow-x:auto}.refs figure{flex:0 0 112px;margin:0}.refs img{width:112px;height:84px;object-fit:contain;border:1px solid #e9e5df;border-radius:8px;background:#f1f0ed}.refs figcaption{overflow:hidden;margin-top:3px;color:#6f6962;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.review-prompt{display:grid;grid-template-columns:82px minmax(0,1fr);gap:12px;padding:12px;border-radius:10px;background:#f8f7ff}.review-prompt>span{color:#655bb0;font-size:10px;font-weight:850}.review-prompt p{margin:0;color:#46423e;font-size:12px;line-height:1.7}.generation-basis details{color:#5d5750;font-size:11px}.generation-basis summary{cursor:pointer;font-weight:800}.generation-basis pre{max-height:300px;overflow:auto;padding:10px;border-radius:9px;background:#f6f5f2;white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px;line-height:1.65}.review-bar{position:sticky;bottom:12px;z-index:8;display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:12px;padding:10px 12px;border:1px solid #ddd8cf;border-radius:14px;background:rgba(255,255,255,.96);box-shadow:0 12px 32px rgba(36,31,26,.12);backdrop-filter:blur(12px)}.review{display:grid;grid-template-columns:auto minmax(0,1fr);gap:9px;align-items:center}.review span{font-size:11px;font-weight:800;color:#706b64}.review input{min-height:36px;padding:0 10px;border:1px solid #d7d3cc;border-radius:8px}.stale-note{margin:0;padding:11px;border-left:3px solid #c18b35;background:#fff8e9;color:#75541f;font-size:12px}.secondary{background:#fff!important;color:#333!important;border:1px solid #d4d0c9!important}.attempts{padding:12px;border:1px solid #e1dfd9;border-radius:12px;background:#fff}.attempts summary{cursor:pointer;font-size:11px;font-weight:700}.attempts p{display:flex;justify-content:space-between;font-size:10px}.pass{color:#2d7140}.fail,.error,.error-box{color:#a33b32}.error-box{padding:10px;background:#fff1ef;border-radius:9px}.success{color:#2d7140}.empty{padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}@media(max-width:1000px){.generation-workbench{grid-template-columns:1fr;height:auto;min-height:0;overflow:visible}.clip-browser{display:flex;max-height:none;overflow-x:auto;border-right:0;border-bottom:1px solid #ebe8e2}.browser-heading{display:none}.clip-row{flex:0 0 230px;border-right:1px solid #eeeae4;border-bottom:0}.clip-row.active{box-shadow:inset 0 -3px #4a9f60}.qc-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:760px){.stage-header,.inspector-head{align-items:stretch;flex-direction:column}.stage-title{align-items:flex-start;flex-direction:column;gap:5px}.review-bar{position:static;grid-template-columns:1fr}.actions{justify-content:flex-end}.player{min-height:320px}}@media(max-width:560px){.video-inspector{padding:15px}.qc-grid{grid-template-columns:1fr}.review-prompt{grid-template-columns:1fr}.review{grid-template-columns:1fr}.actions button{flex:1}}
</style>
