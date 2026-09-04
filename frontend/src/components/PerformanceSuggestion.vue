<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { startQuietPolling } from '../utils/quietPolling'
const props = defineProps<{ episodeId: string; ordinal: number }>()
const emit = defineEmits<{ close: []; saved: [] }>()
const fields = [{ key: 'performance_text', label: '动作' }, { key: 'expression', label: '表情' }, { key: 'posture', label: '姿态' }, { key: 'gaze', label: '视线' }, { key: 'interaction', label: '人物交互' }]
interface Context { input_fingerprint: string; workflow_revision: string; before: Record<string, string>; reference_url: string | null }
interface Task { id: string; status: string; error_message?: string; result?: { command: Context; suggested?: Record<string, string>; adopted?: boolean } }
const context = ref<Context | null>(null)
const task = ref<Task | null>(null)
const error = ref(''), busy = ref(false), loading = ref(true), selected = ref<string[]>([])
const running = computed(() => ['QUEUED', 'PROCESSING'].includes(task.value?.status || ''))
const suggested = computed(() => task.value?.result?.suggested || {})
const stale = computed(() => Boolean(task.value && context.value && task.value.result?.command.input_fingerprint !== context.value.input_fingerprint))
const before = computed(() => task.value?.result?.command.before || context.value?.before || {})
const storageKey = `performance-suggestion:${props.episodeId}:${props.ordinal}`
const endpoint = `/api/episodes/${encodeURIComponent(props.episodeId)}/shots/${props.ordinal}/performance-suggestion`
let stopPolling: (() => void) | undefined
let disposed = false, commandKey = crypto.randomUUID()
async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: unknown }
    throw new Error(typeof body.detail === 'string' ? body.detail : `请求失败（${response.status}）`)
  }
  return response.json() as Promise<T>
}
function remember(id: string): void { try { localStorage.setItem(storageKey, id) } catch { /* 不影响当前任务 */ } }
function remembered(): string | null { try { return localStorage.getItem(storageKey) } catch { return null } }
function receive(value: Task): void {
  if (disposed) return
  const wasRunning = running.value
  task.value = value
  if (value.status === 'FAILED') error.value = value.error_message || 'AI 分析失败，请检查模型运行状态后重试'
  if (!running.value) {
    stopPolling?.()
    if (wasRunning || !selected.value.length) selected.value = fields.filter(f => value.result?.suggested?.[f.key] && value.result.suggested[f.key] !== value.result.command.before[f.key]).map(f => f.key)
  }
}
function poll(): void {
  stopPolling?.()
  stopPolling = startQuietPolling(async signal => {
    if (task.value && running.value) receive(await request<Task>(`/api/performance-suggestions/${task.value.id}`, { signal }))
  }, () => document.visibilityState === 'visible' && running.value, 3000)
}
async function generate(): Promise<void> {
  if (!context.value || busy.value || running.value) return
  busy.value = true; error.value = ''
  try {
    const value = await request<Task>(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': commandKey }, body: JSON.stringify({ input_fingerprint: context.value.input_fingerprint, workflow_revision: context.value.workflow_revision }) })
    remember(value.id); receive(value); if (!disposed && running.value) poll()
  } catch (e) { error.value = e instanceof Error ? e.message : '启动失败' }
  finally { busy.value = false }
}
async function retry(): Promise<void> {
  error.value = ''; busy.value = true
  try {
    context.value = await request<Context>(endpoint)
    commandKey = crypto.randomUUID(); task.value = null; selected.value = []
  } catch (e) { error.value = e instanceof Error ? e.message : '读取失败'; return }
  finally { busy.value = false }
  await generate()
}
async function adopt(): Promise<void> {
  if (!task.value || !selected.value.length || busy.value || stale.value) return
  busy.value = true; error.value = ''
  try {
    await request(`/api/performance-suggestions/${task.value.id}/adopt`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ fields: selected.value }) })
    if (!disposed) emit('saved')
  } catch (e) { error.value = e instanceof Error ? e.message : '保存失败' }
  finally { busy.value = false }
}
onMounted(async () => {
  try {
    context.value = await request<Context>(endpoint)
    const id = remembered()
    if (id) { receive(await request<Task>(`/api/performance-suggestions/${encodeURIComponent(id)}`)); if (!disposed && running.value) poll() }
  } catch (e) { error.value = e instanceof Error ? e.message : '读取失败' }
  finally { loading.value = false }
})
onBeforeUnmount(() => { disposed = true; stopPolling?.() })
</script>

<template>
  <Teleport to="body">
    <div class="performance-mask" @click.self="!busy && emit('close')">
      <section class="performance-dialog" role="dialog" aria-modal="true" aria-label="AI 补充动作与表演">
        <header><div><h2>AI 补充动作与表演 · Shot {{ String(ordinal).padStart(2, '0') }}</h2><p>只分析当前镜头。人物、对白、说话人和时间范围保持不变。</p></div><button :disabled="busy" aria-label="关闭补充窗口" @click="emit('close')">×</button></header>
        <p v-if="error" class="performance-error" role="alert">{{ error }}</p>
        <p v-if="stale" class="performance-error">镜头内容已更新，这份建议不能采用。请重新生成。</p>
        <div class="performance-body">
          <div class="performance-reference"><video v-if="context?.reference_url" :src="context.reference_url" controls playsinline preload="metadata"></video><p>请对照原视频核对。看不清的内容不补写，无明显变化可如实保留。</p></div>
          <div class="performance-comparison">
            <p v-if="loading">读取当前镜头…</p>
            <p v-else-if="running" role="status">正在分析当前镜头… 可以关闭窗口，稍后重新打开查看；不会自动采用。</p>
            <p v-else-if="task?.result?.adopted" role="status">这份建议已采用。再次补充将基于最新内容生成。</p>
            <p v-else-if="task?.status === 'READY' && !Object.keys(suggested).length">模型没有提供可用的补充证据，原内容保持不变。</p>
            <div class="performance-columns"><span>当前内容</span><span>AI 建议（勾选采用）</span></div>
            <div v-for="field in fields" :key="field.key" class="performance-field"><strong>{{ field.label }}</strong><div><p>{{ before[field.key] || '未填写' }}</p><label><input v-if="suggested[field.key]" v-model="selected" type="checkbox" :value="field.key" :disabled="busy || stale || task?.result?.adopted" /><span>{{ suggested[field.key] || (running ? '分析中…' : task?.status === 'READY' ? '没有补充证据，保留原值' : '尚未生成') }}</span></label></div></div>
          </div>
        </div>
        <footer><span>建议不是正式事实；采用后才保存，并重新检查内容质量。</span><button :disabled="busy" @click="emit('close')">关闭</button><button v-if="!task" :disabled="loading || busy || !context" @click="generate">{{ busy ? '启动中…' : '生成补充建议' }}</button><button v-else :disabled="running || busy" @click="retry">重新生成</button><button class="performance-primary" :disabled="busy || running || stale || task?.status !== 'READY' || !selected.length || task?.result?.adopted" @click="adopt">{{ busy && task?.status === 'READY' ? '保存中…' : '采用所选建议' }}</button></footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.performance-mask{position:fixed;inset:0;z-index:1400;background:#17243c88;display:flex;align-items:center;justify-content:center;padding:24px}
.performance-dialog{background:white;color:#243653;border-radius:16px;width:min(1100px,100%);max-height:92vh;display:flex;flex-direction:column;box-shadow:0 20px 70px #12234340;font-size:14px}
header{padding:22px 26px;display:flex;justify-content:space-between;align-items:start;border-bottom:1px solid #e4eaf3}h2{margin:0;font-size:19px}p{line-height:1.6;margin:8px 0;color:#62738c}button{border:1px solid #cfdbee;border-radius:7px;background:white;color:#245cbb;padding:9px 14px;cursor:pointer}button:disabled{opacity:.45;cursor:default}header button{font-size:23px;padding:0 10px}
.performance-body{display:grid;grid-template-columns:minmax(230px,.75fr) minmax(0,1.5fr);gap:24px;padding:22px 26px;overflow:auto}.performance-reference video{width:100%;max-height:420px;background:#101824;border-radius:9px}.performance-reference p{font-size:12px}.performance-comparison{min-width:0}.performance-columns{display:grid;grid-template-columns:1fr 1fr;gap:18px;font-size:12px;color:#70819b;padding-bottom:8px}.performance-field{border-top:1px solid #e5ebf4;padding:12px 0}.performance-field strong{font-size:13px}.performance-field>div{display:grid;grid-template-columns:1fr 1fr;gap:18px}.performance-field p{margin:8px 0;white-space:pre-wrap;overflow-wrap:anywhere}.performance-field label{display:flex;align-items:flex-start;gap:8px;margin-top:8px;line-height:1.6;white-space:pre-wrap;overflow-wrap:anywhere}.performance-field input{width:16px;height:16px;flex:none;margin-top:3px;accent-color:#2265ed}.performance-error{background:#fff2f2;color:#b53039;padding:10px 26px;margin:0}footer{border-top:1px solid #e4eaf3;padding:16px 26px;display:flex;gap:10px;align-items:center}footer span{margin-right:auto;font-size:12px;color:#728199;max-width:40%}.performance-primary{background:#2368f5;color:white;border-color:#2368f5}@media(max-width:760px){.performance-mask{padding:10px}.performance-body{grid-template-columns:1fr}.performance-reference video{max-height:220px}footer{flex-wrap:wrap}footer span{max-width:100%;width:100%}}
</style>
