<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PersonLocalizationReview from './PersonLocalizationReview.vue'
import type { PersonMark } from '../utils/personReviewGroups'
const props = defineProps<{ projectId: string; shotId: string }>()
const emit = defineEmits<{ saved: []; close: [] }>()
type Region = { id: string; image_url: string; box: number[] | null; source_time_us: number; reason: string }
type Review = { id: string; ai_suggestion: { candidates: Region[] }; editable_payload?: Record<string, unknown> }
type Context = { revision: string; image_url: string; candidates: { id: string; name: string }[]; reviews?: Review[] }
const context = ref<Context | null>(null)
const selected = ref('')
const mark = ref<PersonMark | null>(null)
const busy = ref(false)
const error = ref('')
const selectedRegion = ref('')
const rejectReason = ref('')
const regions = computed(() => (context.value?.reviews || []).flatMap(review => review.ai_suggestion.candidates.filter(region => !review.editable_payload?.[region.id]).map(region => ({ ...region, issueId: review.id }))))
const region = computed(() => regions.value.find(row => row.id === selectedRegion.value))
function chooseRegion(id: string) {
  selectedRegion.value = id; selected.value = ''; rejectReason.value = ''
  const row = region.value
  mark.value = row?.box ? { shot_id: props.shotId, image_url: row.image_url, box: [...row.box], source: 'MANUAL_BOX' } : null
}
const url = `/api/projects/${encodeURIComponent(props.projectId)}/character-assets/shots/${encodeURIComponent(props.shotId)}/presence`
async function request(options?: RequestInit): Promise<Context> {
  const result = await fetch(url, options)
  const data = await result.json()
  if (!result.ok) throw new Error(data.detail || '补充人物失败')
  return data
}
onMounted(async () => { try { context.value = await request(); chooseRegion(regions.value[0]?.id || '') } catch (e) { error.value = String(e) } })
async function save(decision = 'BIND') {
  if (!context.value || busy.value) return
  if (decision === 'BIND' && (!selected.value || mark.value?.source !== 'MANUAL_BOX')) return
  if (decision === 'NOT_PERSON' && (!region.value || rejectReason.value.trim().length < 2)) return
  busy.value = true; error.value = ''
  try {
    context.value = await request({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ character_id: selected.value, expected_revision: context.value.revision, localization: mark.value || {}, issue_id: region.value?.issueId, candidate_id: region.value?.id, decision, reason: rejectReason.value }) })
    if (regions.value.length) chooseRegion(regions.value[0]!.id)
    else emit('saved')
  } catch (e) { error.value = String(e) } finally { busy.value = false }
}
</script>
<template>
  <section class="missing-person">
    <header><strong>补充当前镜头漏掉的人</strong><button type="button" :disabled="busy" @click="emit('close')">取消</button></header>
    <p>逐帧核对疑似漏人区域，蓝框可拖动重画。检测位置不代表身份；只补此镜头，不指定说话人。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <template v-if="context">
      <label v-if="regions.length">待核对区域（{{ regions.length }} 个，并非人数）<select :value="selectedRegion" :disabled="busy" @change="chooseRegion(($event.target as HTMLSelectElement).value)"><option v-for="(row, index) in regions" :key="row.id" :value="row.id">区域 {{ index + 1 }} · {{ (row.source_time_us / 1000000).toFixed(2) }} 秒</option></select></label>
      <p v-if="region">{{ region.reason }}</p>
      <PersonLocalizationReview :image-url="region?.image_url || context.image_url || ''" :shot-id="shotId" label="待核对的出镜人物" :model-value="mark" :disabled="busy" :allow-single="false" @update:model-value="mark = $event" />
      <label>这个人是谁？<select v-model="selected" :disabled="busy"><option value="">身份不确定，暂不提交</option><option v-for="person in context.candidates" :key="person.id" :value="person.id">{{ person.name }}</option></select></label>
      <p v-if="!context.candidates.length">本场景还没有可用的正式人物，请先完成人物身份审核。</p>
      <button type="button" :disabled="busy || !selected || mark?.source !== 'MANUAL_BOX'" @click="save()">{{ busy ? '保存中…' : '确认框内身份并保存' }}</button>
      <details v-if="region"><summary>这个区域不是人物？</summary><p>仅用于检测误报，不能用于跳过身份不明的人。</p><input v-model="rejectReason" :disabled="busy" placeholder="例如：门框被误检，区域内没有人物" /><button type="button" :disabled="busy || rejectReason.trim().length < 2" @click="save('NOT_PERSON')">记录误报修正</button></details>
    </template>
  </section>
</template>
<style scoped>
.missing-person{background:#fff;border:1px solid #aac7ee;border-radius:10px;padding:12px;display:grid;gap:10px}.missing-person header{display:flex;justify-content:space-between;align-items:center}.missing-person p{font-size:12px;line-height:1.6;margin:0;color:#61718a}.missing-person [role=alert]{color:#b42318}.missing-person button,.missing-person select{padding:8px;border:1px solid #c8d5e7;border-radius:6px;background:#f4f8ff;color:#264c82}.missing-person button:disabled{opacity:.5}.missing-person label{display:flex;gap:10px;align-items:center;font-size:12px}
</style>
