<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  getAssetImages,
  listAssetImageCandidates,
  reviewAssetImages,
  startAssetImages,
  type AssetImageCandidate,
  type AssetImagesContent,
  type AssetImagesRead,
} from '@/features/projects/replicaFiveStep'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const current = ref<AssetImagesRead | null>(null)
const candidates = ref<AssetImageCandidate[]>([])
const action = ref('')
const error = ref('')
const message = ref('')
const reason = ref('已检查人物、场景和道具资产图，确认身份与本土化分镜一致')
let timer: number | undefined

const pending = computed(() => candidates.value.find(item => item.review_status === 'NEEDS_REVIEW') ?? null)
const content = computed<AssetImagesContent | null>(() => pending.value?.content ?? current.value?.content ?? null)

async function refresh(silent = false) {
  try { [current.value, candidates.value] = await Promise.all([getAssetImages(projectId.value), listAssetImageCandidates(projectId.value)]) }
  catch (exc) { if (!silent) error.value = exc instanceof Error ? exc.message : '读取资产图失败' }
}
async function run(name: string, work: () => Promise<unknown>, success: string) { action.value=name; error.value=''; message.value=''; try{await work();message.value=success;await refresh()}catch(exc){error.value=exc instanceof Error?exc.message:'操作失败'}finally{action.value=''} }
const generate = () => run('generate', () => startAssetImages(projectId.value), '资产提取与图片生成已启动。完成后请逐项确认。')
const review = (candidate: AssetImageCandidate, accept: boolean) => run('review', () => reviewAssetImages(projectId.value, candidate, accept, reason.value), accept ? '资产图已正式确认。' : '已拒绝当前资产图候选。')
const label = (type: string) => type === 'CHARACTER' ? '人物' : type === 'SCENE' ? '场景' : '道具'

onMounted(()=>{void refresh();timer=window.setInterval(()=>void refresh(true),4000)})
onBeforeUnmount(()=>{if(timer!==undefined)window.clearInterval(timer)})
</script>

<template>
  <section class="workspace" data-testid="asset-images-workspace">
    <header><div><p class="eyebrow">步骤 3 / 5</p><h2>从本土化分镜提取资产并生成资产图</h2><p>只为实际出现在镜头或对白中的人物、场景、道具生成正式参考图；没有真实图片的文字资产不能进入 H3 多参考生成。</p></div><button type="button" :disabled="Boolean(action) || Boolean(pending)" @click="generate">{{ action==='generate'?'生成中…':current?.status==='CURRENT'?'重新生成资产图':'提取并生成资产图' }}</button></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
    <label v-if="pending" class="review"><span>审核备注</span><input v-model="reason" maxlength="800" /></label>
    <div v-if="!content" class="empty">先确认步骤 2 的本土化分镜，再提取人物、场景和道具。</div>
    <template v-else>
      <div class="metrics"><span>{{ content.assets.length }} 个正式资产</span><span>{{ content.visual_style }}</span><span>{{ pending?'待人工确认':current?.status==='CURRENT'?'正式 CURRENT':'历史结果' }}</span></div>
      <div class="grid"><article v-for="asset in content.assets" :key="asset.target_asset_id"><div class="image"><img v-if="asset.reference_media[0]" :src="asset.reference_media[0].uri" :alt="asset.display_name" loading="lazy" /></div><div class="copy"><small>{{ label(asset.asset_type) }}</small><h3>{{ asset.display_name }}</h3><p>{{ asset.review_description_zh }}</p><details><summary>查看资产图生成提示词</summary><p>{{ asset.image_prompt }}</p></details></div></article></div>
      <div v-if="pending" class="actions"><button type="button" :disabled="Boolean(action)||!reason.trim()" @click="review(pending,true)">确认资产图</button><button type="button" class="secondary" :disabled="Boolean(action)||!reason.trim()" @click="review(pending,false)">拒绝重做</button></div>
    </template>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:16px;max-width:1360px;margin:20px auto}.workspace>header{display:flex;justify-content:space-between;gap:18px;padding:22px;border:1px solid #deded8;border-radius:18px;background:#fff}.workspace h2{margin:3px 0}.workspace header p:last-child{color:#716d66}.eyebrow{margin:0;color:#5a4ed8;font-size:11px;font-weight:850}.workspace button{min-height:38px;padding:0 15px;border:0;border-radius:9px;background:#292925;color:#fff;font-weight:750}.workspace button:disabled{opacity:.5}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.grid article{overflow:hidden;border:1px solid #e1dfd9;border-radius:14px;background:#fff}.image{aspect-ratio:1;background:#eee}.image img{width:100%;height:100%;object-fit:cover}.copy{padding:13px}.copy small{color:#6558df;font-weight:800}.copy h3{margin:3px 0}.copy p{color:#65615b;line-height:1.55}.copy details{font-size:12px}.metrics,.actions{display:flex;gap:8px;flex-wrap:wrap}.metrics span{padding:7px 10px;border-radius:999px;background:#efeee9;font-size:12px}.review{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center}.review input{min-height:36px;padding:0 10px;border:1px solid #d7d3cc;border-radius:8px}.secondary{background:#fff!important;color:#333!important;border:1px solid #d4d0c9!important}.empty{padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@media(max-width:900px){.grid{grid-template-columns:1fr 1fr}.workspace>header{flex-direction:column}}@media(max-width:600px){.grid{grid-template-columns:1fr}}
</style>
