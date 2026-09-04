<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import PersonEvidenceImageV1 from './PersonEvidenceImageV1.vue'
import { groupPersonObservations, validPersonMark, type PersonMark, type PersonObservation } from '../utils/personReviewGroups'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()
type Workspace = { revision: string; observations: PersonObservation[]; characters: { id: string; name: string; cover_url?: string | null }[] }
type Proposal = { character_id?: string | null; localization?: PersonMark | null }
const data = ref<Workspace | null>(null)
const proposals = ref<Record<string, Proposal>>({})
const moves = ref<Record<string, string>>({})
const marks = ref<Record<string, PersonMark>>({})
const checked = ref<string[]>([])
const reviewed = ref<string[]>([])
const groupId = ref('')
const focusKey = ref('')
const search = ref('')
const tab = ref('pending')
const name = ref('')
const names = ref<Record<string, { name: string; target: string }>>({})
const target = ref('')
const moveTarget = ref('unassigned')
const moving = ref(false)
const busy = ref(false)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const editing = ref(false)
const shotIndex = ref(0)
const video = ref('')
let videoSerial = 0
let drag: [number, number] | null = null
const storageKey = computed(() => `person-review:${props.projectId}`)
const groups = computed(() => groupPersonObservations(data.value?.observations || [], data.value?.characters || [], moves.value, proposals.value))
const visibleGroups = computed(() => groups.value.filter((g) => (tab.value === 'confirmed' ? g.id.startsWith('formal:') : !g.id.startsWith('formal:')) && `${g.name} ${g.rows.map(r => r.appearance).join(' ')}`.includes(search.value)))
const group = computed(() => groups.value.find(g => g.id === groupId.value))
const focused = computed(() => group.value?.rows.find(r => r.key === focusKey.value) || group.value?.rows[0])
const currentShot = computed(() => focused.value?.shots[shotIndex.value] || focused.value?.shots[0])
function markFor(row: PersonObservation) { return marks.value[row.key] || row.localization || proposals.value[row.key]?.localization }
const currentMark = computed(() => focused.value ? markFor(focused.value) : null)
const issues = computed(() => group.value?.rows.filter(r => r.identity_issue || !validPersonMark(r, markFor(r)) || !reviewed.value.includes(r.key)) || [])
const overlapping = computed(() => {
  const seen = new Set<string>()
  return !!group.value?.rows.some(row => row.shots.some(shot => { if (seen.has(shot.id)) return true; seen.add(shot.id); return false }))
})
const canConfirm = computed(() => !!group.value?.rows.length && !issues.value.length && !overlapping.value && !!(target.value || name.value.trim()) && group.value.id !== 'unassigned' && !busy.value && !loading.value && !error.value)
function focus(row: PersonObservation) {
  focusKey.value = row.key
  const mark = markFor(row)
  shotIndex.value = Math.max(0, row.shots.findIndex(s => s.id === mark?.shot_id))
  editing.value = false; video.value = ''; videoSerial++
}
function selectGroup(id: string) {
  if (groupId.value) names.value[groupId.value] = { name: name.value, target: target.value }
  groupId.value = id; checked.value = []; moving.value = false; video.value = ''; videoSerial++
  if (id) tab.value = id.startsWith('formal:') ? 'confirmed' : 'pending'
  const g = groups.value.find(g => g.id === id)
  name.value = names.value[id]?.name || ''; target.value = names.value[id]?.target ?? g?.characterId ?? ''
  if (g?.rows[0]) focus(g.rows[0])
}
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const r = await fetch(path, options)
  if (!r.ok) { const p = await r.json().catch(() => ({})); throw new Error(typeof p.detail === 'string' ? p.detail : `请求失败 ${r.status}`) }
  return r.json()
}
async function load() {
  loading.value = true; error.value = ''
  try {
    const result = await request<{ workspace: Workspace; proposals: Record<string, Proposal> }>(`/api/projects/${props.projectId}/character-assets/review-plan`)
    data.value = result.workspace; proposals.value = result.proposals
    moves.value = {}; marks.value = {}; reviewed.value = []; names.value = {}; groupId.value = ''
    try {
      const draft = JSON.parse(localStorage.getItem(storageKey.value) || 'null')
      if (draft?.revision === data.value.revision) { moves.value = draft.moves || {}; marks.value = draft.marks || {}; reviewed.value = draft.reviewed || []; names.value = draft.names || {} }
      else if (draft) notice.value = '源版本已变化，旧审核草稿未应用。'
    } catch { notice.value = '本地草稿不可读取，请重新核对。' }
    selectGroup(visibleGroups.value[0]?.id || '')
  } catch (e) { error.value = e instanceof Error ? e.message : '读取失败' }
  finally { loading.value = false }
}
function saveDraft() {
  if (groupId.value) names.value[groupId.value] = { name: name.value, target: target.value }
  try { localStorage.setItem(storageKey.value, JSON.stringify({ revision: data.value?.revision, moves: moves.value, marks: marks.value, reviewed: reviewed.value, names: names.value })); notice.value = '已暂存到当前浏览器，尚未修改正式人物。' }
  catch { error.value = '浏览器无法暂存草稿，请勿关闭页面。' }
}
function toggle(key: string) { checked.value = checked.value.includes(key) ? checked.value.filter(k => k !== key) : [...checked.value, key] }
function resetDraft() {
  try { localStorage.removeItem(storageKey.value); notice.value = '已撤销本地草稿，正式人物未改变。'; void load() }
  catch { error.value = '无法清除本地草稿' }
}
function moveSelection(destination: string, all = false) {
  if (destination.startsWith('formal:')) destination = destination.replace('formal:', 'candidate:')
  const keys = all ? group.value?.rows.map(r => r.key) || [] : checked.value
  for (const key of keys) moves.value[key] = destination
  reviewed.value = reviewed.value.filter(key => !keys.includes(key))
  checked.value = []; moving.value = false
  saveDraft(); selectGroup(destination)
}
function split() { moveSelection(`draft:${Date.now()}`) }
function cropBox(row: PersonObservation) { const mark = markFor(row); return validPersonMark(row,mark) ? mark.box : null }
function imageUrl(row: PersonObservation) { const mark = markFor(row); return validPersonMark(row, mark) ? mark.image_url : row.shots[0]?.thumbnail_url }
function episodeLabel(row: PersonObservation) { const number = row.episode_title.match(/第(\d+)集/); return number ? `EP${number[1]}` : row.episode_title }
function position(event: PointerEvent): [number, number] { const r = (event.currentTarget as HTMLElement).getBoundingClientRect(); return [Math.max(0, Math.min(1, (event.clientX-r.left)/r.width)), Math.max(0, Math.min(1, (event.clientY-r.top)/r.height))] }
function start(event: PointerEvent) { if (!editing.value || busy.value) return; drag = position(event); (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId) }
function draw(event: PointerEvent) {
  if (!drag || !focused.value || !currentShot.value?.thumbnail_url) return
  const [x,y] = position(event)
  marks.value[focused.value.key] = { shot_id: currentShot.value.id, image_url: currentShot.value.thumbnail_url, box: [Math.min(x,drag[0]),Math.min(y,drag[1]),Math.abs(x-drag[0]),Math.abs(y-drag[1])] }
  reviewed.value = reviewed.value.filter(k => k !== focused.value?.key)
}
function end(event: PointerEvent) { draw(event); drag = null }
function markStyle() { if (!currentMark.value || currentMark.value.shot_id !== currentShot.value?.id) return {}; const [x=0,y=0,w=0,h=0] = currentMark.value.box; return { left:`${x*100}%`, top:`${y*100}%`, width:`${w*100}%`, height:`${h*100}%` } }
async function showVideo() {
  if (!focused.value || !currentShot.value) return
  const serial = ++videoSerial
  try { const shots = await api.listShots(focused.value.episode_id); if (serial === videoSerial) { video.value = shots.find(s => s.id === currentShot.value?.id)?.reference_url || ''; if (!video.value) notice.value = '当前镜头没有可播放片段。' } }
  catch { error.value = '视频读取失败' }
}
function acceptFrame() { if (!focused.value || focused.value.identity_issue || !validPersonMark(focused.value, currentMark.value)) return; reviewed.value = [...new Set([...reviewed.value, focused.value.key])]; editing.value = false; saveDraft() }
async function confirm() {
  if (!canConfirm.value || !data.value || !group.value) return
  busy.value = true; error.value = ''
  const rows = [...group.value.rows]
  try {
    await request(`/api/projects/${props.projectId}/character-assets/assign`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ expected_revision:data.value.revision, keys:rows.map(r=>r.key), character_id:target.value || null, name:target.value ? '' : name.value.trim(), localizations:Object.fromEntries(rows.map(r=>[r.key, markFor(r)])) }) })
    try { localStorage.removeItem(storageKey.value) } catch { /* 保存成功不受本地存储影响 */ }
    notice.value = '人物身份与关联镜头已保存。其他草稿需基于新版本重新核对。'
    emit('changed'); await load()
  } catch(e) { error.value = e instanceof Error ? e.message : '保存失败' }
  finally { busy.value = false }
}
onMounted(load)
</script>

<template>
  <section class="person-review">
    <div v-if="error" class="alert error" role="alert">{{ error }} <button :disabled="busy" @click="load">重新读取</button></div>
    <div v-if="notice" class="alert">{{ notice }} <button aria-label="关闭提示" @click="notice=''">×</button></div>
    <div v-if="loading && !data" class="empty">正在读取人物分组与关键帧证据…</div>
    <div v-else class="review-layout" :class="{ busy: busy || loading }">
      <aside class="group-queue">
        <h2>人物分组</h2><p>核对图片，确认同一个人</p>
        <nav><button :class="{active:tab==='pending'}" @click="tab='pending'; selectGroup(visibleGroups[0]?.id || '')">待审核 {{ groups.filter(g=>!g.id.startsWith('formal:')).length }}</button><button :class="{active:tab==='confirmed'}" @click="tab='confirmed'; selectGroup(visibleGroups[0]?.id || '')">已确认 {{ groups.filter(g=>g.id.startsWith('formal:')).length }}</button></nav>
        <input v-model="search" placeholder="搜索人物或描述" aria-label="搜索人物分组" />
        <button v-if="Object.keys(moves).length || Object.keys(marks).length || reviewed.length" @click="resetDraft">撤销本地草稿</button>
        <div class="queue-scroll"><button v-for="g in visibleGroups" :key="g.id" class="group-item" :class="{selected:g.id===groupId}" @click="selectGroup(g.id)"><img v-if="g.rows[0] && imageUrl(g.rows[0])" :src="imageUrl(g.rows[0])!" alt="分组参考画面"/><div><strong>{{ g.id.startsWith('candidate:') ? '候选 · ' : '' }}{{ g.name }}</strong><span>{{ g.rows.length }} 条观察 · {{ new Set(g.rows.map(r=>r.episode_id)).size }} 集</span><small>{{ g.rows.some(r=>r.identity_issue) ? '含多人混合观察' : g.id.startsWith('formal:') ? '已保存人物映射' : '待人工核对' }}</small></div></button><p v-if="!visibleGroups.length">没有符合条件的分组。</p></div>
      </aside>
      <main v-if="group" class="group-main">
        <header><h2>{{ group.name }}</h2><div><button @click="checked=group.rows.map(r=>r.key); moving=true">合并 / 移组</button><button :disabled="!checked.length" @click="split">拆分选中观察</button></div></header>
        <p :class="overlapping ? 'warning' : 'group-hint'">{{overlapping ? '存在同镜头人物冲突，请移出错分观察后确认。' : '选择图片查看原图；移组包含该观察的关联镜头。'}}</p>
        <div class="frame-grid"><article v-for="row in group.rows" :key="row.key" :class="['frame-card',{focused:focused?.key===row.key,problem:!!row.identity_issue}]">
          <button class="frame-image" @click="focus(row)"><PersonEvidenceImageV1 v-if="imageUrl(row)" :src="imageUrl(row)!" :box="cropBox(row)" :alt="row.appearance || row.name"/><span v-else>暂无画面</span><em>{{ row.identity_issue ? '多人混合' : reviewed.includes(row.key) ? '已核对' : validPersonMark(row,markFor(row)) ? '待核对' : '待定位' }}</em></button>
          <label :title="row.episode_title"><input type="checkbox" :checked="checked.includes(row.key)" @change="toggle(row.key)"/><span>{{ episodeLabel(row) }}<small>镜头 {{ row.shots[0]?.ordinal }} · 关联 {{ row.shots.length }} 个镜头</small></span></label>
        </article></div>
        <div class="selection-bar"><span>已选 {{ checked.length }} 条观察</span><button :disabled="!checked.length" @click="moving=true">移到其他组</button><button :disabled="!checked.length" @click="moveSelection('unassigned')">移至未归组</button></div>
        <div v-if="moving" class="move-panel"><select v-model="moveTarget" aria-label="目标分组"><option value="unassigned">未归组</option><option v-for="g in groups.filter(g=>g.id!==groupId && g.id!=='unassigned')" :key="g.id" :value="g.id">{{g.name}}</option><option v-for="c in data?.characters || []" :key="c.id" :value="`candidate:${c.id}`">候选 · {{c.name}}</option></select><button @click="moveSelection(moveTarget)">暂存移组</button><button @click="moving=false">取消</button></div>
        <footer><div><label>绑定已有正式人物<select v-model="target"><option value="">新建人物</option><option v-for="c in data?.characters || []" :key="c.id" :value="c.id">{{c.name}}</option></select></label><input v-if="!target" v-model="name" placeholder="确认后的姓名" aria-label="确认后的姓名"/></div><div><button @click="saveDraft">暂存</button><button class="primary" :disabled="!canConfirm" @click="confirm">{{busy?'保存中…':'确认这一组'}}</button></div><small>{{ group.id==='unassigned' ? '先选中观察并拆分为候选组，再确认身份。' : `还有 ${issues.length} 条观察需要定位、核对或修正。确认会更新人物与关联镜头。` }}</small></footer>
      </main>
      <div v-else class="empty">选择左侧人物分组开始审核。</div>
      <aside v-if="focused" class="evidence-panel"><h2>原图核对</h2><p>{{focused.appearance || focused.name}}</p><div v-if="focused.identity_issue" class="warning">{{focused.identity_issue}} 此条不能直接确认，框选不会自动拆分对白和动作。</div>
        <video v-if="video" :src="video" controls autoplay />
        <div v-else-if="currentShot?.thumbnail_url" class="original" :class="{drawing:editing}" @pointerdown="start" @pointermove="draw" @pointerup="end" @pointercancel="drag=null"><img :src="currentShot.thumbnail_url" alt="当前原始关键帧" draggable="false"/><div v-if="currentMark?.shot_id===currentShot.id" class="box" :style="markStyle()"><span>当前人物</span></div></div>
        <select :value="shotIndex" aria-label="查看关联镜头" @change="shotIndex=Number(($event.target as HTMLSelectElement).value); video=''; videoSerial++; editing=false"><option v-for="(s,i) in focused.shots" :key="s.id" :value="i">镜头 {{s.ordinal}} · 关联画面 {{i+1}} / {{focused.shots.length}}</option></select>
        <div class="evidence-actions"><button @click="editing=!editing; video=''">{{editing?'结束框选':'调整人物框'}}</button><button @click="showVideo">查看视频</button></div><p>{{editing?'在原图上拖动框出一个人。':'一张画面有多人时，请分别定位。其他关联镜头需逐一核对。'}}</p><button class="primary" :disabled="!!focused.identity_issue || !validPersonMark(focused,currentMark)" @click="acceptFrame">此观察及关联镜头已核对</button>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.person-review{display:flex;flex-direction:column;min-height:0;height:100%;font:14px/1.5 "Segoe UI","Microsoft YaHei",sans-serif;color:#25334a}
.person-review *{box-sizing:border-box}
.person-review button,.person-review input,.person-review select{font:inherit;color:inherit;box-shadow:none}
.person-review button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:36px;width:auto;margin:0;padding:7px 12px;border:1px solid #dce3ed;border-radius:7px;background:#fff;cursor:pointer;line-height:1.35}
.person-review button:hover:not(:disabled){border-color:#87aaf3;background:#f4f7fe}
.person-review button:disabled{opacity:.43;cursor:not-allowed}
.person-review input:not([type=checkbox]),.person-review select{min-width:0;min-height:36px;height:36px;border:1px solid #dce3ed;background:#fff;border-radius:7px;padding:6px 10px}
.person-review input[type=checkbox]{appearance:auto;display:block;flex:0 0 16px;width:16px;height:16px;min-width:16px;min-height:16px;max-width:16px;max-height:16px;padding:0;margin:3px 0 0;accent-color:#2868e8;border-radius:3px}
.person-review .primary{background:#2868e8;color:#fff;border-color:#2868e8}
.person-review .primary:hover:not(:disabled){background:#1958d4}
.person-review h2{font-size:19px;line-height:1.35;margin:0;font-weight:650}
.person-review p{margin:0;color:#78869a;font-size:12px}
.person-review .review-layout{flex:1;display:grid;grid-template-columns:210px minmax(0,1fr) 300px;gap:16px;min-height:0}
.person-review .busy{pointer-events:none;opacity:.6}
.person-review .group-queue,.person-review .group-main,.person-review .evidence-panel{min-width:0;min-height:0;background:#fff;border:1px solid #e2e7ee;border-radius:10px;padding:16px;overflow:hidden}
.person-review .group-queue{display:flex;flex-direction:column;gap:12px}
.person-review .group-queue>p{margin-top:-5px}
.person-review nav{display:flex;border-bottom:1px solid #e8edf3;flex-shrink:0}
.person-review nav button{flex:1;border:0;border-bottom:2px solid transparent;border-radius:0;padding:8px 2px;font-size:12px}
.person-review nav .active{border-bottom-color:#2868e8;color:#2868e8;font-weight:600}
.person-review .queue-scroll{flex:1;min-height:0;overflow-y:auto;scrollbar-width:thin;padding-right:3px}
.person-review .group-item{width:100%;display:flex;justify-content:flex-start;align-items:center;gap:10px;padding:9px;margin-bottom:10px;min-height:94px;text-align:left}
.person-review .group-item img{display:block;width:52px;height:72px;flex:0 0 52px;object-fit:cover;border-radius:5px}
.person-review .group-item>div{min-width:0;display:flex;flex-direction:column;gap:4px}
.person-review .group-item strong{font-size:13px;font-weight:650;line-height:1.4}
.person-review .group-item span,.person-review .group-item small{font-size:11px;color:#8692a4}
.person-review .group-item small{color:#a9762e}
.person-review .group-item.selected{border-color:#6090f2;background:#eff5ff}
.person-review .group-main{display:flex;flex-direction:column;gap:12px}
.person-review .group-main>header{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-shrink:0}
.person-review .group-main>header>div{display:flex;gap:6px}
.person-review .group-main>header button{font-size:12px}
.person-review .warning{flex-shrink:0;padding:9px 12px;border:1px solid #f1ddbb;background:#fff8ed;border-radius:6px;color:#a4712e;font-size:12px}
.person-review .group-hint{flex-shrink:0;padding:0 1px;font-size:12px}
.person-review .frame-grid{flex:1;min-height:100px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));grid-template-rows:none;grid-auto-rows:max-content;align-content:start;gap:12px;overflow-y:auto;overflow-x:hidden;padding:2px 5px 2px 2px;scrollbar-width:thin}
.person-review .frame-card{display:block;align-self:start;min-width:0;height:auto;min-height:0;margin:0;border:1px solid #e1e6ed;border-radius:8px;overflow:hidden;background:#fff}
.person-review .frame-card.focused{border-color:#397aef;box-shadow:0 0 0 1px #397aef}
.person-review .frame-card.problem{border-color:#de6c6c}
.person-review .frame-image{display:block;position:relative;width:100%;height:auto;min-height:0;aspect-ratio:3/4;padding:0;border:0;border-radius:0;background:#f0f2f5;overflow:hidden}
.person-review .frame-image em{position:absolute;top:7px;right:7px;padding:3px 6px;border-radius:4px;background:#fff6df;color:#997126;font-size:10px;font-style:normal;line-height:1.4}
.person-review .frame-card>label{display:flex;align-items:flex-start;justify-content:flex-start;gap:9px;padding:10px;margin:0;min-height:56px;width:100%;font-size:12px;line-height:1.5}
.person-review .frame-card>label>span{flex:1;min-width:0;font-weight:500}
.person-review .frame-card small{display:block;font-size:11px;color:#8a96a6;font-weight:400;margin-top:1px}
.person-review .selection-bar{display:flex;align-items:center;gap:7px;flex-shrink:0;padding:8px 0;border-top:1px solid #edf0f5;background:#fff}
.person-review .selection-bar>span{margin-right:auto;font-size:12px;color:#738197}
.person-review .selection-bar button{font-size:12px}
.person-review .move-panel{display:flex;gap:6px;flex-shrink:0}
.person-review .move-panel select{flex:1}
.person-review footer{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px;flex-shrink:0;padding:12px 0 0;border-top:1px solid #e8edf3;margin:0;background:#fff}
.person-review footer>div{display:flex;align-items:center;gap:8px}
.person-review footer label{display:flex;gap:8px;align-items:center;font-size:12px;margin:0}
.person-review footer input{width:130px}
.person-review footer small{flex-basis:100%;color:#8c97a8;font-size:11px}
.person-review .evidence-panel{display:flex;flex-direction:column;gap:12px;overflow-y:auto;scrollbar-width:thin}
.person-review .original{position:relative;align-self:center;line-height:0;max-width:100%;flex-shrink:0;touch-action:none}
.person-review .original img{display:block;max-width:100%;width:auto;height:auto;max-height:calc(100vh - 490px);min-height:0;user-select:none;border-radius:6px}
.person-review .original.drawing{cursor:crosshair}
.person-review .box{position:absolute;border:2px solid #367cf5;pointer-events:none}
.person-review .box span{position:absolute;right:-2px;top:0;padding:3px 5px;background:#367cf5;color:white;line-height:1.4;font-size:10px}
.person-review .evidence-panel video{width:100%;max-height:calc(100vh - 425px);flex-shrink:0}
.person-review .evidence-panel select{width:100%;flex-shrink:0;font-size:12px}
.person-review .evidence-actions{display:flex;gap:8px;flex-shrink:0}
.person-review .evidence-actions button{flex:1;font-size:12px}
.person-review .evidence-panel>.primary{margin-top:auto;flex-shrink:0;font-size:12px}
.person-review .alert{padding:7px 12px;background:#edf5ff;margin-bottom:8px;border-radius:6px;font-size:12px;display:flex;justify-content:space-between;align-items:center}
.person-review .alert button{min-height:24px;padding:0 8px}
.person-review .alert.error{background:#fff0ef;color:#b33a31}
.person-review .empty{padding:24px;color:#8290a5}
@media(min-width:1650px){.person-review .review-layout{grid-template-columns:240px minmax(0,1fr) 330px}.person-review .frame-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.person-review .frame-image{max-height:260px}.person-review .group-item img{width:62px;height:82px;flex-basis:62px}}
@media(max-width:1250px){.person-review .review-layout{grid-template-columns:190px minmax(0,1fr) 260px;gap:10px}.person-review .group-queue,.person-review .group-main,.person-review .evidence-panel{padding:12px}.person-review .frame-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.person-review footer>div{flex-wrap:wrap}.person-review .group-main>header{align-items:flex-start;flex-direction:column}}
@media(max-height:800px) and (min-width:801px){.person-review .frame-image{aspect-ratio:4/3}.person-review .group-main{gap:8px}.person-review .original img{max-height:calc(100vh - 465px)}.person-review .evidence-panel{gap:9px}}
@media(max-width:800px){.person-review .review-layout{display:flex;flex-direction:column;overflow-y:auto}.person-review .group-queue{min-height:220px;flex-shrink:0}.person-review .queue-scroll{display:flex;gap:8px}.person-review .group-item{min-width:180px;max-width:220px}.person-review .group-main{min-height:620px;flex-shrink:0}.person-review .evidence-panel{min-height:480px;flex-shrink:0}.person-review .original img{max-height:300px}}
</style>
