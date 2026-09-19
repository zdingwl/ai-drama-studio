<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  getScriptSource, pasteScriptSource, uploadScriptSource,
  type ScriptSourceRead,
} from '@/features/projects/scriptLocalization'

const props = withDefaults(defineProps<{ mode?: 'source' | 'script' }>(), { mode: 'source' })
const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const source = ref<ScriptSourceRead | null>(null)
const pasteText = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const notice = ref('')

async function refresh() {
  const id = projectId.value
  loading.value = true
  error.value = ''
  try {
    const next = await getScriptSource(id)
    if (id === projectId.value) source.value = next
  } catch (exc) {
    if (id === projectId.value) error.value = exc instanceof Error ? exc.message : '读取剧本失败'
  } finally {
    if (id === projectId.value) loading.value = false
  }
}

async function paste() {
  if (busy.value || !pasteText.value.trim()) return
  busy.value = true
  notice.value = ''
  error.value = ''
  try {
    await pasteScriptSource(projectId.value, pasteText.value)
    pasteText.value = ''
    notice.value = '原剧本已保存为新的不可变版本。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '保存剧本失败'
  } finally { busy.value = false }
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file || busy.value) return
  input.value = ''
  busy.value = true
  notice.value = ''
  error.value = ''
  try {
    await uploadScriptSource(projectId.value, file)
    notice.value = '原剧本已上传并保存。'
    await refresh()
  } catch (exc) {
    error.value = exc instanceof Error ? exc.message : '上传剧本失败'
  } finally { busy.value = false }
}

watch(projectId, () => { source.value = null; pasteText.value = ''; notice.value = ''; void refresh() })
onMounted(() => { void refresh() })
</script>

<template>
  <section class="script-workspace" data-testid="script-localization-workspace">
    <header><p class="eyebrow">剧本本土化</p><h2>{{ props.mode === 'source' ? '原剧本' : '本土化剧本' }}</h2><p>保持原始文本不可变；所有目标版本与原剧本独立。</p></header>
    <p v-if="error" class="message error" role="alert">{{ error }}</p>
    <p v-if="notice" class="message success" role="status">{{ notice }}</p>
    <p v-if="loading" class="message">正在读取原剧本…</p>
    <template v-else>
      <section class="panel" v-if="props.mode === 'source'">
        <h3>导入原剧本</h3>
        <p>支持 TXT、MD、Markdown（UTF-8）。上传或粘贴新文本将创建新的源文件版本，并使本项目旧的下游结果过期。</p>
        <label class="file-select">选择剧本文件<input data-testid="script-upload" type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" :disabled="busy" @change="upload" /></label>
        <label class="paste-label" for="script-paste">或粘贴剧本正文</label>
        <textarea id="script-paste" v-model="pasteText" rows="8" maxlength="2000000" placeholder="粘贴原剧本，保存后原始内容不可变…" :disabled="busy" />
        <button type="button" :disabled="busy || !pasteText.trim()" @click="paste">{{ busy ? '保存中…' : '保存粘贴剧本' }}</button>
      </section>
      <section class="panel">
        <h3>{{ props.mode === 'source' ? '当前原剧本' : '当前源文件' }}</h3>
        <template v-if="source?.document_id">
          <p class="meta">{{ source.filename }} · r{{ source.revision }} · {{ source.text?.length ?? 0 }} 字符</p>
          <pre class="source-text">{{ source.text }}</pre>
        </template>
        <p v-else>还没有原剧本，请在「原剧本」页面上传 TXT / MD 或粘贴文字。</p>
      </section>
      <section v-if="props.mode === 'script'" class="panel">
        <h3>本土化生产链</h3>
        <p>剧本结构分析、文化映射、本土化生成与正式导出尚未接入当前工作区。这里不会将原文冒充目标剧本，也不会启动复刻短剧的视频流程。</p>
      </section>
    </template>
  </section>
</template>

<style scoped>
.script-workspace{display:grid;gap:14px;max-width:1120px;margin:auto;color:#1b2b42}.script-workspace header,.panel{padding:20px 22px;border:1px solid #e2e8f0;border-radius:12px;background:#fff}.script-workspace header h2{margin:2px 0 8px;font-size:24px}.script-workspace header p,.panel p{color:#67788c;font-size:13px;line-height:1.7}.eyebrow{margin:0;color:#466de2!important;font-weight:800}.panel{display:grid;gap:12px}.panel h3{margin:0;font-size:17px}.file-select{display:inline-flex;justify-content:center;align-items:center;width:max-content;max-width:100%;padding:10px 14px;border:1px solid #bbc9da;border-radius:8px;cursor:pointer;font-size:13px;font-weight:700}.file-select input{max-width:250px;margin-left:12px}.paste-label{font-size:13px;font-weight:700}.panel textarea{width:100%;padding:12px;border:1px solid #cbd5e1;border-radius:8px;resize:vertical;font:13px/1.7 inherit}.panel button{width:max-content;padding:11px 16px;border:0;border-radius:8px;background:#2878ff;color:white;font-weight:700;cursor:pointer}.panel button:disabled{opacity:.5;cursor:not-allowed}.meta{margin:0}.source-text{max-height:65vh;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere;background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;font-size:13px;line-height:1.85}.message{padding:12px 15px;border-radius:8px;background:#f3f6ff}.error{background:#fff1f0;color:#a52626}.success{background:#edfff2;color:#22713d}
</style>
