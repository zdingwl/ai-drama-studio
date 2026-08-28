<script setup lang="ts">
import { computed } from 'vue'
import type { BreakdownRunSummary } from '../types/breakdown'
import { componentStatusLabel, runStatusLabel } from '../utils/breakdownUiText'

const props = defineProps<{
  run: BreakdownRunSummary
  unassignedCount: number
}>()

const components = [
  { key: 'ASR', label: 'ASR 语音识别' },
  { key: 'OCR', label: 'OCR 文字识别' },
  { key: 'VLM', label: 'VLM 画面理解' },
  { key: 'FUSION', label: '融合发布' },
]

const title = computed(() => {
  if (props.run.status === 'FAILED') return '本次 AI 拉片运行失败'
  if (props.run.status === 'PROCESSING') return '本次 AI 拉片仍在处理中'
  if (props.run.status === 'STALE') return '这是历史镜头版本的拉片草稿'
  return '本次运行没有可展示的场景草稿'
})

const description = computed(() => {
  if (props.run.status === 'FAILED') return '失败运行会作为历史记录保留，不会覆盖已经存在的可用 Draft。请根据下方处理链和错误信息定位失败阶段。'
  if (props.run.status === 'PROCESSING') return '完整 Structured Draft 尚未通过 Fusion / Validator 发布。后台任务完成后页面会自动重新读取当前 Draft。'
  if (props.run.status === 'STALE') return '该 Run 固定锚定历史 ShotRevision，只用于历史回看；不会自动冒充当前镜头版本结果。'
  return 'P3 不会把不完整数据伪装成可用 Draft。可以查看 Run 提示、未归属数据和处理链状态。'
})

function revisionLabel(): string {
  return props.run.source_shot_revision ? `R${props.run.source_shot_revision.revision}` : 'R?'
}

function componentStatus(key: string): string {
  const value = props.run.component_status?.[key]
  if (typeof value === 'string') return value.toUpperCase()
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    for (const field of ['status', 'state', 'result']) {
      if (typeof record[field] === 'string') return String(record[field]).toUpperCase()
    }
  }
  return '—'
}

function componentClass(status: string): string {
  if (status === 'READY') return 'ready'
  if (status === 'READY_WITH_WARNINGS' || status === 'NO_EVIDENCE') return 'warning'
  if (status === 'FAILED' || status === 'NOT_AVAILABLE') return 'danger'
  if (status === 'PROCESSING') return 'processing'
  return 'neutral'
}
</script>

<template>
  <section :class="['run-state-panel-v1', run.status.toLowerCase()]">
    <div class="run-state-icon">{{ run.status === 'FAILED' ? '!' : run.status === 'PROCESSING' ? '…' : 'i' }}</div>

    <div class="run-state-copy">
      <span>BREAKDOWN RUN · {{ revisionLabel() }}</span>
      <h3>{{ title }}</h3>
      <p>{{ description }}</p>

      <div class="run-state-context">
        <span><b>运行状态</b>{{ runStatusLabel(run.status) }}</span>
        <span><b>草稿关系</b>{{ run.is_current ? '当前剧集采用' : '只读历史 Run' }}</span>
        <span><b>镜头版本</b>{{ run.source_shot_revision?.is_current ? '当前 ShotRevision' : '历史 ShotRevision' }}</span>
        <span v-if="unassignedCount"><b>未归属数据</b>{{ unassignedCount }}</span>
      </div>

      <div class="run-pipeline-status">
        <div
          v-for="component in components"
          :key="component.key"
          :class="['run-component', componentClass(componentStatus(component.key))]"
        >
          <span>{{ component.label }}</span>
          <b>{{ componentStatusLabel(componentStatus(component.key)) }}</b>
        </div>
      </div>

      <div v-if="run.error_message" class="run-error-detail">
        <strong>错误详情</strong>
        <p>{{ run.error_message }}</p>
      </div>

      <div class="run-state-meta">
        <span>{{ run.pipeline_profile || run.schema_version }}</span>
        <span>{{ run.schema_version }}</span>
        <span v-if="run.started_at">开始 {{ run.started_at }}</span>
        <span v-if="run.completed_at">完成 {{ run.completed_at }}</span>
      </div>
    </div>
  </section>
</template>

<style scoped>
.run-state-panel-v1 { min-height: 520px; display: grid; grid-template-columns: 52px minmax(0, 720px); justify-content: center; align-content: center; gap: 18px; border: 1px solid #dfe5ef; border-radius: 15px; padding: 42px; background: #fff; box-shadow: 0 8px 28px rgba(45, 62, 94, .045); }
.run-state-icon { width: 48px; height: 48px; display: grid; place-items: center; border-radius: 50%; background: #eef3fb; color: #5273ad; font-size: 22px; font-weight: 900; }
.run-state-panel-v1.failed .run-state-icon { background: #ffe9e9; color: #b64444; }
.run-state-panel-v1.processing .run-state-icon { background: #eaf2ff; color: #3569bf; }
.run-state-panel-v1.stale .run-state-icon { background: #f0edf7; color: #756395; }
.run-state-copy { min-width: 0; }
.run-state-copy > span { color: #7d8ba0; font-size: 12px; font-weight: 850; letter-spacing: .04em; }
.run-state-copy h3 { margin: 5px 0 6px; color: #2b3d59; font-size: 21px; letter-spacing: -.01em; }
.run-state-copy > p { margin: 0; color: #6f7f96; font-size: 14px; line-height: 1.65; }
.run-state-context { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 16px; }
.run-state-context span { display: inline-flex; gap: 5px; align-items: center; border: 1px solid #e2e7ef; border-radius: 999px; padding: 6px 9px; background: #fafbfd; color: #60718b; font-size: 12px; }
.run-state-context b { color: #344b6d; }
.run-pipeline-status { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px; margin-top: 16px; }
.run-component { display: grid; gap: 4px; border: 1px solid #e1e6ee; border-radius: 10px; padding: 9px 10px; background: #f8fafc; }
.run-component span { color: #78869a; font-size: 11px; }
.run-component b { color: #526078; font-size: 12px; }
.run-component.ready { border-color: #ccebd9; background: #f0faf5; }
.run-component.ready b { color: #147e4d; }
.run-component.warning { border-color: #f0dfb5; background: #fff9eb; }
.run-component.warning b { color: #8f620f; }
.run-component.danger { border-color: #efc8c8; background: #fff3f3; }
.run-component.danger b { color: #ad4444; }
.run-component.processing { border-color: #cadefa; background: #f2f6ff; }
.run-component.processing b { color: #3569bf; }
.run-error-detail { margin-top: 14px; border: 1px solid #efc6c6; border-radius: 10px; padding: 10px 12px; background: #fff5f5; }
.run-error-detail strong { color: #9f4141; font-size: 12px; }
.run-error-detail p { margin: 5px 0 0; color: #8d4d4d; font-size: 13px; line-height: 1.55; word-break: break-word; }
.run-state-meta { display: flex; flex-wrap: wrap; gap: 8px 12px; margin-top: 13px; color: #8895a7; font-size: 11px; }
@media (max-width: 900px) {
  .run-state-panel-v1 { grid-template-columns: 1fr; padding: 24px; }
  .run-pipeline-status { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 560px) {
  .run-pipeline-status { grid-template-columns: 1fr; }
}
</style>
