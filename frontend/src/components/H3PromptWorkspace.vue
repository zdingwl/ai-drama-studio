<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
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

const task=computed(()=>tasks.value.find(item=>item.task_type===TASK_TYPE)??null)
const busy=computed(()=>action.value||task.value?.status==='queued'||task.value?.status==='running')
const allSegments=computed(()=>prompts.value?.content?.segments??[])
const segments=computed(()=>allSegments.value.filter(segment=>!episodeId.value||segment.episode_id===episodeId.value))
const filteredSegments=computed(()=>{
  const keyword=query.value.trim().toLocaleLowerCase()
  return segments.value.filter(segment=>!keyword||[String(segment.segment_number),segment.review_prompt_zh??'',segment.generation_prompt,...segment.dialogue_refs.flatMap(line=>[line.final_target_dialogue,line.target_dialogue_zh??''])].some(value=>value.toLocaleLowerCase().includes(keyword)))
})
const selectedSegment=computed(()=>filteredSegments.value.find(segment=>segment.generation_segment_id===selectedSegmentId.value)??filteredSegments.value[0]??null)

async function refresh(silent=false){try{[prompts.value,tasks.value]=await Promise.all([getH3Prompts(projectId.value),listProjectTasks(projectId.value)])}catch(exc){if(!silent)error.value=exc instanceof Error?exc.message:'读取 H3 提示词失败'}}
async function generate(){if(busy.value)return;action.value=true;error.value='';message.value='';try{await startH3Prompts(projectId.value);message.value='已启动模型专属 Prompt Skill。';await refresh()}catch(exc){error.value=exc instanceof Error?exc.message:'启动提示词生成失败'}finally{action.value=false}}
function seconds(us:number){return `${(us/1_000_000).toFixed(2)}s`}

onMounted(()=>{void refresh();timer=window.setInterval(()=>void refresh(true),3500)})
onBeforeUnmount(()=>{if(timer!==undefined)window.clearInterval(timer)})
</script>

<template>
  <section class="workspace" data-testid="h3-prompt-workspace">
    <header class="stage-header"><div class="stage-title"><h2>H3 提示词</h2><div v-if="prompts?.status==='CURRENT'&&prompts.content" class="header-meta"><span><b>{{ segments.length }}</b> 个生成段</span><span>{{ prompts.provenance?.model_id }}</span><span>{{ prompts.provenance?.professional_skill_id }}@{{ prompts.provenance?.professional_skill_version }}</span></div></div><div class="stage-actions"><label v-if="prompts?.status==='CURRENT'&&prompts.content" class="search"><span>⌕</span><input v-model="query" type="search" placeholder="搜索 Segment、对白或提示词" /></label><button type="button" :disabled="busy" @click="generate">{{ task?.status==='running'?`Skill 执行中 ${task.progress_percent}%`:prompts?.status==='CURRENT'?'重新生成 H3 提示词':'生成 H3 提示词' }}</button></div></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
    <div v-if="prompts?.status!=='CURRENT'||!prompts.content" class="empty"><strong>{{ task?.last_error || '还没有正式 H3 提示词' }}</strong><span>必须先确认步骤 3 的真实资产图。</span></div>
    <template v-else>
      <div class="prompt-workbench">
        <aside class="segment-browser" aria-label="H3 Segment 列表">
          <div class="browser-heading"><strong>生成段</strong><span>{{ filteredSegments.length }} / {{ segments.length }}</span></div>
          <button v-for="segment in filteredSegments" :key="segment.generation_segment_id" type="button" class="segment-row" :class="{ active:selectedSegment?.generation_segment_id===segment.generation_segment_id }" @click="selectedSegmentId=segment.generation_segment_id">
            <span class="segment-number">{{ String(segment.segment_number).padStart(2,'0') }}</span>
            <span class="row-copy"><strong>第 {{ segment.episode_order }} 集 · Segment {{ segment.segment_number }}</strong><small>{{ segment.dialogue_refs[0]?.target_dialogue_zh || segment.review_prompt_zh || '无对白镜头' }}</small><em>{{ seconds(segment.duration_us) }} · {{ segment.output_ratio }}</em></span>
            <span class="ref-count">{{ segment.reference_conditions.length }} 图</span>
          </button>
          <div v-if="!filteredSegments.length" class="browser-empty">当前筛选没有匹配生成段</div>
        </aside>

        <article v-if="selectedSegment" class="prompt-inspector">
          <div class="inspector-head"><div><span>MiniMax H3</span><h3>第 {{ selectedSegment.episode_order }} 集 · Segment {{ selectedSegment.segment_number }}</h3></div><div class="segment-meta"><span>{{ seconds(selectedSegment.duration_us) }}</span><span>{{ selectedSegment.output_ratio }}</span><span>{{ selectedSegment.reference_conditions.length }} 张参考图</span></div></div>
          <section class="reference-section"><div class="section-title"><strong>多参考图槽位</strong><span>Prompt 中按 Picture 编号精确引用</span></div><div v-if="selectedSegment.reference_conditions.length" class="refs"><figure v-for="ref in selectedSegment.reference_conditions" :key="ref.reference_id"><img :src="ref.reference_uri" :alt="`Picture ${ref.picture_index}`" loading="lazy" /><figcaption><b>&lt;Picture {{ ref.picture_index }}&gt;</b><span>{{ ref.asset_type }} · {{ ref.reference_role }}</span></figcaption></figure></div><p v-else class="no-refs">本段没有参考图条件</p></section>
          <section class="review-copy"><span>中文审核说明</span><p>{{ selectedSegment.review_prompt_zh }}</p></section>
          <section v-if="selectedSegment.dialogue_refs.length" class="dialogue-section"><div class="section-title"><strong>本段对白</strong><span>{{ selectedSegment.dialogue_refs.length }} 句</span></div><div class="dialogue-list"><article v-for="line in selectedSegment.dialogue_refs" :key="line.utterance_id"><p lang="auto">{{ line.final_target_dialogue }}</p><small v-if="line.target_dialogue_zh">{{ line.target_dialogue_zh }}</small></article></div></section>
          <details class="execution-details"><summary>查看 MiniMax H3 execution prompt</summary><div><div class="execution-meta">{{ prompts.provenance?.prompt_provider }} / {{ prompts.provenance?.prompt_model }}</div><pre>{{ selectedSegment.generation_prompt }}</pre><p v-if="selectedSegment.negative_prompt"><b>Negative：</b>{{ selectedSegment.negative_prompt }}</p></div></details>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:8px;min-width:0;margin:0}.stage-header{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:46px;padding:0 2px 6px;border-bottom:1px solid #e8eaf0}.stage-title{display:flex;align-items:center;gap:10px;min-width:0}.stage-title h2{margin:0;color:#142647;font-size:20px;letter-spacing:-.015em}.header-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.header-meta span{padding:4px 7px;border:1px solid #e5e2dc;border-radius:999px;background:#fff;color:#6b665f;font-size:10px}.stage-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;min-width:0}.stage-actions>button{min-height:32px;padding:0 13px;border:0;border-radius:8px;background:linear-gradient(135deg,#704cf4,#5a38e6);color:#fff;font-size:12px;font-weight:750;cursor:pointer;box-shadow:0 5px 12px rgba(91,59,227,.14)}.stage-actions>button:disabled{opacity:.5}.segment-meta{display:flex;gap:7px;flex-wrap:wrap}.search{display:flex;align-items:center;gap:6px;min-width:300px;padding:0 10px;border:1px solid #dedbd4;border-radius:9px;background:#fff;color:#918b83}.search input{width:100%;height:34px;border:0;outline:0;background:transparent;font-size:12px}.prompt-workbench{display:grid;grid-template-columns:340px minmax(0,1fr);height:clamp(540px,calc(100vh - 300px),760px);min-height:540px;overflow:hidden;border:1px solid #e0e3eb;border-radius:12px;background:#fff;box-shadow:0 5px 18px rgba(31,43,69,.035)}.segment-browser{min-height:0;overflow:auto;border-right:1px solid #e5e7ee;background:#fbfcfe}.browser-heading{position:sticky;top:0;z-index:2;display:flex;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #ebe8e2;background:rgba(250,249,246,.96);font-size:12px;backdrop-filter:blur(8px)}.browser-heading span{color:#918c85}.segment-row{display:grid;grid-template-columns:36px minmax(0,1fr) auto;align-items:center;gap:10px;width:100%;min-height:72px;padding:8px 11px;border:0;border-bottom:1px solid #eceef3;background:#fff;color:#33435f;text-align:left;cursor:pointer}.segment-row:hover{background:#f7f8fc}.segment-row.active{background:#f2efff;box-shadow:inset 3px 0 #674cf0}.segment-number{display:grid;place-items:center;width:32px;height:32px;border-radius:9px;background:#ebe9e4;color:#69645e;font-size:11px;font-weight:850}.active .segment-number{background:#6152e8;color:#fff}.row-copy{display:grid;min-width:0;gap:2px}.row-copy strong{font-size:13px}.row-copy small,.row-copy em{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.row-copy small{color:#5d6d87;font-size:12px}.row-copy em{color:#7f899b;font-size:11px;font-style:normal}.ref-count{padding:3px 5px;border-radius:6px;background:#fff;color:#6f69a7;font-size:10px}.browser-empty{padding:28px;color:#89847d;font-size:12px;text-align:center}.prompt-inspector{display:grid;align-content:start;gap:16px;min-width:0;padding:20px 22px 26px}.inspector-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}.inspector-head>div:first-child{display:grid;gap:3px}.inspector-head>div:first-child>span{color:#6658de;font-size:10px;font-weight:850;letter-spacing:.08em}.inspector-head h3{margin:0;font-size:19px}.segment-meta span{padding:5px 7px;border-radius:7px;background:#f1f0ec;color:#716b64;font-size:10px}.reference-section,.dialogue-section{display:grid;gap:9px;padding-top:14px;border-top:1px solid #eeeae4}.section-title{display:flex;align-items:center;justify-content:space-between;gap:12px}.section-title strong{font-size:13px}.section-title span{color:#7d776f;font-size:10px}.refs{display:flex;gap:9px;overflow-x:auto;padding-bottom:3px}.refs figure{flex:0 0 142px;margin:0}.refs img{width:142px;height:106px;object-fit:contain;border:1px solid #ebe8e2;border-radius:9px;background:#f1f0ed}.refs figcaption{display:grid;gap:1px;margin-top:4px}.refs figcaption b{color:#554ad0;font-size:10px}.refs figcaption span{overflow:hidden;color:#6e6963;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.no-refs{margin:0;padding:18px;border-radius:9px;background:#f7f6f2;color:#7d776f;font-size:12px}.review-copy{display:grid;grid-template-columns:82px minmax(0,1fr);gap:13px;padding:14px;border-radius:12px;background:#f8f7ff}.review-copy>span{color:#665bb0;font-size:10px;font-weight:850}.review-copy p{margin:0;color:#45413d;font-size:14px;line-height:1.78}.dialogue-list{display:grid;gap:7px}.dialogue-list article{display:grid;grid-template-columns:1.15fr .85fr;gap:10px;padding:10px 11px;border:1px solid #e9e5ef;border-radius:9px}.dialogue-list p{margin:0;color:#2f2c29;font-size:13px;line-height:1.6}.dialogue-list small{color:#6e6963;font-size:12px;line-height:1.6}.execution-details{padding-top:14px;border-top:1px solid #eeeae4;color:#514c46;font-size:12px}.execution-details summary{cursor:pointer;font-weight:800}.execution-details>div{display:grid;gap:9px;margin-top:10px;padding:12px;border-radius:11px;background:#f7f6f3}.execution-meta{color:#8b857e;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:10px}.execution-details pre{max-height:420px;overflow:auto;margin:0;white-space:pre-wrap;color:#45413c;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;line-height:1.7}.execution-details p{margin:0;line-height:1.6}.empty{display:grid;gap:5px;padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@media(max-width:900px){.stage-header,.inspector-head{align-items:stretch;flex-direction:column}.stage-title{align-items:flex-start;flex-direction:column;gap:5px}.stage-actions{width:100%}.search{min-width:0;flex:1}.prompt-workbench{grid-template-columns:1fr;height:auto;min-height:0;overflow:visible}.segment-browser{display:flex;max-height:none;overflow-x:auto;border-right:0;border-bottom:1px solid #ebe8e2}.browser-heading{display:none}.segment-row{flex:0 0 230px;border-right:1px solid #eeeae4;border-bottom:0}.segment-row.active{box-shadow:inset 0 -3px #6152e8}}@media(max-width:620px){.prompt-inspector{padding:15px}.review-copy,.dialogue-list article{grid-template-columns:1fr}.section-title{align-items:flex-start;flex-direction:column}}
</style>
