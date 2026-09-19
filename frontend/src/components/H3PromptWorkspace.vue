<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import { getH3Prompts, startH3Prompts, type H3PromptsRead } from '@/features/projects/replicaFiveStep'
import type { TaskRead } from '@/features/projects/types'

const TASK_TYPE='replica.h3-prompts'
const route=useRoute()
const projectId=computed(()=>String(route.params.id??''))
const episodeId=computed(()=>String(route.query.episode??''))
const episodeOrder=computed(()=>Number(route.query.ep??1)||1)
const prompts=ref<H3PromptsRead|null>(null)
const tasks=ref<TaskRead[]>([])
const action=ref(false)
const error=ref('')
const message=ref('')
const query=ref('')
const selectedSegmentId=ref('')
let timer:number|undefined

const task=computed(()=>[...tasks.value.filter(item=>item.task_type===TASK_TYPE&&item.episode_id===episodeId.value)].sort((a,b)=>+new Date(b.created_at)-+new Date(a.created_at))[0]??null)
const busy=computed(()=>action.value||task.value?.status==='queued'||task.value?.status==='running')
const hasValidationIssues=computed(()=>prompts.value?.status==='CURRENT'&&Boolean(prompts.value?.validation_issues?.length))
const taskFailure=computed(()=>task.value&&['failed','interrupted'].includes(task.value.status)?task.value.last_error||'生成未完成，请重试。':'')
const generateLabel=computed(()=>action.value?'正在提交…':task.value?.status==='queued'?'排队中…':task.value?.status==='running'?`正在生成 ${task.value.progress_percent}%`:hasValidationIssues.value?'请先修订本土化分镜':prompts.value?.status==='CURRENT'?'重新生成提示词':'生成 H3 提示词')
const allSegments=computed(()=>prompts.value?.content?.segments??[])
const segments=computed(()=>allSegments.value.filter(segment=>!episodeId.value||segment.episode_id===episodeId.value))
const filteredSegments=computed(()=>{
  const keyword=query.value.trim().toLocaleLowerCase()
  return segments.value.filter(segment=>!keyword||[String(segment.segment_number),segment.review_prompt_zh??'',segment.generation_prompt,...segment.dialogue_refs.flatMap(line=>[line.final_target_dialogue,line.target_dialogue_zh??''])].some(value=>value.toLocaleLowerCase().includes(keyword)))
})
const selectedSegment=computed(()=>filteredSegments.value.find(segment=>segment.generation_segment_id===selectedSegmentId.value)??filteredSegments.value[0]??null)

async function refresh(silent=false){const project=projectId.value;const episode=episodeId.value;if(!episode)return;try{const [result,items]=await Promise.all([getH3Prompts(project,episode),listProjectTasks(project)]);if(project===projectId.value&&episode===episodeId.value){prompts.value=result;tasks.value=items}}catch(exc){if(!silent&&episode===episodeId.value)error.value=exc instanceof Error?exc.message:'读取 H3 提示词失败'}}
async function generate(){if(busy.value)return;if(hasValidationIssues.value){error.value='当前正式 H3 分段仍有上游对白或参考图问题。请先按标红提示修订对应本土化分镜或资产，确认后再重新生成。';return}if(!episodeId.value){error.value='请先选择剧集';return}const episode=episodeId.value;const order=episodeOrder.value;action.value=true;error.value='';message.value='';try{await startH3Prompts(projectId.value,episode);if(episode===episodeId.value)message.value=`已开始生成第 ${order} 集的 H3 提示词。`;await refresh()}catch(exc){if(episode===episodeId.value)error.value=exc instanceof Error?exc.message:'启动提示词生成失败'}finally{action.value=false}}
watch([projectId,episodeId],()=>{prompts.value=null;selectedSegmentId.value='';error.value='';message.value='';void refresh()})
function seconds(us:number){return `${(us/1_000_000).toFixed(2)}s`}
function referenceTypeLabel(assetType:string){return ({CHARACTER:'人物',SCENE:'场景',PROP:'道具'} as Record<string,string>)[assetType]??'参考图'}
function referenceRoleLabel(role:string){return ({FACE:'脸部身份',FULL_BODY:'全身形象',FULL_BODY_FRONT:'正面全身',LAYOUT:'场景环境',DETAIL:'细节'} as Record<string,string>)[role]??'视觉参考'}

onMounted(()=>{void refresh();timer=window.setInterval(()=>void refresh(true),3500)})
onBeforeUnmount(()=>{if(timer!==undefined)window.clearInterval(timer)})
</script>

<template>
  <section class="workspace" data-testid="h3-prompt-workspace">
    <header class="stage-header"><div class="stage-title"><h2>H3 提示词</h2><div v-if="prompts?.status==='CURRENT'&&prompts.content" class="header-meta"><span><b>{{ segments.length }}</b> 个镜头段</span><span v-if="prompts.provenance?.generation_sequence">第 {{ prompts.provenance.generation_sequence }} 版</span><span>MiniMax H3</span></div></div><div class="stage-actions"><label v-if="prompts?.status==='CURRENT'&&prompts.content" class="search"><span>⌕</span><input v-model="query" type="search" placeholder="搜索镜头段、对白或画面说明" /></label><button type="button" :disabled="busy||hasValidationIssues" @click="generate">{{ generateLabel }}</button></div></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div v-if="taskFailure&&!action" class="error" role="alert"><strong>第 {{ episodeOrder }} 集重新生成未完成</strong><p>{{ taskFailure }}</p><p v-if="prompts?.content">下方保留的是上次生成结果，本次未产生新版本。</p></div>
    <p v-else-if="message&&busy" class="success" role="status">{{ message }}</p>
    <div v-if="prompts?.status==='CURRENT'&&prompts?.validation_issues?.length" class="validation-banner" role="alert"><strong>{{ prompts.validation_issues.length }} 个镜头段需要先修订</strong><p>问题来自当前正式 H3 所依赖的已定稿对白或参考图。请按标红提示修订对应本土化分镜或资产，确认后再回到本页生成新版。</p></div>
    <div v-if="prompts?.status!=='CURRENT'||!prompts.content" class="empty"><strong>{{ task?.last_error || (prompts?.status==='STALE' ? '上一版 H3 已因上游更新而失效' : '还没有正式 H3 提示词') }}</strong><span>{{ prompts?.status==='STALE' ? '当前本土化分镜或资产已更新，可以直接生成新版 H3 提示词。' : '必须先确认步骤 3 的真实资产图。' }}</span></div>
    <template v-else>
      <div class="prompt-workbench">
        <aside class="segment-browser" aria-label="H3 镜头段列表">
          <div class="browser-heading"><strong>镜头段</strong><span>{{ filteredSegments.length }} / {{ segments.length }}</span></div>
          <button v-for="segment in filteredSegments" :key="segment.generation_segment_id" type="button" class="segment-row" :class="{ active:selectedSegment?.generation_segment_id===segment.generation_segment_id }" @click="selectedSegmentId=segment.generation_segment_id">
            <span class="segment-number">{{ String(segment.segment_number).padStart(2,'0') }}</span>
            <span class="row-copy"><strong>第 {{ segment.episode_order }} 集 · 镜头段 {{ segment.segment_number }}</strong><small>{{ segment.dialogue_refs[0]?.target_dialogue_zh || segment.review_prompt_zh || '无对白镜头' }}</small><em>{{ seconds(segment.duration_us) }} · {{ segment.output_ratio }}</em></span>
            <span class="ref-count">{{ segment.reference_conditions.length }} 图</span>
          </button>
          <div v-if="!filteredSegments.length" class="browser-empty">当前筛选没有匹配镜头段</div>
        </aside>

        <article v-if="selectedSegment" class="prompt-inspector">
          <div v-if="prompts?.validation_issues?.some(issue=>issue.generation_segment_id===selectedSegment?.generation_segment_id)" role="alert" class="error">
            <p v-for="issue in prompts.validation_issues.filter(issue=>issue.generation_segment_id===selectedSegment?.generation_segment_id)" :key="issue.code">{{ issue.message }}</p>
          </div>
          <div class="inspector-head"><div><span>MiniMax H3 音画提示词</span><h3>第 {{ selectedSegment.episode_order }} 集 · 镜头段 {{ selectedSegment.segment_number }}</h3></div><div class="segment-meta"><span>{{ seconds(selectedSegment.duration_us) }}</span><span>{{ selectedSegment.output_ratio }}</span><span>{{ selectedSegment.reference_conditions.length }} 张参考图</span></div></div>
          <section class="reference-section"><div class="section-title"><strong>本段参考图</strong><span>人物、场景和道具将自动带入视频生成</span></div><div v-if="selectedSegment.reference_conditions.length" class="refs"><figure v-for="ref in selectedSegment.reference_conditions" :key="ref.reference_id"><img :src="ref.reference_uri" :alt="`参考图 ${ref.picture_index}`" loading="lazy" /><figcaption><b>参考图 {{ ref.picture_index }}</b><span>{{ referenceTypeLabel(ref.asset_type) }} · {{ referenceRoleLabel(ref.reference_role) }}</span></figcaption></figure></div><p v-else class="no-refs">本段没有可用的参考图</p></section>
          <section class="review-copy"><span>画面与声音说明</span><p>{{ selectedSegment.review_prompt_zh }}</p></section>
          <section v-if="selectedSegment.dialogue_refs.length" class="dialogue-section"><div class="section-title"><strong>本段对白</strong><span>{{ selectedSegment.dialogue_refs.length }} 句</span></div><div class="dialogue-list"><article v-for="line in selectedSegment.dialogue_refs" :key="line.utterance_id"><p lang="auto">{{ line.final_target_dialogue }}</p><small v-if="line.target_dialogue_zh">{{ line.target_dialogue_zh }}</small></article></div></section>
          <details class="execution-details"><summary>查看发送给 H3 的原始提示词</summary><div><pre>{{ selectedSegment.generation_prompt }}</pre><p v-if="selectedSegment.negative_prompt"><b>限制条件：</b>{{ selectedSegment.negative_prompt }}</p></div></details>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:10px;min-width:0}.stage-header{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:48px;padding:0 2px 8px;border-bottom:1px solid #e8eaf0}.stage-title{display:flex;align-items:center;gap:10px;min-width:0}.stage-title h2{margin:0;color:#142647;font-size:20px}.header-meta,.segment-meta{display:flex;gap:6px;flex-wrap:wrap}.header-meta span,.segment-meta span{padding:5px 8px;border:1px solid #e7e4df;border-radius:999px;background:#fff;color:#67625c;font-size:11px}.stage-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;min-width:0}.stage-actions>button{min-height:34px;padding:0 14px;border:0;border-radius:8px;background:linear-gradient(135deg,#704cf4,#5a38e6);color:#fff;font-size:12px;font-weight:750;cursor:pointer;box-shadow:0 5px 12px rgba(91,59,227,.14)}.stage-actions>button:disabled{opacity:.5}.search{display:flex;align-items:center;gap:6px;min-width:300px;padding:0 10px;border:1px solid #dedbd4;border-radius:9px;background:#fff;color:#918b83}.search input{width:100%;height:34px;border:0;outline:0;background:transparent;font-size:12px}.prompt-workbench{display:grid;grid-template-columns:326px minmax(0,1fr);height:clamp(440px,calc(100vh - 390px),620px);min-height:440px;overflow:hidden;border:1px solid #e0e3eb;border-radius:12px;background:#fff;box-shadow:0 5px 18px rgba(31,43,69,.035)}.segment-browser{min-height:0;overflow:auto;border-right:1px solid #e5e7ee;background:#fbfcfe}.browser-heading{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #ebe8e2;background:rgba(250,249,246,.96);font-size:12px;backdrop-filter:blur(8px)}.browser-heading span{color:#918c85}.segment-row{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:10px;width:100%;min-height:72px;padding:8px 11px;border:0;border-bottom:1px solid #eceef3;background:#fff;color:#33435f;text-align:left;cursor:pointer}.segment-row:hover{background:#f7f8fc}.segment-row.active{background:#f2efff;box-shadow:inset 3px 0 #674cf0}.segment-number{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:#ebe9e4;color:#69645e;font-size:11px;font-weight:850}.active .segment-number{background:#6152e8;color:#fff}.row-copy{display:grid;min-width:0;gap:2px}.row-copy strong{font-size:13px}.row-copy small,.row-copy em{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.row-copy small{color:#5d6d87;font-size:12px}.row-copy em{color:#7f899b;font-size:11px;font-style:normal}.ref-count{padding:3px 5px;border-radius:6px;background:#fff;color:#6f69a7;font-size:10px}.browser-empty{padding:28px;color:#89847d;font-size:12px;text-align:center}.prompt-inspector{display:grid;align-content:start;gap:18px;min-width:0;min-height:0;overflow-y:auto;padding:21px 24px 28px}.inspector-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.inspector-head>div:first-child{display:grid;gap:4px}.inspector-head>div:first-child>span{color:#6658de;font-size:11px;font-weight:850;letter-spacing:.05em}.inspector-head h3{margin:0;color:#182541;font-size:20px}.reference-section,.dialogue-section{display:grid;gap:10px;padding-top:16px;border-top:1px solid #eeeae4}.section-title{display:flex;align-items:center;justify-content:space-between;gap:12px}.section-title strong{color:#283756;font-size:13px}.section-title span{color:#7d776f;font-size:11px}.refs{display:grid;grid-template-columns:repeat(auto-fill,144px);justify-content:start;gap:10px}.refs figure{width:144px;min-width:0;margin:0}.refs img{display:block;width:144px;height:100px;object-fit:contain;border:1px solid #ebe8e2;border-radius:9px;background:#f4f3f0}.refs figcaption{display:grid;gap:2px;margin-top:5px}.refs figcaption b{color:#5146c8;font-size:11px}.refs figcaption span{overflow:hidden;color:#6e6963;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.no-refs{margin:0;padding:18px;border-radius:9px;background:#f7f6f2;color:#7d776f;font-size:12px}.review-copy{display:grid;grid-template-columns:104px minmax(0,1fr);gap:13px;padding:15px 16px;border:1px solid #edeaff;border-radius:10px;background:#faf9ff}.review-copy>span{color:#665bb0;font-size:11px;font-weight:850}.review-copy p{margin:0;color:#45413d;font-size:13px;line-height:1.8}.dialogue-list{display:grid;gap:7px}.dialogue-list article{display:grid;grid-template-columns:1.15fr .85fr;gap:14px;padding:11px 12px;border:1px solid #e9e5ef;border-radius:9px;background:#fff}.dialogue-list p{margin:0;color:#2f2c29;font-size:13px;line-height:1.6}.dialogue-list small{color:#6e6963;font-size:12px;line-height:1.6}.execution-details{padding-top:16px;border-top:1px solid #eeeae4;color:#514c46;font-size:12px}.execution-details summary{cursor:pointer;font-weight:800}.execution-details>div{display:grid;gap:9px;margin-top:10px;padding:12px;border-radius:11px;background:#f7f6f3}.execution-details pre{max-height:420px;overflow:auto;margin:0;white-space:pre-wrap;color:#45413c;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;line-height:1.7}.execution-details p{margin:0;line-height:1.6}.empty{display:grid;gap:5px;padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@media(max-width:900px){.stage-header,.inspector-head{align-items:stretch;flex-direction:column}.stage-title{align-items:flex-start;flex-direction:column;gap:5px}.stage-actions{width:100%}.search{min-width:0;flex:1}.prompt-workbench{grid-template-columns:1fr;height:auto;min-height:0;overflow:visible}.segment-browser{display:flex;max-height:none;overflow-x:auto;border-right:0;border-bottom:1px solid #ebe8e2}.browser-heading{display:none}.segment-row{flex:0 0 230px;border-right:1px solid #eeeae4;border-bottom:0}.segment-row.active{box-shadow:inset 0 -3px #6152e8}}@media(max-width:620px){.prompt-inspector{padding:15px}.review-copy,.dialogue-list article{grid-template-columns:1fr}.section-title{align-items:flex-start;flex-direction:column}.refs{grid-template-columns:repeat(2,144px);overflow-x:auto;justify-content:start}}
.validation-banner{padding:12px 14px;border:1px solid #efc9c3;border-radius:10px;background:#fff4f2;color:#953b32}.validation-banner p{margin:5px 0 0;font-size:12px;line-height:1.6}
</style>
