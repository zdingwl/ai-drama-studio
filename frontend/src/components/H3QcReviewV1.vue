<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { remakeApi } from '../api/remake'
import type { GenerationAttempt, GenerationAttemptSummary, GenerationQualityCheck, GenerationQualitySummary, ReviewIssue } from '../types/remake'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()

const issues = ref<ReviewIssue[]>([])
const attempts = ref<GenerationAttemptSummary | null>(null)
const quality = ref<GenerationQualitySummary | null>(null)
const loading = ref(false)
const selectingId = ref('')
const retryingSegmentId = ref('')
const error = ref('')

const h3Issues = computed(() => issues.value.filter((item) => item.issue_type === 'H3_QC'))
const attemptById = computed(() => new Map((attempts.value?.attempts ?? []).map((attempt) => [attempt.id, attempt])))
const qcByAttempt = computed(() => new Map((quality.value?.checks ?? []).map((check) => [check.generation_attempt_id, check])))

function payload(issue: ReviewIssue): { generation_segment_id?: string; shot_ordinal?: number; shot_segment_index?: number; attempt_ids?: string[] } {
  if (!issue.editable_payload || typeof issue.editable_payload !== 'object') return {}
  return issue.editable_payload as { generation_segment_id?: string; shot_ordinal?: number; shot_segment_index?: number; attempt_ids?: string[] }
}

function issueAttempts(issue: ReviewIssue): GenerationAttempt[] {
  return (payload(issue).attempt_ids ?? [])
    .map((id) => attemptById.value.get(id))
    .filter((item): item is GenerationAttempt => Boolean(item && item.status === 'SUCCEEDED'))
    .sort((a, b) => b.attempt_number - a.attempt_number)
}

function qc(attempt: GenerationAttempt): GenerationQualityCheck | null { return qcByAttempt.value.get(attempt.id) ?? null }
function attemptVideo(attempt: GenerationAttempt): string { return remakeApi.generationAttemptVideoUrl(attempt.id) }
function score(value: number | null | undefined): string { return value == null ? '—' : `${Math.round(value * 100)}%` }
function qcLabel(value: string | undefined): string {
  const labels: Record<string, string> = { PASS: '通过', RETRY: '未通过', REVIEW: '模型不确定', WAITING_MODEL: '等待质检模型', STALE: '已失效' }
  return labels[value || ''] || value || '未质检'
}

async function load(): Promise<void> {
  if (!props.projectId) return
  loading.value = true
  try {
    const [issueResult, attemptResult, qualityResult] = await Promise.all([
      remakeApi.listReviewIssues(props.projectId, 'OPEN'),
      remakeApi.listGenerationAttempts(props.projectId),
      remakeApi.getH3Quality(props.projectId),
    ])
    issues.value = issueResult
    attempts.value = attemptResult
    quality.value = qualityResult
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'H3 待确认结果读取失败'
  } finally {
    loading.value = false
  }
}

async function selectAttempt(attempt: GenerationAttempt): Promise<void> {
  if (selectingId.value || retryingSegmentId.value) return
  selectingId.value = attempt.id
  try {
    await remakeApi.selectGenerationAttempt(attempt.id)
    await load()
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '采用 H3 版本失败'
  } finally {
    selectingId.value = ''
  }
}

async function retry(issue: ReviewIssue): Promise<void> {
  const segmentId = payload(issue).generation_segment_id
  if (!segmentId || selectingId.value || retryingSegmentId.value) return
  retryingSegmentId.value = segmentId
  try {
    await remakeApi.retryH3Segment(props.projectId, segmentId)
    error.value = ''
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'H3 重新生成任务启动失败'
  } finally {
    retryingSegmentId.value = ''
  }
}

watch(() => props.projectId, () => void load())
onMounted(() => void load())
</script>

<template>
  <section v-if="h3Issues.length || error" class="h3-review">
    <header>
      <div><small>H3 成片异常</small><strong>自动重试后仍需要你决定</strong><span>这里只出现真正无法安全自动决定的生成结果；采用版本会写入真实 Selected Output。</span></div>
      <button :disabled="loading" @click="load">刷新</button>
    </header>
    <p v-if="error" class="error">{{ error }}</p>

    <article v-for="issue in h3Issues" :key="issue.id" class="issue">
      <div class="issue-head">
        <div>
          <small>Shot {{ payload(issue).shot_ordinal ?? '—' }}<template v-if="payload(issue).shot_segment_index"> · Segment {{ payload(issue).shot_segment_index }}</template></small>
          <strong>{{ issue.reason }}</strong>
        </div>
        <button class="retry" :disabled="Boolean(selectingId) || Boolean(retryingSegmentId)" @click="retry(issue)">
          {{ retryingSegmentId === payload(issue).generation_segment_id ? '正在启动…' : '再生成一次' }}
        </button>
      </div>

      <div v-if="issueAttempts(issue).length" class="versions">
        <article v-for="attempt in issueAttempts(issue)" :key="attempt.id" class="version">
          <video controls preload="metadata" :src="attemptVideo(attempt)" />
          <div class="meta">
            <div><strong>版本 {{ attempt.attempt_number }}</strong><span>{{ attempt.mode }} · QC {{ score(qc(attempt)?.quality_score) }}</span></div>
            <em :class="(qc(attempt)?.status || 'none').toLowerCase()">{{ qcLabel(qc(attempt)?.status) }}</em>
          </div>
          <p>{{ qc(attempt)?.reason || '该版本尚无语义 QC 结论' }}</p>
          <button class="select" :disabled="Boolean(selectingId) || Boolean(retryingSegmentId)" @click="selectAttempt(attempt)">
            {{ selectingId === attempt.id ? '正在采用…' : '采用这个版本' }}
          </button>
        </article>
      </div>
      <p v-else class="empty">当前没有可人工采用的成功版本，建议重新生成。</p>
    </article>
  </section>
</template>

<style scoped>
.h3-review{overflow:hidden;border:1px solid #e2d5ad;border-radius:13px;background:#fff}.h3-review>header{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:13px 15px;border-bottom:1px solid #eee5cf;background:#fffaf0}.h3-review>header>div{display:grid;gap:2px}.h3-review small{font-size:9px;color:#9b7a3f}.h3-review strong{font-size:11px;color:#4c5666}.h3-review span{font-size:9px;color:#8792a0}.h3-review>header button,.retry,.select{border:1px solid #d7dfe8;border-radius:8px;background:#fff;color:#66758a;font-size:9px;cursor:pointer}.h3-review>header button{padding:7px 10px}.issue{padding:13px 15px;border-top:1px solid #eee}.issue:first-of-type{border-top:0}.issue-head{display:flex;justify-content:space-between;align-items:center;gap:16px}.issue-head>div{display:grid;gap:3px}.retry{min-height:34px;padding:0 12px;border-color:#d7b77b;color:#895f1e}.versions{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;margin-top:10px}.version{overflow:hidden;border:1px solid #e1e6ed;border-radius:9px;background:#fafbfd}.version video{display:block;width:100%;aspect-ratio:9/16;max-height:390px;background:#111}.meta{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px}.meta>div{display:grid;gap:2px}.meta em{padding:4px 7px;border-radius:999px;background:#f1f3f6;color:#728095;font-size:8px;font-style:normal}.meta em.pass{background:#eaf7ef;color:#317653}.meta em.retry,.meta em.review{background:#fff1e2;color:#9a6313}.version p{min-height:30px;margin:0;padding:0 8px 8px;color:#738094;font-size:9px;line-height:1.5}.select{width:calc(100% - 16px);min-height:34px;margin:0 8px 8px;border-color:#96addc;color:#315bab;font-weight:700}.retry:disabled,.select:disabled,.h3-review>header button:disabled{opacity:.45}.empty{margin:10px 0 0;padding:10px;border-radius:8px;background:#f6f7f9;color:#7b8797;font-size:9px}.error{margin:10px 15px;padding:8px 10px;border-radius:7px;background:#fff2f2;color:#a94e4e;font-size:10px}@media(max-width:1000px){.versions{grid-template-columns:1fr 1fr}}@media(max-width:700px){.versions{grid-template-columns:1fr}.issue-head{align-items:stretch;flex-direction:column}}
</style>
