<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { remakeApi } from '../api/remake'
import AssetReviewInboxV1 from '../components/AssetReviewInboxV1.vue'
import AssetStageV4 from '../components/AssetStageV4.vue'
import EpisodeManagerV3 from '../components/EpisodeManagerV3.vue'
import FinalOutputV1 from '../components/FinalOutputV1.vue'
import H3OutputV1 from '../components/H3OutputV1.vue'
import H3QcReviewV1 from '../components/H3QcReviewV1.vue'
import LipSyncReviewV1 from '../components/LipSyncReviewV1.vue'
import ShotWorkbenchV4 from '../components/ShotWorkbenchV4.vue'
import TargetLocalizationReviewV1 from '../components/TargetLocalizationReviewV1.vue'
import TaskProgressDock from '../components/TaskProgressDock.vue'
import TimingReviewV1 from '../components/TimingReviewV1.vue'
import type { ProjectRemakePolicy, ReviewIssue, ScenePolicy } from '../types/remake'
import type { BackgroundTask, Project } from '../types/studio'

type StudioView = 'project' | 'review' | 'output'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId || ''))
const project = ref<Project | null>(null)
const policy = ref<ProjectRemakePolicy | null>(null)
const issues = ref<ReviewIssue[]>([])
const tasks = ref<BackgroundTask[]>([])
const loading = ref(true)
const savingPolicy = ref(false)
const startingAuto = ref(false)
const error = ref('')
const advancedAssetOpen = ref(false)

function viewFromRoute(): StudioView {
  const value = String(route.query.view || '')
  return value === 'review' || value === 'output' ? value : 'project'
}

const activeView = ref<StudioView>(viewFromRoute())
const activeTask = computed(() => tasks.value.find((task) => task.status === 'QUEUED' || task.status === 'PROCESSING') ?? null)
const autoTask = computed(() => tasks.value.find((task) => task.task_type === 'AUTO_REMAKE_PREP_V1') ?? null)
const postTask = computed(() => tasks.value.find((task) => task.task_type === 'POSTPRODUCTION_V1') ?? null)
const openIssueCount = computed(() => issues.value.length)
const blockingCount = computed(() => issues.value.filter((item) => item.severity === 'BLOCKING').length)
const domainEditedIssueTypes = new Set(['TARGET_CHARACTER', 'SCENE_LOCALIZATION', 'LOCALIZATION', 'DIALOGUE_TIMING', 'H3_QC', 'LIP_SYNC_QC'])
const genericIssues = computed(() => issues.value.filter((item) => !domainEditedIssueTypes.has(item.issue_type)))
const issueGroups = computed(() => {
  const result: Record<string, number> = {}
  for (const issue of issues.value) result[issue.issue_type] = (result[issue.issue_type] || 0) + 1
  return result
})

const viewItems: Array<{ id: StudioView; title: string; subtitle: string }> = [
  { id: 'project', title: '项目', subtitle: '素材、出海规则、自动处理' },
  { id: 'review', title: '待确认', subtitle: '只处理 AI 不确定或高风险内容' },
  { id: 'output', title: '成片', subtitle: '整集预览、字幕、下载' },
]

const scenePolicyOptions: Array<{ value: ScenePolicy; label: string; detail: string }> = [
  { value: 'AUTO', label: '智能判断', detail: '普通场景尽量保留，明显地域元素自动本土化' },
  { value: 'KEEP', label: '尽量保留原场景', detail: '重点替换人物、语言和声音' },
  { value: 'LOCALIZE', label: '全部本土化', detail: '所有场景都按目标地区重新设计' },
]

function issueTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    SHOT_BOUNDARY: '镜头切点',
    CHARACTER_IDENTITY: '原人物身份',
    ASSET_BINDING: '原片人物 / 场景 / 道具',
    SPEAKER: '说话人',
    TARGET_CHARACTER: '目标人物',
    SCENE_LOCALIZATION: '场景本土化',
    LOCALIZATION: '本土化对白',
    DIALOGUE_TIMING: '对白时长',
    H3_QC: 'H3 生成结果',
    LIP_SYNC_QC: '口型',
  }
  return labels[type] || type
}

async function refresh(): Promise<void> {
  if (!projectId.value) return
  try {
    const [projectResult, policyResult, issueResult, taskResult] = await Promise.all([
      api.getProject(projectId.value),
      remakeApi.getPolicy(projectId.value),
      remakeApi.listReviewIssues(projectId.value, 'OPEN'),
      api.listProjectTasks(projectId.value, 40),
    ])
    project.value = projectResult
    policy.value = policyResult
    issues.value = issueResult
    tasks.value = taskResult
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目读取失败'
  } finally {
    loading.value = false
  }
}

async function updateScenePolicy(value: ScenePolicy): Promise<void> {
  if (!project.value || savingPolicy.value) return
  savingPolicy.value = true
  try {
    policy.value = await remakeApi.updatePolicy(project.value.id, value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '场景策略保存失败'
  } finally {
    savingPolicy.value = false
  }
}

async function startAutoPrepare(): Promise<void> {
  if (!project.value || startingAuto.value || activeTask.value || !project.value.episodes.length) return
  startingAuto.value = true
  error.value = ''
  try {
    await remakeApi.startAutoPrepare(project.value.id)
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '自动处理任务启动失败'
  } finally {
    startingAuto.value = false
  }
}

async function closeIssue(issue: ReviewIssue, status: 'RESOLVED' | 'IGNORED'): Promise<void> {
  if (domainEditedIssueTypes.has(issue.issue_type)) return
  try {
    await remakeApi.setReviewIssueStatus(issue.id, status, { manual: true })
    await refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '待确认状态更新失败'
  }
}

function selectView(view: StudioView): void {
  activeView.value = view
  void router.replace({ query: { ...route.query, view } })
}

function onAdvancedAssetToggle(event: Event): void {
  const target = event.currentTarget
  advancedAssetOpen.value = target instanceof HTMLDetailsElement ? target.open : false
}

function onTaskCreated(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  tasks.value = [task, ...tasks.value.filter((item) => item.id !== task.id)]
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== projectId.value) return
  void refresh().then(() => {
    if (issues.value.length) selectView('review')
  })
}

function onTruthChanged(event: Event): void {
  const detail = (event as CustomEvent<{ project_id?: string }>).detail
  if (detail?.project_id && detail.project_id !== projectId.value) return
  void refresh()
}

watch(() => route.query.view, () => { activeView.value = viewFromRoute() })
onMounted(() => {
  window.addEventListener('studio-task-created', onTaskCreated)
  window.addEventListener('studio-task-finished', onTaskFinished)
  window.addEventListener('studio-project-truth-changed', onTruthChanged)
  void refresh()
})
onUnmounted(() => {
  window.removeEventListener('studio-task-created', onTaskCreated)
  window.removeEventListener('studio-task-finished', onTaskFinished)
  window.removeEventListener('studio-project-truth-changed', onTruthChanged)
})
</script>

<template>
  <div v-if="project" class="studio">
    <aside class="sidebar">
      <button class="back" @click="router.push('/')">← 返回项目</button>
      <div class="brand">
        <small>短剧本土化重拍</small>
        <strong>{{ project.name }}</strong>
        <span>{{ project.source_language }} → {{ project.target_language }} · {{ project.target_region }}</span>
      </div>
      <nav>
        <button v-for="item in viewItems" :key="item.id" :class="{ active: activeView === item.id }" @click="selectView(item.id)">
          <i v-if="item.id === 'review' && openIssueCount">{{ openIssueCount }}</i>
          <strong>{{ item.title }}</strong><span>{{ item.subtitle }}</span>
        </button>
      </nav>
      <div class="engine"><span>最终生成</span><strong>MiniMax H3 Local</strong><small>Ref2VA / FL2VA</small></div>
    </aside>

    <section class="workspace">
      <header class="topbar">
        <div><small>当前工作</small><strong>{{ viewItems.find((item) => item.id === activeView)?.title }}</strong><span>{{ activeTask?.message || (openIssueCount ? `${openIssueCount} 项需要确认` : '自动流程正常') }}</span></div>
        <div class="stats"><span>剧集 <b>{{ project.episodes.length }}</b></span><span :class="{ attention: openIssueCount }">待确认 <b>{{ openIssueCount }}</b></span><span>场景 <b>{{ policy?.scene_policy || 'AUTO' }}</b></span></div>
        <TaskProgressDock embedded />
      </header>
      <p v-if="error" class="error">{{ error }}</p>

      <main v-if="activeView === 'project'" class="panel">
        <section class="hero">
          <div><small>出海规则</small><h1>原短剧作为导演参考，重新拍成目标地区版本</h1><p>人物必须更换；场景按策略保留或本土化；对白自动翻译、本土化并生成固定角色声音；目标语音时长自动重排镜头，最终由本地 MiniMax H3 重拍。</p></div>
          <div class="locale"><span>{{ project.target_language }}</span><strong>{{ project.target_region }}</strong></div>
        </section>
        <section class="rules">
          <article><small>人物</small><strong>必须替换</strong><span>原 Character → TargetCharacter，全剧一致</span></article>
          <article><small>对白</small><strong>{{ project.target_language }}</strong><span>自动翻译 / Qwen3-TTS / Timing</span></article>
          <article><small>生成</small><strong>H3 Local</strong><span>原 Shot 作为导演 Reference Video</span></article>
        </section>
        <section class="scene-policy">
          <header><small>场景策略</small><strong>场景是否跟随目标地区改变</strong></header>
          <div>
            <button v-for="item in scenePolicyOptions" :key="item.value" :class="{ active: policy?.scene_policy === item.value }" :disabled="savingPolicy" @click="updateScenePolicy(item.value)"><strong>{{ item.label }}</strong><span>{{ item.detail }}</span></button>
          </div>
        </section>
        <section class="auto-run">
          <div><small>自动流程</small><strong>能自动完成的全部在后台完成</strong><p>素材 → 镜头 → ASR/OCR/VLM → 原片资产 → SourceDramaSnapshot → 目标人物/场景 → 目标对白/TTS → Timing → GenerationSegment。只有异常进入待确认。</p></div>
          <button class="primary" :disabled="startingAuto || Boolean(activeTask) || !project.episodes.length" @click="startAutoPrepare">{{ startingAuto ? '正在启动…' : activeTask ? '处理中…' : project.episodes.length ? '开始自动处理' : '先导入原短剧' }}</button>
        </section>
        <EpisodeManagerV3 :project="project" @refresh="refresh" />
      </main>

      <main v-else-if="activeView === 'review'" class="panel">
        <section class="review-head">
          <div><small>人工只处理异常</small><h1>{{ openIssueCount ? `需要确认 ${openIssueCount} 项` : '当前没有需要人工确认的问题' }}</h1><p>目标人物、目标场景、目标对白、极端镜头时长、H3 重试仍失败的版本，以及多人镜头无法安全定位说话人的口型问题，必须修改真实业务结果或重新执行对应处理；不能只关闭提示来绕过问题。</p></div>
          <div class="chips"><span>阻塞 <b>{{ blockingCount }}</b></span><span v-for="(count, key) in issueGroups" :key="key">{{ issueTypeLabel(String(key)) }} <b>{{ count }}</b></span></div>
        </section>

        <TargetLocalizationReviewV1 :project-id="project.id" @changed="refresh" />
        <TimingReviewV1 :project-id="project.id" @changed="refresh" />
        <H3QcReviewV1 :project-id="project.id" @changed="refresh" />
        <LipSyncReviewV1 :project-id="project.id" :busy="Boolean(activeTask)" @changed="refresh" />

        <section v-if="genericIssues.length" class="issues">
          <article v-for="issue in genericIssues" :key="issue.id" :class="{ blocking: issue.severity === 'BLOCKING' }">
            <div><small>{{ issue.severity === 'BLOCKING' ? '必须处理' : '建议确认' }}</small><strong>{{ issueTypeLabel(issue.issue_type) }}</strong></div>
            <p>{{ issue.reason }}</p>
            <div class="issue-actions"><button @click="closeIssue(issue, 'IGNORED')">忽略提示</button><button @click="closeIssue(issue, 'RESOLVED')">标记已处理</button></div>
          </article>
        </section>

        <section class="review-tool"><header><small>原片人物 / 场景 / 道具</small><strong>只显示冲突、未绑定和低置信度镜头</strong></header><AssetReviewInboxV1 :project-id="project.id" :episodes="project.episodes" @open-matrix="advancedAssetOpen = true" /></section>
        <details class="advanced" :open="advancedAssetOpen" @toggle="onAdvancedAssetToggle"><summary>高级：修改全部原片资产绑定</summary><AssetStageV4 :project-id="project.id" :episodes="project.episodes" /></details>
        <details class="advanced"><summary>镜头切点修正</summary><ShotWorkbenchV4 :project-id="project.id" :episodes="project.episodes" @refresh-project="refresh" /></details>
      </main>

      <main v-else class="panel">
        <section class="hero"><div><small>生成交付</small><h1>直接查看和下载本土化短剧成片</h1><p>MiniMax H3 镜头生成、自动质检、目标人物口型、最终目标对白音轨、字幕和整集拼接全部在后台完成；正常情况下这里只需要看最终剧集。</p></div></section>
        <section class="pipeline">
          <article :class="{ ready: autoTask?.status === 'READY' || autoTask?.status === 'READY_WITH_WARNINGS' }"><b>01</b><strong>原片理解</strong><span>SourceDramaSnapshot</span></article>
          <article :class="{ ready: autoTask?.status === 'READY' || autoTask?.status === 'READY_WITH_WARNINGS' }"><b>02</b><strong>目标人物 / 场景</strong><span>TargetCharacter + Scene Mapping</span></article>
          <article :class="{ ready: autoTask?.status === 'READY' || autoTask?.status === 'READY_WITH_WARNINGS' }"><b>03</b><strong>对白 / TTS / Timing</strong><span>真实目标语音 → RemakeTimeline → GenerationSegment</span></article>
          <article><b>04</b><strong>MiniMax H3</strong><span>Ref2VA / FL2VA → 自动生成目标镜头</span></article>
          <article><b>05</b><strong>自动质检</strong><span>人物 / 场景 / 动作镜头 / 连续性 → Selected Output</span></article>
          <article :class="{ ready: postTask?.status === 'READY' || postTask?.status === 'READY_WITH_WARNINGS' }"><b>06</b><strong>口型 / 字幕 / 成片</strong><span>LatentSync → 最终目标音轨 → Episode Output</span></article>
        </section>
        <FinalOutputV1 :project-id="project.id" :busy="Boolean(activeTask)" @changed="refresh" />
        <details class="advanced output-diagnostics"><summary>高级：查看 H3 镜头生成与质检明细</summary><H3OutputV1 :project-id="project.id" :busy="Boolean(activeTask)" @changed="refresh" /></details>
      </main>
    </section>
  </div>
  <div v-else-if="loading" class="state">正在读取项目…</div>
  <div v-else class="state"><strong>项目无法打开</strong><span>{{ error }}</span><button @click="router.push('/')">返回项目列表</button></div>
</template>

<style scoped>
.studio{min-height:100vh;display:grid;grid-template-columns:220px minmax(0,1fr);background:#f4f6f9;color:#34465e}.sidebar{height:100vh;position:sticky;top:0;box-sizing:border-box;padding:18px 13px;display:flex;flex-direction:column;gap:18px;border-right:1px solid #dde3eb;background:#fff}.back{align-self:start;border:0;background:none;color:#77869a;font-size:10px;cursor:pointer}.brand{display:grid;gap:4px;padding:4px 6px}.brand small,.engine span,.engine small{color:#8190a5;font-size:9px}.brand strong{font-size:15px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.brand span{color:#8a96a7;font-size:9px}.sidebar nav{display:grid;gap:7px}.sidebar nav button{position:relative;display:grid;gap:2px;padding:11px;border:1px solid transparent;border-radius:10px;background:none;text-align:left;cursor:pointer}.sidebar nav button.active{border-color:#cfdaeb;background:#f2f6fd}.sidebar nav strong{font-size:12px;color:#405168}.sidebar nav span{font-size:9px;color:#8793a4}.sidebar nav i{position:absolute;right:8px;top:8px;min-width:19px;height:19px;display:grid;place-items:center;border-radius:99px;background:#c98522;color:#fff;font-size:8px;font-style:normal}.engine{margin-top:auto;display:grid;gap:2px;padding:11px;border-radius:10px;background:#eef4ff}.engine strong{color:#315bab;font-size:11px}.workspace{min-width:0}.topbar{min-height:72px;display:grid;grid-template-columns:minmax(240px,1fr) auto minmax(250px,350px);gap:16px;align-items:center;padding:9px 20px;border-bottom:1px solid #dfe5ed;background:#fff}.topbar>div:first-child{display:grid;gap:2px}.topbar small{font-size:9px;color:#8995a5}.topbar strong{font-size:13px}.topbar span{font-size:9px;color:#7d8a9d}.stats{display:flex;gap:6px}.stats span{padding:7px 9px;border:1px solid #e1e6ed;border-radius:8px}.stats b{color:#465a75}.stats .attention{background:#fff8e8;border-color:#ecd69c}.error{margin:12px 20px 0;padding:9px 11px;border:1px solid #ebcccc;border-radius:8px;background:#fff3f3;color:#a84a4a;font-size:10px}.panel{max-width:1480px;margin:auto;padding:18px 22px 34px;display:grid;gap:13px}.hero,.rules,.scene-policy,.auto-run,.review-head,.review-tool,.advanced,.pipeline{border:1px solid #dfe5ed;border-radius:13px;background:#fff}.hero{display:flex;justify-content:space-between;gap:18px;padding:18px}.hero small,.scene-policy small,.auto-run small,.review-head small,.review-tool small{font-size:9px;color:#8693a5}.hero h1,.review-head h1{margin:3px 0 5px;font-size:21px}.hero p,.review-head p,.auto-run p{margin:0;max-width:900px;color:#78869a;font-size:10px;line-height:1.6}.locale{min-width:140px;display:grid;place-items:center;align-content:center;border-radius:10px;background:#f3f6fb}.locale span{font-size:9px;color:#8794a5}.locale strong{font-size:14px;color:#466080}.rules{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:10px}.rules article{display:grid;gap:2px;padding:9px;border-radius:8px;background:#f8fafc}.rules small,.rules span{font-size:9px;color:#8793a4}.rules strong{font-size:11px}.scene-policy{padding:14px;display:grid;gap:9px}.scene-policy header{display:grid;gap:2px}.scene-policy header strong{font-size:11px}.scene-policy>div{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.scene-policy button{display:grid;gap:3px;padding:10px;border:1px solid #dfe5ed;border-radius:8px;background:#fff;text-align:left;cursor:pointer}.scene-policy button.active{border-color:#91abe0;background:#f1f6ff}.scene-policy button strong{font-size:10px}.scene-policy button span{font-size:9px;color:#8793a4}.auto-run{padding:14px 16px;display:flex;align-items:center;justify-content:space-between;gap:20px}.auto-run>div{display:grid;gap:3px}.auto-run>div>strong{font-size:13px}.primary{min-height:38px;border:0;border-radius:8px;padding:0 15px;background:#3566d6;color:#fff;font-size:10px;font-weight:800;cursor:pointer}.primary:disabled{opacity:.45}.review-head{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:16px}.chips{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:5px}.chips span{padding:5px 8px;border-radius:99px;background:#f2f4f7;color:#718096;font-size:9px}.issues{display:grid;gap:7px}.issues article{display:grid;grid-template-columns:130px 1fr auto;align-items:center;gap:12px;padding:10px 12px;border:1px solid #e8d7a7;border-radius:9px;background:#fffaf0}.issues article.blocking{border-color:#e8c4c4;background:#fff4f4}.issues article>div:first-child{display:grid}.issues small{font-size:8px;color:#9b7837}.issues strong,.issues p{font-size:10px}.issues p{margin:0;color:#6f6048}.issue-actions{display:flex;gap:6px}.issue-actions button{min-height:30px;border:1px solid #d7dfe8;border-radius:7px;background:#fff;color:#66758a;font-size:9px;cursor:pointer}.review-tool{overflow:hidden}.review-tool>header{display:grid;gap:2px;padding:12px 15px 0}.review-tool>header strong{font-size:10px}.advanced{overflow:hidden}.advanced>summary{padding:12px 15px;font-size:10px;font-weight:750;cursor:pointer}.advanced[open]>summary{border-bottom:1px solid #e5e9ef}.output-diagnostics{background:#f9fafc}.pipeline{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:10px}.pipeline article{min-height:90px;display:grid;align-content:start;gap:4px;padding:12px;border:1px solid #e2e7ee;border-radius:9px}.pipeline article.ready{border-color:#cce2d7;background:#f6fbf8}.pipeline b{font-size:9px;color:#9ba5b3}.pipeline strong{font-size:11px}.pipeline span{font-size:9px;color:#8793a4}.state{min-height:100vh;display:grid;place-items:center;align-content:center;gap:8px;background:#f4f6f9;color:#748297}.state button{border:1px solid #d8e0e9;border-radius:8px;padding:8px;background:#fff;cursor:pointer}@media(max-width:1050px){.studio{grid-template-columns:185px minmax(0,1fr)}.topbar{grid-template-columns:1fr}.rules,.scene-policy>div,.pipeline{grid-template-columns:1fr}.auto-run,.review-head,.hero{align-items:stretch;flex-direction:column}.issues article{grid-template-columns:1fr}}
</style>