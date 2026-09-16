<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { listProjectTasks } from '@/features/projects/api'
import {
  getAssetImages,
  getLocalizedStoryboard,
  regenerateAssetImages,
  startAssetImages,
  type AssetImagesContent,
  type AssetImagesRead,
  type LocalizedStoryboardRead,
} from '@/features/projects/replicaFiveStep'
import type { TaskRead, TaskStatus } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const episodeId = computed(() => String(route.query.episode ?? ''))
const episodeOrder = computed(() => Number(route.query.ep ?? 1) || 1)
const current = ref<AssetImagesRead | null>(null)
const localized = ref<LocalizedStoryboardRead | null>(null)
const assetTask = ref<TaskRead | null>(null)
const action = ref('')
const error = ref('')
const message = ref('')
const assetFilter = ref<'ALL' | 'CHARACTER' | 'SCENE' | 'PROP'>('ALL')
const query = ref('')
const selectedAssetId = ref('')
let refreshTimer: number | undefined
let taskTimer: number | undefined

const content = computed<AssetImagesContent | null>(() => current.value?.content ?? null)
const hasExistingAssetRevision = computed(() => Boolean(current.value?.artifact_id))
const taskRunning = computed(() => assetTask.value?.status === 'queued' || assetTask.value?.status === 'running')
const taskFailed = computed(() => assetTask.value?.status === 'failed' || assetTask.value?.status === 'cancelled' || assetTask.value?.status === 'interrupted')
const taskSucceededWithoutResult = computed(() => assetTask.value?.status === 'succeeded' && !content.value)
const showTaskProgress = computed(() => taskRunning.value || taskFailed.value || taskSucceededWithoutResult.value)
const progressPercent = computed(() => Math.max(0, Math.min(100, assetTask.value?.progress_percent ?? 0)))
const episodeEntityIds = computed<Set<string> | null>(() => {
  if (!episodeId.value || !localized.value?.content) return null
  const ids = new Set<string>()
  for (const shot of localized.value.content.shots) {
    if (shot.episode_id !== episodeId.value) continue
    shot.target_character_ids.forEach(id => ids.add(id))
    shot.target_scene_ids.forEach(id => ids.add(id))
    shot.target_prop_ids.forEach(id => ids.add(id))
  }
  return ids
})
const episodeAssets = computed(() => (content.value?.assets ?? []).filter(asset => episodeEntityIds.value === null || episodeEntityIds.value.has(asset.target_entity_id)))
const assetCounts = computed(() => ({
  ALL: episodeAssets.value.length,
  CHARACTER: episodeAssets.value.filter(asset => asset.asset_type === 'CHARACTER').length,
  SCENE: episodeAssets.value.filter(asset => asset.asset_type === 'SCENE').length,
  PROP: episodeAssets.value.filter(asset => asset.asset_type === 'PROP').length,
}))
const filteredAssets = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  return episodeAssets.value.filter(asset => {
    if (assetFilter.value !== 'ALL' && asset.asset_type !== assetFilter.value) return false
    if (!keyword) return true
    return [asset.display_name, asset.review_description_zh, asset.prompt_review_zh ?? '', asset.image_prompt].some(value => value.toLocaleLowerCase().includes(keyword))
  })
})
const selectedAsset = computed(() => (
  episodeAssets.value.find(asset => asset.target_asset_id === selectedAssetId.value) ?? null
))
const modelSummary = computed(() => {
  const models = [...new Set(episodeAssets.value.map(asset => asset.image_model_id).filter(Boolean))]
  if (!models.length) return 'Z-Image Turbo'
  return models.length === 1 ? String(models[0]) : `按资产配置（${models.length} 个模型）`
})
const resolutionSummary = computed(() => {
  const sizes = [...new Set(episodeAssets.value.flatMap(asset => asset.reference_media.map(media => `${media.width}×${media.height}`)))]
  if (!sizes.length) return '由模型自动确定'
  return sizes.length === 1 ? sizes[0] : `${sizes.length} 种规格`
})

const taskStatusText: Record<TaskStatus, string> = {
  queued: '排队中',
  running: '正在生成',
  succeeded: '生成完成',
  failed: '生成失败',
  cancelled: '已取消',
  interrupted: '已中断',
}

const taskStageText = computed(() => {
  const task = assetTask.value
  if (!task) return ''
  if (task.status === 'queued') return '任务已进入队列，等待资产图 Worker 开始执行。'
  if (task.status === 'failed') return task.last_error || '资产图生成失败，请检查 Prompt Skill、ComfyUI、Z-Image Turbo 模型和任务日志后重试。'
  if (task.status === 'cancelled') return '资产图生成任务已取消。'
  if (task.status === 'interrupted') return task.last_error || '资产图生成任务已中断，可以重新发起。'
  if (task.status === 'succeeded') return '资产图已经生成完成并自动采用，正在加载正式结果。'
  if (task.progress_percent >= 95) return '人物、场景和道具参考图已生成，正在完成一致性检查并自动设为当前资产。'
  if (task.progress_percent >= 30) return '模型专属提示词已经编译，正在通过本机 ComfyUI / Z-Image Turbo 逐项生成真实资产图。'
  if (task.progress_percent > 0) return '已从本土化分镜提取资产，正在用 Z-Image Turbo Professional Skill 分析分镜证据并生成资产提示词。'
  return '正在从本土化分镜提取实际使用的人物、场景和道具。'
})

const generateButtonText = computed(() => {
  if (action.value === 'generate') return '启动中…'
  if (assetTask.value?.status === 'queued') return `资产排队中 ${progressPercent.value}%`
  if (assetTask.value?.status === 'running') return `资产生成中 ${progressPercent.value}%`
  if (taskFailed.value) return '重试生成资产图'
  return hasExistingAssetRevision.value ? '重新生成资产图' : '提取并生成资产图'
})

function latestAssetTask(rows: TaskRead[]): TaskRead | null {
  const relevant = rows.filter(item => item.task_type === 'replica.asset-images')
  if (!relevant.length) return null
  return [...relevant].sort((left, right) => new Date(right.created_at).getTime() - new Date(left.created_at).getTime())[0] ?? null
}

function stopTaskPolling() {
  if (taskTimer !== undefined) {
    window.clearInterval(taskTimer)
    taskTimer = undefined
  }
}

function startTaskPolling() {
  if (taskTimer !== undefined) return
  taskTimer = window.setInterval(() => void refreshTask(true), 1000)
}

async function refresh(silent = false) {
  try {
    const [read, localizedRead] = await Promise.all([getAssetImages(projectId.value), getLocalizedStoryboard(projectId.value)])
    current.value = read
    localized.value = localizedRead
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '读取资产图失败'
  }
}

async function refreshTask(silent = false) {
  try {
    const rows = await listProjectTasks(projectId.value)
    const tracked = assetTask.value ? rows.find(item => item.id === assetTask.value?.id) ?? null : null
    assetTask.value = tracked ?? latestAssetTask(rows)
    if (taskRunning.value) {
      startTaskPolling()
    } else {
      stopTaskPolling()
      if (message.value.includes('任务已启动')) message.value = ''
      if (assetTask.value?.status === 'succeeded') await refresh(true)
    }
  } catch (exc) {
    if (!silent) error.value = exc instanceof Error ? exc.message : '读取资产图任务进度失败'
  }
}

async function generate() {
  action.value = 'generate'
  error.value = ''
  message.value = ''
  try {
    const previousTaskId = assetTask.value?.id ?? null
    const startedTask = hasExistingAssetRevision.value
      ? await regenerateAssetImages(projectId.value)
      : await startAssetImages(projectId.value)
    if (startedTask.task_type !== 'replica.asset-images' || startedTask.project_id !== projectId.value) {
      throw new Error('后端没有返回有效的资产图任务，请刷新页面后重试。')
    }
    if (previousTaskId && startedTask.id === previousTaskId) {
      throw new Error('没有创建新的资产图任务，请刷新页面后重试。')
    }
    if (startedTask.status !== 'queued' && startedTask.status !== 'running') {
      throw new Error(startedTask.last_error || '资产图任务没有进入执行队列，请刷新页面后重试。')
    }
    assetTask.value = startedTask
    message.value = '资产提取 → Prompt Skill 分析分镜 → Z-Image Turbo 出图任务已启动，可在下方查看实时进度；如果失败会直接显示失败原因。'
    if (taskRunning.value) startTaskPolling()
    await refresh(true)
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '资产图任务启动失败'
  } finally {
    action.value = ''
  }
}

const label = (type: string) => type === 'CHARACTER' ? '人物' : type === 'SCENE' ? '场景' : '道具'
const closeAssetDrawer = () => { selectedAssetId.value = '' }

onMounted(() => {
  void Promise.all([refresh(), refreshTask()])
  refreshTimer = window.setInterval(() => void refresh(true), 4000)
})
onBeforeUnmount(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
  stopTaskPolling()
})
</script>

<template>
  <section class="workspace" data-testid="asset-images-workspace">
    <header class="stage-header"><div class="stage-title"><h2>视觉资产</h2><div v-if="content" class="header-meta"><span><b>{{ episodeAssets.length }}</b> 个资产</span><span>{{ content.visual_style }}</span><span>{{ current?.status==='CURRENT'?'当前可用':current?.status==='STALE'?'需要重新生成':'历史结果' }}</span></div><span class="visually-hidden">人物资产固定为正面全身 + 侧面全身 + 背面全身 + 面部特写；整段人物小传不会直接送进图片模型。</span></div><div class="stage-actions"><label v-if="content" class="search"><span>⌕</span><input v-model="query" type="search" placeholder="搜索资产名称、描述或提示词" /></label><button v-if="!content" type="button" :disabled="Boolean(action) || taskRunning" @click="generate">{{ generateButtonText }}</button></div></header>
    <p v-if="error" class="error">{{ error }}</p><p v-if="message" class="success">{{ message }}</p>
    <p v-if="current?.status==='STALE' && content" class="stale-note">这批资产使用旧人物一致性合同，已保留供查看，但必须重新生成后才能进入 H3 提示词和视频生成。</p>
    <div v-if="showTaskProgress && assetTask" class="task-progress" :class="{ failed: taskFailed }" data-testid="asset-images-progress" role="status" aria-live="polite">
      <div class="task-progress-heading">
        <div><strong>{{ taskStatusText[assetTask.status] }}</strong><span>{{ taskStageText }}</span></div>
        <b>{{ progressPercent }}%</b>
      </div>
      <div class="progress-track" role="progressbar" aria-label="资产图生成进度" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="progressPercent">
        <div class="progress-value" :class="{ active: taskRunning }" :style="{ width: `${progressPercent}%` }"></div>
      </div>
      <p v-if="taskFailed" class="task-error">{{ assetTask.last_error || '任务没有返回更详细的错误信息，请查看后端日志后重试。' }}</p>
    </div>
    <div v-if="!content" class="empty">先确认步骤 2 的本土化分镜，再提取人物、场景和道具。</div>
    <template v-else>
      <div class="asset-production-shell">
        <aside class="batch-panel" aria-label="资产生成设置">
          <div class="batch-heading"><div><strong>资产生成设置</strong><span>{{ episodeAssets.length }}</span></div><small>当前第 {{ episodeOrder }} 集</small></div>

          <section class="batch-section">
            <strong>快捷筛选</strong>
            <div class="quick-filters" aria-label="资产类型筛选">
              <button type="button" class="filter-button" :class="{ active: assetFilter === 'ALL' }" @click="assetFilter = 'ALL'">全部资产 <span>{{ assetCounts.ALL }}</span></button>
              <button type="button" class="filter-button" :class="{ active: assetFilter === 'CHARACTER' }" @click="assetFilter = 'CHARACTER'">人物 <span>{{ assetCounts.CHARACTER }}</span></button>
              <button type="button" class="filter-button" :class="{ active: assetFilter === 'SCENE' }" @click="assetFilter = 'SCENE'">场景 <span>{{ assetCounts.SCENE }}</span></button>
              <button type="button" class="filter-button" :class="{ active: assetFilter === 'PROP' }" @click="assetFilter = 'PROP'">道具 <span>{{ assetCounts.PROP }}</span></button>
            </div>
          </section>

          <section class="batch-section batch-readonly">
            <label><span>生成模型</span><div>{{ modelSummary }}</div></label>
            <label><span>分辨率</span><div>{{ resolutionSummary }}</div></label>
            <label><span>视觉风格</span><div>{{ content.visual_style }}</div></label>
          </section>

          <div class="batch-help">人物资产会固定生成正面全身、侧面全身、背面全身与面部特写；生成参数由当前 Professional Skill 和后端正式合同控制。</div>
          <button type="button" class="batch-generate" :disabled="Boolean(action) || taskRunning" @click="generate">{{ generateButtonText }}</button>
        </aside>

        <section class="asset-board" aria-label="资产列表">
          <div class="board-heading"><div><strong>资产列表</strong><span>{{ filteredAssets.length }} / {{ episodeAssets.length }}</span></div><small>点击资产查看大图和生成详情</small></div>
          <div class="asset-gallery">
            <button v-for="asset in filteredAssets" :key="asset.target_asset_id" type="button" class="asset-card" :class="{ active: selectedAsset?.target_asset_id === asset.target_asset_id }" @click="selectedAssetId = asset.target_asset_id">
              <div class="thumb"><img v-if="asset.reference_media[0]" :src="asset.reference_media[0].uri" :alt="asset.display_name" loading="lazy" /><span v-else>暂无图片</span></div>
              <div class="card-copy"><div class="card-title"><strong>{{ asset.display_name }}</strong><span class="asset-status">已生成提示词</span></div><div class="asset-tags"><small>{{ label(asset.asset_type) }}</small><span v-if="asset.image_model_id">{{ asset.image_model_id }}</span><span v-if="asset.reference_media[0]">{{ asset.reference_media[0].width }}×{{ asset.reference_media[0].height }}</span></div><p>{{ asset.review_description_zh }}</p></div>
            </button>
            <div v-if="!filteredAssets.length" class="gallery-empty">当前筛选没有匹配资产</div>
          </div>
        </section>
      </div>

      <div v-if="selectedAsset" class="drawer-backdrop" @click.self="closeAssetDrawer">
        <aside class="asset-drawer" aria-label="单资产详情">
          <header class="drawer-head"><div><strong>{{ selectedAsset.display_name }} · 单独查看</strong><span>{{ label(selectedAsset.asset_type) }}</span></div><button type="button" aria-label="关闭资产详情" @click="closeAssetDrawer">×</button></header>
          <div class="drawer-scroll">
            <div class="drawer-preview"><img v-if="selectedAsset.reference_media[0]" :src="selectedAsset.reference_media[0].uri" :alt="selectedAsset.display_name" /><span v-else>暂无正式参考图</span></div>

            <section v-if="selectedAsset.reference_media.length" class="drawer-section"><strong>参考图片</strong><div class="reference-strip"><img v-for="media in selectedAsset.reference_media" :key="media.reference_id" :src="media.uri" :alt="`${selectedAsset.display_name} ${media.role}`" /></div></section>

            <section class="drawer-form">
              <label><span>生成模型</span><div>{{ selectedAsset.image_model_id || 'Z-Image Turbo' }}</div></label>
              <label><span>分辨率</span><div>{{ selectedAsset.reference_media[0] ? `${selectedAsset.reference_media[0].width} × ${selectedAsset.reference_media[0].height}` : '—' }}</div></label>
            </section>

            <section class="drawer-section"><strong>视觉定义</strong><p>{{ selectedAsset.review_description_zh }}</p></section>
            <section v-if="selectedAsset.prompt_review_zh" class="drawer-section"><strong>提示词审核</strong><p>{{ selectedAsset.prompt_review_zh }}</p></section>
            <section class="drawer-section prompt-section"><strong>模型提示词 <small>只读</small></strong><textarea :value="selectedAsset.image_prompt" rows="7" readonly></textarea><p v-if="selectedAsset.negative_prompt" class="negative-prompt"><b>避免：</b>{{ selectedAsset.negative_prompt }}</p><p v-if="selectedAsset.prompt_skill_id" class="prompt-meta">{{ selectedAsset.prompt_skill_id }}@{{ selectedAsset.prompt_skill_version }} · {{ selectedAsset.prompt_contract }}</p></section>
          </div>
        </aside>
      </div>

    </template>
  </section>
</template>

<style scoped>
.workspace{display:grid;gap:8px;min-width:0;margin:0}.stage-header{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:46px;padding:0 2px 6px;border-bottom:1px solid #e8eaf0}.stage-title{display:flex;align-items:center;gap:10px;min-width:0}.stage-title h2{margin:0;color:#142647;font-size:20px;letter-spacing:-.015em}.header-meta{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.header-meta span{padding:4px 7px;border:1px solid #e5e2dc;border-radius:999px;background:#fff;color:#69645e;font-size:10px}.header-meta .attention{border-color:#ead9b0;background:#fff9ec;color:#805d18}.stage-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;min-width:0}.stage-actions>button,.batch-generate{min-height:32px;padding:0 13px;border:0;border-radius:8px;background:linear-gradient(135deg,#704cf4,#5a38e6);color:#fff;font-size:12px;font-weight:750;cursor:pointer;box-shadow:0 5px 12px rgba(91,59,227,.14)}.stage-actions>button:disabled,.batch-generate:disabled{opacity:.5}.task-progress{display:grid;gap:10px;padding:15px 17px;border:1px solid #dedbe9;border-radius:14px;background:#fff}.task-progress.failed{border-color:#e5b8b3;background:#fff8f7}.task-progress-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.task-progress-heading>div{display:grid;gap:4px}.task-progress-heading strong{font-size:13px}.task-progress-heading span{color:#706d67;font-size:12px;line-height:1.5}.task-progress-heading>b{font-size:15px;font-variant-numeric:tabular-nums}.progress-track{height:8px;overflow:hidden;border-radius:999px;background:#e7e5ee}.progress-value{height:100%;border-radius:inherit;background:#6558e8;transition:width .25s ease}.progress-value.active{position:relative;overflow:hidden}.progress-value.active::after{position:absolute;inset:0;content:"";background:linear-gradient(90deg,transparent,rgba(255,255,255,.55),transparent);animation:progress-shimmer 1.4s linear infinite}.task-error{margin:0;padding:9px 10px;border-radius:9px;background:#fff0ee;color:#9a3129;font-size:12px;line-height:1.55}.actions{display:flex;gap:7px;flex-wrap:wrap}.search{display:flex;align-items:center;gap:6px;min-width:min(360px,42vw);padding:0 10px;border:1px solid #dedbd4;border-radius:9px;background:#fff;color:#918b83}.search input{width:100%;height:34px;border:0;outline:0;background:transparent;font-size:12px}.asset-production-shell{display:grid;grid-template-columns:250px minmax(0,1fr);min-height:0;border:1px solid #e0e3ea;border-radius:12px;background:#fff;overflow:hidden}.batch-panel{display:flex;flex-direction:column;gap:16px;min-width:0;padding:16px;border-right:1px solid #e5e7ee;background:#fcfcfd}.batch-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.batch-heading>div{display:flex;align-items:center;gap:7px}.batch-heading strong{font-size:15px;color:#172848}.batch-heading>div span{padding:2px 6px;border-radius:6px;background:#efedff;color:#6352df;font-size:10px}.batch-heading small{color:#8994a7;font-size:10px}.batch-section{display:grid;gap:9px}.batch-section>strong{font-size:12px;color:#344562}.quick-filters{display:grid;gap:7px}.workspace .filter-button{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:34px;padding:0 10px;border:1px solid #d9d3ff;border-radius:6px;background:#fff;color:#5e51dc;font-size:11px;text-align:left;cursor:pointer}.workspace .filter-button span{min-width:20px;padding:2px 5px;border-radius:999px;background:#f0eeff;color:#5d50d7;font-size:9px;text-align:center}.workspace .filter-button.active{background:#efecff;border-color:#7865ef;color:#4e3fd1;box-shadow:inset 0 0 0 1px rgba(105,82,232,.12)}.batch-readonly label{display:grid;gap:5px}.batch-readonly label>span{color:#56657d;font-size:11px;font-weight:750}.batch-readonly label>div{min-height:34px;padding:8px 9px;border:1px solid #e1e4eb;border-radius:7px;background:#fff;color:#4b5a73;font-size:11px;line-height:1.45}.batch-help{padding:10px;border-radius:8px;background:#f7f5ff;color:#6b6481;font-size:10px;line-height:1.55}.batch-generate{margin-top:auto;min-height:38px}.asset-board{min-width:0;padding:14px;background:#fff}.board-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:11px}.board-heading>div{display:flex;align-items:center;gap:7px}.board-heading strong{font-size:14px;color:#1a2b48}.board-heading span{padding:2px 6px;border-radius:6px;background:#f0f2f7;color:#69758a;font-size:10px}.board-heading small{color:#8b95a7;font-size:10px}.asset-gallery{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.workspace .asset-card{display:grid;grid-template-rows:180px auto;min-width:0;overflow:hidden;padding:0;border:1px solid #e1e4ea;border-radius:9px;background:#fff;color:#36332f;text-align:left;box-shadow:0 1px 3px rgba(30,37,50,.05);cursor:pointer}.workspace .asset-card:hover{border-color:#c9c3ff;box-shadow:0 5px 14px rgba(62,52,145,.08)}.workspace .asset-card.active{border-color:#7865ef;box-shadow:0 0 0 2px #eeebff}.thumb{display:grid;place-items:center;min-width:0;overflow:hidden;background:#f0f1f3;color:#969089;font-size:10px}.thumb img{width:100%;height:100%;object-fit:contain}.card-copy{display:grid;min-width:0;gap:7px;padding:10px 11px 12px}.card-title{display:flex;align-items:center;justify-content:space-between;gap:8px}.card-title strong{overflow:hidden;color:#263956;font-size:13px;line-height:1.4;text-overflow:ellipsis;white-space:nowrap}.asset-status{flex:0 0 auto;padding:2px 5px;border:1px solid #55bf8d;border-radius:4px;color:#289564!important;font-size:9px!important}.asset-tags{display:flex;align-items:center;gap:5px;flex-wrap:wrap}.asset-tags small{padding:2px 5px;border:1px solid #ff9c4a;border-radius:4px;color:#df711a;font-size:9px;font-weight:750}.asset-tags span{max-width:160px;overflow:hidden;padding:2px 5px;border:1px solid #dfe3ea;border-radius:4px;color:#596a84!important;font-size:9px!important;text-overflow:ellipsis;white-space:nowrap}.card-copy p{display:-webkit-box;overflow:hidden;margin:0;color:#59667a;font-size:10px;line-height:1.55;-webkit-box-orient:vertical;-webkit-line-clamp:2}.gallery-empty{grid-column:1/-1;padding:38px;border:1px dashed #d6d2cb;border-radius:9px;background:#faf9f6;color:#89847d;font-size:12px;text-align:center}.drawer-backdrop{position:fixed;inset:56px 0 0 0;z-index:75;background:rgba(24,29,40,.08)}.asset-drawer{position:absolute;top:0;right:0;width:min(470px,calc(100vw - 220px));height:100%;display:grid;grid-template-rows:auto minmax(0,1fr);border-left:1px solid #dfe2e9;background:#fff;box-shadow:-12px 0 32px rgba(28,34,48,.14)}.drawer-head{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:58px;padding:0 18px;border-bottom:1px solid #e5e7ec}.drawer-head>div{display:flex;align-items:center;gap:8px;min-width:0}.drawer-head strong{overflow:hidden;color:#172848;font-size:15px;text-overflow:ellipsis;white-space:nowrap}.drawer-head span{padding:3px 6px;border:1px solid #ff9c4a;border-radius:4px;color:#df711a;font-size:9px}.drawer-head button{display:grid;place-items:center;width:30px;height:30px;border:0;border-radius:6px;background:transparent;color:#4a556b;font-size:20px;cursor:pointer}.drawer-scroll{min-height:0;overflow:auto;padding:16px}.drawer-preview{display:grid;place-items:center;min-height:320px;max-height:430px;overflow:hidden;border-radius:8px;background:#eff0f2;color:#8c95a5;font-size:11px}.drawer-preview img{width:100%;height:100%;max-height:430px;object-fit:contain}.drawer-section{display:grid;gap:8px;padding:16px 0;border-bottom:1px solid #eceef2}.drawer-section>strong,.drawer-form label>span{color:#344562;font-size:11px;font-weight:800}.drawer-section>p{margin:0;color:#526078;font-size:11px;line-height:1.65}.reference-strip{display:flex;gap:8px;overflow-x:auto;padding-bottom:3px}.reference-strip img{flex:0 0 84px;width:84px;height:72px;object-fit:contain;border:1px solid #e1e4ea;border-radius:5px;background:#f4f5f7}.drawer-form{display:grid;gap:12px;padding:16px 0;border-bottom:1px solid #eceef2}.drawer-form label{display:grid;gap:6px}.drawer-form label>div{min-height:36px;padding:9px 10px;border:1px solid #dfe2e8;border-radius:7px;background:#fafbfc;color:#45546e;font-size:11px}.prompt-section strong{display:flex;align-items:center;gap:6px}.prompt-section strong small{padding:2px 5px;border-radius:4px;background:#eef1f5;color:#7b8798;font-size:8px}.prompt-section textarea{width:100%;resize:vertical;padding:10px;border:1px solid #dfe2e8;border-radius:7px;background:#fff;color:#3f4f69;font-size:11px;line-height:1.6}.negative-prompt{padding:8px 9px;border-radius:7px;background:#fff7f4;color:#775c55!important}.prompt-meta{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;color:#7b7690!important;font-size:9px!important}.stale-note{margin:0;padding:10px 12px;border-left:3px solid #c18b35;background:#fff8e9;color:#75541f;font-size:12px;line-height:1.55}.empty{padding:26px;border:1px dashed #cbc7c0;border-radius:14px;color:#746f68}.error{color:#a33b32}.success{color:#2d7140}@keyframes progress-shimmer{from{transform:translateX(-100%)}to{transform:translateX(100%)}}@media(max-width:1280px){.asset-gallery{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:980px){.asset-production-shell{grid-template-columns:1fr}.batch-panel{border-right:0;border-bottom:1px solid #e5e7ee}.quick-filters{grid-template-columns:repeat(4,minmax(0,1fr))}.batch-generate{margin-top:0}.asset-drawer{width:min(470px,92vw)}}@media(max-width:820px){.stage-header,.task-progress-heading{align-items:stretch;flex-direction:column}.stage-title{align-items:flex-start;flex-direction:column;gap:5px}.stage-actions{width:100%}.search{min-width:0;width:100%}.asset-gallery{grid-template-columns:1fr 1fr}.quick-filters{grid-template-columns:1fr 1fr}}@media(max-width:620px){.asset-gallery{grid-template-columns:1fr}.drawer-backdrop{inset:0}.asset-drawer{width:100vw}}
</style>
