<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { getEpisodeShotBoundary, getProject, listProjectEpisodes } from '@/features/projects/api'
import type { EpisodeRead, EpisodeShotBoundaryRead, ProjectRead } from '@/features/projects/types'
import { apiRequest } from '@/lib/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const episodes = ref<EpisodeRead[]>([])
const boundaries = ref<Record<string, EpisodeShotBoundaryRead | null>>({})
const loading = ref(true)
const uploading = ref(false)
const error = ref('')
const fileInput = ref<HTMLInputElement | null>(null)

const totalDurationUs = computed(() => episodes.value.reduce((sum, item) => sum + item.duration_us, 0))
const totalShots = computed(() => episodes.value.reduce((sum, item) => sum + (boundaries.value[item.id]?.shot_count ?? 0), 0))
const analyzedCount = computed(() => episodes.value.filter(item => boundaries.value[item.id]?.status === 'CURRENT').length)
function duration(us: number) { const seconds=Math.max(0,Math.round(us/1_000_000));return `${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}` }
function displayName(filename: string) { return filename.replace(/\.[^.]+$/, '') }
function enterEpisode(episode: EpisodeRead) { void router.push({ path:`/projects/${projectId.value}/source`, query:{ episode:episode.id, ep:String(episode.episode_order) } }) }
function chooseFiles() { fileInput.value?.click() }
async function upload(event: Event) {
  const input=event.target as HTMLInputElement
  if(!input.files?.length||uploading.value)return
  uploading.value=true;error.value=''
  try{const data=new FormData();Array.from(input.files).forEach(file=>data.append('files',file));await apiRequest<EpisodeRead[]>(`/projects/${projectId.value}/sources/videos`,{method:'POST',body:data});await load()}
  catch(exc){error.value=exc instanceof Error?exc.message:'新增剧集失败'}
  finally{uploading.value=false;input.value=''}
}
async function load(){loading.value=true;error.value='';try{const [p,rows]=await Promise.all([getProject(projectId.value),listProjectEpisodes(projectId.value)]);project.value=p;episodes.value=[...rows].sort((a,b)=>a.episode_order-b.episode_order);const boundaryRows=await Promise.all(episodes.value.map(async episode=>{try{return [episode.id,await getEpisodeShotBoundary(projectId.value,episode.id)] as const}catch{return [episode.id,null] as const}}));boundaries.value=Object.fromEntries(boundaryRows)}catch(exc){error.value=exc instanceof Error?exc.message:'读取剧集失败'}finally{loading.value=false}}
onMounted(()=>{void load()})
</script>

<template>
  <section class="episodes-page" data-testid="episode-management-workspace">
    <header class="page-header"><div><p class="eyebrow">剧集管理</p><h2>{{ project?.name || '当前项目' }}</h2><p>每一集都是独立制作单元。在这里上传 Episode、查看原片规格和分析状态，再进入对应剧集制作。</p></div><button type="button" :disabled="uploading" @click="chooseFiles">{{ uploading?'正在上传…':'＋ 新增剧集' }}</button><input ref="fileInput" class="visually-hidden" type="file" multiple accept="video/mp4,video/quicktime,video/x-matroska,video/webm,.mp4,.mov,.mkv,.webm,.avi,.m4v" @change="upload" /></header>
    <p v-if="error" class="message error">{{ error }}</p><div v-if="loading" class="state-box">正在读取剧集…</div>
    <template v-else>
      <div class="summary"><article><span>剧集总数</span><strong>{{ episodes.length }}</strong></article><article><span>总时长</span><strong>{{ duration(totalDurationUs) }}</strong></article><article><span>已识别镜头</span><strong>{{ totalShots }}</strong></article><article><span>原片分析</span><strong>{{ analyzedCount }} / {{ episodes.length }}</strong></article></div>
      <div v-if="episodes.length" class="episode-list">
        <article v-for="episode in episodes" :key="episode.id" class="episode-row"><div class="episode-index">{{ episode.episode_order }}</div><div class="episode-main"><div class="title-row"><div><span>第 {{ episode.episode_order }} 集</span><strong>{{ displayName(episode.source_asset.original_filename) }}</strong></div><em :class="{ready:boundaries[episode.id]?.status==='CURRENT',stale:boundaries[episode.id]?.status==='STALE'}">{{ boundaries[episode.id]?.status==='CURRENT'?'原片已分析':boundaries[episode.id]?.status==='STALE'?'需要重新分析':'待分析' }}</em></div><div class="meta-grid"><span><small>时长</small><b>{{ duration(episode.duration_us) }}</b></span><span><small>画面尺寸</small><b>{{ episode.width }} × {{ episode.height }}</b></span><span><small>编码</small><b>{{ episode.codec_name||'—' }}</b></span><span><small>帧率</small><b>{{ episode.avg_frame_rate||'—' }}</b></span><span><small>音轨</small><b>{{ episode.has_audio?'有音频':'无音频' }}</b></span><span><small>镜头数</small><b>{{ boundaries[episode.id]?.shot_count??0 }} 镜</b></span></div></div><div class="row-action"><button type="button" @click="enterEpisode(episode)">{{ boundaries[episode.id]?.status==='CURRENT'?'进入制作':'分析本集' }} →</button></div></article>
      </div>
      <div v-else class="empty-state"><div class="empty-icon">＋</div><strong>还没有剧集</strong><p>上传完整 Episode 视频后，每一集会独立进入原片分镜、本土化、资产、H3 提示词和视频生成流程。</p><button type="button" :disabled="uploading" @click="chooseFiles">上传第一集</button></div>
    </template>
  </section>
</template>

<style scoped>
.episodes-page{display:grid;gap:13px;min-width:0;color:#263653}.page-header{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:22px 24px;border:1px solid #e1e4ec;border-radius:14px;background:linear-gradient(135deg,#fff 0%,#f8f7ff 100%)}.page-header>div{min-width:0}.page-header h2{margin:3px 0 6px;color:#17294a;font-size:25px}.page-header p:last-child{max-width:760px;margin:0;color:#748097;font-size:12px;line-height:1.6}.eyebrow{margin:0;color:#6552e8;font-size:10px;font-weight:850;letter-spacing:.08em}.page-header>button,.empty-state button,.row-action button{min-height:38px;padding:0 15px;border:0;border-radius:9px;background:#6552e8;color:#fff;font-size:11px;font-weight:800;cursor:pointer;white-space:nowrap}.page-header>button:disabled{opacity:.55}.summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px}.summary article{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:13px 15px;border:1px solid #e4e6ed;border-radius:11px;background:#fff}.summary span{color:#8791a3;font-size:10px}.summary strong{color:#213554;font-size:18px}.episode-list{display:grid;gap:9px}.episode-row{display:grid;grid-template-columns:50px minmax(0,1fr) auto;align-items:center;gap:14px;padding:13px 15px;border:1px solid #e3e6ed;border-radius:12px;background:#fff}.episode-row:hover{border-color:#d7d1ff;box-shadow:0 5px 16px rgba(47,55,85,.04)}.episode-index{display:grid;place-items:center;width:42px;height:42px;border-radius:11px;background:#efedff;color:#5d49e2;font-size:15px;font-weight:850}.episode-main{display:grid;gap:10px;min-width:0}.title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.title-row>div{display:grid;min-width:0;gap:2px}.title-row span{color:#6552e8;font-size:9px;font-weight:850}.title-row strong{overflow:hidden;color:#2d3f5e;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.title-row em{padding:4px 8px;border-radius:999px;background:#f0f1f4;color:#7b8495;font-size:8px;font-style:normal;font-weight:800}.title-row em.ready{background:#e8f6ec;color:#34784a}.title-row em.stale{background:#fff0da;color:#8a5c19}.meta-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:8px}.meta-grid span{display:grid;gap:2px;padding:7px 9px;border-radius:8px;background:#f8f9fb}.meta-grid small{color:#949dac;font-size:8px}.meta-grid b{overflow:hidden;color:#4a5b75;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.row-action button{min-height:34px;padding:0 12px;font-size:9px}.state-box,.message,.empty-state{padding:26px;border:1px dashed #ccd2dd;border-radius:12px;background:#fff;color:#6d788c}.message{padding:10px 12px}.error{border-style:solid;border-color:#efd6d2;background:#fff5f3;color:#a33b32}.empty-state{display:grid;justify-items:center;gap:8px;text-align:center}.empty-state p{max-width:580px;margin:0;font-size:11px;line-height:1.6}.empty-icon{display:grid;place-items:center;width:50px;height:50px;border-radius:50%;background:#efedff;color:#6552e8;font-size:24px}.visually-hidden{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}@media(max-width:1050px){.meta-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:720px){.page-header{align-items:stretch;flex-direction:column}.summary{grid-template-columns:repeat(2,minmax(0,1fr))}.episode-row{grid-template-columns:42px minmax(0,1fr)}.row-action{grid-column:1/-1}.row-action button{width:100%}.meta-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.page-header>button{width:100%}}
</style>
