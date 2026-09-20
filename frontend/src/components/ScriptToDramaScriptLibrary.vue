<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import { getDramaState, type ScriptToDramaState } from '@/features/projects/scriptToDrama'
import {
  extractDramaAssets, getDramaScript, listDramaScripts, pasteDramaScript, selectDramaScript,
  updateDramaScript, uploadDramaScripts, type DramaScriptDetail, type DramaScriptItem,
  type DramaScriptLibrary,
} from '@/features/projects/scriptToDramaLibrary'
import type { TaskRead } from '@/features/projects/types'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.id ?? ''))
const library = ref<DramaScriptLibrary | null>(null)
const state = ref<ScriptToDramaState | null>(null)
const tasks = ref<TaskRead[]>([])
const keyword = ref('')
const search = ref('')
const checkedIds = ref<string[]>([])
const dialog = ref<'new' | 'detail' | null>(null)
const dialogId = ref<string | null>(null)
const title = ref('')
const draft = ref('')
const detail = ref<DramaScriptDetail | null>(null)
const detailLoading = ref(false)
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const notice = ref('')
let timer: number | undefined

const current = computed(() => library.value?.scripts.find(item => item.is_active) ?? null)
const detailItem = computed(() => library.value?.scripts.find(item => item.id === dialogId.value) ?? null)
const filtered = computed(() => (library.value?.scripts ?? []).filter(item =>
  `${item.title} ${item.filename} ${item.excerpt}`.toLocaleLowerCase().includes(search.value.trim().toLocaleLowerCase()),
))
const selected = computed(() => (library.value?.scripts ?? []).filter(item => checkedIds.value.includes(item.id)))
const allFilteredSelected = computed(() => filtered.value.length > 0 && filtered.value.every(item => checkedIds.value.includes(item.id)))
const latest = computed(() => [...tasks.value]
  .filter(task => ['SCRIPT_TO_DRAMA_ASSET_EXTRACTION', 'SCRIPT_TO_DRAMA_PREPRODUCTION'].includes(task.task_type ?? ''))
  .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] ?? null)
const processing = computed(() => busy.value || ['queued', 'running'].includes(latest.value?.status ?? ''))
const worldReady = computed(() => state.value?.world.status === 'CURRENT' && state.value?.assets.status === 'CURRENT')
const approved = computed(() => worldReady.value && state.value?.world.content?.review_status === 'APPROVED' && state.value?.assets.content?.review_status === 'APPROVED')
const selectedCurrentOnly = computed(() => selected.value.length === 1 && selected.value[0]?.is_active === true)
const dialogChanged = computed(() => dialog.value === 'new'
  ? !!title.value.trim() && !!draft.value.trim()
  : !!detail.value && (title.value.trim() !== detail.value.title || draft.value !== detail.value.text))

function items(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => item !== null && typeof item === 'object' && !Array.isArray(item)) : []
}
function names(kind: 'characters' | 'locations' | 'props'): string[] {
  if (!worldReady.value) return []
  return items(state.value?.world.content?.[kind]).map(item => String(item.name ?? '')).filter(Boolean).slice(0, 5)
}
function status(item: DramaScriptItem): string {
  if (!item.is_active) return '未记录独立提取状态'
  if (latest.value && ['queued', 'running'].includes(latest.value.status)) {
    return latest.value.status === 'queued' ? '资产提取排队中' : `资产提取中 · ${latest.value.progress_percent}%`
  }
  if (worldReady.value) return approved.value ? '资产已确认' : '已提取 · 待确认'
  if (latest.value?.status === 'failed') return '资产提取失败'
  return '未提取资产'
}
async function refresh(silent = false) {
  const id = projectId.value
  if (!silent) loading.value = true
  try {
    const [scripts, nextState, nextTasks] = await Promise.all([
      listDramaScripts(id), getDramaState(id), listProjectTasks(id),
    ])
    if (id !== projectId.value) return
    library.value = scripts
    state.value = nextState
    tasks.value = [...nextTasks]
    checkedIds.value = checkedIds.value.filter(scriptId => scripts.scripts.some(item => item.id === scriptId))
  } catch (exc) {
    if (id === projectId.value) error.value = exc instanceof Error ? exc.message : '读取剧本库失败'
  } finally { if (id === projectId.value && !silent) loading.value = false }
}
function toggle(id: string) {
  checkedIds.value = checkedIds.value.includes(id) ? checkedIds.value.filter(value => value !== id) : [...checkedIds.value, id]
}
function selectFiltered() {
  const ids = filtered.value.map(item => item.id)
  checkedIds.value = allFilteredSelected.value
    ? checkedIds.value.filter(id => !ids.includes(id))
    : [...new Set([...checkedIds.value, ...ids])]
}
function closeDialog() {
  if (busy.value) return
  if (dialogChanged.value && !window.confirm('关闭后将丢失未保存的修改，确定关闭吗？')) return
  dialog.value = null; dialogId.value = null; detail.value = null; title.value = ''; draft.value = ''
}
function createScript() {
  if (processing.value) return
  dialog.value = 'new'; dialogId.value = null; detail.value = null; title.value = ''; draft.value = ''; error.value = ''
}
async function openDetail(item: DramaScriptItem) {
  if (busy.value) return
  dialog.value = 'detail'; dialogId.value = item.id; detail.value = null; title.value = ''; draft.value = ''
  detailLoading.value = true; error.value = ''
  const id = projectId.value
  try {
    const result = await getDramaScript(id, item.id)
    if (id === projectId.value && dialog.value === 'detail' && dialogId.value === item.id) {
      detail.value = result; title.value = result.title; draft.value = result.text
    }
  } catch (exc) { if (dialogId.value === item.id) error.value = exc instanceof Error ? exc.message : '读取完整剧本失败' }
  finally { if (dialogId.value === item.id) detailLoading.value = false }
}
async function useScript(item: DramaScriptItem) {
  if (processing.value || item.is_active) return
  if (current.value && worldReady.value && !window.confirm('切换当前剧本会使原有分析、资产、分镜与视频成为历史版本。确认切换吗？')) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    library.value = await selectDramaScript(projectId.value, item.id, library.value?.current_document_id ?? null)
    dialog.value = null; dialogId.value = null; detail.value = null
    checkedIds.value = []
    notice.value = '已选为当前制作剧本，其他剧本及其正文版本未改变。'
    await refresh(true)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '切换剧本失败' }
  finally { busy.value = false }
}
async function saveNew() {
  if (processing.value || !dialogChanged.value || title.value.length > 160 || draft.value.length > 200000) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    library.value = await pasteDramaScript(projectId.value, title.value.trim(), draft.value)
    dialog.value = null; title.value = ''; draft.value = ''; checkedIds.value = []
    notice.value = '新剧本已保存到剧本库，当前制作剧本没有改变。'
    await refresh(true)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '保存剧本失败' }
  finally { busy.value = false }
}
async function saveEdit() {
  if (busy.value || detailLoading.value || !detail.value || !dialogChanged.value ||
      !title.value.trim() || !draft.value.trim() || title.value.length > 160 || draft.value.length > 200000) return
  busy.value = true; error.value = ''; notice.value = ''
  const changedBody = draft.value !== detail.value.text
  try {
    const result = await updateDramaScript(projectId.value, detail.value.id, detail.value.latest_revision, title.value.trim(), draft.value)
    detail.value = result; title.value = result.title; draft.value = result.text
    notice.value = changedBody ? '正文已保存为独立的新版本；如果修改了当前制作剧本，下游产物需要重新生成。' : '剧本名称已保存，原有提取结果不受影响。'
    await refresh(true)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '保存修改失败，请刷新后重试' }
  finally { busy.value = false }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (processing.value || !files.length) return
  if (files.length > 20 || !files.every(file => /\.(txt|md|markdown)$/i.test(file.name) && file.size <= 800000)) {
    error.value = '每批最多上传 20 份 TXT / MD 剧本，单份不得超过 800 KB。'; return
  }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    library.value = await uploadDramaScripts(projectId.value, files)
    checkedIds.value = []
    notice.value = `已保存 ${files.length} 份剧本；当前制作剧本未改变。`
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '上传失败，可能有部分文件已保存，请刷新核对' }
  finally { await refresh(true); busy.value = false }
}
async function extractSelected() {
  if (processing.value || !selectedCurrentOnly.value || !current.value) return
  if (worldReady.value) { await router.push(`/projects/${projectId.value}/assets`); return }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await extractDramaAssets(projectId.value)
    notice.value = '已为当前剧本启动资产提取；完成后可以前往视觉资产审核。'
    await refresh(true)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '资产提取任务提交失败' }
  finally { busy.value = false }
}
watch(projectId, () => {
  library.value = null; state.value = null; tasks.value = []; checkedIds.value = []
  dialog.value = null; dialogId.value = null; detail.value = null; error.value = ''; notice.value = ''; void refresh()
})
onMounted(() => {
  void refresh()
  timer = window.setInterval(() => { if (!busy.value) void refresh(true) }, 3000)
})
onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer) })
</script>

<template>
  <section class="script-manager" data-testid="script-to-drama-script-library">
    <header class="page-header"><h2>剧本管理</h2><span>共 {{ library?.scripts.length ?? 0 }} 份剧本</span></header>
    <div class="toolbar">
      <div class="toolbar-line">
        <form class="search-form" @submit.prevent="search = keyword"><input v-model="keyword" type="search" aria-label="搜索剧本" placeholder="搜索剧本名称…" /><button type="submit" class="secondary">搜索</button></form>
        <div class="toolbar-actions"><button type="button" :disabled="processing" @click="createScript">＋ 新建剧本</button><label class="upload-button" :class="{ disabled: processing }">批量上传剧本<input type="file" accept=".txt,.md,.markdown" multiple :disabled="processing" @change="upload" /></label></div>
      </div>
      <div class="toolbar-line bulk-line"><label class="select-all"><input type="checkbox" :checked="allFilteredSelected" :disabled="!filtered.length" @change="selectFiltered" /> 全选当前结果</label><span class="selection-count">已选 {{ selected.length }} 份</span><span class="bulk-spacer" /><button type="button" :disabled="processing || !selectedCurrentOnly" @click="extractSelected">{{ selectedCurrentOnly && worldReady ? '审核已提取资产' : '提取资产' }}</button><button type="button" class="danger" disabled title="多剧本安全删除接口完成后开放">批量删除剧本 · 待接入</button></div>
      <p v-if="selected.length && !selectedCurrentOnly" class="helper">当前仅支持提取选中的一份当前制作剧本；批量提取需要下一阶段的独立任务与资产关联。</p>
    </div>
    <p v-if="error" class="message error" role="alert">{{ error }}</p>
    <p v-if="notice" class="message" role="status">{{ notice }}</p>
    <p v-if="latest && ['queued', 'running'].includes(latest.status)" class="message" role="status">{{ latest.task_name }} · {{ latest.status === 'queued' ? '排队中' : `处理进度 ${latest.progress_percent}%` }}</p>
    <p v-if="latest && ['failed', 'interrupted'].includes(latest.status)" class="message error">{{ latest.last_error || '最近一次任务未成功' }}</p>
    <div v-if="loading" class="empty">正在读取剧本库…</div>
    <div v-else-if="!filtered.length" class="empty">{{ library?.scripts.length ? '没有匹配的剧本' : '暂无剧本，点击「新建剧本」或「批量上传剧本」开始。' }}</div>
    <div v-else class="script-grid">
      <article v-for="item in filtered" :key="item.id" class="script-card" :class="{ active: item.is_active, checked: checkedIds.includes(item.id) }">
        <label class="card-check" :aria-label="`选择 ${item.title}`"><input type="checkbox" :checked="checkedIds.includes(item.id)" @change="toggle(item.id)" /></label>
        <button type="button" class="card-content" @click="openDetail(item)"><span class="card-top"><strong>{{ item.title }}</strong><span v-if="item.is_active" class="badge active-badge">当前制作</span></span><span class="excerpt">{{ item.excerpt || '暂无正文摘要' }}</span><span v-if="item.is_active && worldReady" class="asset-tags"><span v-for="name in names('characters')" :key="`c-${name}`">{{ name }}</span><span v-for="name in names('locations')" :key="`l-${name}`">{{ name }}</span><span v-for="name in names('props')" :key="`p-${name}`">{{ name }}</span></span><span class="card-bottom"><span :class="['state', { ready: item.is_active && worldReady }]">{{ status(item) }}</span><span>{{ item.char_count.toLocaleString() }} 字符</span></span></button>
      </article>
    </div>
    <div v-if="dialog" class="overlay" @click.self="closeDialog">
      <section class="detail-dialog" role="dialog" aria-modal="true" :aria-label="dialog === 'new' ? '新建剧本' : '剧本详情'">
        <header class="dialog-header"><div><h3>{{ dialog === 'new' ? '新建剧本' : '剧本详情' }}</h3><small v-if="detail">{{ detail.filename }} · 剧本版本 r{{ detail.latest_revision }}</small></div><button type="button" class="close" aria-label="关闭详情" :disabled="busy" @click="closeDialog">×</button></header>
        <div class="dialog-body"><p v-if="detailLoading" class="helper">正在读取完整剧本…</p><label class="field">剧本名称<input v-model="title" maxlength="160" :disabled="busy || detailLoading" placeholder="输入剧本名称" /></label><label class="field">剧本正文<textarea v-model="draft" rows="13" maxlength="200000" :disabled="busy || detailLoading" placeholder="保留完整场次、动作与对白…" /></label><p class="char-count">{{ draft.length.toLocaleString() }} / 200,000 字符</p>
          <div v-if="dialog === 'detail'" class="related"><div class="related-heading"><strong>关联人物资产</strong><span v-if="detailItem?.is_active && worldReady" class="badge">{{ approved ? '已审核' : '待审核' }}</span></div><p v-if="!detailItem?.is_active">仅当前制作剧本的资产已接入制作流程。此剧本的独立资产关联将在下一阶段接入。</p><p v-else-if="!worldReady">尚未提取资产，提取完成后才会显示人物。</p><template v-else><div class="asset-tags"><span v-for="name in names('characters')" :key="name">{{ name }}</span><span v-if="!names('characters').length">尚未识别人物</span></div><p class="helper">人物关联编辑将在下一阶段接入，当前可前往视觉资产核对已有设定。</p><button type="button" class="secondary" :disabled="processing" @click="router.push(`/projects/${projectId}/assets`)">前往视觉资产</button></template></div>
        </div>
        <footer class="dialog-footer"><button type="button" class="secondary" :disabled="busy" @click="closeDialog">取消</button><button v-if="dialog === 'new'" type="button" :disabled="processing || !dialogChanged || title.length > 160 || draft.length > 200000" @click="saveNew">保存剧本</button><template v-else><button v-if="detailItem && !detailItem.is_active" type="button" class="secondary" :disabled="processing || dialogChanged || detailLoading" @click="useScript(detailItem)">设为当前剧本</button><button v-else-if="detailItem && !worldReady" type="button" class="secondary" :disabled="processing || dialogChanged || detailLoading" @click="checkedIds = [detailItem.id]; extractSelected()">提取资产</button><button type="button" :disabled="busy || detailLoading || !dialogChanged || !title.trim() || !draft.trim() || title.length > 160 || draft.length > 200000" @click="saveEdit">保存修改</button></template></footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.script-manager{display:grid;align-content:start;gap:12px;color:#25344e}.page-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:3px 1px}.page-header h2{font-size:18px;font-weight:800;margin:0}.page-header span,.selection-count,.helper,.char-count{font-size:11px;color:#778198}.toolbar{display:grid;gap:10px;padding:12px 14px;background:#fff;border:1px solid #e3e6ee;border-radius:10px}.toolbar-line{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.toolbar-actions{margin-left:auto;display:flex;align-items:center;gap:8px}.search-form{display:flex;align-items:center;gap:7px}.search-form input{width:235px;max-width:45vw;padding:8px 10px;border:1px solid #dadee8;border-radius:7px;background:#fff;font:inherit;font-size:12px}.bulk-line{border-top:1px solid #edf0f5;padding-top:10px}.select-all{display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer}.select-all input,.card-check input{accent-color:#6551e5}.bulk-spacer{flex:1}.helper{margin:0;line-height:1.5}button,.upload-button{border:0;border-radius:7px;background:#6551e5;color:#fff;font:inherit;font-size:12px;font-weight:700;padding:9px 12px;cursor:pointer;white-space:nowrap}.secondary{background:#f2efff;color:#5744ce;border:1px solid #dcd5ff}.danger{background:#fff0f1;color:#a9404c}.upload-button input{display:none}button:disabled,.upload-button.disabled{opacity:.5;cursor:not-allowed}.script-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.script-card{position:relative;min-width:0;background:#fff;border:1px solid #e0e4eb;border-radius:11px;overflow:hidden}.script-card.active{border-color:#9b8df5}.script-card.checked{box-shadow:0 0 0 2px #e8e3ff}.card-check{position:absolute;z-index:2;right:12px;top:13px;cursor:pointer}.card-check input{width:16px;height:16px;cursor:pointer}.card-content{display:flex;flex-direction:column;align-items:stretch;gap:10px;width:100%;min-height:176px;padding:14px 38px 13px 14px;border:0;border-radius:0;background:transparent;color:inherit;text-align:left;white-space:normal}.card-content:hover{background:#faf9ff}.card-top{display:flex;align-items:center;gap:7px;min-width:0}.card-top strong{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.badge{display:inline-block;padding:3px 6px;border-radius:5px;background:#f0edff;color:#6250ca;font-size:10px;white-space:nowrap}.active-badge{background:#e8f5ec;color:#277642}.excerpt{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden;min-height:51px;font-size:11px;line-height:1.55;color:#69758b;overflow-wrap:anywhere;white-space:pre-wrap}.asset-tags{display:flex;flex-wrap:wrap;gap:5px}.asset-tags span{padding:3px 6px;background:#f2f4f8;border-radius:5px;color:#66728b;font-size:10px}.card-bottom{display:flex;justify-content:space-between;gap:6px;align-items:center;margin-top:auto;color:#8290a5;font-size:10px}.state{color:#8992a4}.state.ready{color:#24814c}.empty{padding:70px 20px;text-align:center;border:1px dashed #d9deea;border-radius:12px;background:#fff;color:#7a869a}.message{margin:0;padding:10px 12px;border:1px solid #ded9fc;background:#f6f4ff;border-radius:8px;font-size:12px;color:#5b46cb}.message.error{background:#fff2f2;color:#b33b49;border-color:#ffdddd}.overlay{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:18px;background:#1b254866}.detail-dialog{display:flex;flex-direction:column;width:min(800px,95vw);max-height:min(780px,92vh);overflow:hidden;background:#fff;border-radius:13px;box-shadow:0 20px 70px #1a234133}.dialog-header,.dialog-footer{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #e7e9ef}.dialog-header h3{margin:0;font-size:17px}.dialog-header small{font-size:11px;color:#8190a5}.dialog-header .close{background:transparent;color:#6d7890;font-size:22px;padding:0 7px}.dialog-body{display:grid;gap:12px;overflow:auto;padding:16px 18px}.field{display:grid;gap:6px;font-size:12px;font-weight:700}.field input,.field textarea{box-sizing:border-box;width:100%;padding:10px 12px;border:1px solid #d9dee9;border-radius:8px;background:#fff;color:#25344e;font:inherit;font-size:12px;font-weight:400}.field textarea{resize:vertical;min-height:260px;line-height:1.6}.char-count{margin:-7px 0 0;text-align:right}.related{display:grid;gap:9px;border-top:1px solid #eaecf1;padding-top:12px}.related-heading{display:flex;align-items:center;gap:9px}.related p{font-size:12px;color:#78849a;margin:0}.related .secondary{justify-self:start}.dialog-footer{justify-content:flex-end;gap:8px;border-top:1px solid #e7e9ef;border-bottom:0}@media(max-width:1080px){.script-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.script-grid{grid-template-columns:1fr}.toolbar-actions{margin-left:0}.search-form input{max-width:calc(100vw - 150px)}.card-content{min-height:155px}}
</style>
