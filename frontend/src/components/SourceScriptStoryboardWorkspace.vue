<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getProject } from '@/features/projects/api'
import {
  editStoryboardShot,
  getSourceAnalysisStatus,
  getSourceScript,
  getStoryboardDraft,
  startSourceAnalysis,
  type SourceAnalysisStatusRead,
  type SourceScriptRead,
  type SourceScriptShot,
  type StoryboardDraftRead,
  type StoryboardShotOverride,
} from '@/features/projects/sourceAnalysis'
import type { ProjectRead } from '@/features/projects/types'

type WorkspaceTab = 'script' | 'storyboard' | 'assets'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const status = ref<SourceAnalysisStatusRead | null>(null)
const script = ref<SourceScriptRead | null>(null)
const draft = ref<StoryboardDraftRead | null>(null)
const loading = ref(true)
const starting = ref(false)
const savingShot = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const activeTab = ref<WorkspaceTab>('script')
const editingShot = ref<StoryboardShotOverride | null>(null)
let pollTimer: number | null = null

const visible = computed(() => project.value?.project_type === 'REPLICA' || project.value?.project_type === 'REDRAW')
const isReady = computed(() => status.value?.state === 'READY' && script.value?.state === 'READY')
const draftByShot = computed(() => new Map(
  draft.value?.status === 'CURRENT'
    ? draft.value.overrides.map((item) => [item.shot_anchor_id, item] as const)
    : [],
))
const sceneCount = computed(() => script.value?.scenes.length ?? 0)
const shotCount = computed(() => script.value?.scenes.reduce((sum, scene) => sum + scene.shots.length, 0) ?? 0)

function commandKey(): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
  return `source-analysis-${suffix}`.slice(0, 128)
}

function formatTime(us: number): string {
  const totalSeconds = Math.max(0, us) / 1_000_000
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds - minutes * 60
  return `${String(minutes).padStart(2, '0')}:${seconds.toFixed(2).padStart(5, '0')}`
}

function stopPolling(): void {
  if (pollTimer !== null) window.clearInterval(pollTimer)
  pollTimer = null
}

async function loadResults(): Promise<void> {
  const [sourceScript, storyboardDraft] = await Promise.all([
    getSourceScript(projectId.value),
    getStoryboardDraft(projectId.value),
  ])
  script.value = sourceScript
  draft.value = storyboardDraft
}

async function refreshStatus(): Promise<void> {
  status.value = await getSourceAnalysisStatus(projectId.value)
}

function startPolling(): void {
  if (pollTimer !== null) return
  pollTimer = window.setInterval(async () => {
    try {
      await refreshStatus()
      if (status.value?.state !== 'RUNNING') {
        stopPolling()
        if (status.value?.state === 'READY') await loadResults()
      }
    } catch (error) {
      stopPolling()
      errorMessage.value = error instanceof Error ? error.message : '原片解析状态读取失败'
    }
  }, 1200)
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    project.value = await getProject(projectId.value)
    if (!visible.value) return
    await refreshStatus()
    if (status.value?.state === 'READY') await loadResults()
    if (status.value?.state === 'RUNNING') startPolling()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '原片结果读取失败'
  } finally {
    loading.value = false
  }
}

async function analyzeSource(): Promise<void> {
  if (starting.value || status.value?.state === 'RUNNING') return
  starting.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    status.value = await startSourceAnalysis(projectId.value, commandKey())
    if (status.value.state === 'READY') await loadResults()
    else startPolling()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '原片解析启动失败'
  } finally {
    starting.value = false
  }
}

function effectiveShot(shot: SourceScriptShot): StoryboardShotOverride {
  return draftByShot.value.get(shot.shot_anchor_id) ?? {
    shot_anchor_id: shot.shot_anchor_id,
    visual_description: shot.visual_description,
    shot_size: shot.shot_size,
    composition: shot.composition,
    angle_or_type: shot.angle_or_type,
    movement: shot.movement,
    focal_length_dof: shot.focal_length_dof,
  }
}

function openShotEditor(shot: SourceScriptShot): void {
  editingShot.value = { ...effectiveShot(shot) }
  successMessage.value = ''
}

function closeShotEditor(): void {
  if (!savingShot.value) editingShot.value = null
}

async function saveShot(): Promise<void> {
  if (!editingShot.value || savingShot.value) return
  savingShot.value = true
  errorMessage.value = ''
  successMessage.value = ''
  let saved = false
  try {
    draft.value = await editStoryboardShot(projectId.value, {
      expected_revision: draft.value?.revision ?? null,
      shot_anchor_id: editingShot.value.shot_anchor_id,
      visual_description: editingShot.value.visual_description,
      shot_size: editingShot.value.shot_size,
      composition: editingShot.value.composition,
      angle_or_type: editingShot.value.angle_or_type,
      movement: editingShot.value.movement,
      focal_length_dof: editingShot.value.focal_length_dof,
    })
    successMessage.value = '分镜草稿已保存。原片事实保持不变。'
    saved = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '分镜草稿保存失败'
  } finally {
    savingShot.value = false
    if (saved) closeShotEditor()
  }
}

async function resetShot(shot: SourceScriptShot): Promise<void> {
  if (savingShot.value) return
  savingShot.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    draft.value = await editStoryboardShot(projectId.value, {
      expected_revision: draft.value?.revision ?? null,
      shot_anchor_id: shot.shot_anchor_id,
      reset_to_source: true,
    })
    successMessage.value = `镜头 #${String(shot.shot_number).padStart(3, '0')} 已恢复原片分镜。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '恢复原片分镜失败'
  } finally {
    savingShot.value = false
  }
}

onMounted(load)
onBeforeUnmount(stopPolling)
</script>

<template>
  <section v-if="visible" class="source-workspace" data-testid="source-script-storyboard-workspace">
    <header class="workspace-heading">
      <div>
        <p class="eyebrow">原片解析结果</p>
        <h2>剧本与分镜</h2>
        <p>上传原片后只解析一次。镜头、对白、剧情、人物和场景都在后台处理，完成后直接得到可工作的剧本和分镜。</p>
      </div>
      <button
        v-if="status?.state !== 'READY'"
        class="primary-button"
        type="button"
        :disabled="loading || starting || status?.state === 'RUNNING'"
        data-testid="analyze-source-button"
        @click="analyzeSource"
      >
        {{ starting ? '正在启动…' : status?.state === 'NEEDS_REFRESH' || status?.state === 'FAILED' ? '重新解析原片' : '解析原片' }}
      </button>
    </header>

    <p v-if="errorMessage" class="message error">{{ errorMessage }}</p>
    <p v-if="successMessage" class="message success">{{ successMessage }}</p>

    <div v-if="loading" class="state-box">正在读取原片结果…</div>
    <div v-else-if="status?.state === 'RUNNING'" class="state-box">
      <div class="progress-copy"><strong>{{ status.message }}</strong><span>{{ status.progress_percent }}%</span></div>
      <div class="progress-track"><i :style="{ width: `${status.progress_percent}%` }"></i></div>
      <small>不需要逐步操作，完成后这里会直接出现剧本和分镜。</small>
    </div>
    <div v-else-if="status?.state === 'FAILED'" class="state-box warning">
      <strong>这次解析没有完成</strong><p>{{ status.message }}</p>
    </div>
    <div v-else-if="status?.state === 'NEEDS_REFRESH'" class="state-box warning">
      <strong>原片结果有更新</strong><p>重新解析时只补跑已经失效的部分。</p>
    </div>
    <div v-else-if="status?.state === 'NOT_READY'" class="state-box">
      <strong>还没有可用的原片剧本</strong><p>上传完整视频后，点击“解析原片”。</p>
    </div>

    <template v-else-if="isReady && script">
      <div class="summary">
        <span><b>{{ sceneCount }}</b> 场</span>
        <span><b>{{ shotCount }}</b> 镜</span>
        <span><b>{{ script.characters.length }}</b> 人物</span>
        <span><b>{{ script.props.length }}</b> 关键道具</span>
      </div>

      <nav class="tabs">
        <button :class="{ active: activeTab === 'script' }" type="button" @click="activeTab = 'script'">原片剧本</button>
        <button :class="{ active: activeTab === 'storyboard' }" type="button" @click="activeTab = 'storyboard'">分镜</button>
        <button :class="{ active: activeTab === 'assets' }" type="button" @click="activeTab = 'assets'">人物资产</button>
      </nav>

      <div v-if="activeTab === 'script'" class="result-body" data-testid="source-script-view">
        <article v-for="scene in script.scenes" :key="`${scene.scene_number}-${scene.start_us}`" class="scene">
          <header>
            <div><small>场 {{ scene.scene_number }}</small><h3>{{ scene.scene_name }}</h3></div>
            <div class="scene-meta">
              <span>{{ formatTime(scene.start_us) }} – {{ formatTime(scene.end_us) }}</span>
              <span v-if="scene.character_names.length">{{ scene.character_names.join(' · ') }}</span>
            </div>
          </header>
          <div class="script-copy">
            <template v-for="shot in scene.shots" :key="shot.shot_anchor_id">
              <p class="action">{{ shot.visual_description }}</p>
              <div v-for="dialogue in shot.dialogues" :key="dialogue.utterance_id" class="dialogue">
                <strong>{{ dialogue.speaker_name }}</strong><p>{{ dialogue.text }}</p>
              </div>
            </template>
          </div>
        </article>
      </div>

      <div v-else-if="activeTab === 'storyboard'" class="result-body" data-testid="source-storyboard-view">
        <div class="draft-note">
          <strong>{{ draft?.status === 'STALE' ? '旧分镜草稿已归档' : draft?.overrides.length ? `分镜编辑草稿 r${draft.revision}` : '原片分镜' }}</strong>
          <span>{{ draft?.status === 'STALE' ? '原片结果已更新，旧草稿不会自动套用；新的修改会从当前原片分镜开始。' : '直接修改保存为工作草稿，不覆盖原片事实。' }}</span>
        </div>
        <section v-for="scene in script.scenes" :key="`board-${scene.scene_number}-${scene.start_us}`" class="board-scene">
          <header><strong>场 {{ scene.scene_number }} · {{ scene.scene_name }}</strong><span>{{ scene.shots.length }} 镜</span></header>
          <article v-for="shot in scene.shots" :key="shot.shot_anchor_id" class="shot-card">
            <div class="shot-number"><b>#{{ String(shot.shot_number).padStart(3, '0') }}</b><small>{{ formatTime(shot.start_us) }} – {{ formatTime(shot.end_us) }}</small></div>
            <div class="shot-copy">
              <div class="tags">
                <span>{{ effectiveShot(shot).shot_size || '景别未标注' }}</span>
                <span v-if="effectiveShot(shot).movement">{{ effectiveShot(shot).movement }}</span>
                <em v-if="draftByShot.has(shot.shot_anchor_id)">已修改</em>
              </div>
              <p>{{ effectiveShot(shot).visual_description }}</p>
              <small v-if="effectiveShot(shot).composition">构图：{{ effectiveShot(shot).composition }}</small>
            </div>
            <div class="shot-actions">
              <button type="button" @click="openShotEditor(shot)">编辑分镜</button>
              <button v-if="draftByShot.has(shot.shot_anchor_id)" type="button" @click="resetShot(shot)">恢复原片</button>
            </div>
          </article>
        </section>
      </div>

      <div v-else class="assets" data-testid="source-assets-view">
        <section><small>人物</small><div><span v-for="item in script.characters" :key="item.id">{{ item.name }}</span></div></section>
        <section><small>场景</small><div><span v-for="scene in script.scenes" :key="scene.scene_number">{{ scene.scene_name }}</span></div></section>
        <section><small>关键道具</small><div><span v-for="item in script.props" :key="item.id">{{ item.name }}</span></div></section>
      </div>
    </template>

    <div v-if="editingShot" class="editor-backdrop" @click.self="closeShotEditor">
      <form class="editor" data-testid="storyboard-shot-editor" @submit.prevent="saveShot">
        <header><div><small>分镜编辑草稿</small><h3>修改镜头</h3></div><button type="button" :disabled="savingShot" @click="closeShotEditor">×</button></header>
        <label><span>画面 / 动作</span><textarea v-model="editingShot.visual_description" rows="5" required></textarea></label>
        <div class="two-columns">
          <label><span>景别</span><input v-model="editingShot.shot_size" /></label>
          <label><span>镜头类型 / 角度</span><input v-model="editingShot.angle_or_type" /></label>
        </div>
        <label><span>构图</span><input v-model="editingShot.composition" /></label>
        <label><span>运镜</span><input v-model="editingShot.movement" /></label>
        <label><span>焦段 / 景深</span><input v-model="editingShot.focal_length_dof" /></label>
        <footer><span>保存只修改工作草稿，原片分析保持只读。</span><div><button type="button" :disabled="savingShot" @click="closeShotEditor">取消</button><button class="save" type="submit" :disabled="savingShot">{{ savingShot ? '保存中…' : '保存修改' }}</button></div></footer>
      </form>
    </div>
  </section>
</template>

<style scoped>
.source-workspace { max-width: 1320px; margin: 20px auto 40px; padding: 0 24px; color: #172033; }
.workspace-heading { display:flex; justify-content:space-between; gap:24px; padding:24px 26px; border:1px solid #e1e6ed; border-radius:18px 18px 0 0; background:#fff; }
.workspace-heading h2 { margin:4px 0 8px; font-size:24px; }
.workspace-heading p { max-width:780px; margin:0; color:#657083; font-size:13px; line-height:1.65; }
.eyebrow { color:#7b8492 !important; font-size:11px !important; font-weight:800; letter-spacing:.08em; }
.primary-button { align-self:flex-start; border:0; border-radius:10px; padding:11px 18px; background:#172033; color:#fff; font-weight:800; cursor:pointer; white-space:nowrap; }
button:disabled { opacity:.5; cursor:not-allowed; }
.message { margin:0; padding:10px 18px; font-size:12px; }.message.error{background:#fff2f2;color:#a62626}.message.success{background:#eef9f1;color:#267a48}
.state-box { padding:32px 26px; border:1px solid #e1e6ed; border-top:0; background:#fff; color:#697386; }.state-box.warning{background:#fffaf0}.state-box p{margin:6px 0 0}.state-box strong{color:#273244}
.progress-copy { display:flex; justify-content:space-between; color:#273244; }.progress-track{height:8px;margin:14px 0 10px;border-radius:999px;background:#edf0f4;overflow:hidden}.progress-track i{display:block;height:100%;background:#273244}
.summary { display:grid; grid-template-columns:repeat(4,1fr); border:1px solid #e1e6ed; border-top:0; background:#fff; }.summary span{padding:16px 24px;border-right:1px solid #edf0f4;color:#7b8492;font-size:12px}.summary span:last-child{border-right:0}.summary b{color:#172033;font-size:22px}
.tabs { display:flex; gap:6px; padding:14px 18px; border:1px solid #e1e6ed; border-top:0; background:#fafbfc; }.tabs button{border:0;border-radius:8px;padding:9px 14px;background:transparent;color:#667085;font-weight:800;cursor:pointer}.tabs button.active{background:#172033;color:#fff}
.result-body,.assets { border:1px solid #e1e6ed; border-top:0; border-radius:0 0 18px 18px; background:#fff; }
.scene { padding:28px 34px; border-bottom:1px solid #edf0f4; }.scene:last-child{border-bottom:0}.scene>header,.board-scene>header{display:flex;justify-content:space-between;gap:20px}.scene h3{margin:3px 0 0}.scene small,.scene-meta{color:#7b8492;font-size:11px}.scene-meta{display:flex;flex-direction:column;align-items:flex-end;gap:4px}.script-copy{max-width:820px;margin:18px auto 0}.action{color:#4e5969;line-height:1.8}.dialogue{max-width:560px;margin:18px auto}.dialogue strong{font-size:12px}.dialogue p{margin:6px 0 0;line-height:1.75}
.draft-note { display:flex;justify-content:space-between;gap:16px;padding:14px 22px;background:#f7f8fa;color:#6a7484;font-size:12px }.draft-note strong{color:#273244}
.board-scene{padding:22px;border-top:1px solid #edf0f4}.board-scene>header{margin-bottom:10px;color:#596579;font-size:12px}.shot-card{display:grid;grid-template-columns:150px minmax(0,1fr) auto;gap:18px;padding:16px;margin-top:10px;border:1px solid #e3e7ed;border-radius:12px}.shot-number{display:flex;flex-direction:column;gap:5px}.shot-number small,.shot-copy>small{color:#8490a0;font-size:10px}.shot-copy p{margin:8px 0;line-height:1.65}.tags{display:flex;flex-wrap:wrap;gap:6px}.tags span,.tags em{padding:3px 8px;border-radius:999px;background:#f0f2f5;color:#596579;font-size:10px;font-style:normal}.tags em{background:#eaf6ed;color:#267a48}.shot-actions{display:flex;flex-direction:column;gap:6px}.shot-actions button{border:1px solid #d8dee7;border-radius:8px;padding:7px 10px;background:#fff;font-size:11px;font-weight:800;cursor:pointer}
.assets{display:grid;grid-template-columns:repeat(3,1fr)}.assets section{padding:28px;border-right:1px solid #edf0f4}.assets section:last-child{border-right:0}.assets section>small{display:block;margin-bottom:12px;color:#7b8492;font-weight:800}.assets section div{display:flex;flex-wrap:wrap;gap:8px}.assets section span{padding:7px 11px;border:1px solid #dfe4eb;border-radius:999px;font-size:12px}
.editor-backdrop{position:fixed;inset:0;z-index:80;display:grid;place-items:center;padding:24px;background:rgba(16,24,40,.42)}.editor{width:min(720px,100%);max-height:calc(100vh - 48px);overflow:auto;padding:24px;border-radius:16px;background:#fff;box-shadow:0 28px 80px rgba(0,0,0,.2)}.editor>header{display:flex;justify-content:space-between;align-items:flex-start}.editor h3{margin:4px 0 0}.editor>header button{border:0;background:transparent;font-size:25px}.editor label{display:grid;gap:6px;margin-top:12px;color:#566172;font-size:11px;font-weight:800}.editor input,.editor textarea{box-sizing:border-box;width:100%;padding:10px 11px;border:1px solid #d8dee7;border-radius:9px;font:inherit;font-size:13px}.two-columns{display:grid;grid-template-columns:1fr 1fr;gap:12px}.editor footer{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:22px;padding-top:16px;border-top:1px solid #edf0f4}.editor footer>span{color:#7b8492;font-size:11px}.editor footer div{display:flex;gap:8px}.editor footer button{padding:8px 13px;border:1px solid #d8dee7;border-radius:8px;background:#fff;font-weight:800}.editor footer .save{border-color:#172033;background:#172033;color:#fff}
@media(max-width:780px){.workspace-heading,.scene>header,.draft-note,.editor footer{flex-direction:column}.summary{grid-template-columns:repeat(2,1fr)}.shot-card,.assets,.two-columns{grid-template-columns:1fr}.shot-actions{flex-direction:row}.scene-meta{align-items:flex-start}.assets section{border-right:0;border-bottom:1px solid #edf0f4}}
</style>
