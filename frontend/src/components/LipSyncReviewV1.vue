<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { remakeApi } from '../api/remake'
import type { ReviewIssue } from '../types/remake'

const props = defineProps<{ projectId: string; busy?: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const issues = ref<ReviewIssue[]>([])
const loading = ref(false)
const retryingId = ref('')
const error = ref('')

const lipIssues = computed(() => issues.value.filter((item) => item.issue_type === 'LIP_SYNC_QC'))

function segmentId(issue: ReviewIssue): string | null {
  const payload = issue.editable_payload
  if (!payload || typeof payload !== 'object') return null
  const value = (payload as Record<string, unknown>).generation_segment_id
  return typeof value === 'string' && value ? value : null
}

async function load(): Promise<void> {
  if (!props.projectId) return
  loading.value = true
  try {
    issues.value = await remakeApi.listReviewIssues(props.projectId, 'OPEN')
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '口型待确认读取失败'
  } finally {
    loading.value = false
  }
}

async function retry(issue: ReviewIssue): Promise<void> {
  const id = segmentId(issue)
  if (!id || props.busy || retryingId.value) return
  retryingId.value = issue.id
  try {
    await remakeApi.retryLipSyncReview(props.projectId, id)
    await remakeApi.startPostProduction(props.projectId)
    error.value = ''
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '重新定位口型人物失败'
  } finally {
    retryingId.value = ''
  }
}

watch(() => props.projectId, () => void load())
watch(() => props.busy, (busy, previous) => { if (previous && !busy) void load() })
onMounted(() => void load())
</script>

<template>
  <section v-if="lipIssues.length || error" class="lip-review">
    <header>
      <div><small>口型</small><strong>说话人物需要确认</strong><span>系统无法安全判断多人同框中应该修改哪一张脸时才会出现在这里。</span></div>
      <button :disabled="loading" @click="load">刷新</button>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <article v-for="issue in lipIssues" :key="issue.id">
      <div class="copy">
        <small>{{ issue.severity === 'BLOCKING' ? '阻塞成片' : '需要确认' }}</small>
        <strong>{{ issue.reason }}</strong>
        <span>如果刚刚修改了目标人物参考或重新生成了镜头，可以重新自动定位。系统定位成功并完成口型后会自动关闭此问题。</span>
      </div>
      <button class="primary" :disabled="props.busy || Boolean(retryingId) || !segmentId(issue)" @click="retry(issue)">
        {{ retryingId === issue.id ? '正在重新定位…' : props.busy ? '后台处理中…' : '重新定位口型人物' }}
      </button>
    </article>
  </section>
</template>

<style scoped>
.lip-review{overflow:hidden;border:1px solid #e6d2ac;border-radius:13px;background:#fffaf2}.lip-review>header{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:12px 14px;border-bottom:1px solid #efe2ca}.lip-review>header>div{display:grid;gap:2px}.lip-review small{font-size:8px;color:#9a783f}.lip-review strong{font-size:10px;color:#5f513a}.lip-review span{font-size:9px;color:#81745e;line-height:1.5}.lip-review>header button{border:1px solid #dfd4c2;border-radius:7px;padding:6px 9px;background:#fff;color:#746752;font-size:9px;cursor:pointer}.lip-review article{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:12px 14px;border-top:1px solid #f0e5d4}.lip-review article:first-of-type{border-top:0}.copy{display:grid;gap:4px;min-width:0}.primary{flex:0 0 auto;min-height:34px;border:0;border-radius:8px;padding:0 12px;background:#3566d6;color:#fff;font-size:9px;font-weight:800;cursor:pointer}.primary:disabled{opacity:.45;cursor:not-allowed}.error{margin:10px 14px;padding:8px 10px;border-radius:7px;background:#fff1f1;color:#a04d4d;font-size:9px}@media(max-width:800px){.lip-review article,.lip-review>header{align-items:stretch;flex-direction:column}}
</style>
