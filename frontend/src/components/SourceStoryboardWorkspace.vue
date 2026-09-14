<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getProject } from '@/features/projects/api'
import {
  getSourceAnalysisStatus,
  getSourceScript,
  startSourceAnalysis,
  type SourceAnalysisStatusRead,
  type SourceScriptRead,
} from '@/features/projects/sourceAnalysis'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const replica = ref(false)
const status = ref<SourceAnalysisStatusRead | null>(null)
const source = ref<SourceScriptRead | null>(null)
const loading = ref(true)
const starting = ref(false)
const error = ref('')
let timer: number | undefined

const storyboardReady = computed(() => status.value?.state === 'READY' && source.value?.visual_enrichment_ready === true)
const shots = computed(() => source.value?.scenes.flatMap(scene => scene.shots.map(shot => ({ ...shot, scene_name: scene.scene_name }))) ?? [])

function commandKey() {
  return `source-storyboard-${crypto.randomUUID()}`
}

function time(us: number) {
  const seconds = us / 1_000_000
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toFixed(2).padStart(5, '0')}`
}

async function refresh() {
  status.value = await getSourceAnalysisStatus(projectId.value)
  if (status.value.script_ready || status.value.state === 'READY') source.value = await getSourceScript(projectId.value)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const project = await getProject(projectId.value)
    replica.value = project.project_type === 'REPLICA'
    if (replica.value) await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '读取视频分析结果失败'
  } finally {
    loading.value = false
  }
}

async function analyze() {
  if (starting.value) return
  starting.value = true
  error.value = ''
  try {
    status.value = await startSourceAnalysis(projectId.value, commandKey())
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '视频分析启动失败'
  } finally {
    starting.value = false
  }
}

onMounted(() => {
  void load()
  timer = window.setInterval(() => { if (replica.value && status.value?.state === 'RUNNING') void refresh().catch(() => {}) }, 1800)
})
onBeforeUnmount(() => { if (timer !== undefined) window.clearInterval(timer) })
</script>

<template>
  <section v-if="replica" class="five-step-workspace" data-testid="source-storyboard-workspace">
    <header>
      <div><p class="eyebrow">步骤 1 / 5</p><h2>分析视频，获取原片分镜表</h2><p>系统内部完成切镜、对白证据、整集理解和逐镜拉片；这里的正式输出只看最终分镜表。</p></div>
      <button type="button" :disabled="starting || status?.state === 'RUNNING'" @click="analyze">{{ status?.state === 'RUNNING' ? `分析中 ${status.progress_percent}%` : storyboardReady ? '重新分析视频' : '分析视频' }}</button>
    </header>
    <p v-if="error" class="message error">{{ error }}</p>
    <div v-if="loading" class="empty">正在读取原片分镜…</div>
    <div v-else-if="!storyboardReady" class="empty"><strong>{{ status?.message || '还没有正式分镜表' }}</strong><span>只有精确逐镜结果和 Source Snapshot 完成后，步骤 2 才能开始。</span></div>
    <template v-else>
      <div class="metrics"><span>{{ shots.length }} 镜</span><span>{{ source?.scenes.length ?? 0 }} 场</span><span>正式 Source Snapshot 已就绪</span></div>
      <div class="shot-table">
        <article v-for="shot in shots" :key="shot.shot_anchor_id">
          <img :src="shot.thumbnail_url" :alt="`Shot ${shot.shot_number}`" loading="lazy" />
          <div class="index"><strong>#{{ String(shot.shot_number).padStart(3, '0') }}</strong><small>{{ time(shot.start_us) }} – {{ time(shot.end_us) }}</small><small>{{ shot.scene_name }}</small></div>
          <div class="copy"><p>{{ shot.visual_description }}</p><small>{{ [shot.shot_size, shot.angle_or_type, shot.movement, shot.composition].filter(Boolean).join(' · ') }}</small><div v-if="shot.dialogues.length" class="dialogues"><span v-for="line in shot.dialogues" :key="line.utterance_id"><b>{{ line.speaker_name }}</b> {{ line.text }}</span></div></div>
        </article>
      </div>
    </template>
  </section>
</template>

<style scoped>
.five-step-workspace{display:grid;gap:16px;max-width:1360px;margin:20px auto}.five-step-workspace>header{display:flex;justify-content:space-between;gap:18px;padding:22px;border:1px solid #deded8;border-radius:18px;background:#fff}.five-step-workspace h2{margin:3px 0}.five-step-workspace header p:last-child,.empty{color:#706d67}.eyebrow{margin:0;color:#5a4ed8;font-size:11px;font-weight:850;letter-spacing:.1em}.five-step-workspace button{align-self:flex-start;min-height:38px;padding:0 15px;border:0;border-radius:10px;background:#292925;color:#fff;font-weight:750}.five-step-workspace button:disabled{opacity:.5}.metrics{display:flex;gap:8px;flex-wrap:wrap}.metrics span{padding:8px 11px;border-radius:999px;background:#efeee9;font-size:12px}.shot-table{display:grid;gap:8px}.shot-table article{display:grid;grid-template-columns:150px 150px minmax(0,1fr);gap:14px;padding:10px;border:1px solid #e3e1dc;border-radius:13px;background:#fff}.shot-table img{width:150px;height:96px;object-fit:cover;border-radius:8px;background:#111}.index,.copy,.dialogues{display:grid;gap:5px}.index small,.copy small{color:#858078}.copy p{margin:0;line-height:1.6}.dialogues span{padding:5px 8px;border-left:2px solid #8278e8;background:#f8f7ff;font-size:12px}.empty{display:grid;gap:5px;padding:28px;border:1px dashed #ccc8c0;border-radius:14px;background:#faf9f6}.error{color:#a33b32}@media(max-width:820px){.shot-table article{grid-template-columns:100px 1fr}.shot-table img{width:100px;height:75px}.copy{grid-column:1/-1}.five-step-workspace>header{flex-direction:column}}
</style>
