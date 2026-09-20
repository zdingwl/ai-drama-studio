<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import { getDramaState, runDramaStage, type ScriptToDramaState } from '@/features/projects/scriptToDrama'
import { listDramaScripts, pasteDramaScript, selectDramaScript, uploadDramaScripts,
  type DramaScriptItem, type DramaScriptLibrary } from '@/features/projects/scriptToDramaLibrary'
import type { TaskRead } from '@/features/projects/types'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.id ?? ''))
const library = ref<DramaScriptLibrary | null>(null)
const state = ref<ScriptToDramaState | null>(null)
const tasks = ref<TaskRead[]>([])
const keyword = ref('')
const selectedId = ref<string | null>(null)
const createOpen = ref(false)
const title = ref('')
const draft = ref('')
const busy = ref(false)
const loading = ref(true)
const error = ref('')
const notice = ref('')
let timer: number | undefined

const latest = computed(() => [...tasks.value]
  .filter(task => ['SCRIPT_TO_DRAMA_PREPRODUCTION', 'SCRIPT_TO_DRAMA_PRODUCTION'].includes(task.task_type ?? ''))
  .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] ?? null)
const processing = computed(() => busy.value || ['queued', 'running'].includes(latest.value?.status ?? ''))
const current = computed(() => library.value?.scripts.find(item => item.is_active) ?? null)
const selected = computed(() => library.value?.scripts.find(item => item.id === selectedId.value) ?? null)
const filtered = computed(() => (library.value?.scripts ?? []).filter(item =>
  `${item.title} ${item.filename} ${item.excerpt}`.toLocaleLowerCase().includes(keyword.value.trim().toLocaleLowerCase()),
))
const analysisReady = computed(() => state.value?.analysis.status === 'CURRENT')
const worldReady = computed(() => state.value?.world.status === 'CURRENT')

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
    if (!selectedId.value || !scripts.scripts.some(item => item.id === selectedId.value)) {
      selectedId.value = scripts.scripts.find(item => item.is_active)?.id ?? scripts.scripts[0]?.id ?? null
    }
  } catch (exc) {
    if (id === projectId.value) error.value = exc instanceof Error ? exc.message : '读取剧本库失败'
  } finally { if (id === projectId.value && !silent) loading.value = false }
}

function changeError(exc: unknown, fallback: string) {
  error.value = exc instanceof Error ? exc.message : fallback
}

async function selectScript(item: DramaScriptItem) {
  if (processing.value || item.is_active) return
  if (current.value && (analysisReady.value || worldReady.value) && !window.confirm(
    '切换正式剧本会使当前剧本的分析、资产、分镜和视频变为历史版本。原文与历史产物仍保留。确定切换吗？',
  )) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    library.value = await selectDramaScript(projectId.value, item.id, library.value?.current_document_id ?? null)
    selectedId.value = item.id
    notice.value = '已选为当前制作剧本。旧下游结果保留为历史版本，但不可作为新剧本的正式结果。'
    await refresh(true)
  } catch (exc) { changeError(exc, '切换剧本失败，请刷新后重试') }
  finally { busy.value = false }
}

async function paste() {
  if (processing.value || !title.value.trim() || !draft.value.trim()) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const next = await pasteDramaScript(projectId.value, title.value.trim(), draft.value)
    library.value = next
    selectedId.value = next.scripts.find(item => item.is_active)?.id ?? null
    createOpen.value = false; title.value = ''; draft.value = ''
    notice.value = '剧本已加入库并选为当前剧本；旧结果已按来源版本隔离。'
    await refresh(true)
  } catch (exc) { changeError(exc, '新建剧本失败') }
  finally { busy.value = false }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  if (processing.value || !files.length) return
  if (files.length > 20) { error.value = '每批最多上传 20 份剧本，请分批上传。'; return }
  if (!files.every(file => /\.(txt|md|markdown)$/i.test(file.name))) {
    error.value = '只支持 UTF-8 编码的 TXT、MD、Markdown 文件。'; return
  }
  if (current.value && (analysisReady.value || worldReady.value) && !window.confirm(
    '批量导入会将最后一份剧本设为当前剧本，现有分析与生成产物将保留为历史版本。确定继续吗？',
  )) return
  busy.value = true; error.value = ''; notice.value = ''
  try {
    library.value = await uploadDramaScripts(projectId.value, files)
    selectedId.value = library.value.scripts.find(item => item.is_active)?.id ?? null
    notice.value = `已导入 ${files.length} 份剧本；最后一份为当前制作剧本。可在卡片中切换。`
  } catch (exc) {
    changeError(exc, '导入失败，可能部分文件已保存，请刷新后核对。')
  } finally { await refresh(true); busy.value = false }
}

async function openProduction() {
  if (processing.value || !current.value) return
  if (worldReady.value) { await router.push(`/projects/${projectId.value}/assets`); return }
  busy.value = true; error.value = ''; notice.value = ''
  try {
    if (!analysisReady.value) {
      await runDramaStage(projectId.value, 'analyze')
      notice.value = '已启动原剧本解析。解析完成后进入「目标世界」提取人物、场景和道具。'
      await router.push(`/projects/${projectId.value}/script`)
    } else {
      await runDramaStage(projectId.value, 'world')
      notice.value = '已启动目标世界与资产定义提取。'
      await router.push(`/projects/${projectId.value}/assets`)
    }
  } catch (exc) { changeError(exc, '启动资产提取失败') }
  finally { busy.value = false }
}

watch(projectId, () => {
  library.value = null; state.value = null; tasks.value = []; selectedId.value = null
  error.value = ''; notice.value = ''; createOpen.value = false
  void refresh()
})
onMounted(() => {
  void refresh()
  timer = window.setInterval(() => {
    if (latest.value?.status === 'queued' || latest.value?.status === 'running') void refresh(true)
  }, 2500)
})
onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer) })
</script>

<template>
  <section class="script-shelf" data-testid="script-to-drama-script-library">
    <header class="panel shelf-header">
      <div><p class="eyebrow">剧本生成短剧 · 剧本管理</p><h2>剧本库</h2><p>先管理和选择正式剧本，再解析剧情、提取资产、制作分镜与生成视频。</p></div>
      <div class="header-actions">
        <button type="button" :disabled="processing" @click="createOpen = !createOpen">{{ createOpen ? '收起新建' : '+ 新建剧本' }}</button>
        <label class="upload-button" :class="{ disabled: processing }">批量上传剧本 <input type="file" accept=".txt,.md,.markdown" multiple :disabled="processing" @change="upload" /></label>
      </div>
    </header>
    <p v-if="error" class="message error" role="alert">{{ error }}</p>
    <p v-if="notice" class="message" role="status">{{ notice }}</p>
    <p v-if="latest && ['queued', 'running'].includes(latest.status)" class="message">{{ latest.task_name }} · {{ latest.status === 'queued' ? '排队中' : `处理进度 ${latest.progress_percent}%` }}</p>
    <p v-if="latest && ['failed', 'interrupted'].includes(latest.status)" class="message error">{{ latest.last_error || '最近任务未成功' }}</p>
    <section v-if="createOpen" class="panel create-panel">
      <h3>新建剧本</h3><label>剧本名称<input v-model="title" maxlength="160" placeholder="例如：第一集 · 初遇" :disabled="processing" /></label>
      <label>完整剧本内容<textarea v-model="draft" rows="9" maxlength="200000" placeholder="保留场景标题、人物、动作与对白…" :disabled="processing" /></label>
      <div class="row-actions"><span>{{ draft.length.toLocaleString() }} / 200,000 字符</span><button type="button" :disabled="processing || !title.trim() || !draft.trim()" @click="paste">保存并选用</button></div>
    </section>
    <div v-if="loading" class="panel">正在读取剧本库…</div>
    <template v-else>
      <section class="panel toolbar">
        <label class="search-label">搜索剧本<input v-model="keyword" type="search" placeholder="按剧本名称或内容搜索…" /></label>
        <span>共 {{ library?.scripts.length ?? 0 }} 份 · 选用 {{ current?.title ?? '无' }}</span>
        <button type="button" :disabled="processing || !current || (current.char_count > 200000)" @click="openProduction">{{ worldReady ? '查看已提取资产' : analysisReady ? '提取人物 / 场景 / 道具' : '解析所选剧本' }}</button>
      </section>
      <p class="hint">此项目可以保存多份候选剧本，但同一时间只制作一份「当前剧本」。切换后旧产物保留历史、不与新剧本混用。</p>
      <div v-if="!filtered.length" class="panel empty">{{ library?.scripts.length ? '没有匹配的剧本' : '剧本库为空。点击「新建剧本」或批量上传 TXT / MD 开始。' }}</div>
      <div v-else class="script-grid">
        <article v-for="item in filtered" :key="item.id" class="script-card" :class="{ active: item.is_active, selected: item.id === selectedId }">
          <div class="card-head"><h3>{{ item.title }}</h3><span v-if="item.is_active" class="badge">当前制作</span></div>
          <p class="excerpt">{{ item.excerpt || '暂无内容预览' }}</p>
          <div class="card-meta"><span>{{ item.char_count.toLocaleString() }} 字符</span><span>源版本 r{{ item.latest_revision }}</span></div>
          <div class="card-actions"><button type="button" class="secondary" @click="selectedId = item.id">{{ selectedId === item.id ? '正在预览' : '查看内容' }}</button><button v-if="!item.is_active" type="button" :disabled="processing" @click="selectScript(item)">设为当前剧本</button><button v-else type="button" :disabled="processing" @click="openProduction">继续制作</button></div>
        </article>
      </div>
      <section v-if="selected" class="panel selected-detail">
        <div class="detail-top"><div><h3>{{ selected.title }}</h3><p>{{ selected.filename }} · {{ selected.char_count.toLocaleString() }} 字符</p></div><button type="button" class="secondary" @click="selectedId = null">关闭预览</button></div>
        <p class="hint">显示前 200 字符摘要。完整原文仅在设为当前剧本后进入「剧本分析」页面读取，防止编辑错版本。</p>
        <pre>{{ selected.excerpt }}</pre>
        <button v-if="!selected.is_active" type="button" :disabled="processing" @click="selectScript(selected)">选用这份剧本</button>
      </section>
    </template>
  </section>
</template>

<style scoped>
.script-shelf{display:grid;gap:14px;max-width:1200px;margin:0 auto;color:#24344e}.panel,.script-card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:19px 21px}.shelf-header{display:flex;justify-content:space-between;align-items:center;gap:20px;flex-wrap:wrap}.eyebrow{font-size:12px;color:#466de2;font-weight:750}.shelf-header h2{font-size:24px;margin:6px 0}.shelf-header p,.hint{color:#61718a;font-size:13px;line-height:1.6;margin:0}.header-actions,.card-actions,.row-actions,.detail-top{display:flex;align-items:center;gap:10px;flex-wrap:wrap}.header-actions{justify-content:flex-end}button,.upload-button{font:inherit;cursor:pointer;border:1px solid #2878ff;background:#2878ff;color:#fff;border-radius:8px;padding:9px 12px;font-size:13px}.secondary{color:#375b94;background:#f5f8ff;border-color:#d7e3fb}button:disabled,.upload-button.disabled{opacity:.55;cursor:not-allowed}.upload-button input{display:none}.create-panel{display:grid;gap:13px}.create-panel h3,.selected-detail h3{margin:0;font-size:17px}.create-panel label{display:grid;gap:6px;font-size:13px;font-weight:650}.create-panel input,.create-panel textarea,.toolbar input{width:100%;box-sizing:border-box;padding:10px;border:1px solid #cfdaec;border-radius:8px;font:inherit;font-weight:400;color:#24344e;background:#fff}.create-panel textarea{resize:vertical;min-height:170px}.row-actions{justify-content:space-between}.row-actions span,.toolbar span,.card-meta{font-size:12px;color:#657590}.toolbar{display:flex;justify-content:space-between;gap:12px;align-items:end;flex-wrap:wrap}.search-label{display:grid;gap:5px;min-width:230px;flex:1;font-size:12px;color:#657590}.script-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px}.script-card{display:grid;gap:11px;min-height:194px}.script-card.active{border-color:#7ca2ef;box-shadow:0 0 0 2px #eaf0ff}.card-head{display:flex;justify-content:space-between;align-items:start;gap:8px}.card-head h3{margin:0;font-size:16px;overflow-wrap:anywhere}.badge{border-radius:6px;background:#e9f0ff;color:#345ac2;padding:3px 7px;font-size:11px;white-space:nowrap}.excerpt{font-size:13px;line-height:1.6;color:#475a75;overflow:hidden;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;min-height:57px;margin:0}.card-meta{display:flex;gap:10px;flex-wrap:wrap}.card-actions{margin-top:auto}.card-actions button{padding:7px 9px;font-size:12px}.selected-detail{display:grid;gap:8px}.detail-top{justify-content:space-between}.detail-top p{margin:6px 0;color:#657590;font-size:12px}.selected-detail pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f6f8fc;border-radius:8px;padding:15px;font:13px/1.7 inherit;max-height:250px;overflow:auto}.empty{text-align:center;padding:52px 20px;color:#657590}.message{padding:11px 13px;background:#e9f1ff;border:1px solid #d7e5ff;border-radius:8px;color:#284d91;font-size:13px}.message.error{background:#fff1f2;color:#a52840;border-color:#ffdce2}@media(max-width:700px){.panel,.script-card{padding:15px}.shelf-header{align-items:stretch}.header-actions{justify-content:flex-start}.script-grid{grid-template-columns:1fr}}
</style>
