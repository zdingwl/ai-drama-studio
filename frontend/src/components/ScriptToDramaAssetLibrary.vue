<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import { dramaMediaUrl, getDramaState, runDramaProductionStage, type ScriptToDramaState } from '@/features/projects/scriptToDrama'
import type { TaskRead } from '@/features/projects/types'
import { apiRequest } from '@/lib/api'

type Category = 'characters' | 'locations' | 'props'
type Entry = { id: string; name: string; visual_description: string; category: Category; reference_id: string | null }
const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const state = ref<ScriptToDramaState | null>(null)
const tasks = ref<TaskRead[]>([])
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const keyword = ref('')
const category = ref<'all' | Category>('all')
const view = ref<'cards' | 'table'>('cards')
const selected = ref<Entry | null>(null)
const editing = ref(false)
const description = ref('')
const reason = ref('人工审核视觉设定')
const acknowledged = ref<string[]>([])
let timer: number | undefined

const categories: { id: 'all' | Category; label: string }[] = [
  { id: 'all', label: '全部' }, { id: 'characters', label: '人物' },
  { id: 'locations', label: '场景' }, { id: 'props', label: '道具' },
]
const latest = computed(() => [...tasks.value]
  .filter(item => ['SCRIPT_TO_DRAMA_ASSET_EXTRACTION', 'SCRIPT_TO_DRAMA_PREPRODUCTION', 'SCRIPT_TO_DRAMA_PRODUCTION'].includes(item.task_type ?? ''))
  .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] ?? null)
const processing = computed(() => busy.value || latest.value?.status === 'queued' || latest.value?.status === 'running')
const worldReady = computed(() => state.value?.world.status === 'CURRENT')
const approved = computed(() => worldReady.value && state.value?.assets.status === 'CURRENT' &&
  state.value?.world.content?.review_status === 'APPROVED' && state.value?.assets.content?.review_status === 'APPROVED')
const imageReady = computed(() => state.value?.asset_images.status === 'CURRENT')
const pendingDecisions = computed(() => strings(state.value?.world.content?.unresolved_decisions))

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}
function objects(value: unknown): Record<string, unknown>[] { return Array.isArray(value) ? value.map(object) : [] }
function strings(value: unknown): string[] { return Array.isArray(value) ? value.filter((x): x is string => typeof x === 'string') : [] }
function text(value: unknown): string { return typeof value === 'string' ? value : '' }

const entries = computed<Entry[]>(() => {
  const definitions = state.value?.world.content
  const images = new Map<string, string>()
  if (imageReady.value) {
    for (const asset of objects(state.value?.asset_images.content?.assets)) {
      const media = objects(asset.media)
      if (media.length) images.set(text(asset.target_entity_id), text(media[0].reference_id))
    }
  }
  const result: Entry[] = []
  for (const kind of ['characters', 'locations', 'props'] as Category[]) {
    for (const item of objects(definitions?.[kind])) {
      const id = text(item.id)
      if (id) result.push({ id, name: text(item.name), visual_description: text(item.visual_description),
        category: kind, reference_id: images.get(id) || null })
    }
  }
  return result
})
const filtered = computed(() => entries.value.filter(item =>
  (category.value === 'all' || category.value === item.category) &&
  `${item.name} ${item.visual_description} ${item.id}`.toLocaleLowerCase().includes(keyword.value.trim().toLocaleLowerCase()),
))
const unresolved = computed(() => pendingDecisions.value.length > 0)
const typeName = (kind: Category) => ({ characters: '人物', locations: '场景', props: '道具' })[kind]
const media = (id: string) => dramaMediaUrl(projectId.value, id)

async function refresh(silent = false) {
  const id = projectId.value
  if (!silent) loading.value = true
  try {
    const [nextState, nextTasks] = await Promise.all([getDramaState(id), listProjectTasks(id)])
    if (id !== projectId.value) return
    state.value = nextState
    tasks.value = [...nextTasks]
  } catch (exc) {
    if (id === projectId.value) error.value = exc instanceof Error ? exc.message : '读取资产库失败'
  } finally { if (id === projectId.value && !silent) loading.value = false }
}

async function generateImages() {
  if (processing.value || !approved.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await runDramaProductionStage(projectId.value, 'asset_images')
    notice.value = '已提交当前确认版本的全部资产图生成任务。'
    await refresh(true)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '任务提交失败' }
  finally { busy.value = false }
}

function openEntry(item: Entry) {
  selected.value = item; editing.value = false; description.value = item.visual_description
  reason.value = '人工审核视觉设定'; acknowledged.value = []
}
function openDecisions() {
  selected.value = null; editing.value = true; description.value = ''
  reason.value = '人工核定目标世界冲突'; acknowledged.value = []
}
async function submitReview(approve: boolean) {
  const worldId = state.value?.world.artifact_id
  if (processing.value || !worldReady.value || !worldId || !reason.value.trim()) return
  const changed = selected.value && description.value.trim() !== selected.value.visual_description
  if (!approve && !changed && !acknowledged.value.length) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await apiRequest(`/projects/${projectId.value}/script-to-drama/commands/review-world`, {
      method: 'POST',
      body: JSON.stringify({
        expected_world_artifact_id: worldId,
        corrections: changed && selected.value ? [{
          category: selected.value.category, entity_id: selected.value.id,
          visual_description: description.value.trim(),
        }] : [],
        acknowledged_decisions: acknowledged.value,
        reason: reason.value.trim(),
        approve,
      }),
    })
    selected.value = null; editing.value = false
    notice.value = approve ? '资产清单已人工确认，可以出图并进入导演分镜。' :
      '设定已保存为新版本，请继续核对并点击「确认资产清单」；旧资产图和后续结果已失效。'
    await refresh(true)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '审核保存失败，请刷新后重试' }
  finally { busy.value = false }
}
async function approveWorld() {
  if (processing.value || approved.value || unresolved.value || !worldReady.value) return
  selected.value = null; acknowledged.value = []; description.value = ''
  reason.value = '人工核对人物、场景和道具后确认资产清单'
  if (!window.confirm('确认当前人物、场景和道具清单？确认后才能生成图片和导演分镜；以后修改设定会让相关下游版本过期。')) return
  await submitReview(true)
}
function close() { if (!busy.value) { selected.value = null; editing.value = false } }
watch(projectId, () => { state.value = null; tasks.value = []; selected.value = null; error.value = ''; notice.value = ''; void refresh() })
onMounted(() => {
  void refresh()
  timer = window.setInterval(() => { if (!busy.value) void refresh(true) }, 3000)
})
onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer) })
</script>

<template>
  <section class="asset-library" data-testid="script-to-drama-asset-library">
    <header class="library-header">
      <div><p class="eyebrow">剧本生成短剧 · 资产审核</p><h2>人物、场景与道具</h2><p>解析在后台完成。请核对提取结果、修改设定并确认；分镜和正式出图只使用已确认的资产版本。</p></div>
      <div class="header-actions">
        <button type="button" class="secondary" :disabled="processing || !worldReady" @click="openDecisions">核定未决事项 <span v-if="unresolved">({{ pendingDecisions.length }})</span></button>
        <button v-if="!approved" type="button" :disabled="processing || !worldReady || unresolved" @click="approveWorld">确认资产清单</button>
        <button v-if="approved" type="button" :disabled="processing" @click="generateImages">{{ imageReady ? '重新生成全部资产图' : '生成全部资产图' }}</button>
      </div>
    </header>
    <p v-if="error" class="alert error" role="alert">{{ error }}</p>
    <p v-if="notice" class="alert" role="status">{{ notice }}</p>
    <p v-if="latest && ['failed', 'interrupted'].includes(latest.status)" class="alert error">{{ latest.last_error || '任务失败，请返回剧本库重新提取。' }}</p>
    <p v-if="latest && ['queued', 'running'].includes(latest.status)" class="alert">{{ latest.task_name }} · {{ latest.status === 'queued' ? '等待执行' : `进行中 ${latest.progress_percent}%` }}</p>
    <div v-if="loading" class="panel">正在读取资产…</div>
    <template v-else-if="!worldReady">
      <div class="panel empty"><h3>{{ processing ? '正在提取当前剧本的资产…' : '尚未生成资产清单' }}</h3><p>在剧本库选定剧本后点击「一键提取人物／场景／道具」，后台会自动执行必要的原文解析，无需单独操作。</p><a :href="`/projects/${projectId}/source`">返回剧本库</a></div>
    </template>
    <template v-else>
      <p v-if="approved" class="alert" role="status">当前人物、场景和道具清单已人工确认。后续图片与分镜会引用本版资产 ID。</p>
      <p v-else class="alert">当前清单尚未确认：请检查人物别名、外观、场景和道具，确认后才可出图与生成分镜。</p>
      <div v-if="unresolved" class="alert error">存在 {{ pendingDecisions.length }} 条未决事项，请核定后确认资产清单。<button type="button" class="text-action" @click="openDecisions">查看并核定</button></div>
      <div class="toolbar"><div class="filters"><button v-for="kind in categories" :key="kind.id" type="button" :class="{ active: category === kind.id }" @click="category = kind.id">{{ kind.label }} <small>{{ kind.id === 'all' ? entries.length : entries.filter(item => item.category === kind.id).length }}</small></button></div><div class="tools"><input v-model="keyword" type="search" aria-label="搜索资产" placeholder="搜索人物、场景、道具…" /><button type="button" class="secondary" :aria-pressed="view === 'cards'" @click="view = 'cards'">卡片</button><button type="button" class="secondary" :aria-pressed="view === 'table'" @click="view = 'table'">列表</button></div></div>
      <p class="hint">重新生成目前会处理全部资产；单项多候选、局部重做仍在后续制作范围内，请勿理解为只重做当前筛选项。</p>
      <div v-if="!filtered.length" class="panel empty">没有符合条件的资产。</div>
      <div v-else-if="view === 'cards'" class="cards">
        <article v-for="item in filtered" :key="item.id" class="asset-card">
          <button type="button" class="preview" :aria-label="`查看${item.name}`" @click="openEntry(item)"><img v-if="item.reference_id" :src="media(item.reference_id)" :alt="item.name" /><span v-else>尚未生成图片</span></button>
          <div class="asset-info"><div class="asset-title"><strong>{{ item.name }}</strong><span class="tag">{{ typeName(item.category) }}</span></div><p :title="item.visual_description">{{ item.visual_description }}</p><div class="asset-actions"><span :class="['status', { ready: item.reference_id }]">{{ item.reference_id ? '已有正式参考图' : '待出图' }}</span><button type="button" class="text-action" @click="openEntry(item)">查看 / 编辑</button></div></div>
        </article>
      </div>
      <div v-else class="panel table-wrap"><table><thead><tr><th>预览</th><th>名称</th><th>类型</th><th>视觉设定</th><th>图片状态</th><th>操作</th></tr></thead><tbody><tr v-for="item in filtered" :key="item.id"><td><img v-if="item.reference_id" class="thumb" :src="media(item.reference_id)" :alt="item.name" /><span v-else>—</span></td><td>{{ item.name }}</td><td>{{ typeName(item.category) }}</td><td class="description">{{ item.visual_description }}</td><td>{{ item.reference_id ? '已出图' : '待出图' }}</td><td><button type="button" class="text-action" @click="openEntry(item)">查看 / 编辑</button></td></tr></tbody></table></div>
    </template>
    <div v-if="selected || editing" class="overlay" @click.self="close">
      <section class="dialog" role="dialog" aria-modal="true" :aria-label="selected ? `审核${selected.name}` : '人工核定未决事项'">
        <header class="dialog-head"><div><small>{{ selected ? typeName(selected.category) : '目标世界' }} · 人工审核</small><h3>{{ selected?.name || '核定未决事项' }}</h3></div><button type="button" class="close" aria-label="关闭" @click="close">×</button></header>
        <div v-if="selected" class="dialog-body"><div class="detail-preview"><img v-if="selected.reference_id" :src="media(selected.reference_id)" :alt="selected.name" /><span v-else>尚未生成正式参考图</span></div><p class="hint">实体 ID：{{ selected.id }}。人工审核只修改视觉描述，不更改原文证据、实体 ID 或剧情。</p><label>视觉描述<textarea v-model="description" rows="5" maxlength="1200" :disabled="processing" /></label></div>
        <div v-if="pendingDecisions.length" class="decisions"><strong>尚待人工核定的事项</strong><p>勾选代表已核对并明确接受本次人工决定。</p><label v-for="item in pendingDecisions" :key="item" class="decision"><input v-model="acknowledged" type="checkbox" :value="item" :disabled="processing" />{{ item }}</label></div>
        <div class="dialog-foot"><label>审核理由<input v-model="reason" maxlength="800" :disabled="processing" placeholder="记录为何修改或确认该设定" /></label><div class="foot-actions"><button type="button" class="secondary" :disabled="busy" @click="close">取消</button><button type="button" :disabled="processing || reason.trim().length < 2 || (!acknowledged.length && (!selected || description.trim() === selected.visual_description)) || (selected !== null && !description.trim())" @click="submitReview(false)">保存修改，继续审核</button></div></div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.asset-library{display:grid;gap:14px;max-width:1200px;margin:auto;color:#1b2b42}.library-header,.panel,.asset-card,.dialog{background:#fff;border:1px solid #e2e8f0;border-radius:12px}.library-header{padding:20px 22px;display:flex;align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap}.library-header h2{font-size:23px;margin:3px 0 6px}.library-header p,.hint{font-size:12px;color:#61718a;line-height:1.6;margin:0}.eyebrow{font-weight:750;color:#466de2!important}.header-actions,.tools,.asset-actions,.foot-actions{display:flex;gap:9px;align-items:center;flex-wrap:wrap}button{font:inherit;cursor:pointer}button:not(.text-action,.preview,.close,.filters button){padding:9px 12px;border:1px solid #2878ff;border-radius:8px;background:#2878ff;color:white;font-size:13px;font-weight:650}button.secondary{border-color:#d8e2ef!important;background:white!important;color:#2a466b!important}button:disabled{opacity:.45;cursor:not-allowed}.panel{padding:18px}.empty{display:grid;justify-items:start;gap:10px}.empty h3,.empty p{margin:0}.alert{background:#f2f5ff;padding:12px 14px;border-radius:8px;font-size:13px}.alert.error{color:#ac3434;background:#fff1ee}.toolbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}.filters{display:flex;gap:6px;flex-wrap:wrap}.filters button{border:1px solid #e1e8f2;background:white;color:#53657d;padding:8px 12px;border-radius:8px;font-size:13px}.filters button.active{background:#edf3ff;border-color:#9bbcff;color:#2559b9}.filters small{margin-left:4px}.tools input,.dialog input:not([type=checkbox]),.dialog textarea{min-width:0;border:1px solid #d9e2ec;border-radius:8px;padding:10px;font:inherit;font-size:13px}.tools input{width:min(260px,70vw)}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:14px}.asset-card{overflow:hidden;display:grid;grid-template-rows:174px 1fr}.preview{border:0;background:#f6f8fc;display:grid;place-items:center;overflow:hidden;color:#8291a4;font-size:12px}.preview img{width:100%;height:100%;object-fit:contain}.asset-info{padding:12px;display:grid;gap:8px}.asset-title{display:flex;justify-content:space-between;gap:10px;align-items:center;font-size:14px}.tag{font-size:11px;border:1px solid #b9d4ff;border-radius:5px;color:#3460ac;padding:2px 5px;white-space:nowrap}.asset-info p{margin:0;line-height:1.5;font-size:12px;color:#56677d;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}.asset-actions{justify-content:space-between}.status{font-size:11px;color:#a16d29}.status.ready{color:#328067}.text-action{border:0;background:none;color:#2878ff;font-size:12px;padding:3px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:12px;text-align:left}th,td{border-bottom:1px solid #edf0f5;padding:9px;vertical-align:middle}th{white-space:nowrap;background:#f8fafc}.description{max-width:320px}.thumb{width:60px;height:60px;object-fit:contain}.overlay{position:fixed;inset:0;z-index:1000;background:#15213785;display:grid;place-items:center;padding:16px}.dialog{width:min(700px,100%);max-height:90vh;overflow:auto;box-shadow:0 20px 65px #101c3033}.dialog-head{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid #e9edf4}.dialog-head h3{margin:3px 0 0;font-size:18px}.dialog-head small{color:#60708d}.close{font-size:25px;background:none;border:0;color:#667}.dialog-body,.decisions,.dialog-foot{padding:16px 20px;display:grid;gap:12px}.detail-preview{height:245px;background:#f8fafc;display:grid;place-items:center;color:#8b9bad}.detail-preview img{width:100%;height:100%;object-fit:contain}.dialog label{display:grid;gap:7px;font-size:13px}.dialog textarea{resize:vertical;width:100%;box-sizing:border-box}.decisions{border-block:1px solid #edf0f5}.decisions p{margin:0;font-size:12px;color:#667}.decision{display:flex!important;align-items:flex-start;gap:8px!important}.decision input{margin-top:3px}.dialog-foot input{width:100%;box-sizing:border-box}.foot-actions{justify-content:flex-end}@media(max-width:800px){.library-header{padding:14px}.cards{grid-template-columns:repeat(auto-fill,minmax(165px,1fr))}.asset-card{grid-template-rows:150px 1fr}}
</style>
