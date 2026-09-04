<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()
type Mark = { shot_id: string; image_url: string; box: number[] }
type Observation = { localization?: Mark | null; key: string; name: string; appearance: string | null; episode_id: string; episode_title: string; scene: string; character_id: string | null; shots: { id: string; ordinal: number; thumbnail_url: string | null }[] }
type Version = { id: string; status: string; error: string | null; current: boolean; accepted: boolean; images: { view: string; url: string }[] }
type Target = { id: string; source_character_id: string; target_name: string; appearance_profile: string; generation_prompt: string; current: boolean; fingerprint: string; versions: Version[] }
type Workspace = { revision: string; observations: Observation[]; characters: { id: string; name: string; shot_ids: string[] }[]; targets: Target[]; designable_ids: string[]; snapshot_error: string | null; target_region: string }
const router = useRouter()
const data = ref<Workspace | null>(null)
const error = ref('')
const busy = ref(false)
const selected = ref<string[]>([])
const sourceName = ref('')
const focusKey = ref('')
const shotIndex = ref(0)
const search = ref('')
const imageRatios = reactive<Record<string, number>>({})
function imageLoaded(e: Event, url: string) { const img = e.target as HTMLImageElement; imageRatios[url] = img.naturalWidth / img.naturalHeight }
const marks = reactive<Record<string, Mark>>({})
const focused = computed(() => data.value?.observations.find(o => o.key === focusKey.value))
const filtered = computed(() => data.value?.observations.filter(o => `${o.name} ${o.appearance} ${o.scene} ${o.episode_title}`.includes(search.value)) || [])
const currentShot = computed(() => focused.value?.shots[shotIndex.value])
const currentMark = computed(() => focused.value ? marks[focused.value.key] || focused.value.localization : null)
const shownMark = computed(() => currentMark.value?.shot_id === currentShot.value?.id ? currentMark.value : null)
const selectedRows = computed(() => data.value?.observations.filter(o => selected.value.includes(o.key)) || [])
const allMarked = computed(() => selectedRows.value.length > 0 && selectedRows.value.every(o => marks[o.key] || o.localization))
let dragStart: [number, number] | null = null
function focus(o: Observation) { focusKey.value = o.key; shotIndex.value = 0; dragStart = null }
function markStyle(mark: Mark) { const [x=0,y=0,w=0,h=0] = mark.box; return { left: `${x*100}%`, top: `${y*100}%`, width: `${w*100}%`, height: `${h*100}%` } }
function cropStyle(mark: Mark) { const [x=0,y=0,w=1,h=1] = mark.box; return { width: `${100/w}%`, height: `${100/h}%`, left: `${-100*x/w}%`, top: `${-100*y/h}%` } }
function point(e: PointerEvent): [number,number] { const r = (e.currentTarget as HTMLElement).getBoundingClientRect(); return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))] }
function startMark(e: PointerEvent) { if (busy.value || !currentShot.value?.thumbnail_url) return; dragStart = point(e); (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId) }
function moveMark(e: PointerEvent) {
  if (!dragStart || !focused.value || !currentShot.value?.thumbnail_url) return
  const [x,y] = point(e); const [sx,sy] = dragStart
  marks[focused.value.key] = { shot_id: currentShot.value.id, image_url: currentShot.value.thumbnail_url, box: [Math.min(x,sx),Math.min(y,sy),Math.abs(x-sx),Math.abs(y-sy)] }
}
function endMark(e: PointerEvent) { if (!dragStart) return; moveMark(e); dragStart = null; const m = currentMark.value; if (m && (m.box[2]! < .02 || m.box[3]! < .02)) delete marks[focusKey.value] }
function addFocused() { if (focused.value && currentMark.value && !selected.value.includes(focused.value.key)) selected.value.push(focused.value.key) }

const destination = ref('')
const opened = ref('')
const preview = ref('')
const editRevisions = reactive<Record<string, string>>({})
const editFingerprints = reactive<Record<string, string | null>>({})
const drafts = reactive<Record<string, { target_name: string; appearance_profile: string; generation_prompt: string }>>({})
const active = computed(() => data.value?.targets.some(t => t.versions.some(v => ['QUEUED', 'PROCESSING'].includes(v.status))))
let timer: ReturnType<typeof setInterval> | undefined
let reading = false
async function request<T>(path: string, body?: unknown, key?: string): Promise<T> {
  const response = await fetch(`/api/${path}`, body === undefined ? undefined : { method: 'POST', headers: { 'Content-Type': 'application/json', ...(key ? { 'Idempotency-Key': key } : {}) }, body: JSON.stringify(body) })
  if (!response.ok) { const payload = await response.json(); throw new Error(typeof payload.detail === 'string' ? payload.detail : '请求失败，请检查输入') }
  return response.json()
}
async function load() {
  if (reading) return
  reading = true
  try {
    const result = await request<Workspace>(`projects/${props.projectId}/character-assets`)
    if (data.value && result.revision !== data.value.revision) { selected.value = []; Object.keys(marks).forEach(k => delete marks[k]) }
    data.value = result
    if (!result.observations.some(o => o.key === focusKey.value) && result.observations[0]) focus(result.observations[0])
  }
  catch (e) { error.value = String(e instanceof Error ? e.message : e) }
  finally { reading = false }
}
async function act(action: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await action(); await load(); emit('changed') }
  catch (e) { error.value = e instanceof Error ? e.message : String(e) }
  finally { busy.value = false }
}
async function assign() {
  await act(async () => {
    await request(`projects/${props.projectId}/character-assets/assign`, { keys: selected.value, name: sourceName.value, character_id: destination.value || null, expected_revision: data.value!.revision, localizations: Object.fromEntries(selectedRows.value.map(o => [o.key, marks[o.key] || o.localization])) })
    selected.value = []; sourceName.value = ''
  })
}
function target(id: string) { return data.value?.targets.find(t => t.source_character_id === id) }
function edit(id: string) {
  const t = target(id)
  editRevisions[id] = data.value!.revision
  editFingerprints[id] = t?.fingerprint || null
  drafts[id] = { target_name: t?.target_name || '', appearance_profile: t?.appearance_profile || '', generation_prompt: t?.generation_prompt || '' }
  opened.value = id
}
async function save(id: string) {
  await act(async () => { await request(`projects/${props.projectId}/character-assets/design`, { ...drafts[id], source_character_id: id, expected_target_fingerprint: editFingerprints[id], expected_revision: editRevisions[id] }); opened.value = '' })
}
function generate(t: Target) {
  return act(() => request(`target-characters/${t.id}/four-views`, { fingerprint: t.fingerprint }, crypto.randomUUID()))
}
function accept(t: Target, version: Version) { return act(() => request(`character-view-versions/${version.id}/accept`, { fingerprint: t.fingerprint })) }
function viewName(view: string) { return ({ front: '正面', left: '左侧', back: '背面', right: '右侧' } as Record<string, string>)[view] || view }
function onKey(event: KeyboardEvent) { if (event.key === 'Escape') preview.value = '' }
onMounted(() => { void load(); timer = setInterval(() => { if (active.value && !busy.value) void load() }, 4000); window.addEventListener('keydown', onKey) })
onBeforeUnmount(() => { if (timer) clearInterval(timer); window.removeEventListener('keydown', onKey) })
</script>

<template>
  <section class="character-assets">
    <header><div><h2>人物资产库</h2><p>识别人物 → 跨分镜归并并绑定 → 设计替换人物 → 四视图审核采用</p></div><button :disabled="busy" @click="load">刷新</button></header>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="!data">正在读取人物资产…</p>
    <template v-else>
      <section>
        <h3>1. 归并原片人物 <small>{{ data.observations.length }} 组观察 · {{ data.characters.length }} 个原片人物资产</small></h3>
        <p>先核对画面中的具体人物，再把同一人的不同场景观察放入右侧归并清单。</p>
        <div class="identity-workspace">
          <aside class="observation-list">
            <input v-model="search" aria-label="搜索人物观察" placeholder="搜索人物、外观、场景" />
            <div class="observation-scroll">
              <button v-for="(o,index) in filtered" :key="o.key" class="observation-row" :class="{chosen: focusKey === o.key}" @click="focus(o)">
                <span class="observation-number">{{ index + 1 }}</span><span><strong>{{ o.name }}</strong><small>{{ o.appearance || '暂无外观描述' }}</small><small>{{ o.scene }} · {{ o.shots.length }} 个分镜</small><em>{{ selected.includes(o.key) ? '已加入归并清单' : o.character_id ? '已绑定 · 可重新核对' : '待核对人物位置' }}</em></span>
              </button>
            </div>
          </aside>
          <section v-if="focused" class="person-inspector">
            <header><div><h3>{{ focused.name }} <small>当前核对</small></h3><p>{{ focused.appearance }}</p></div><span class="location-state">{{ shownMark ? '已标记具体人物' : '待定位 · 未确定画面中哪一人' }}</span></header>
            <small>{{ focused.episode_title }} · {{ focused.scene }}</small>
            <p class="mark-help">{{ shownMark ? '蓝框是本次绑定的人物。可以重新拖动框选修正位置。' : '当前观察没有可靠的位置标记。请在下方画面中拖动框选对应人物，避免误绑同框的另一人。' }}</p>
            <div class="frame-stage">
              <div v-if="currentShot?.thumbnail_url" :key="currentShot.id" class="mark-canvas" @pointerdown.prevent="startMark" @pointermove="moveMark" @pointerup="endMark" @pointercancel="dragStart = null">
                <img :src="currentShot.thumbnail_url" alt="当前镜头完整画面，请框选要绑定的人物" draggable="false" />
                <div v-if="shownMark" class="person-box" :style="markStyle(shownMark)"><span>{{ focused.name }} · 绑定对象</span></div>
              </div>
              <p v-else>此镜头没有可用画面，请选择其他分镜。</p>
            </div>
            <div class="shot-picker"><button v-for="(shot,index) in focused.shots" :key="shot.id" :class="{chosen: shotIndex === index}" @click="shotIndex = index">镜头 {{ shot.ordinal }}{{ currentMark?.shot_id === shot.id ? ' · 已标记' : '' }}</button></div>
            <div class="person-confirm">
              <div v-if="currentMark" :style="{aspectRatio: `${(imageRatios[currentMark.image_url] || 1) * currentMark.box[2]! / currentMark.box[3]!}`}" class="person-crop"><img @load="imageLoaded($event, currentMark.image_url)" :src="currentMark.image_url" :style="cropStyle(currentMark)" alt="本次标记的人物局部" /></div>
              <div><strong>{{ currentMark ? '请确认裁剪图中是要归并的人物' : '标记后显示人物局部' }}</strong><p>只标记当前代表画面，不会把框套用到其他分镜。</p><button :disabled="busy || !currentMark" @click="addFocused">{{ selected.includes(focused.key) ? '已加入归并清单' : '确认此人，加入归并清单' }}</button></div>
            </div>
            <button @click="router.push({name: 'breakdown', params: {projectId}, query: {episode: focused.episode_id, shot: currentShot?.ordinal}})">前往分镜核对完整内容 ↗</button>
          </section>
          <aside class="merge-panel">
            <h3>归并为同一个人</h3><p>逐个核对后加入。这里的所有观察将绑定到同一个原片人物。</p>
            <div v-for="o in selectedRows" :key="o.key" class="merge-row"><button class="merge-person" @click="focus(o)"><strong>{{ o.name }}</strong><small>{{ o.scene }} · {{ o.shots.length }} 个分镜</small></button><button :aria-label="`移除${o.name}`" @click="selected = selected.filter(k => k !== o.key)">×</button></div>
            <p v-if="!selected.length" class="empty-selection">尚未选择人物<br />先在中间画面标记并确认</p>
            <label>归并到<select v-model="destination" aria-label="归并到原片人物"><option value="">新建原片人物</option><option v-for="c in data.characters" :key="c.id" :value="c.id">{{ c.name }}</option></select></label>
            <label v-if="!destination">原片人物名称<input v-model="sourceName" placeholder="例如：邻居大妈" /></label>
            <button class="primary" :disabled="busy || !allMarked || (!destination && !sourceName.trim())" @click="assign">保存标记并绑定 {{ selected.length }} 组</button>
            <small>保存前的标记为待提交内容。保存后可重新核对和分配。</small>
          </aside>
        </div>
        <p v-if="!data.observations.length">暂无当前拉片人物观察，请先完成本集拉片。</p>
      </section>
      <section>
        <h3>2. 替换人物与四视图 <small>目标地区：{{ data.target_region }}</small></h3>
        <p>每个原片人物对应独立的新人物。保存设计不会自动生成；四视图生成完成后，请确认角度、脸、服装一致再采用。</p>
        <p v-if="data.snapshot_error" class="error">原片快照尚不可用：{{ data.snapshot_error }}</p>
        <article v-for="c in data.characters" :key="c.id" class="target-card">
          <header><div><strong>{{ c.name }}</strong><span> · 已绑定 {{ c.shot_ids.length }} 个分镜 → {{ target(c.id)?.target_name || '尚未设计替换人物' }}</span></div><button :disabled="busy || !data.designable_ids.includes(c.id)" @click="edit(c.id)">设计替换人物</button></header>
          <p v-if="!data.designable_ids.includes(c.id)">请先把识别人物归并到此资产，形成当前原片快照中的人物映射。</p>
          <form v-if="opened === c.id" @submit.prevent="save(c.id)"><label>目标人物姓名<input v-model="drafts[c.id]!.target_name" required /></label><label>外貌、发型、年龄、服装<textarea v-model="drafts[c.id]!.appearance_profile" rows="3" required /></label><label>生成描述<textarea v-model="drafts[c.id]!.generation_prompt" rows="3" required placeholder="描述新的可替换人物，保持四个角度相同的脸、发型和服装" /></label><div><button type="button" @click="opened = ''">取消</button><button :disabled="busy">保存人物设计</button></div></form>
          <template v-if="target(c.id)">
            <p>{{ target(c.id)!.appearance_profile }}</p>
            <p v-if="!target(c.id)!.current" class="error">原片人物或地区设置已变化，请重新保存设计。</p>
            <button :disabled="busy || active || !target(c.id)!.current" @click="generate(target(c.id)!)">{{ active ? '四视图生成中…' : '生成新的四视图版本' }}</button>
            <section v-for="v in target(c.id)!.versions" :key="v.id" class="version">
              <strong>{{ v.accepted && v.current ? '已采用' : v.current ? '候选版本' : '历史版本（已过期）' }}</strong>
              <p v-if="v.error" class="error">{{ v.error }}</p><p v-else-if="!v.images.length">{{ v.status === 'QUEUED' ? '排队中' : v.status === 'PROCESSING' ? '生成中' : v.status }}</p>
              <div class="four-views"><button v-for="image in v.images" :key="image.view" @click="preview = image.url"><img :src="image.url" :alt="viewName(image.view)" /><span>{{ viewName(image.view) }} · 放大</span></button></div>
              <button v-if="v.images.length && v.current && !v.accepted" :disabled="busy" @click="accept(target(c.id)!, v)">确认四个角度及人物一致，采用此版本</button>
            </section>
          </template>
        </article>
        <p v-if="!data.characters.length">先完成上方人物归并，再设计替换人物。</p>
      </section>
    </template>
    <div v-if="preview" class="preview" @click.self="preview = ''"><div role="dialog" aria-label="人物参考图" aria-modal="true"><button @click="preview = ''">关闭 ×</button><img :src="preview" alt="人物参考图大图" /></div></div>
  </section>
</template>

<style scoped>
.character-assets { padding: 20px; display: grid; gap: 24px; color: #25354c; background: #fff; border: 1px solid #e1e7ef; border-radius: 12px; min-width: 0; }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; } h2,h3 { margin: 0 0 8px; } h2 { font-size: 20px; } h3 { font-size: 16px; } p { color: #6b7b90; line-height: 1.6; font-size: 13px; } small { color: #7a889b; font-weight: normal; font-size: 12px; }
button,input,select,textarea { font: inherit; font-size: 13px; border: 1px solid #d7e0ec; border-radius: 6px; padding: 8px 10px; background: white; color: #314963; box-sizing: border-box; } button { cursor: pointer; } button:disabled { opacity: .5; cursor: not-allowed; }
.character-assets input[type="checkbox"] { width: 16px; height: 16px; min-height: 0; padding: 0; margin: 0; flex: 0 0 16px; }
.assignment select { width: auto; max-width: 100%; flex: 0 1 240px; } .assignment input { width: auto; min-width: 180px; flex: 1 1 220px; }
.assignment { display: flex; flex-wrap: wrap; gap: 8px; margin: 16px 0; } .assignment button { background: #1769ff; color: white; }
.observations { max-height: 620px; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fit,minmax(280px,1fr)); gap: 12px; } article { min-width: 0; padding: 14px; border: 1px solid #e2e8f0; border-radius: 8px; } article label { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; } label span { margin-left: auto; color: #74849a; font-size: 12px; }
.shot-evidence { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 5px; } .shot-evidence button { flex: 0 0 70px; padding: 3px; display: grid; gap: 4px; font-size: 10px; } .shot-evidence img { width: 62px; height: 58px; object-fit: cover; }
.target-card { margin-top: 12px; } form { display: grid; gap: 12px; padding: 16px 0; } form label { display: grid; gap: 5px; } form input,textarea { width: 100%; } .version { margin-top: 16px; padding: 12px; background: #f7f9fc; border-radius: 8px; } .four-views { display: grid; grid-template-columns: repeat(4,minmax(0,160px)); gap: 8px; margin: 12px 0; } .four-views button { padding: 4px; } .four-views img { width: 100%; height: 170px; object-fit: contain; background: #edf1f6; } .four-views span { display: block; font-size: 11px; } .error { color: #a84a4a; background: #fff4f4; padding: 10px; border-radius: 6px; }
.preview { position: fixed; inset: 0; z-index: 1200; display: grid; place-items: center; background: #111b; padding: 20px; } .preview img { display: block; max-width: 90vw; max-height: 82vh; } .preview button { display: block; margin-left: auto; } @media(max-width:700px) { .four-views { grid-template-columns: repeat(2,minmax(0,1fr)); } .observations { grid-template-columns: minmax(0,1fr); } }
</style>

<style scoped>
.identity-workspace{display:grid;grid-template-columns:220px minmax(280px,1fr) 250px;gap:16px;align-items:start;margin-top:16px}
.observation-list{background:#f7f9fc;border:1px solid #e2e8f0;border-radius:10px;padding:10px;min-width:0}.observation-list>input{width:100%;margin-bottom:10px}.observation-scroll{max-height:680px;overflow:auto;display:grid;gap:6px}.observation-row{display:flex;gap:10px;text-align:left;width:100%;padding:12px 8px;background:transparent;border-color:transparent}.observation-row small,.merge-person small{display:block;margin-top:5px;line-height:1.5}.observation-row em{display:block;margin-top:6px;font-size:11px;font-style:normal;color:#866414}.observation-number{border-radius:6px;background:#e9eef6;padding:3px 6px;align-self:flex-start;font-size:11px}.chosen{border-color:#3979ef!important;background:#eff5ff!important}.person-inspector{min-width:0}.person-inspector header p{margin:0 0 8px}.location-state{font-size:11px;color:#8b6218;background:#fff7e5;padding:6px;border-radius:5px}.mark-help{background:#eff5ff;padding:10px;border-radius:6px;color:#325786}.frame-stage{background:#121a26;min-height:220px;display:flex;align-items:center;justify-content:center;border-radius:8px;padding:14px;overflow:hidden}.mark-canvas{position:relative;max-width:100%;line-height:0;touch-action:none;cursor:crosshair;user-select:none}.mark-canvas>img{display:block;width:auto;max-width:100%;max-height:440px;object-fit:contain;pointer-events:none}.person-box{position:absolute;border:3px solid #31a6ff;box-shadow:0 0 0 999px #0006;pointer-events:none;box-sizing:border-box}.person-box span{position:absolute;left:-3px;top:0;line-height:1.3;background:#1267d9;color:white;padding:4px 6px;white-space:nowrap;font-size:12px}.shot-picker{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0;max-height:100px;overflow:auto}.shot-picker button{font-size:11px}.person-confirm{display:flex;gap:12px;align-items:center;padding:12px;background:#f7f9fc;border-radius:8px;margin-bottom:12px}.person-confirm strong{font-size:13px}.person-confirm p{font-size:11px;margin:6px 0}.person-crop{position:relative;overflow:hidden;width:84px;height:auto;flex:0 0 84px;background:#e6eaf1;border-radius:6px}.person-crop img{position:absolute;max-width:none;object-fit:fill}.merge-panel{padding:16px;background:#f7f9fc;border:1px solid #e2e8f0;border-radius:10px;display:grid;gap:12px;min-width:0}.merge-panel p{margin:0}.merge-panel label{display:grid;gap:6px;font-size:12px}.merge-panel input,.merge-panel select{width:100%;min-width:0}.merge-panel>small{line-height:1.5}.merge-row{display:flex;gap:6px}.merge-person{flex:1;min-width:0;text-align:left}.empty-selection{padding:24px 8px;border:1px dashed #ccd6e5;text-align:center}.primary{background:#1769ff;color:white}.person-confirm button{background:#1769ff;color:white}
@media(max-width:1450px){.identity-workspace{grid-template-columns:180px minmax(240px,1fr)}.merge-panel{grid-column:1/-1;grid-template-columns:repeat(2,minmax(0,1fr))}.merge-panel>h3,.merge-panel>p{grid-column:1/-1}}
@media(max-width:800px){.identity-workspace{grid-template-columns:minmax(0,1fr)}.observation-scroll{max-height:200px}.merge-panel{grid-template-columns:minmax(0,1fr)}.person-confirm{flex-wrap:wrap}}
</style>
