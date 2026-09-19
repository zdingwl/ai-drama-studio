<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import {
  acceptDramaGenerated, dramaMediaUrl, getDramaSource, getDramaState, pasteDramaSource,
  runDramaProductionStage, runDramaStage, uploadDramaSource,
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
  .filter(item => ['SCRIPT_TO_DRAMA_PREPRODUCTION', 'SCRIPT_TO_DRAMA_PRODUCTION'].includes(item.task_type))
  .sort((a, b) => +new Date(b.created_at) - +new Date(a.created_at))[0] ?? null)
const processing = computed(() => busy.value || latest.value?.status === 'queued' || latest.value?.status === 'running')
const analysisReady = computed(() => state.value?.analysis.status === 'CURRENT')
const worldReady = computed(() => state.value?.world.status === 'CURRENT')
const storyboardReady = computed(() => state.value?.storyboard.status === 'CURRENT')
const assetImagesReady = computed(() => state.value?.asset_images.status === 'CURRENT')
const promptsReady = computed(() => state.value?.prompts.status === 'CURRENT')
const generatedReady = computed(() => state.value?.generated_video.status === 'CURRENT')
const selectionReady = computed(() => state.value?.selection.status === 'CURRENT')
const finalReady = computed(() => state.value?.final_output.status === 'CURRENT')
const generatedClips = computed(() => objects(state.value?.generated_video.content?.clips))
const promptSegments = computed(() => objects(state.value?.prompts.content?.segments))
const generatedArtifactId = computed(() => state.value?.generated_video.artifact_id ?? null)
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

async function executeProduction(stage: 'asset_images' | 'prompts' | 'generate' | 'post') {
  if (processing.value) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await runDramaProductionStage(projectId.value, stage)
    notice.value = '生产任务已提交。只有完整通过版本、覆盖和媒体校验后才会发布正式结果。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '提交生产任务失败'
  } finally { busy.value = false }
}

async function acceptGenerated() {
  const artifactId = generatedArtifactId.value
  if (processing.value || !artifactId || !generatedClips.value.length) return
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    const segmentIds = generatedClips.value.map(item => String(item.generation_segment_id ?? '')).filter(Boolean)
    await acceptDramaGenerated(projectId.value, artifactId, segmentIds, '人工确认当前全部生成镜头用于成片')
    notice.value = '已人工确认全部生成镜头，可以进行正式成片合成。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '确认生成镜头失败'
  } finally { busy.value = false }
}

function media(referenceId: unknown): string {
  return dramaMediaUrl(projectId.value, String(referenceId ?? ''))
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
        <h3>第三步 · 目标世界与资产 <small>{{ label(state?.world.status) }}</small></h3>
        <p>先定义人物、场景与重要道具的稳定 ID，再用图片模型专属 Skill 生成正式参考图。</p>
        <button type="button" :disabled="processing || !analysisReady" @click="execute('world')">生成目标世界与资产定义</button>
        <template v-if="worldReady">
          <p v-if="unresolved.length" class="message error">以下冲突需人工核定，本版本暂不能继续：{{ unresolved.join('；') }}</p>
          <template v-for="kind in ['characters', 'locations', 'props']" :key="kind">
            <h4>{{ { characters: '人物', locations: '场景', props: '道具' }[kind as 'characters' | 'locations' | 'props'] }}</h4>
            <p v-for="(item, i) in objects(state?.world.content?.[kind])" :key="i">{{ item.id }} · {{ item.name }}：{{ item.visual_description }}</p>
          </template>
        </template>
        <hr />
        <h3>第四步 · 正式资产图 <small>{{ label(state?.asset_images.status) }}</small></h3>
        <p>消费导演分镜和资产定义，使用当前图片模型 Prompt Skill + 图片 Runtime；不会写入 Replica 的资产表。</p>
        <button type="button" :disabled="processing || !storyboardReady || unresolved.length > 0" @click="executeProduction('asset_images')">生成正式资产图</button>
        <div v-if="assetImagesReady" class="media-grid">
          <article v-for="(item, i) in objects(state?.asset_images.content?.assets)" :key="i" class="asset-card">
            <strong>{{ item.display_name }}</strong>
            <img v-if="objects(item.media)[0]" :src="media(objects(item.media)[0].reference_id)" :alt="String(item.display_name ?? '资产图')" />
          </article>
        </div>
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
        <h3>第五步 · H3 模型专属 Prompt <small>{{ label(state?.prompts.status) }}</small></h3>
        <p>从正式资产图与导演分镜编译 MiniMax H3 原生 Prompt 和参考图槽位，不由前端拼字符串。</p>
        <button type="button" :disabled="processing || !assetImagesReady" @click="executeProduction('prompts')">编译 H3 Prompt</button>
        <details v-if="promptsReady"><summary>查看 {{ promptSegments.length }} 个生成分段</summary>
          <article v-for="(item, i) in promptSegments" :key="i" class="shot">
            <strong>{{ item.generation_segment_id }}</strong><p>{{ item.review_prompt_zh }}</p>
          </article>
        </details>
        <hr />
        <h3>第六步 · 生成音画镜头 <small>{{ label(state?.generated_video.status) }}</small></h3>
        <p>调用当前 H3 Runtime；每段输出必须通过文件 hash、ffprobe 和时长校验。生成后仍需人工确认，不能直接冒充正式成片。</p>
        <button type="button" :disabled="processing || !promptsReady" @click="executeProduction('generate')">生成全部镜头</button>
        <div v-if="generatedReady" class="video-list">
          <article v-for="(clip, i) in generatedClips" :key="i" class="shot">
            <strong>{{ clip.generation_segment_id }}</strong>
            <video controls preload="metadata" :src="media(clip.generation_segment_id)" />
          </article>
        </div>
        <button v-if="generatedReady && !selectionReady" type="button" :disabled="processing" @click="acceptGenerated">人工确认全部镜头用于成片</button>
        <p v-if="selectionReady" class="message">正式选片已确认。</p>
        <hr />
        <h3>第七步 · 合成正式短剧 <small>{{ label(state?.final_output.status) }}</small></h3>
        <p>只消费人工确认后的正式选片，使用 FFmpeg 合成为 H.264/AAC MP4。</p>
        <button type="button" :disabled="processing || !selectionReady" @click="executeProduction('post')">合成正式成片</button>
        <video v-if="finalReady" controls preload="metadata" :src="media('final')" class="final-video" />
      </section>
    </template>
  </section>
</template>

<style scoped>
.drama-workspace{display:grid;gap:14px;max-width:1100px;margin:auto;color:#1b2b42}.panel{padding:20px 22px;border:1px solid #e2e8f0;border-radius:12px;background:#fff;display:grid;gap:10px}.panel h2,.panel h3,.panel h4,.panel p{margin:0}.panel h2{font-size:24px}.panel h3{font-size:18px}.panel h4{font-size:14px}.panel p{font-size:13px;line-height:1.7;color:#56677d}.panel small{font-size:12px;color:#5572a6}.eyebrow{font-size:13px;font-weight:800;color:#466de2!important}.panel textarea{width:100%;min-height:100px;padding:12px;border:1px solid #cbd5e1;border-radius:8px;font-size:13px;line-height:1.7}.panel button{width:max-content;padding:10px 14px;border:0;border-radius:8px;background:#2878ff;color:#fff;font-weight:700;cursor:pointer}.panel button:disabled{opacity:.5;cursor:not-allowed}.panel pre{max-height:60vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;border-radius:8px;background:#f8fafc}.panel details{min-width:0}.message{padding:12px 14px;background:#f2f5ff;border-radius:8px;font-size:13px}.error{background:#fff0ed;color:#ae2929}.shot{padding:12px;border:1px solid #e2e8f0;border-radius:9px;display:grid;gap:6px}.media-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:10px}.asset-card{display:grid;gap:8px;padding:10px;border:1px solid #e2e8f0;border-radius:9px}.asset-card img{width:100%;aspect-ratio:1/1;object-fit:contain;background:#f8fafc;border-radius:7px}.video-list{display:grid;gap:12px}.video-list video,.final-video{width:100%;max-height:68vh;background:#111;border-radius:8px}.panel hr{width:100%;border:0;border-top:1px solid #e2e8f0;margin:6px 0}
</style>
