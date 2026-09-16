<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
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
  type StoryboardDraftRead,
} from '@/features/projects/sourceAnalysis'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const episodeId = computed(() => String(route.query.episode ?? ''))
const episodeOrder = computed(() => Number(route.query.ep ?? 1) || 1)
const replica = ref(false)
const status = ref<SourceAnalysisStatusRead | null>(null)
const source = ref<SourceScriptRead | null>(null)
const draft = ref<StoryboardDraftRead | null>(null)
const loading = ref(true)
const starting = ref(false)
const savingShot = ref(false)
const error = ref('')
const success = ref('')
const query = ref('')
const selectedShotId = ref('')
type EditableShotField = 'visual_description' | 'shot_size' | 'composition' | 'angle_or_type' | 'movement' | 'focal_length_dof'
const editingField = ref<EditableShotField | null>(null)
const inlineValue = ref('')
let pendingSaves = 0
let saveQueue: Promise<void> = Promise.resolve()
let timer: number | undefined

const storyboardReady = computed(() => status.value?.state === 'READY' && source.value?.visual_enrichment_ready === true)
const episodeScenes = computed(() => (source.value?.scenes ?? []).filter(scene => !episodeId.value || scene.episode_id === episodeId.value))
const shots = computed(() => episodeScenes.value.flatMap(scene => scene.shots.map(shot => ({ ...shot, scene_name: scene.scene_name, character_names: scene.character_names }))))
const draftByShot = computed(() => new Map(
  draft.value?.status === 'CURRENT'
    ? draft.value.overrides.map(item => [item.shot_anchor_id, item] as const)
    : [],
))

function effectiveShot<T extends { shot_anchor_id: string; visual_description: string; shot_size: string; composition: string; angle_or_type: string; movement: string; focal_length_dof: string }>(shot: T): T {
  const override = draftByShot.value.get(shot.shot_anchor_id)
  return override ? { ...shot, ...override } : shot
}

const filteredShots = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return shots.value
  return shots.value.filter(shot => {
    const effective = effectiveShot(shot)
    return [String(shot.shot_number), shot.scene_name, effective.visual_description, ...shot.character_names, ...shot.dialogues.flatMap(line => [line.speaker_name, line.text])].some(value => value.toLocaleLowerCase().includes(keyword))
  })
})
const selectedShot = computed(() => {
  const shot = filteredShots.value.find(item => item.shot_anchor_id === selectedShotId.value) ?? filteredShots.value[0] ?? null
  return shot ? effectiveShot(shot) : null
})
const selectedIndex = computed(() => selectedShot.value ? filteredShots.value.findIndex(shot => shot.shot_anchor_id === selectedShot.value?.shot_anchor_id) : -1)
const selectedShotEdited = computed(() => Boolean(selectedShot.value && draftByShot.value.has(selectedShot.value.shot_anchor_id)))
const episodeEditedCount = computed(() => shots.value.filter(shot => draftByShot.value.has(shot.shot_anchor_id)).length)

function commandKey() { return `source-storyboard-${crypto.randomUUID()}` }
function time(us: number) {
  const seconds = us / 1_000_000
  return `${Math.floor(seconds / 60).toString().padStart(2, '0')}:${(seconds % 60).toFixed(2).padStart(5, '0')}`
}
function duration(us: number) { return `${(us / 1_000_000).toFixed(2)}s` }
function moveShot(offset: number) {
  const target = filteredShots.value[selectedIndex.value + offset]
  if (target) {
    editingField.value = null
    selectedShotId.value = target.shot_anchor_id
  }
}
function selectShot(shotAnchorId: string) {
  editingField.value = null
  selectedShotId.value = shotAnchorId
}

async function refresh() {
  status.value = await getSourceAnalysisStatus(projectId.value, episodeId.value || undefined)
  if (status.value.state === 'READY') {
    const [sourceResult, draftResult] = await Promise.all([
      getSourceScript(projectId.value),
      getStoryboardDraft(projectId.value),
    ])
    source.value = sourceResult
    draft.value = draftResult
  } else if (status.value.script_ready) {
    source.value = await getSourceScript(projectId.value)
  }
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
    status.value = await startSourceAnalysis(projectId.value, commandKey(), episodeId.value || undefined)
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '视频分析启动失败'
  } finally {
    starting.value = false
  }
}

function startInlineEdit(field: EditableShotField) {
  const shot = selectedShot.value
  if (!shot) return
  editingField.value = field
  inlineValue.value = String(shot[field] ?? '')
  success.value = ''
  void nextTick(() => {
    const editor = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(`.inline-editor[data-edit-field="${field}"]`)
    if (!editor) return
    editor.focus()
    const length = editor.value.length
    editor.setSelectionRange(length, length)
  })
}

function cancelInlineEdit() {
  editingField.value = null
  inlineValue.value = ''
}

function saveInlineEdit(field: EditableShotField) {
  const shot = selectedShot.value
  if (!shot || editingField.value !== field) return
  const shotAnchorId = shot.shot_anchor_id
  const nextValue = inlineValue.value.trim()
  if (nextValue === String(shot[field] ?? '')) {
    editingField.value = null
    return
  }

  pendingSaves += 1
  savingShot.value = true
  error.value = ''
  success.value = ''
  saveQueue = saveQueue.then(async () => {
    const sourceShot = shots.value.find(item => item.shot_anchor_id === shotAnchorId)
    if (!sourceShot) return
    const current = effectiveShot(sourceShot)
    const payload = {
      expected_revision: draft.value?.revision ?? null,
      shot_anchor_id: shotAnchorId,
      visual_description: current.visual_description,
      shot_size: current.shot_size,
      composition: current.composition,
      angle_or_type: current.angle_or_type,
      movement: current.movement,
      focal_length_dof: current.focal_length_dof,
      [field]: nextValue,
    }
    draft.value = await editStoryboardShot(projectId.value, payload)
    success.value = '已自动保存'
  }).catch((exc: unknown) => {
    error.value = exc instanceof Error ? exc.message : '自动保存失败'
  }).finally(() => {
    pendingSaves = Math.max(0, pendingSaves - 1)
    savingShot.value = pendingSaves > 0
    if (editingField.value === field && selectedShot.value?.shot_anchor_id === shotAnchorId) editingField.value = null
  })
}

async function resetShot() {
  if (!selectedShot.value || savingShot.value) return
  savingShot.value = true
  error.value = ''
  success.value = ''
  try {
    draft.value = await editStoryboardShot(projectId.value, {
      expected_revision: draft.value?.revision ?? null,
      shot_anchor_id: selectedShot.value.shot_anchor_id,
      reset_to_source: true,
    })
    success.value = `镜头 #${String(selectedShot.value.shot_number).padStart(3, '0')} 已恢复原始分析结果。`
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '恢复分析结果失败'
  } finally {
    savingShot.value = false
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
    <header class="stage-header">
      <div class="stage-title"><div class="title-line"><h2>原片分镜</h2><span v-if="storyboardReady" class="completed">已完成</span><span v-if="storyboardReady" class="stage-meta">{{ shots.length }} 镜 · {{ episodeScenes.length }} 场<span v-if="episodeEditedCount"> · {{ episodeEditedCount }} 镜人工修订</span></span></div></div>
      <div v-if="storyboardReady && selectedShot" class="stage-selection">
        <div class="shot-heading"><h3>#{{ String(selectedShot.shot_number).padStart(3, '0') }}</h3><span>第 {{ episodeOrder }} 集 · {{ selectedShot.scene_name }}</span><em v-if="selectedShotEdited">已人工修改</em></div>
        <div class="shot-nav"><span class="timecode">◷ {{ time(selectedShot.start_us) }} → {{ time(selectedShot.end_us) }}</span><b>{{ duration(selectedShot.duration_us) }}</b><button type="button" :disabled="selectedIndex <= 0" @click="moveShot(-1)">‹ 上一镜</button><button type="button" :disabled="selectedIndex >= filteredShots.length - 1" @click="moveShot(1)">下一镜 ›</button></div>
      </div>
      <div class="stage-actions"><label v-if="storyboardReady" class="header-search"><span>⌕</span><input v-model="query" type="search" placeholder="搜索镜号、场景、人物或对白" /></label><button type="button" :disabled="starting || status?.state === 'RUNNING'" @click="analyze">{{ status?.state === 'RUNNING' ? `分析中 ${status.progress_percent}%` : storyboardReady ? '重新分析' : '分析视频' }}</button></div>
    </header>
    <p v-if="error" class="message error">{{ error }}</p>
    <div v-if="loading" class="empty">正在读取原片分镜…</div>
    <div v-else-if="!storyboardReady" class="empty"><strong>{{ status?.message || '还没有正式分镜表' }}</strong><span>完成原片分析后，才能进入本集本土化分镜。</span></div>
    <template v-else>
      <div class="review-shell">
        <aside class="shot-browser" aria-label="原片镜头列表">
          <div class="browser-heading"><strong>镜头列表 <em>({{ shots.length }})</em></strong><span>↗</span></div>
          <div class="shot-list">
            <button v-for="shot in filteredShots" :key="shot.shot_anchor_id" type="button" class="shot-row" :class="{ active: selectedShot?.shot_anchor_id === shot.shot_anchor_id }" @click="selectShot(shot.shot_anchor_id)"><img :src="shot.thumbnail_url" :alt="`镜头 ${shot.shot_number}`" loading="lazy" /><span class="row-copy"><strong>#{{ String(shot.shot_number).padStart(3, '0') }}</strong><em>{{ time(shot.start_us) }} - {{ time(shot.end_us) }}</em><small>{{ shot.scene_name }}</small></span><span class="line-count">{{ shot.dialogues.length }}句</span></button>
            <div v-if="!filteredShots.length" class="browser-empty">没有匹配镜头</div>
          </div>
        </aside>

        <article v-if="selectedShot" class="shot-inspector">
          <div class="preview-frame"><video :src="selectedShot.reference_clip_url" :poster="selectedShot.thumbnail_url" controls preload="metadata"></video></div>
          <section class="content-block editable-block"><strong>画面内容 <span v-if="selectedShotEdited" class="edited-inline">人工修订</span></strong><textarea v-if="editingField === 'visual_description'" v-model="inlineValue" class="inline-editor inline-textarea" rows="4" maxlength="4000" data-edit-field="visual_description" @blur="saveInlineEdit('visual_description')" @keydown.esc.prevent="cancelInlineEdit"></textarea><button v-else type="button" class="editable-copy" data-edit-field="visual_description" @click="startInlineEdit('visual_description')">{{ selectedShot.visual_description || '点击填写画面描述' }}</button></section>
          <section class="content-block compact-block editable-language"><strong>镜头语言</strong><div class="camera-edit-grid"><label v-for="item in ([['shot_size','景别'],['angle_or_type','角度 / 类型'],['movement','运镜'],['composition','构图'],['focal_length_dof','焦段 / 景深']] as const)" :key="item[0]" class="camera-field"><span>{{ item[1] }}</span><input v-if="editingField === item[0]" v-model="inlineValue" class="inline-editor" :data-edit-field="item[0]" :maxlength="item[0] === 'shot_size' ? 240 : item[0] === 'angle_or_type' ? 400 : item[0] === 'composition' ? 1000 : 800" @blur="saveInlineEdit(item[0])" @keydown.enter.prevent="($event.target as HTMLInputElement).blur()" @keydown.esc.prevent="cancelInlineEdit" /><button v-else type="button" class="editable-chip" :data-edit-field="item[0]" @click="startInlineEdit(item[0])">{{ selectedShot[item[0]] || '点击填写' }}</button></label></div></section>
          <section v-if="selectedShot.character_names.length" class="content-block compact-block"><strong>出现人物</strong><div class="camera-chips character-chips"><span v-for="name in selectedShot.character_names" :key="name">{{ name }}</span></div></section>
          <section v-if="selectedShot.action_summary" class="content-block"><strong>动作摘要 <span class="readonly-inline">原始分析</span></strong><p>{{ selectedShot.action_summary }}</p></section>
        </article>

        <aside v-if="selectedShot" class="detail-sidebar">
          <section class="side-card dialogue-card"><div class="side-heading"><strong>原片对白 <small>只读</small></strong><span>({{ selectedShot.dialogues.length }}句)</span></div><div v-if="selectedShot.dialogues.length" class="dialogues"><article v-for="line in selectedShot.dialogues" :key="line.utterance_id"><header><span>{{ time(line.start_us) }}</span><b>{{ line.speaker_name }}</b></header><p>{{ line.text }}</p></article></div><div v-else class="no-dialogue">本镜头暂无对白</div></section>
          <section class="side-card edit-status-card"><div class="side-heading"><strong>编辑状态</strong><span class="autosave-state" :class="{ saving: savingShot }">{{ savingShot ? '保存中…' : success || (selectedShotEdited ? '修改已保存' : '自动保存') }}</span></div><p>直接点击内容即可修改；画面内容和镜头语言支持原位编辑，光标离开后自动保存。</p><button v-if="selectedShotEdited" type="button" class="reset-result" :disabled="savingShot" @click="resetShot">恢复分析结果</button></section>
          <section class="side-card metadata-card"><div class="side-heading"><strong>⌄ 更多信息</strong><span>⌃</span></div><dl><dt>场景</dt><dd>{{ selectedShot.scene_name }}</dd><dt>时长</dt><dd>{{ duration(selectedShot.duration_us) }}</dd><dt>镜头类型</dt><dd>{{ selectedShot.shot_size || '—' }}</dd><dt>拍摄角度</dt><dd>{{ selectedShot.angle_or_type || '—' }}</dd><dt>运动方式</dt><dd>{{ selectedShot.movement || '—' }}</dd><dt>构图方式</dt><dd>{{ selectedShot.composition || '—' }}</dd><dt>焦段景深</dt><dd>{{ selectedShot.focal_length_dof || '—' }}</dd></dl></section>
        </aside>
      </div>
    </template>

  </section>
</template>

<style scoped>
.five-step-workspace{display:flex;flex-direction:column;gap:8px;min-width:0;height:100%;min-height:0;overflow:hidden}.stage-header{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:18px;min-height:46px;padding:0 2px 6px;border-bottom:1px solid #e8eaf0}.stage-title{min-width:0}.title-line{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.stage-selection{display:flex;align-items:center;justify-content:space-between;gap:14px;min-width:0;padding:0 6px}.stage-selection .shot-heading{flex:1 1 auto}.stage-selection .shot-nav{flex:0 0 auto}.stage-title h2{margin:0;color:#142647;font-size:20px;letter-spacing:-.015em}.completed{padding:3px 7px;border-radius:999px;background:#eaf7ee;color:#2d8a4d;font-size:10px;font-weight:800}.stage-meta{color:#6f7b90;font-size:10px}.stage-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;min-width:0}.header-search{display:flex;align-items:center;gap:6px;width:min(300px,32vw);height:32px;padding:0 9px;border:1px solid #d9dee8;border-radius:8px;background:#fff;color:#7f8aa0}.header-search input{width:100%;border:0;outline:0;background:transparent;color:#293954;font-size:12px}.stage-actions>button{min-height:32px;padding:0 13px;border:0;border-radius:8px;background:linear-gradient(135deg,#704cf4,#5a38e6);color:#fff;font-size:12px;font-weight:800;box-shadow:0 5px 12px rgba(91,59,227,.16);cursor:pointer}.stage-actions>button:disabled{opacity:.5}.review-shell{display:grid;grid-template-columns:294px minmax(480px,1fr) 310px;flex:1 1 auto;height:auto;min-height:0;overflow:hidden;border:1px solid #e0e3eb;border-radius:12px;background:#fff;box-shadow:0 5px 18px rgba(31,43,69,.035)}.shot-browser{display:grid;grid-template-rows:auto minmax(0,1fr);min-width:0;min-height:0;overflow:hidden;border-right:1px solid #e5e7ee;background:#fff}.browser-heading{display:flex;justify-content:space-between;align-items:center;padding:13px 14px 8px;color:#172848;font-size:13px}.browser-heading em{color:#737f94;font-style:normal;font-weight:500}.browser-heading>span{color:#7a86a0}.search{display:flex;align-items:center;gap:7px;margin:0 12px 7px;padding:0 9px;border:1px solid #d9dee8;border-radius:7px;color:#7f8aa0}.search input{width:100%;height:34px;border:0;outline:0;background:transparent;color:#293954;font-size:10px}.shot-list{min-height:0;overflow:auto;overscroll-behavior:contain}.shot-row{display:grid;grid-template-columns:88px minmax(0,1fr) auto;align-items:center;gap:8px;width:100%;min-height:72px;padding:7px 10px;border:0;border-top:1px solid #f0f1f5;background:#fff;color:#283956;text-align:left;cursor:pointer}.shot-row:hover{background:#fafaff}.shot-row.active{background:#f3f1ff;box-shadow:inset 3px 0 #674cf0}.shot-row img{width:88px;height:54px;object-fit:cover;border-radius:6px;background:#151515}.row-copy{display:grid;min-width:0;gap:1px}.row-copy strong{color:#2b3d62;font-size:13px}.row-copy em{color:#6f7e98;font-size:10px;font-style:normal;font-variant-numeric:tabular-nums}.row-copy small{overflow:hidden;color:#50617f;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.line-count{align-self:start;margin-top:6px;padding:3px 5px;border-radius:6px;background:#f0f2f7;color:#586984;font-size:10px}.browser-empty{padding:24px;color:#8d97a7;font-size:11px;text-align:center}.shot-inspector{display:grid;align-content:start;gap:10px;min-width:0;min-height:0;overflow:auto;overscroll-behavior:contain;padding:13px;border-right:1px solid #e5e7ee}.inspector-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.shot-heading{display:flex;align-items:center;gap:8px;min-width:0}.shot-heading h3{margin:0;color:#102342;font-size:21px}.shot-heading>span{overflow:hidden;padding:5px 8px;border-radius:7px;background:#f4f5f8;color:#697792;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.shot-heading>em{padding:4px 7px;border-radius:999px;background:#fff4dc;color:#8b6119;font-size:10px;font-style:normal;font-weight:800}.shot-nav{display:flex;align-items:center;gap:5px;flex-wrap:wrap;justify-content:flex-end}.timecode{color:#687793;font-size:10px;font-variant-numeric:tabular-nums}.shot-nav>b{padding:5px 7px;border-radius:6px;background:#efecff;color:#5b48dc;font-size:10px}.shot-nav button{min-height:26px;padding:0 8px;border:1px solid #dfe2e9;border-radius:6px;background:#fff;color:#50617d;font-size:10px;cursor:pointer}.shot-nav button:disabled{opacity:.4}.autosave-state{padding:5px 7px;border-radius:999px;background:#eef7f0!important;color:#39734a!important;font-weight:800}.autosave-state.saving{background:#fff4dc!important;color:#8b6119!important}.reset-result{border:1px solid #d9dce5;background:#fff;color:#65718a}.preview-frame{display:grid;place-items:center;min-height:360px;overflow:visible;margin-bottom:10px;border-radius:9px;background:#0c0d0f}.preview-frame video{display:block;width:100%;height:min(45vh,470px);border-radius:9px;object-fit:contain;background:#090a0c}.content-block{display:grid;gap:6px;padding:10px 11px;border:1px solid #edf0f4;border-radius:8px;background:#fbfcfe}.content-block strong{color:#1c2d4a;font-size:13px}.content-block p{margin:0;color:#455875;font-size:12px;line-height:1.75}.editable-block{transition:border-color .15s ease,background .15s ease}.editable-block:focus-within{border-color:#8a7bf2;background:#fff}.editable-copy{width:100%;padding:4px 5px;border:1px solid transparent;border-radius:6px;background:transparent;color:#4f607b;text-align:left;font:inherit;font-size:12px;line-height:1.75;cursor:text}.editable-copy:hover{border-color:#d9d3ff;background:#f8f7ff}.inline-editor{width:100%;min-width:0;padding:6px 8px;border:1px solid #7765ef;border-radius:7px;outline:0;background:#fff;color:#283956;font:inherit;font-size:12px;line-height:1.55;box-shadow:0 0 0 3px rgba(101,82,232,.08)}.inline-textarea{resize:vertical}.edited-inline,.readonly-inline{margin-left:6px;padding:2px 5px;border-radius:999px;font-size:9px;font-weight:800}.edited-inline{background:#fff0cf;color:#8e6217}.readonly-inline{background:#eef1f5;color:#7c8799}.compact-block{grid-template-columns:88px minmax(0,1fr);align-items:center}.camera-chips{display:flex;gap:5px;flex-wrap:wrap}.camera-chips span{padding:4px 7px;border-radius:6px;background:#f0f2f7;color:#566782;font-size:10px}.camera-edit-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}.camera-field{display:grid;grid-template-columns:66px minmax(0,1fr);align-items:center;gap:5px;min-width:0}.camera-field>span{color:#748096;font-size:10px}.editable-chip{min-width:0;padding:5px 7px;border:1px solid #e3e5eb;border-radius:6px;background:#f4f5f8;color:#566782;text-align:left;font-size:10px;white-space:normal;cursor:text}.editable-chip:hover{border-color:#cfc8ff;background:#f3f1ff;color:#4f43c3}.character-chips span{background:#f1efff;color:#5c4fce}.detail-sidebar{display:grid;align-content:start;gap:10px;min-height:0;overflow:auto;overscroll-behavior:contain;padding:0;background:#fbfcfe}.side-card{display:grid;gap:10px;padding:13px;background:#fff;border-bottom:1px solid #e5e7ee}.side-heading{display:flex;align-items:center;justify-content:space-between;color:#172848}.side-heading strong{font-size:13px}.side-heading strong small{margin-left:5px;padding:2px 5px;border-radius:999px;background:#eef1f5;color:#7b8799;font-size:8px}.side-heading span{color:#8a95a7;font-size:9px}.edit-status-card{gap:8px;background:#faf9ff}.edit-status-card p{margin:0;color:#6f6981;font-size:10px;line-height:1.55}.edit-status-card .reset-result{justify-self:start;min-height:28px;padding:0 9px;border-radius:7px;font-size:10px;font-weight:800;cursor:pointer}.dialogues{display:grid;gap:8px}.dialogues article{display:grid;gap:5px;padding:10px;border:1px solid #e4e7ed;border-radius:8px;background:#fff}.dialogues header{display:flex;gap:9px;color:#5f4bea;font-size:10px}.dialogues header b{font-size:10px}.dialogues p{margin:0;color:#263956;font-size:12px;line-height:1.6}.no-dialogue{display:grid;place-items:center;min-height:140px;border:1px dashed #e0e3ea;border-radius:9px;color:#8a96aa;font-size:10px}.metadata-card dl{display:grid;grid-template-columns:72px minmax(0,1fr);gap:8px 10px;margin:0;padding-top:4px;border-top:1px solid #edf0f4}.metadata-card dt{color:#6f7d94;font-size:10px}.metadata-card dd{margin:0;color:#40516e;font-size:10px;line-height:1.5}.message{margin:0;padding:9px 11px;border-radius:8px;font-size:11px}.empty{display:grid;gap:5px;padding:28px;border:1px dashed #ccd2dd;border-radius:12px;background:#fff;color:#66738a}.error{color:#a33b32}@media(max-width:1320px){.review-shell{grid-template-columns:280px minmax(430px,1fr) 275px}.shot-row{grid-template-columns:76px minmax(0,1fr) auto}.shot-row img{width:76px}}@media(max-width:1100px){.review-shell{height:auto;max-height:none;grid-template-columns:280px minmax(0,1fr)}.detail-sidebar{grid-column:1/-1;grid-template-columns:1fr 1fr;overflow:visible;border-top:1px solid #e5e7ee}.shot-inspector{overflow:visible;border-right:0}.dialogue-card,.metadata-card{border-bottom:0}.preview-frame{min-height:300px}}@media(max-width:760px){.stage-header{display:flex;align-items:stretch;flex-direction:column}.stage-selection{align-items:stretch;flex-direction:column;padding:0}.stage-selection .shot-nav{justify-content:flex-start}.stage-actions{width:100%}.header-search{width:100%;max-width:none}.camera-edit-grid{grid-template-columns:1fr}.review-shell{grid-template-columns:1fr}.shot-browser{max-height:360px;border-right:0;border-bottom:1px solid #e5e7ee}.shot-inspector{padding:10px}.detail-sidebar{grid-template-columns:1fr}.compact-block{grid-template-columns:1fr}.editor-grid{grid-template-columns:1fr}}
</style>
