<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/client'
import { remakeApi } from '../api/remake'
import AssetReviewInboxV1 from '../components/AssetReviewInboxV1.vue'
import AssetStageV4 from '../components/AssetStageV4.vue'
import EpisodeManagerV3 from '../components/EpisodeManagerV3.vue'
import LocalizationStageV1 from '../components/LocalizationStageV1.vue'
import ShotWorkbenchV4 from '../components/ShotWorkbenchV4.vue'
import TaskProgressDock from '../components/TaskProgressDock.vue'
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
const openIssueCount = computed(() => issues.value.length)
const blockingCount = computed(() => issues.value.filter((item) => item.severity === 'BLOCKING').length)
const issueGroups = computed(() => {
  const result: Record<string, number> = {}
  for (const issue of issues.value) result[issue.issue_type] = (result[issue.issue_type] || 0) + 1
  return result
})

const viewItems: Array<{ id: StudioView; title: string; subtitle: string }> = [
  { id: 'project', title: '项目', subtitle: '素材、目标地区、自动处理' },
  { id: 'review', title: '待确认', subtitle: '只处理 AI 不确定或高风险内容' },
  { id: 'output', title: '成片', subtitle: 'H3 生成、质检、整集导出' },
]

const scenePolicyOptions: Array<{ value: ScenePolicy; label: string; detail: string }> = [
  { value: 'AUTO', label: '智能判断', detail: '普通场景尽量保留，明显地域元素自动本土化' },
  { value: 'KEEP', label: '尽量保留原场景', detail: '重点替换人物、语言和声音' },
  { value: 'LOCALIZE', label: '全部本土化', detail: '人物和场景都按目标地区重新设计' },
]

function issueTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    SHOT_BOUNDARY: '镜头切点',
    ASSET_BINDING: '人物 / 场景 / 道具',
    SPEAKER: '说话人',
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
  try {
    await remakeApi.setReviewIssueStatus(issue.id, status, {
      manual: true,
      note: status === 'IGNORED' ? '用户选择忽略当前自动提示' : '用户确认已处理',
    })
    issues.value = issues.value.filter((item) => item.id !== issue.id)
  } catch (err) {
    error.value = err instanceof Error ? err.message : '待确认状态更新失败'
  }
}

function selectView(view: StudioView): void {
  activeView.value = view
  const query = { ...route.query, view } as Record<string, string | string[] | null | undefined>
  delete query.stage
  delete query.breakdown_view
  delete query.asset_tab
  void router.replace({ query })
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
  <div v-if="project" class="studio-v4">
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
          <strong>{{ item.title }}</strong>
          <span>{{ item.subtitle }}</span>
        </button>
      </nav>

      <div class="engine-card">
        <span>生成引擎</span>
        <strong>MiniMax H3</strong>
        <small>本地部署 · Ref2VA / FL2VA</small>
      </div>
    </aside>

    <section class="workspace">
      <header class="command-bar">
        <div>
          <small>当前工作</small>
          <strong>{{ viewItems.find((item) => item.id === activeView)?.title }}</strong>
          <span v-if="activeTask">{{ activeTask.title }} · {{ activeTask.message || '处理中' }}</span>
          <span v-else-if="openIssueCount">有 {{ openIssueCount }} 项需要人工确认</span>
          <span v-else>自动流程会把异常集中到「待确认」</span>
        </div>
        <div class="command-stats">
          <div><small>剧集</small><strong>{{ project.episodes.length }}</strong></div>
          <div :class="{ attention: openIssueCount }"><small>待确认</small><strong>{{ openIssueCount }}</strong></div>
          <div><small>场景策略</small><strong>{{ policy?.scene_policy || 'AUTO' }}</strong></div>
        </div>
        <TaskProgressDock embedded />
      </header>

      <p v-if="error" class="error-banner">{{ error }}</p>

      <main v-if="activeView === 'project'" class="main-panel project-panel">
        <section class="remake-settings">
          <header>
            <div><small>出海规则</small><h1>原片是导演参考，不是最终画面</h1><p>人物默认替换成目标地区角色；对白翻译成目标语言并重新对口型；不同语言造成的时长差由目标时间轴自动延长、裁剪或跨反应镜处理。</p></div>
            <div class="locale"><span>{{ project.target_language }}</span><strong>{{ project.target_region }}</strong></div>
          </header>

          <div class="fixed-policy-grid">
            <article><small>人物</small><strong>必须本土化替换</strong><span>Source Character → Target Character，全剧保持一致</span></article>
            <article><small>语言</small><strong>{{ project.target_language }}</strong><span>翻译 / 本土化 / TTS / Lip Sync</span></article>
            <article><small>生成</small><strong>MiniMax H3 Local</strong><span>原 Shot 作为 Reference Video</span></article>
          </div>

          <section class="scene-policy-card">
            <div><small>场景策略</small><strong>选择场景要不要跟随目标地区改变</strong></div>
            <div class="policy-options">
              <button v-for="item in scenePolicyOptions" :key="item.value" :class="{ active: policy?.scene_policy === item.value }" :disabled="savingPolicy" @click="updateScenePolicy(item.value)">
                <strong>{{ item.label }}</strong><span>{{ item.detail }}</span>
              </button>
            </div>
          </section>
        </section>

        <section class="auto-card">
          <div>
            <small>自动流程</small>
            <h2>{{ activeTask ? '后台正在处理' : '一次启动，自动完成能自动完成的部分' }}</h2>
            <p>当前第一版会自动完成：素材准备 → 镜头检测 → ASR / OCR / Qwen3-VL 拉片 → 人物 / 场景 / 道具识别。异常自动进入待确认，不再要求逐页点击。</p>
          </div>
          <button class="primary" :disabled="startingAuto || Boolean(activeTask) || !project.episodes.length" @click="startAutoPrepare">
            {{ startingAuto ? '正在启动…' : activeTask ? '处理中…' : project.episodes.length ? '开始自动处理' : '先导入原短剧' }}
          </button>
        </section>

        <div class="source-manager-wrap"><EpisodeManagerV3 :project="project" @refresh="refresh" /></div>
      </main>

      <main v-else-if="activeView === 'review'" class="main-panel review-panel">
        <section class="review-summary">
          <div><small>人工只处理异常</small><h1>{{ openIssueCount ? `需要确认 ${openIssueCount} 项` : '当前没有需要人工确认的问题' }}</h1><p>高置信度内容自动继续；低置信度、冲突、镜头切点异常以及后续对白时长/H3 QC 问题统一进入这里。</p></div>
          <div class="review-counts"><span>阻塞 <strong>{{ blockingCount }}</strong></span><span v-for="(count, key) in issueGroups" :key="key">{{ issueTypeLabel(String(key)) }} <strong>{{ count }}</strong></span></div>
        </section>

        <section v-if="issues.length" class="issue-list">
          <article v-for="issue in issues" :key="issue.id" :class="['issue-card', { blocking: issue.severity === 'BLOCKING' }]">
            <div class="issue-type"><small>{{ issue.severity === 'BLOCKING' ? '必须处理' : '建议确认' }}</small><strong>{{ issueTypeLabel(issue.issue_type) }}</strong></div>
            <div class="issue-copy"><strong>{{ issue.reason }}</strong><span v-if="issue.shot_id">关联镜头：{{ issue.shot_id }}</span></div>
            <div class="issue-actions"><button @click="closeIssue(issue, 'IGNORED')">忽略提示</button><button class="done" @click="closeIssue(issue, 'RESOLVED')">我已处理</button></div>
          </article>
        </section>

        <section class="review-tool">
          <header><div><small>人物 / 场景 / 道具</small><strong>只显示冲突、未绑定和低置信度镜头</strong></div></header>
          <AssetReviewInboxV1 :project-id="project.id" :episodes="project.episodes" @open-matrix="advancedAssetOpen = true" />
        </section>

        <details class="advanced-tool" :open="advancedAssetOpen" @toggle="advancedAssetOpen = ($event.target as HTMLDetailsElement).open">
          <summary>高级：查看并修改全部人物 / 场景 / 道具绑定</summary>
          <AssetStageV4 :project-id="project.id" :episodes="project.episodes" />
        </details>

        <details class="advanced-tool">
          <summary>镜头切点修正（只有自动检测异常时才需要打开）</summary>
          <ShotWorkbenchV4 :project-id="project.id" :episodes="project.episodes" @refresh-project="refresh" />
        </details>

        <details class="advanced-tool">
          <summary>本土化稿件过渡工具（后续改为自动翻译 + 只审异常）</summary>
          <LocalizationStageV1 :project="project" />
        </details>
      </main>

      <main v-else class="main-panel output-panel">
        <section class="output-hero">
          <small>最终目标</small>
          <h1>本地 MiniMax H3 重拍整部短剧</h1>
          <p>这一页只负责看生成进度、失败镜头、成片和导出。TTS、对白时长规划、H3 Ref2VA/FL2VA、Lip Sync、QC 都是后台能力，不再各做一个页面。</p>
        </section>
        <section class="output-grid">
          <article class="ready"><span>01</span><strong>原短剧理解</strong><small>{{ autoTask?.status === 'READY' || autoTask?.status === 'READY_WITH_WARNINGS' ? '已有自动处理结果' : '等待自动处理完成' }}</small></article>
          <article><span>02</span><strong>目标人物 / 场景</strong><small>下一阶段接入 Target Character / Scene Mapping</small></article>
          <article><span>03</span><strong>对白 + TTS + Timing</strong><small>将按真实目标语音时长重排镜头</small></article>
          <article><span>04</span><strong>MiniMax H3 Local</strong><small>Ref2VA 主重制 · FL2VA 延长 / 补镜</small></article>
          <article><span>05</span><strong>Lip Sync + QC</strong><small>失败自动重试，多次失败才进入待确认</small></article>
          <article><span>06</span><strong>整集导出</strong><small>字幕、混音、拼接、最终视频</small></article>
        </section>
        <button class="primary disabled-action" disabled>H3 生成链接入后在这里开始 / 继续生成</button>
      </main>
    </section>
  </div>

  <div v-else-if="loading" class="screen-state">正在读取项目…</div>
  <div v-else class="screen-state"><strong>项目无法打开</strong><span>{{ error }}</span><button @click="router.push('/')">返回项目列表</button></div>
</template>

<style scoped>
.studio-v4 { min-height: 100vh; display: grid; grid-template-columns: 230px minmax(0, 1fr); background: #f4f6f9; color: #2e3f57; }.sidebar { position: sticky; top: 0; height: 100vh; display: flex; flex-direction: column; gap: 18px; padding: 18px 14px; border-right: 1px solid #dde3eb; background: #fff; }.back { align-self: start; border: 0; background: transparent; color: #758399; font-size: 11px; cursor: pointer; }.brand { display: grid; gap: 4px; padding: 4px 6px 10px; }.brand small { color: #7186a7; font-size: 9px; font-weight: 850; }.brand strong { overflow: hidden; font-size: 15px; text-overflow: ellipsis; white-space: nowrap; }.brand span { color: #8894a4; font-size: 9px; }.sidebar nav { display: grid; gap: 7px; }.sidebar nav button { position: relative; display: grid; gap: 2px; padding: 11px 12px; border: 1px solid transparent; border-radius: 10px; background: transparent; text-align: left; cursor: pointer; }.sidebar nav button.active { border-color: #cfdaeb; background: #f2f6fd; }.sidebar nav strong { color: #405168; font-size: 12px; }.sidebar nav span { color: #8995a5; font-size: 9px; line-height: 1.45; }.sidebar nav i { position: absolute; top: 8px; right: 8px; min-width: 20px; height: 20px; display: grid; place-items: center; border-radius: 999px; background: #cf8a24; color: #fff; font-size: 9px; font-style: normal; font-weight: 850; }.engine-card { margin-top: auto; display: grid; gap: 2px; padding: 11px; border-radius: 10px; background: #eef4ff; }.engine-card span, .engine-card small { color: #7184a3; font-size: 9px; }.engine-card strong { color: #315bab; font-size: 12px; }.workspace { min-width: 0; }.command-bar { min-height: 72px; display: grid; grid-template-columns: minmax(250px, 1fr) auto minmax(260px, 360px); gap: 18px; align-items: center; padding: 10px 20px; border-bottom: 1px solid #dfe5ed; background: #fff; }.command-bar > div:first-child { display: grid; gap: 1px; }.command-bar small { color: #8a95a5; font-size: 9px; }.command-bar strong { color: #374960; font-size: 13px; }.command-bar span { color: #78869a; font-size: 10px; }.command-stats { display: flex; gap: 7px; }.command-stats > div { min-width: 78px; display: grid; gap: 1px; padding: 7px 9px; border: 1px solid #e1e6ed; border-radius: 8px; }.command-stats > div.attention { border-color: #ead59f; background: #fff9ec; }.command-stats > div.attention strong { color: #96640e; }.error-banner { margin: 12px 20px 0; padding: 9px 11px; border: 1px solid #edcdcd; border-radius: 9px; background: #fff3f3; color: #aa4949; font-size: 11px; }.main-panel { max-width: 1500px; margin: 0 auto; padding: 18px 22px 32px; display: grid; gap: 14px; }.remake-settings, .auto-card, .review-summary, .review-tool, .output-hero, .advanced-tool { border: 1px solid #dfe5ed; border-radius: 14px; background: #fff; }.remake-settings { padding: 18px; display: grid; gap: 14px; }.remake-settings > header { display: flex; justify-content: space-between; gap: 20px; }.remake-settings h1, .review-summary h1, .output-hero h1 { margin: 3px 0 5px; font-size: 22px; }.remake-settings p, .review-summary p, .output-hero p { max-width: 920px; margin: 0; color: #778598; font-size: 11px; line-height: 1.6; }.locale { min-width: 150px; display: grid; place-items: center; align-content: center; padding: 10px; border-radius: 10px; background: #f3f6fb; }.locale span { color: #8b96a5; font-size: 9px; }.locale strong { color: #455d80; font-size: 14px; }.fixed-policy-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }.fixed-policy-grid article { display: grid; gap: 2px; padding: 11px; border: 1px solid #e4e8ee; border-radius: 9px; background: #fbfcfe; }.fixed-policy-grid article small { color: #8995a5; font-size: 9px; }.fixed-policy-grid article strong { color: #42536a; font-size: 11px; }.fixed-policy-grid article span { color: #8792a3; font-size: 9px; }.scene-policy-card { display: grid; gap: 9px; padding-top: 4px; }.scene-policy-card > div:first-child { display: grid; gap: 2px; }.scene-policy-card small { color: #8995a5; font-size: 9px; }.scene-policy-card strong { font-size: 11px; }.policy-options { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }.policy-options button { display: grid; gap: 3px; padding: 11px; border: 1px solid #dfe5ed; border-radius: 9px; background: #fff; text-align: left; cursor: pointer; }.policy-options button.active { border-color: #93afe4; background: #f3f7ff; }.policy-options button strong { color: #445773; font-size: 11px; }.policy-options button span { color: #8491a3; font-size: 9px; line-height: 1.45; }.auto-card { display: flex; justify-content: space-between; gap: 22px; align-items: center; padding: 16px 18px; }.auto-card > div { display: grid; gap: 3px; }.auto-card h2 { margin: 0; font-size: 16px; }.auto-card p { max-width: 900px; margin: 0; color: #7c899b; font-size: 10px; line-height: 1.55; }.primary { min-height: 40px; border: 0; border-radius: 9px; padding: 0 16px; background: #3566d6; color: #fff; font-size: 11px; font-weight: 850; cursor: pointer; }.primary:disabled { opacity: .45; cursor: not-allowed; }.source-manager-wrap :deep(.source-next-step) { display: none; }.review-summary { display: flex; justify-content: space-between; gap: 20px; align-items: center; padding: 16px 18px; }.review-counts { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }.review-counts span { padding: 6px 8px; border-radius: 999px; background: #f2f4f7; color: #718096; font-size: 9px; }.review-counts strong { color: #4f5f75; }.issue-list { display: grid; gap: 7px; }.issue-card { display: grid; grid-template-columns: 135px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 11px 12px; border: 1px solid #ead9aa; border-radius: 10px; background: #fffaf0; }.issue-card.blocking { border-color: #ebc5c5; background: #fff4f4; }.issue-type, .issue-copy { display: grid; gap: 2px; }.issue-type small { color: #9d7a35; font-size: 8px; }.issue-type strong, .issue-copy strong { color: #604f31; font-size: 10px; }.issue-copy span { color: #917b58; font-size: 8px; }.issue-actions { display: flex; gap: 6px; }.issue-actions button { min-height: 32px; border: 1px solid #d8c9a8; border-radius: 7px; padding: 0 9px; background: #fff; color: #7b6640; font-size: 9px; cursor: pointer; }.issue-actions .done { border-color: #94cbb3; color: #237552; }.review-tool { overflow: hidden; }.review-tool > header { padding: 12px 16px 0; }.review-tool > header > div { display: grid; gap: 2px; }.review-tool > header small { color: #8995a5; font-size: 9px; }.review-tool > header strong { color: #42536a; font-size: 11px; }.advanced-tool { padding: 0; overflow: hidden; }.advanced-tool > summary { padding: 12px 15px; color: #5e6d82; font-size: 10px; font-weight: 800; cursor: pointer; }.advanced-tool[open] > summary { border-bottom: 1px solid #e5e9ef; }.output-hero { padding: 20px; }.output-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }.output-grid article { min-height: 110px; display: grid; align-content: start; gap: 5px; padding: 14px; border: 1px solid #e1e6ed; border-radius: 11px; background: #fff; }.output-grid article span { color: #9aa4b2; font-size: 9px; font-weight: 850; }.output-grid article strong { color: #45566d; font-size: 12px; }.output-grid article small { color: #8793a4; font-size: 9px; line-height: 1.5; }.output-grid article.ready { border-color: #cce3d8; background: #f7fbf9; }.disabled-action { justify-self: start; }.screen-state { min-height: 100vh; display: grid; place-items: center; align-content: center; gap: 7px; background: #f4f6f9; color: #778598; }.screen-state button { border: 1px solid #d8e0e9; border-radius: 8px; padding: 8px 10px; background: #fff; cursor: pointer; }
@media (max-width: 1050px) { .studio-v4 { grid-template-columns: 190px minmax(0, 1fr); }.command-bar { grid-template-columns: 1fr; }.fixed-policy-grid, .policy-options, .output-grid { grid-template-columns: 1fr; }.issue-card { grid-template-columns: 1fr; }.review-summary, .auto-card { align-items: stretch; flex-direction: column; } }
</style>
