<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import PersonEvidenceImageV1 from './PersonEvidenceImageV1.vue'

type Mark = { shot_id: string; image_url: string; box: number[]; source?: string; evidence_id?: string }
type Person = { id: string; name: string; cover_url?: string; cover_box?: number[]; shot_ids: string[] }
type Observation = { key: string; episode_id: string; name: string; appearance?: string; character_id?: string;
  identity_issue?: string; extracted_image_url?: string; extracted_localization?: Mark;
  shots: {id: string; ordinal: number}[] }
type Workspace = { revision: string; observations: Observation[]; characters: Person[] }
const props = defineProps<{ projectId: string; episodeId: string; shotId: string; refreshToken?: string; disabled?: boolean }>()
const emit = defineEmits<{ saved: []; locate: [key: string] }>()
const workspace = ref<Workspace | null>(null)
const selected = ref<string[]>([])
const allEpisode = ref(false)
const target = ref('')
const name = ref('')
const busy = ref(false)
const loading = ref(false)
const error = ref('')
let serial = 0
const episodeRows = computed(() => workspace.value?.observations.filter(r => r.episode_id === props.episodeId) || [])
const visibleRows = computed(() => episodeRows.value.filter(r => allEpisode.value || r.shots.some(s => s.id === props.shotId)))
const pending = computed(() => visibleRows.value.filter(r => !r.character_id))
const people = computed(() => {
  const ids = new Set(visibleRows.value.map(r => r.character_id))
  return workspace.value?.characters.filter(p => ids.has(p.id) || (!allEpisode.value && p.shot_ids.includes(props.shotId))) || []
})
const choices = computed(() => workspace.value?.characters || [])
const locked = computed(() => props.disabled || busy.value || loading.value)
async function request(url: string, init?: RequestInit) {
  const response = await fetch(url, init)
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || '人物数据读取失败') }
  return response.json()
}
async function load() {
  const token = ++serial
  loading.value = true
  error.value = ''
  selected.value = []
  try {
    const result = await request(`/api/projects/${encodeURIComponent(props.projectId)}/character-assets`)
    if (token === serial) workspace.value = result
  } catch (e) { if (token === serial) error.value = String(e instanceof Error ? e.message : e) }
  finally { if (token === serial) loading.value = false }
}
watch(() => [props.projectId, props.episodeId, props.refreshToken], () => {
  workspace.value = null; target.value = ''; name.value = ''; void load()
}, { immediate: true })
watch(() => [props.shotId, allEpisode.value], () => { selected.value = []; target.value = ''; name.value = '' })
async function merge() {
  if (!workspace.value || locked.value || !selected.value.length) return
  busy.value = true; error.value = ''
  const localizations = Object.fromEntries(workspace.value.observations.filter(r => selected.value.includes(r.key))
    .map(r => [r.key, r.extracted_localization]))
  try {
    workspace.value = await request(`/api/projects/${encodeURIComponent(props.projectId)}/character-assets/assign`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys: selected.value, name: name.value.trim(), character_id: target.value || null,
        expected_revision: workspace.value.revision, localizations }),
    })
    selected.value = []; target.value = ''; name.value = ''; emit('saved')
  } catch (e) { error.value = String(e instanceof Error ? e.message : e) }
  finally { busy.value = false }
}
</script>

<template>
  <section class="source-people-panel" aria-label="原片人物归并">
    <header class="people-header"><strong>{{ allEpisode ? '本集人物' : '当前分镜人物' }}</strong>
      <button type="button" :disabled="locked" @click="allEpisode = !allEpisode">{{ allEpisode ? '查看当前分镜' : '整理本集人物' }}</button></header>
    <p class="people-help">人物归并后自动绑定关联分镜。每人只展示一张代表图，其余识别证据保存在数据库。</p>
    <p v-if="loading">正在读取人物…</p>
    <p v-if="error" role="alert" class="people-error">{{ error }} <button type="button" :disabled="busy" @click="load">重新读取</button></p>
    <div class="people-grid">
      <article v-for="person in people" :key="person.id" class="identity-card">
        <div class="identity-image"><PersonEvidenceImageV1 v-if="person.cover_url" :src="person.cover_url" :box="person.cover_box" :alt="person.name" /><span v-else>待提取展示图</span></div>
        <strong>{{ person.name }}</strong><span>已绑定 · {{ person.shot_ids.length }} 个分镜</span>
        <button v-if="selected.length" type="button" :disabled="locked" @click="target = person.id; name = ''">{{ target === person.id ? '已选为合并目标' : '合并到此人物' }}</button>
      </article>
    </div>
    <h4 v-if="pending.length">待人工归并 · {{ pending.length }} 组</h4>
    <p v-if="!loading && !pending.length && !people.length">尚无可用人物结果，请执行分镜或整集拉片。</p>
    <div class="pending-people">
      <label v-for="row in pending" :key="row.key" class="pending-person">
        <input v-model="selected" type="checkbox" :value="row.key" :disabled="locked || !row.extracted_localization || !!row.identity_issue" />
        <div class="pending-image"><PersonEvidenceImageV1 v-if="row.extracted_image_url" :src="row.extracted_image_url" :alt="row.appearance || row.name" /><span v-else>待定位</span></div>
        <div><strong>{{ row.name }}</strong><p>{{ row.appearance || '外观信息待补全' }}</p>
          <small>分镜 {{ row.shots.map(s => String(s.ordinal).padStart(2, '0')).join('、') }}</small>
          <p v-if="row.identity_issue" class="people-error">{{ row.identity_issue }}</p>
          <button v-if="!row.extracted_localization" type="button" :disabled="locked" @click.prevent="emit('locate', row.key)">核对人物位置</button></div>
      </label>
    </div>
    <form v-if="selected.length" class="merge-controls" @submit.prevent="merge">
      <strong>将选中的 {{ selected.length }} 组视为同一个人</strong>
      <label>合并目标<select v-model="target" :disabled="locked"><option value="">建立新人物</option><option v-for="p in choices" :key="p.id" :value="p.id">{{ p.name }}</option></select></label>
      <label v-if="!target">人物名称<input v-model="name" :disabled="locked" placeholder="输入人物名称" maxlength="100" /></label>
      <button type="submit" :disabled="locked || (!target && !name.trim())">{{ busy ? '保存中…' : '确认合并并绑定分镜' }}</button>
    </form>
  </section>
</template>

<style scoped>
.source-people-panel{display:grid;gap:14px;min-width:0}.people-header{display:flex;align-items:center;justify-content:space-between;gap:8px}.people-help{color:#697386;font-size:12px;line-height:1.7;margin:0}.source-people-panel button{cursor:pointer;border:1px solid #cfdaef;background:#f5f8ff;color:#295ec5;border-radius:7px;padding:7px 10px;font-size:12px}.source-people-panel button:disabled{opacity:.5;cursor:not-allowed}.people-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px}.identity-card{border:1px solid #e1e7ee;border-radius:10px;overflow:hidden;display:flex;flex-direction:column;gap:7px;padding:10px;min-width:0}.identity-card>span{font-size:12px;color:#697386}.identity-image{height:140px;background:#f0f2f5;border-radius:7px;overflow:hidden;display:grid;place-items:center}.identity-image>span,.pending-image>span{font-size:12px;color:#768198}.pending-people{display:grid;gap:8px}.pending-person{display:grid;grid-template-columns:16px 68px minmax(0,1fr);align-items:start;gap:9px;padding:10px;border:1px solid #e1e7ee;border-radius:9px;cursor:pointer}.pending-person input[type=checkbox]{width:16px;height:16px;margin:4px 0;flex:none}.pending-image{height:90px;overflow:hidden;display:grid;place-items:center}.pending-person p{margin:5px 0;font-size:12px;line-height:1.6}.pending-person small{font-size:11px;color:#697386;overflow-wrap:anywhere}.merge-controls{display:grid;gap:10px;background:#f2f6ff;padding:12px;border-radius:9px}.merge-controls label{display:grid;gap:5px;font-size:12px}.merge-controls input,.merge-controls select{width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:6px;padding:8px;background:white}.people-error{color:#b42318;font-size:12px;line-height:1.5}.source-people-panel h4{margin:3px 0;font-size:13px}
</style>
