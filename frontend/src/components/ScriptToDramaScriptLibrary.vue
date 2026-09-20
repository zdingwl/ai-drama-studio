<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import { getDramaSource, getDramaState, type ScriptToDramaState } from '@/features/projects/scriptToDrama'
import {
  extractDramaAssets, listDramaScripts, pasteDramaScript, selectDramaScript, uploadDramaScripts,
  type DramaScriptItem, type DramaScriptLibrary,
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
const fullText = ref<string | null>(null)
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
  .filter(task => ['SCRIPT_TO_DRAMA_ASSET_EXTRACTION', 'SCRIPT_TO_DRAMA_PREPRODUCTION', 'SCRIPT_TO_DRAMA_PRODUCTION'].includes(task.task_type ?? ''))
  .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] ?? null)
const processing = computed(() => busy.value || ['queued', 'running'].includes(latest.value?.status ?? ''))
const worldReady = computed(() => state.value?.world.status === 'CURRENT' && state.value?.assets.status === 'CURRENT')
const approved = computed(() => worldReady.value && state.value?.world.content?.review_status === 'APPROVED' && state.value?.assets.content?.review_status === 'APPROVED')
const selectedCurrentOnly = computed(() => selected.value.length === 1 && selected.value[0]?.is_active === true)
const dialogChanged = computed(() => dialog.value === 'new' && title.value.trim().length > 0 && draft.value.trim().length > 0)

function items(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => item !== null && typeof item === 'object' && !Array.isArray(item)) : []
}
function names(kind: 'characters' | 'locations' | 'props'): string[] {
  if (!worldReady.value) return []
  return items(state.value?.world.content?.[kind]).map(item => String(item.name ?? '')).filter(Boolean).slice(0, 5)
}
function status(item: DramaScriptItem): string {
  if (!item.is_active) return '未记录独立提取状态'
  if (latest.value && ['queued', 'running'].includes(latest.value.status) &&
    ['SCRIPT_TO_DRAMA_ASSET_EXTRACTION', 'SCRIPT_TO_DRAMA_PREPRODUCTION'].includes(latest.value.task_type ?? '')) {
    return latest.value.status === 'queued' ? '资产提取排队中' : `资产提取中 · ${latest.value.progress_percent}%`
  }
  if (worldReady.value) return approved.value ? '资产已确认' : '已提取 · 待确认'
  if (latest.value?.status === 'failed' &&
    ['SCRIPT_TO_DRAMA_ASSET_EXTRACTION', 'SCRIPT_TO_DRAMA_PREPRODUCTION'].includes(latest.value.task_type ?? '')) return '资产提取失败'
  return '未提取资产'
}

async function refresh(silent = false) {
  const id = projectId.value
  if (!silent) loading.value = true
  try {
    const [scripts, nextState, nextTasks] = await Promise.all([listDramaScripts(id), getDramaState(id), listProjectTasks(id)])
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
  checkedIds.value = allFilteredSelected.value ? checkedIds.value.filter(id => !ids.includes(id)) : [...new Set([...checkedIds.value, ...ids])]
}
function closeDialog() {
  if (busy.value) return
  if (dialog.value === 'new' && (title.value || draft.value) && !window.confirm('关闭后将丢失尚未保存的新剧本，确定关闭吗？')) return
  dialog.value = null; dialogId.value = null; fullText.value = null; title.value = ''; draft.value = ''
}
function createScript() {
  if (processing.value) return
  dialog.value = 'new'; dialogId.value = null; title.value = ''; draft.value = ''; fullText.value = null; error.value = ''
}
async function openDetail(item: DramaScriptItem) {
  dialog.value = 'detail'; dialogId.value = item.id; title.value = item.title; draft.value = ''; fullText.value = null
  detailLoading.value = item.is_active
  if (!item.is_active) return
  const id = projectId.value
  try {
    const source = await getDramaSource(id)
    if (id === projectId.value && dialogId.value === item.id) fullText.value = source.text ?? ''
  } catch (exc) { if (dialogId.value === item.id) error.value = exc instanceof Error ? exc.message : '读取完整剧本失败' }
  finally { if (dialogId.value === item.id) detailLoading.value = false }
}
async function useScript(item: DramaScriptItem) {
  if (processing.value || item.is_active) return
  if (current.value && worldReady.value && !window.confirm('切换当前剧本会使原有分析、资产、分镜与视频成为历史版本。确认切换吗？')) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    library.value = await selectDramaScript(projectId.value, item.id, library.value?.current_document_id ?? null)
    notice.value = `已将「${item.title}」设为当前制作剧本。`
    await refresh(true)
    if (dialogId.value === item.id) await openDetail({ ...item, is_active: true })
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '切换剧本失败' }
  finally { busy.value = false }
}
async function saveNew() {
  if (processing.value || !dialogChanged.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const next = await pasteDramaScript(projectId.value, title.value.trim(), draft.value)
    library.value = next
    dialog.value = null; title.value = ''; draft.value = ''
    checkedIds.value = []
    notice.value = '新剧本已保存并设为当前制作剧本。提取资产前不会显示人物、场景和道具标签。'
    await refresh(true)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '保存剧本失败' }
  finally { busy.value = false }
}
async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (processing.value || !files.length) return
  if (files.length > 20 || !files.every(file => /\.(txt|md|markdown)$/i.test(file.name))) {
    error.value = '每次最多上传 20 份 UTF-8 编码的 TXT、MD 或 Markdown 剧本。'; return
  }
  if (current.value && worldReady.value && !window.confirm('目前批量上传会将最后一份设为当前剧本，已有制作结果将成为历史版本。确认上传吗？')) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    library.value = await uploadDramaScripts(projectId.value, files)
    checkedIds.value = []
    notice.value = `上传完成：共提交 ${files.length} 份；目前最后一份会被设为当前剧本。`
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '批量上传失败，可能有部分文件已保存' }
  finally { await refresh(true); busy.value = false }
}
async function extractSelected() {
  if (processing.value || !selectedCurrentOnly.value || !current.value) return
  if (worldReady.value) { await router.push(`/projects/${projectId.value}/assets`); return }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    await extractDramaAssets(projectId.value)
    notice.value = '已为当前剧本启动资产提取。请等待完成，再进入视觉资产审核。'
    await refresh(true)
  } catch (exc) { error.value = exc instanceof Error ? exc.message : '资产提取任务提交失败' }
  finally { busy.value = false }
}

watch(projectId, () => {
  library.value = null; state.value = null; tasks.value = []; checkedIds.value = []
  dialog.value = null; dialogId.value = null; error.value = ''; notice.value = ''; void refresh()
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
        <form class="search-form" @submit.prevent="search = keyword"><input v-model="keyword" type="search" aria-label="搜索剧本" placeholder="搜索剧本名称或正文…" /><button type="submit" class="secondary">搜索</button></form>
        <div class="toolbar-actions"><button type="button" :disabled="processing" @click="createScript">＋ 新建剧本</button><label class="upload-button" :class="{ disabled: processing }">批量上传剧本<input type="file" accept=".txt,.md,.markdown" multiple :disabled="processing" @change="upload" /></label></div>
      </div>
      <div class="toolbar-line bulk-line"><label class="select-all"><input type="checkbox" :checked="allFilteredSelected" :disabled="!filtered.length" @change="selectFiltered" /> 全选当前结果</label><span class="selection-count">已选 {{ selected.length }} 份</span><span class="bulk-spacer" /><button type="button" :disabled="processing || !selectedCurrentOnly" @click="extractSelected">{{ selectedCurrentOnly && worldReady ? '审核已提取资产' : '提取资产' }}</button><button type="button" class="danger" disabled title="待多剧本独立版本和安全删除接口接入后开放">批量删除剧本 · 待接入</button></div>
      <p v-if="selected.length && !selectedCurrentOnly" class="helper">当前后端只支持提取一份选中的当前剧本；其他剧本请先在详情中设为当前。多剧本批量提取和删除不会假装成功。</p>
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
      <section class="detail-dialog" role="dialog" aria-modal="true" aria-label="剧本详情">
        <header class="dialog-header"><div><h3>{{ dialog === 'new' ? '新建剧本' : '剧本详情' }}</h3><small v-if="detailItem">{{ detailItem.filename }} · 源版本 r{{ detailItem.latest_revision }}</small></div><button type="button" class="close" aria-label="关闭详情" :disabled="busy" @click="closeDialog">×</button></header>
        <div class="dialog-body"><label class="field">剧本名称<input v-model="title" maxlength="160" :readonly="dialog === 'detail'" :disabled="busy" placeholder="输入剧本名称" /></label><label class="field">剧本正文<textarea v-if="dialog === 'new'" v-model="draft" rows="13" maxlength="200000" :disabled="busy" placeholder="粘贴完整剧本…" /><textarea v-else :value="detailItem?.is_active ? (fullText ?? '') : detailItem?.excerpt ?? ''" rows="13" readonly :disabled="detailLoading" /></label><p class="char-count">{{ dialog === 'new' ? draft.length.toLocaleString() : (detailItem?.char_count ?? 0).toLocaleString() }} / 200,000 字符</p>
          <div v-if="dialog === 'detail'" class="related"><div class="related-heading"><strong>关联人物资产</strong><span v-if="detailItem?.is_active && worldReady" class="badge">{{ approved ? '已审核' : '待审核' }}</span></div><p v-if="!detailItem?.is_active">请先将此剧本设为当前制作剧本，才能读取完整正文与当前资产。独立剧本版本管理尚未接通。</p><p v-else-if="!worldReady">尚未提取资产，提取完成后才能查看关联人物。</p><template v-else><div class="asset-tags"><span v-for="name in names('characters')" :key="name">{{ name }}</span><span v-if="!names('characters').length">尚未识别人物</span></div><button type="button" class="secondary" :disabled="processing" @click="router.push(`/projects/${projectId}/assets`)">在视觉资产页核对人物设定</button></template><p class="helper">现有接口暂不支持在此修改已有剧本正文或跨剧本人物关联；本弹窗不会将更改悄悄另存为一份新剧本。</p></div>
        </div>
        <footer class="dialog-footer"><button type="button" class="secondary" :disabled="busy" @click="closeDialog">关闭</button><button v-if="dialog === 'new'" type="button" :disabled="processing || !dialogChanged" @click="saveNew">保存剧本</button><button v-else-if="detailItem && !detailItem.is_active" type="button" :disabled="processing" @click="useScript(detailItem)">设为当前剧本</button><button v-else-if="detailItem && !worldReady" type="button" :disabled="processing" @click="checkedIds = [detailItem.id]; extractSelected()">提取资产</button></footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.script-manager{display:grid;align-content:start;gap:12px;color:#25344e}.page-header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:3px 1px}.page-header h2{font-size:18px;font-weight:800;margin:0}.page-header span,.selection-count,.helper,.char-count{font-size:11px;color:#778198}.toolbar{display:grid;gap:10px;padding:12px 14px;background:#fff;border:1px solid #e3e6ee;border-radius:10px}.toolbar-line{display:flex;align-items:center;gap:9px;flex-wrap:wrap}.toolbar-actions{margin-left:auto;display:flex;align-items:center;gap:8px}.search-form{display:flex;align-items:center;gap:7px}.search-form input{width:235px;max-width:45vw;padding:8px 10px;border:1px solid #dadee8;border-radius:7px;background:#fff;font:inherit;font-size:12px}.bulk-line{border-top:1px solid #edf0f5;padding-top:10px}.select-all{display:flex;align-items:center;gap:6px;font-size:12px;cursor:pointer}.select-all input,.card-check input{accent-color:#6551e5}.bulk-spacer{flex:1}.helper{margin:0;line-height:1.5}button,.upload-button{border:0;border-radius:7px;background:#6551e5;color:#fff;font:inherit;font-size:12px;font-weight:700;padding:9px 12px;cursor:pointer;white-space:nowrap}.secondary{background:#f2efff;color:#5744ce;border:1px solid #dcd5ff}.danger{background:#fff0f1;color:#a9404c}.upload-button input{display:none}button:disabled,.upload-button.disabled{opacity:.5;cursor:not-allowed}.script-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.script-card{position:relative;min-width:0;background:#fff;border:1px solid #e0e4eb;border-radius:11px;overflow:hidden}.script-card.active{border-color:#9b8df5}.script-card.checked{box-shadow:0 0 0 2px #e8e3ff}.card-check{position:absolute;z-index:2;right:12px;top:13px;cursor:pointer}.card-check input{width:16px;height:16px;cursor:pointer}.card-content{display:flex;flex-direction:column;align-items:stretch;gap:10px;width:100%;min-height:176px;padding:14px 38px 13px 14px;border:0;border-radius:0;background:transparent;color:inherit;text-align:left;white-space:normal}.card-content:hover{background:#faf9ff}.card-top{display:flex;align-items:center;gap:7px;min-width:0}.card-top strong{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.badge{display:inline-block;padding:3px 6px;border-radius:5px;background:#f0edff;color:#6250ca;font-size:10px;white-space:nowrap}.active-badge{background:#e8f5ec;color:#277642}.excerpt{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden;min-height:51px;font-size:11px;line-height:1.55;color:#69758b;overflow-wrap:anywhere;white-space:pre-wrap}.asset-tags{display:flex;flex-wrap:wrap;gap:5px}.asset-tags span{padding:3px 6px;background:#f2f4f8;border-radius:5px;color:#66728b;font-size:10px}.card-bottom{display:flex;justify-content:space-between;gap:6px;align-items:center;margin-top:auto;color:#8290a5;font-size:10px}.state{color:#8992a4}.state.ready{color:#24814c}.empty{padding:70px 20px;text-align:center;border:1px dashed #d9deea;border-radius:12px;background:#fff;color:#7a869a}.message{margin:0;padding:10px 12px;border:1px solid #ded9fc;background:#f6f4ff;border-radius:8px;font-size:12px;color:#5b46cb}.message.error{background:#fff2f2;color:#b33b49;border-color:#ffdddd}.overlay{position:fixed;inset:0;z-index:100;display:grid;place-items:center;padding:18px;background:#1b254866}.detail-dialog{display:flex;flex-direction:column;width:min(800px,95vw);max-height:min(780px,92vh);overflow:hidden;background:#fff;border-radius:13px;box-shadow:0 20px 70px #1a234133}.dialog-header,.dialog-footer{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #e7e9ef}.dialog-header h3{margin:0;font-size:17px}.dialog-header small{font-size:11px;color:#8190a5}.dialog-header .close{background:transparent;color:#6d7890;font-size:22px;padding:0 7px}.dialog-body{display:grid;gap:12px;overflow:auto;padding:16px 18px}.field{display:grid;gap:6px;font-size:12px;font-weight:700}.field input,.field textarea{box-sizing:border-box;width:100%;padding:10px 12px;border:1px solid #d9dee9;border-radius:8px;background:#fff;color:#25344e;font:inherit;font-size:12px;font-weight:400}.field textarea{resize:vertical;min-height:260px;line-height:1.6}.field input[readonly],.field textarea[readonly]{background:#f9fafc}.char-count{margin:-7px 0 0;text-align:right}.related{display:grid;gap:9px;border-top:1px solid #eaecf1;padding-top:12px}.related-heading{display:flex;align-items:center;gap:9px}.related p{font-size:12px;color:#78849a;margin:0}.related .secondary{justify-self:start}.dialog-footer{justify-content:flex-end;gap:8px;border-top:1px solid #e7e9ef;border-bottom:0}@media(max-width:1080px){.script-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){.script-grid{grid-template-columns:1fr}.toolbar-actions{margin-left:0}.search-form input{max-width:calc(100vw - 150px)}.card-content{min-height:155px}}
</style>
