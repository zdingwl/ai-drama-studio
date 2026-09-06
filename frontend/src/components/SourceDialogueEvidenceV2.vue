<script setup lang="ts">
import { computed, ref, watch } from 'vue'
type Evidence = { id: string; revision: string; status: string; start_us: number; end_us: number; asr_text?: string; subtitle_text: string; utterance_id?: string; requires_full_text?: boolean }
const props = defineProps<{ episodeId: string; startUs: number; endUs: number; refreshToken?: string; disabled?: boolean }>()
const emit = defineEmits<{ saved: [] }>()
const rows = ref<Evidence[]>([])
const error = ref('')
const busy = ref(false)
const edits = ref<Record<string,string>>({})
let serial = 0
const visible = computed(() => rows.value.filter(r => r.status === 'OPEN' && Math.min(r.end_us, props.endUs) > Math.max(r.start_us, props.startUs)))
async function load() {
  const token = ++serial; rows.value = []; error.value = ''
  try {
    const response = await fetch(`/api/episodes/${encodeURIComponent(props.episodeId)}/dialogue-evidence`)
    if (!response.ok) throw new Error('对白校正证据读取失败')
    const data = await response.json()
    if (token === serial) {
      rows.value = data
      edits.value = Object.fromEntries(rows.value.map(r => [r.id, (r.requires_full_text ? r.asr_text : r.subtitle_text) || '']))
    }
  } catch (e) { if (token === serial) error.value = String(e instanceof Error ? e.message : e) }
}
watch(() => [props.episodeId, props.refreshToken], load, { immediate: true })
async function decide(row: Evidence, choice: string) {
  if (busy.value || props.disabled) return
  busy.value = true; error.value = ''
  const token = serial
  try {
    const response = await fetch(`/api/episodes/${encodeURIComponent(props.episodeId)}/dialogue-evidence/${row.id}/decide`, {
      method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({revision: row.revision, choice, text: edits.value[row.id]}),
    })
    if (!response.ok) { const body = await response.json(); throw new Error(body.detail || '保存失败') }
    if (token !== serial) return
    await load(); emit('saved')
  } catch (e) { if (token === serial) error.value = String(e instanceof Error ? e.message : e) }
  finally { busy.value = false }
}
</script>
<template>
  <section v-if="visible.length || error" class="dialogue-evidence" aria-label="语音与字幕校正">
    <h3>语音与字幕校正</h3><p>核对当前分镜的声音和字幕，确认后会同步同一句对白的所有分镜。</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <article v-for="row in visible" :key="row.id">
      <dl><dt>语音识别</dt><dd>{{ row.asr_text || '未获得可靠对白' }}</dd><dt>字幕识别</dt><dd>{{ row.subtitle_text }}</dd></dl>
      <p v-if="row.requires_full_text">这条字幕只对应部分对白，请核对并填写完整台词。</p>
      <label>完整台词<textarea v-model="edits[row.id]" :disabled="busy || disabled" maxlength="4000" /></label>
      <div><button type="button" :disabled="busy || disabled || row.requires_full_text" @click="decide(row,'SUBTITLE')">采用字幕为对白</button>
        <button type="button" :disabled="busy || disabled || !edits[row.id]?.trim()" @click="decide(row,'EDIT')">保存校正台词</button>
        <button v-if="row.asr_text" type="button" :disabled="busy || disabled" @click="decide(row,'ASR')">保留语音识别</button>
        <button v-if="!row.utterance_id" type="button" :disabled="busy || disabled" @click="decide(row,'NOT_DIALOGUE')">确认是画面文字</button></div>
    </article>
  </section>
</template>
<style scoped>
.dialogue-evidence label{display:grid;gap:6px;margin:10px 0;font-size:12px}.dialogue-evidence textarea{width:100%;min-height:70px;box-sizing:border-box;resize:vertical;border:1px solid #d6c5a7;border-radius:6px;padding:8px;font:inherit}
.dialogue-evidence{border:1px solid #efd39f;background:#fffbf2;padding:13px;border-radius:9px;display:grid;gap:10px}.dialogue-evidence h3{font-size:14px;margin:0}.dialogue-evidence p{font-size:12px;line-height:1.7;margin:0;color:#786244}.dialogue-evidence article{border-top:1px solid #ecdfc5;padding-top:10px}.dialogue-evidence dl{margin:0 0 10px;font-size:13px}.dialogue-evidence dt{font-size:11px;color:#8b7755;margin-bottom:4px}.dialogue-evidence dd{margin:0 0 8px;line-height:1.6}.dialogue-evidence article>div{display:flex;gap:7px;flex-wrap:wrap}.dialogue-evidence button{font-size:12px;padding:7px;border-radius:6px;border:1px solid #d6c5a7;background:white;color:#705325;cursor:pointer}.dialogue-evidence button:disabled{opacity:.5;cursor:not-allowed}
</style>
