<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import {
  getDramaSource, getDramaState, pasteDramaSource, runDramaStage, uploadDramaSource,
  type ScriptToDramaSource, type ScriptToDramaState,
} from '@/features/projects/scriptToDrama'
import type { TaskRead } from '@/features/projects/types'

const props = withDefaults(defineProps<{ mode?: 'source' | 'script' | 'assets' | 'storyboard' | 'generation' }>(), { mode: 'source' })
const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const source = ref<ScriptToDramaSource | null>(null)
const state = ref<ScriptToDramaState | null>(null)
const tasks = ref<TaskRead[]>([])
const draft = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')
let timer: number | undefined

const latest = computed(() => [...tasks.value]
  .filter(item => item.task_type === 'SCRIPT_TO_DRAMA_PREPRODUCTION')
  .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] ?? null)
const processing = computed(() => busy.value || latest.value?.status === 'queued' || latest.value?.status === 'running')
const analysisReady = computed(() => state.value?.analysis.status === 'CURRENT')
const worldReady = computed(() => state.value?.world.status === 'CURRENT')
const storyboardReady = computed(() => state.value?.storyboard.status === 'CURRENT')
const unresolved = computed(() => arrayOfStrings(state.value?.world.content?.unresolved_decisions))
const sourceReady = computed(() => Boolean(source.value?.document_id) && (source.value?.text?.length ?? 0) <= 200_000)

function object(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {}
}
function objects(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(object) : []
}
function arrayOfStrings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}
function label(status: string | undefined): string {
  return status === 'CURRENT' ? '已生成' : status === 'STALE' ? '原文或上游已更新，需要重新制作' : '尚未生成'
}

async function refresh(silent = false) {
  const id = projectId.value
  if (!silent) loading.value = true
  try {
    const [s, p, t] = await Promise.all([getDramaSource(id), getDramaState(id), listProjectTasks(id)])
    if (id !== projectId.value) return
    source.value = s
    state.value = p
    tasks.value = [...t]
  } catch (exc) {
    if (id === projectId.value && !silent) error.value = exc instanceof Error ? exc.message : '读取剧本项目失败'
  } finally {
    if (id === projectId.value && !silent) loading.value = false
  }
}

async function paste() {
  if (processing.value || !draft.value.trim()) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await pasteDramaSource(projectId.value, draft.value)
    draft.value = ''
    notice.value = '原剧本已经保存为新的不可变版本。'
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
    await uploadDramaSource(projectId.value, file)
    notice.value = '原剧本已上传，原文件保留为独立版本。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '上传失败'
  } finally { busy.value = false }
}

async function execute(stage: 'analyze' | 'world' | 'storyboard') {
  if (processing.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await runDramaStage(projectId.value, stage)
    notice.value = '后台任务已提交，将按分段执行；只有全部分段通过校验才发布正式结果。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '提交任务失败'
  } finally { busy.value = false }
}

watch(projectId, () => {
  source.value = null; state.value = null; tasks.value = []; draft.value = ''; error.value = ''; notice.value = ''
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
  <section class="drama-workspace" data-testid="script-to-drama-workspace">
    <header class="panel"><p class="eyebrow">剧本生成短剧</p><h2>从剧本到镜头计划</h2><p>文本输入、世界设定与导演分镜独立于复刻短剧；资产图片和真实视频生成尚未接入此项目，绝不把计划冒充成片。</p></header>
    <p v-if="error" class="message error" role="alert">{{ error }}</p>
    <p v-if="notice" class="message" role="status">{{ notice }}</p>
    <p v-if="latest && ['failed', 'interrupted'].includes(latest.status)" class="message error" role="alert">{{ latest.last_error || '任务未完成，可在检查模型配置后重新提交。' }}</p>
    <p v-if="latest && ['queued', 'running'].includes(latest.status)" class="message" role="status">{{ latest.task_name }} · {{ latest.status === 'queued' ? '排队中' : `已处理 ${latest.progress_percent}%` }}</p>
    <p v-if="loading" class="message">正在读取…</p>
    <template v-else>
      <section v-if="props.mode === 'source'" class="panel">
        <h3>第一步 · 导入原剧本</h3>
        <p>TXT / MD（UTF-8），或粘贴原剧本。当前分段工作流上限为 200,000 字符；每段完整保存，超限不会截断原文。</p>
        <label>选择文件 <input type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" :disabled="processing" @change="upload" /></label>
        <label for="drama-script-text">或粘贴剧本</label>
        <textarea id="drama-script-text" v-model="draft" rows="10" maxlength="200000" placeholder="保留原始场景、对白和动作…" :disabled="processing" />
        <button type="button" :disabled="processing || !draft.trim()" @click="paste">保存原剧本</button>
      </section>
      <section class="panel">
        <h3>当前原剧本</h3>
        <template v-if="source?.document_id">
          <p>{{ source.filename }} · r{{ source.revision }} · {{ source.text?.length ?? 0 }} 字符</p>
          <p v-if="!sourceReady" class="message error">此份文件超过当前单文档安全上限，需按集拆分；原文仍已保留，不会被静默截断。</p>
          <details :open="props.mode === 'source'"><summary>查看完整原文</summary><pre>{{ source.text }}</pre></details>
        </template>
        <p v-else>尚无原剧本，请先在「原剧本」页面上传或粘贴内容。</p>
      </section>
      <section v-if="props.mode === 'script'" class="panel">
        <h3>第二步 · 逐段结构分析 <small>{{ label(state?.analysis.status) }}</small></h3>
        <p>复用现有剧本分析 Skill 与长文本检查点；分析结果不会修改原文。</p>
        <button type="button" :disabled="processing || !sourceReady" @click="execute('analyze')">解析完整剧本</button>
        <template v-if="analysisReady">
          <p>{{ object(state?.analysis.content?.semantic).synopsis }}</p>
          <h4>人物</h4>
          <p v-for="(item, i) in objects(object(state?.analysis.content?.semantic).characters)" :key="i">{{ item.name }}：{{ item.role }}</p>
          <h4>故事节奏</h4>
          <p v-for="(item, i) in objects(object(state?.analysis.content?.semantic).story_beats)" :key="i">{{ item.order }} · {{ item.function }}：{{ item.summary }}</p>
        </template>
      </section>
      <section v-if="props.mode === 'assets'" class="panel">
        <h3>第三步 · 目标世界与资产定义 <small>{{ label(state?.world.status) }}</small></h3>
        <p>定义人物、场景与重要道具的稳定 ID；本阶段只有结构化资产卡，不生成图片。</p>
        <button type="button" :disabled="processing || !analysisReady" @click="execute('world')">生成目标世界与资产定义</button>
        <template v-if="worldReady">
          <p v-if="unresolved.length" class="message error">以下冲突需人工核定，本版本暂不能生成正式分镜：{{ unresolved.join('；') }}</p>
          <template v-for="kind in ['characters', 'locations', 'props']" :key="kind">
            <h4>{{ { characters: '人物', locations: '场景', props: '道具' }[kind as 'characters' | 'locations' | 'props'] }}</h4>
            <p v-for="(item, i) in objects(state?.world.content?.[kind])" :key="i">{{ item.id }} · {{ item.name }}：{{ item.visual_description }}</p>
          </template>
        </template>
      </section>
      <section v-if="props.mode === 'storyboard'" class="panel">
        <h3>第四步 · 导演分镜计划 <small>{{ label(state?.storyboard.status) }}</small></h3>
        <p>逐段回指源剧本，检查人物/场景/道具引用与镜头连续性；分镜预估时长不等于实际音频时长。</p>
        <button type="button" :disabled="processing || !worldReady || unresolved.length > 0" @click="execute('storyboard')">生成导演分镜</button>
        <template v-if="storyboardReady">
          <article v-for="(shot, i) in objects(state?.storyboard.content?.shots)" :key="i" class="shot">
            <h4>{{ shot.shot_id }} · 来源第 {{ shot.source_chunk_index }} 段 · {{ shot.shot_size }}</h4>
            <p>原文：{{ shot.source_quote }}</p>
            <p>动作：{{ shot.visible_action }}</p>
            <p>构图/机位：{{ shot.composition }} · {{ shot.camera_angle }} · {{ shot.camera_motion }}</p>
            <p>对白/旁白：{{ shot.dialogue_or_voiceover }} · 估计 {{ shot.estimated_seconds }} 秒</p>
          </article>
        </template>
      </section>
      <section v-if="props.mode === 'generation'" class="panel">
        <h3>视频生成</h3>
        <p>此项目暂只提供原剧本理解、目标世界/资产定义和可审阅的导演分镜；图片首帧、模型专属提示词、真实 H3 调用、人工选片与成片功能尚未接入，不调用复刻短剧的专属 API 冒充完成。</p>
        <p v-if="storyboardReady">导演分镜已生成，当前可先检查镜头计划和人物、场景连续性。</p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.drama-workspace{display:grid;gap:14px;max-width:1100px;margin:auto;color:#1b2b42}.panel{padding:20px 22px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;display:grid;gap:10px}.panel h2,.panel h3,.panel h4,.panel p{margin:0}.panel h2{font-size:24px}.panel h3{font-size:18px}.panel h4{font-size:14px}.panel p{font-size:13px;line-height:1.7;color:#56677d}.panel small{font-size:12px;color:#5572a6}.eyebrow{font-size:13px;font-weight:800;color:#466de2!important}.panel textarea{width:100%;min-height:100px;padding:12px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px;line-height:1.7}.panel button{width:max-content;padding:10px 14px;border:0;border-radius:8px;background:#2878ff;color:#fff;font-weight:700;cursor:pointer}.panel button:disabled{opacity:.5;cursor:not-allowed}.panel pre{max-height:60vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;border-radius:8px;background:#f8fafc}.panel details{min-width:0}.message{padding:12px 14px;background:#f2f5ff;border-radius:8px;font-size:13px}.error{background:#fff0ed;color:#ae2929}.shot{padding:12px;border:1px solid #e2e8f0;border-radius:9px;display:grid;gap:6px}
</style>
