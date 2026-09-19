<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import {
  exportLocalizedScript, getScriptSource, getScriptState, pasteScriptSource,
  runScriptStage, saveLocalizedScript, uploadScriptSource,
  type ScriptLocalizationStateRead, type ScriptSourceRead,
} from '@/features/projects/scriptLocalization'
import type { TaskRead } from '@/features/projects/types'

const props = withDefaults(defineProps<{ mode?: 'source' | 'script' }>(), { mode: 'source' })
const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const source = ref<ScriptSourceRead | null>(null)
const state = ref<ScriptLocalizationStateRead | null>(null)
const tasks = ref<TaskRead[]>([])
const pasteText = ref('')
const targetDraft = ref('')
const editingArtifactId = ref<string | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')
let timer: number | undefined

const latestTask = computed(() => [...tasks.value]
  .filter(item => item.task_type === 'SCRIPT_LOCALIZATION_STAGE')
  .sort((left, right) => +new Date(right.created_at) - +new Date(left.created_at))[0] ?? null)
const processing = computed(() => busy.value || latestTask.value?.status === 'queued' || latestTask.value?.status === 'running')
const analysisReady = computed(() => state.value?.analysis.status === 'CURRENT')
const planReady = computed(() => state.value?.plan.status === 'CURRENT')
const targetReady = computed(() => state.value?.target_script.status === 'CURRENT')
const exportReady = computed(() => state.value?.final_output.status === 'CURRENT')
const analysis = computed(() => object(state.value?.analysis.content?.semantic))
const plan = computed(() => object(state.value?.plan.content?.semantic))
const storyBeats = computed(() => array(analysis.value.story_beats))
const characters = computed(() => array(analysis.value.characters))
const mappings = computed(() => array(plan.value.mappings))
const unresolved = computed(() => Array.isArray(plan.value.unresolved_decisions) ? plan.value.unresolved_decisions as string[] : [])
const hasSource = computed(() => Boolean(source.value?.document_id))
const eligibleForModel = computed(() => hasSource.value && (source.value?.text?.length ?? 0) <= 24000)

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}
function array(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(item => object(item)) : []
}
function statusText(value?: string) {
  return value === 'CURRENT' ? '已生成' : value === 'STALE' ? '上游已变更，需重新生成' : '尚未生成'
}

async function refresh(silent = false) {
  const id = projectId.value
  if (!silent) loading.value = true
  try {
    const [sourceResult, stateResult, taskResult] = await Promise.all([
      getScriptSource(id), getScriptState(id), listProjectTasks(id),
    ])
    if (id !== projectId.value) return
    source.value = sourceResult
    state.value = stateResult
    tasks.value = [...taskResult]
    const target = stateResult.target_script
    if (target.status === 'CURRENT' && target.artifact_id !== editingArtifactId.value) {
      targetDraft.value = String(target.content?.text ?? '')
      editingArtifactId.value = target.artifact_id
    } else if (target.status !== 'CURRENT') {
      targetDraft.value = ''
      editingArtifactId.value = null
    }
  } catch (exc) {
    if (id === projectId.value && !silent) error.value = exc instanceof Error ? exc.message : '读取剧本项目失败'
  } finally {
    if (id === projectId.value && !silent) loading.value = false
  }
}

async function paste() {
  if (processing.value || !pasteText.value.trim()) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await pasteScriptSource(projectId.value, pasteText.value)
    pasteText.value = ''
    notice.value = '原剧本已保存为新的不可变版本。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '保存剧本失败'
  } finally { busy.value = false }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || processing.value) return
  input.value = ''
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await uploadScriptSource(projectId.value, file)
    notice.value = '原剧本已上传并保存。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '上传剧本失败'
  } finally { busy.value = false }
}

async function execute(stage: 'analyze' | 'plan' | 'generate') {
  if (processing.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await runScriptStage(projectId.value, stage)
    notice.value = '任务已提交，正在等待真实模型处理。结果通过校验后才会发布。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '提交任务失败'
  } finally { busy.value = false }
}

async function save() {
  const id = editingArtifactId.value
  if (processing.value || !id || !targetDraft.value.trim()) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await saveLocalizedScript(projectId.value, id, targetDraft.value)
    notice.value = '人工修订已保存为新的目标剧本版本。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '保存目标剧本失败'
  } finally { busy.value = false }
}

async function exportScript() {
  if (processing.value || !targetReady.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const result = await exportLocalizedScript(projectId.value)
    if (result.status !== 'CURRENT' || typeof result.content?.text !== 'string') {
      throw new Error('正式导出结果无效')
    }
    const filename = typeof result.content.filename === 'string' ? result.content.filename : '本土化剧本.md'
    const blob = new Blob([result.content.text], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    try {
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
    } finally { URL.revokeObjectURL(url) }
    notice.value = '已按当前正式目标剧本版本生成并导出 Markdown 文件。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '导出剧本失败'
  } finally { busy.value = false }
}

watch(projectId, () => {
  source.value = null
  state.value = null
  tasks.value = []
  targetDraft.value = ''
  editingArtifactId.value = null
  pasteText.value = ''
  error.value = ''
  notice.value = ''
  void refresh()
})
onMounted(() => {
  void refresh()
  timer = window.setInterval(() => {
    if (latestTask.value?.status === 'queued' || latestTask.value?.status === 'running') void refresh(true)
  }, 2500)
})
onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer) })
</script>

<template>
  <section class="script-workspace" data-testid="script-localization-workspace">
    <header><p class="eyebrow">剧本本土化</p><h2>{{ props.mode === 'source' ? '原剧本' : '本土化剧本' }}</h2><p>原始文本不可变，分析、目标方案和目标剧本分别建立可追溯版本。</p></header>
    <p v-if="error" class="message error" role="alert">{{ error }}</p>
    <p v-if="notice" class="message success" role="status">{{ notice }}</p>
    <p v-if="latestTask && ['failed', 'interrupted'].includes(latestTask.status)" class="message error" role="alert">{{ latestTask.last_error || '上次任务未完成，请检查模型配置后重试。' }}</p>
    <p v-if="latestTask && ['queued', 'running'].includes(latestTask.status)" class="message" role="status">{{ latestTask.task_name }} · {{ latestTask.status === 'queued' ? '排队中' : `运行中 ${latestTask.progress_percent}%` }}</p>
    <p v-if="loading" class="message">正在读取剧本项目…</p>
    <template v-else>
      <section v-if="props.mode === 'source'" class="panel">
        <h3>导入原剧本</h3>
        <p>支持 TXT、MD、Markdown（UTF-8）。上传或粘贴新文本将创建源文件版本；只影响本项目下游结果。</p>
        <label class="file-select">选择剧本文件<input data-testid="script-upload" type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" :disabled="processing" @change="upload" /></label>
        <label class="paste-label" for="script-paste">或粘贴剧本正文</label>
        <textarea id="script-paste" v-model="pasteText" rows="8" maxlength="2000000" placeholder="粘贴原剧本，保存后原始内容不可变…" :disabled="processing" />
        <button type="button" :disabled="processing || !pasteText.trim()" @click="paste">{{ processing ? '处理中…' : '保存粘贴剧本' }}</button>
      </section>
      <section class="panel">
        <h3>当前原剧本</h3>
        <template v-if="source?.document_id">
          <p class="meta">{{ source.filename }} · r{{ source.revision }} · {{ source.text?.length ?? 0 }} 字符</p>
          <p v-if="!eligibleForModel" class="message error">当前单次分析上限为 24000 字符。长文本分块链尚未验收，系统不会截断后冒充全文分析。</p>
          <details :open="props.mode === 'source'"><summary>查看原始内容</summary><pre class="source-text">{{ source.text }}</pre></details>
        </template>
        <p v-else>还没有原剧本，请在「原剧本」页面上传 TXT / MD 或粘贴文字。</p>
      </section>
      <template v-if="props.mode === 'script'">
        <section class="panel">
          <h3>第一步 · 原剧本结构化分析 <small>{{ statusText(state?.analysis.status) }}</small></h3>
          <p>提取人物、场景、故事骨架、节奏及文化锚点；只理解原文，不改写原文。</p>
          <button type="button" :disabled="processing || !eligibleForModel" @click="execute('analyze')">{{ analysisReady ? '重新分析剧本' : '分析剧本' }}</button>
          <template v-if="analysisReady">
            <p class="synopsis">{{ analysis.synopsis }}</p>
            <h4>人物</h4><p v-for="(item, index) in characters" :key="index">{{ item.name }}：{{ item.role }} · {{ item.speech_style }}</p>
            <h4>故事骨架</h4><p v-for="(item, index) in storyBeats" :key="index">{{ item.order }} · {{ item.function }}：{{ item.summary }}</p>
          </template>
        </section>
        <section class="panel">
          <h3>第二步 · 制定本土化方案 <small>{{ statusText(state?.plan.status) }}</small></h3>
          <p>先生成统一的人物、地点、机构、称谓和文化表达映射，锁定原故事因果与人物功能。</p>
          <button type="button" :disabled="processing || !analysisReady" @click="execute('plan')">{{ planReady ? '重新生成本土化方案' : '生成本土化方案' }}</button>
          <template v-if="planReady">
            <p>{{ plan.creative_intent }}</p>
            <h4>全剧映射</h4>
            <p v-for="(item, index) in mappings" :key="index">{{ item.category }}：{{ item.source }} → {{ item.target }}（{{ item.reason }}）</p>
            <p v-if="unresolved.length" class="message error">以下文化冲突需要人工决策，不能直接自动生成正式目标剧本：{{ unresolved.join('；') }}</p>
          </template>
        </section>
        <section class="panel">
          <h3>第三步 · 生成与修订目标剧本 <small>{{ statusText(state?.target_script.status) }}</small></h3>
          <p>遵守已确认的本土化方案和原故事骨架，生成完整目标剧本；支持人工修订并产生新版本。</p>
          <button type="button" :disabled="processing || !planReady || unresolved.length > 0" @click="execute('generate')">{{ targetReady ? '重新生成目标剧本' : '生成本土化剧本' }}</button>
          <template v-if="targetReady">
            <p class="meta">正式目标剧本 · r{{ state?.target_script.revision }}</p>
            <label for="target-script-editor">目标剧本正文（可编辑）</label>
            <textarea id="target-script-editor" v-model="targetDraft" rows="20" maxlength="2000000" :disabled="processing" />
            <button type="button" :disabled="processing || !targetDraft.trim() || targetDraft === String(state?.target_script.content?.text ?? '')" @click="save">保存人工修订</button>
          </template>
        </section>
        <section class="panel">
          <h3>第四步 · 正式剧本导出 <small>{{ exportReady ? '已生成可追溯版本' : '尚未导出' }}</small></h3>
          <p>从当前正式目标剧本生成 Markdown；旧剧本修改后，旧导出版本会自动过期。</p>
          <button type="button" :disabled="processing || !targetReady" @click="exportScript">导出正式剧本（.md）</button>
        </section>
      </template>
    </template>
  </section>
</template>

<style scoped>
.script-workspace{display:grid;gap:14px;max-width:1120px;margin:auto;color:#1b2b42}.script-workspace header,.panel{padding:20px 22px;border:1px solid #e2e8f0;border-radius:12px;background:#fff}.script-workspace header h2{margin:2px 0 8px;font-size:24px}.script-workspace header p,.panel p{color:#67788c;font-size:13px;line-height:1.7}.eyebrow{margin:0;color:#466de2!important;font-weight:800}.panel{display:grid;gap:12px}.panel h3{margin:0;font-size:17px}.panel h3 small{margin-left:10px;color:#5572a6;font-size:12px}.panel h4{margin:2px 0;font-size:13px}.panel .synopsis{padding:10px;background:#f8fafc}.file-select{display:inline-flex;justify-content:center;align-items:center;width:max-content;max-width:100%;padding:10px 14px;border:1px solid #bbc9da;border-radius:8px;cursor:pointer;font-size:13px;font-weight:700}.file-select input{max-width:250px;margin-left:12px}.paste-label,.panel label{font-size:13px;font-weight:700}.panel textarea{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:8px;resize:vertical;font-size:13px;line-height:1.7}.panel button{width:max-content;padding:11px 16px;border:0;border-radius:8px;background:#2878ff;color:white;font-weight:700;cursor:pointer}.panel button:disabled{opacity:.5;cursor:not-allowed}.meta{margin:0}.source-text{max-height:65vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:13px;line-height:1.85}.message{padding:12px 15px;border-radius:8px;background:#f3f6ff}.error{background:#fff1f0;color:#a52626}.success{background:#edfff2;color:#22713d}
</style>
