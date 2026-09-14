<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  getLocalizedStoryboard,
  listLocalizedStoryboardCandidates,
  reviewLocalizedStoryboard,
  startLocalizedStoryboard,
  type LocalizedStoryboardCandidate,
  type LocalizedStoryboardContent,
  type LocalizedStoryboardRead,
} from '@/features/projects/replicaFiveStep'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const current = ref<LocalizedStoryboardRead | null>(null)
const candidates = ref<LocalizedStoryboardCandidate[]>([])
const action = ref('')
const error = ref('')
const message = ref('')
const reason = ref('已逐镜检查中文描述、本土语言对白和中文翻译，确认可进入资产生成')
let timer: number | undefined

const pending = computed(() => candidates.value.find(item => item.review_status === 'NEEDS_REVIEW') ?? null)
const content = computed<LocalizedStoryboardContent | null>(() => pending.value?.content ?? current.value?.content ?? null)

function seconds(us: number) { return `${(us / 1_000_000).toFixed(2)}s` }

async function refresh(silent = false) {
  try {
    const [read, rows] = await Promise.all([getLocalizedStoryboard(projectId.value), listLocalizedStoryboardCandidates(projectId.value)])
    current.value = read
    candidates.value = rows
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '读取本土化分镜失败'
  }
}

async function run(name: string, work: () => Promise<unknown>, success: string) {
  action.value = name; error.value = ''; message.value = ''
  try { await work(); message.value = success; await refresh() }
  catch (exc) { error.value = exc instanceof Error ? exc.message : '操作失败' }
  finally { action.value = '' }
}

const generate = () => run('generate', () => startLocalizedStoryboard(projectId.value), '本土化分镜任务已启动，完成后会出现待确认候选。')
const review = (candidate: LocalizedStoryboardCandidate, accept: boolean) => run('review', () => reviewLocalizedStoryboard(projectId.value, candidate, accept, reason.value), accept ? '本土化分镜已正式确认。' : '已拒绝当前本土化分镜。')

onMounted(() => { void refresh(); timer = window.setInterval(() => void refresh(true), 4000) })
onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer) })
</script>

<template>
  <section class="workspace" data-testid="localized-storyboard-workspace">
    <header><div><p class="eyebrow">步骤 2 / 5</p><h2>本土化改写分镜表</h2><p>画面与镜头说明统一用中文审核；真正说出口的对白使用目标地区语言，并同时保留一份中文翻译供理解。</p></div><button type="button" :disabled="Boolean(action) || Boolean(pending)" @click="generate">{{ action === 'generate' ? '启动中…' : current?.status === 'CURRENT' ? '重新本土化' : '生成本土化分镜' }}</button></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
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
.workspace{display:grid;gap:16px;max-width:1360px;margin:20px auto}.workspace>header{display:flex;justify-content:space-between;gap:16px;padding:22px;border:1px solid #deded8;border-radius:18px;background:#fff}.workspace h2{margin:3px 0}.workspace header p:last-child{color:#706d67}.eyebrow{margin:0;color:#5a4ed8;font-size:11px;font-weight:850}.workspace button{min-height:38px;padding:0 15px;border:0;border-radius:9px;background:#292925;color:#fff;font-weight:750}.workspace button:disabled{opacity:.5}.metrics,.actions{display:flex;gap:8px;flex-wrap:wrap}.metrics span{padding:7px 10px;border-radius:999px;background:#efeee9;font-size:12px}.shots{display:grid;gap:10px}.shots article{display:grid;gap:10px;padding:16px;border:1px solid #e2e0da;border-radius:14px;background:#fff}.shot-head{display:flex;justify-content:space-between}.shot-head small{color:#817c74}.fact{display:grid;grid-template-columns:110px 1fr;gap:12px}.fact p,.dialogue p{margin:0;line-height:1.6}.dialogue{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px;border-radius:10px;background:#f8f7ff}.dialogue>div{display:grid;gap:4px}.dialogue b,.fact b{font-size:11px;color:#68635c}.review{display:grid;grid-template-columns:auto 1fr;gap:10px;align-items:center}.review input{min-height:36px;padding:0 10px;border:1px solid #d7d3cc;border-radius:8px}.secondary{background:#fff!important;color:#333!important;border:1px solid #d4d0c9!important}.empty{padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@media(max-width:800px){.workspace>header,.shot-head{flex-direction:column}.dialogue,.fact{grid-template-columns:1fr}}
</style>
