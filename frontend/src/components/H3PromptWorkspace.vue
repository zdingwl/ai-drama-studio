<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import { getH3Prompts, startH3Prompts, type H3PromptsRead } from '@/features/projects/replicaFiveStep'
import type { TaskRead } from '@/features/projects/types'

const TASK_TYPE='replica.h3-prompts'
const route=useRoute()
const projectId=computed(()=>String(route.params.id??''))
const prompts=ref<H3PromptsRead|null>(null)
const tasks=ref<TaskRead[]>([])
const action=ref(false)
const error=ref('')
const message=ref('')
let timer:number|undefined

const task=computed(()=>tasks.value.find(item=>item.task_type===TASK_TYPE)??null)
const busy=computed(()=>action.value||task.value?.status==='queued'||task.value?.status==='running')

async function refresh(silent=false){try{[prompts.value,tasks.value]=await Promise.all([getH3Prompts(projectId.value),listProjectTasks(projectId.value)])}catch(exc){if(!silent)error.value=exc instanceof Error?exc.message:'读取 H3 提示词失败'}}
async function generate(){if(busy.value)return;action.value=true;error.value='';message.value='';try{await startH3Prompts(projectId.value);message.value='已启动模型专属 Prompt Skill。';await refresh()}catch(exc){error.value=exc instanceof Error?exc.message:'启动提示词生成失败'}finally{action.value=false}}
function seconds(us:number){return `${(us/1_000_000).toFixed(2)}s`}

onMounted(()=>{void refresh();timer=window.setInterval(()=>void refresh(true),3500)})
onBeforeUnmount(()=>{if(timer!==undefined)window.clearInterval(timer)})
</script>

<template>
  <section class="workspace" data-testid="h3-prompt-workspace">
    <header><div><p class="eyebrow">步骤 4 / 5</p><h2>用 MiniMax H3 专属 Skill 生成多参考音画同步提示词</h2><p>这里不是通用 Prompt 拼接。系统根据当前视频模型路由到对应 Professional Skill，读取 Skill 手册和规则，再把本土化分镜剧本 + 已确认资产图编译为模型原生提示词。</p></div><button type="button" :disabled="busy" @click="generate">{{ task?.status==='running'?`Skill 执行中 ${task.progress_percent}%`:prompts?.status==='CURRENT'?'重新生成 H3 提示词':'生成 H3 提示词' }}</button></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
    <div v-if="prompts?.status!=='CURRENT'||!prompts.content" class="empty"><strong>{{ task?.last_error || '还没有正式 H3 提示词' }}</strong><span>必须先确认步骤 3 的真实资产图。</span></div>
    <template v-else>
      <div class="contract"><span>模型：{{ prompts.provenance?.model_id }}</span><span>Prompt Skill：{{ prompts.provenance?.professional_skill_id }}@{{ prompts.provenance?.professional_skill_version }}</span><span>执行器：{{ prompts.provenance?.prompt_provider }} / {{ prompts.provenance?.prompt_model }}</span></div>
      <div class="segments"><article v-for="segment in prompts.content.segments" :key="segment.generation_segment_id"><header><strong>第 {{ segment.episode_order }} 集 · Segment {{ segment.segment_number }}</strong><small>{{ seconds(segment.duration_us) }} · {{ segment.output_ratio }} · {{ segment.reference_conditions.length }} 张参考图</small></header><div v-if="segment.reference_conditions.length" class="refs"><figure v-for="ref in segment.reference_conditions" :key="ref.reference_id"><img :src="ref.reference_uri" :alt="`Picture ${ref.picture_index}`" loading="lazy" /><figcaption>&lt;Picture {{ ref.picture_index }}&gt; · {{ ref.asset_type }}</figcaption></figure></div><div class="review-copy"><b>中文审核说明</b><p>{{ segment.review_prompt_zh }}</p></div><details><summary>查看 MiniMax H3 execution prompt</summary><pre>{{ segment.generation_prompt }}</pre><p v-if="segment.negative_prompt"><b>Negative：</b>{{ segment.negative_prompt }}</p></details></article></div>
    </template>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:16px;max-width:1360px;margin:20px auto}.workspace>header{display:flex;justify-content:space-between;gap:18px;padding:22px;border:1px solid #deded8;border-radius:18px;background:#fff}.workspace h2{margin:3px 0}.workspace header p:last-child{color:#716d66}.eyebrow{margin:0;color:#5a4ed8;font-size:11px;font-weight:850}.workspace button{min-height:38px;padding:0 15px;border:0;border-radius:9px;background:#292925;color:#fff;font-weight:750}.workspace button:disabled{opacity:.5}.contract{display:flex;gap:8px;flex-wrap:wrap}.contract span{padding:7px 10px;border-radius:999px;background:#efeee9;font-size:12px}.segments{display:grid;gap:12px}.segments>article{display:grid;gap:12px;padding:16px;border:1px solid #e1dfd9;border-radius:14px;background:#fff}.segments article>header{display:flex;justify-content:space-between}.segments small{color:#7c776f}.refs{display:flex;gap:8px;overflow-x:auto}.refs figure{flex:0 0 118px;margin:0}.refs img{width:118px;height:88px;object-fit:cover;border-radius:8px;background:#eee}.refs figcaption{font-size:10px;color:#67635c}.review-copy{padding:10px;border-radius:10px;background:#f8f7ff}.review-copy p{margin:5px 0 0;line-height:1.6}.segments details{font-size:12px}.segments pre{overflow:auto;white-space:pre-wrap;line-height:1.55}.empty{display:grid;gap:5px;padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@media(max-width:800px){.workspace>header,.segments article>header{flex-direction:column}}
</style>
