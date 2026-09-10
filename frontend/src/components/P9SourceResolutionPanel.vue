<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getProject, listProjectTasks } from '@/features/projects/api'
import { getShotBreakdown, type ShotBreakdownRead } from '@/features/projects/shotBreakdown'
import {
  adjudicateSourceResolution,
  getSourceResolution,
  listSourceResolutionRevisions,
  startSourceResolution,
  type ManualResolutionCommand,
  type ManualResolutionOperation,
  type ResolutionRead,
  type ResolutionStatus,
  type SourceResolutionKind,
  type SourceResolutionRead,
  type SourceResolutionRevisionSummary,
  type StableEntity,
} from '@/features/projects/sourceResolution'
import type { ProjectRead, TaskRead } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const p8 = ref<ShotBreakdownRead | null>(null)
const result = ref<SourceResolutionRead | null>(null)
const revisions = ref<SourceResolutionRevisionSummary[]>([])
const activeTask = ref<TaskRead | null>(null)
const loading = ref(true)
const starting = ref(false)
const adjudicating = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
let pollTimer: number | null = null

const selectedKind = ref<SourceResolutionKind>('CHARACTER')
const manualOperation = ref<ManualResolutionOperation>('CONFIRM')
const manualEntityIds = ref('')
const manualTargetEntityId = ref('')
const manualReferenceIds = ref('')
const manualSplitGroups = ref('')
const manualCharacterId = ref('')
const manualDisplayName = ref('')
const manualReason = ref('')

const visible = computed(() => project.value?.project_type === 'REPLICA' || project.value?.project_type === 'REDRAW')
const p8Ready = computed(() => p8.value?.status === 'CURRENT')
const taskActive = computed(() => activeTask.value?.status === 'queued' || activeTask.value?.status === 'running')

const kindMeta: Record<SourceResolutionKind, { title: string; subtitle: string }> = {
  CHARACTER: { title: 'Character', subtitle: '人物身份' },
  SPEAKER: { title: 'Speaker', subtitle: '说话人归因' },
  SCENE: { title: 'Scene', subtitle: '场景归一' },
  PROP: { title: 'Prop', subtitle: '道具实例' },
}

const statusText: Record<string, string> = {
  CURRENT: 'CURRENT',
  STALE: 'STALE',
  NOT_BUILT: 'NOT_BUILT',
  RESOLVED: '已归一',
  MANUAL_CONFIRMED: '人工确认',
  UNKNOWN: '未知',
  UNRESOLVED: '待裁决',
}

const aggregateStatus = computed(() => {
  if (!result.value) return '读取中'
  const statuses = [
    result.value.characters.status,
    result.value.speakers.status,
    result.value.scenes.status,
    result.value.props.status,
  ]
  if (statuses.every((value) => value === 'CURRENT')) return 'CURRENT'
  if (statuses.some((value) => value === 'STALE')) return 'STALE'
  if (statuses.some((value) => value === 'CURRENT')) return 'PARTIAL'
  return 'NOT_BUILT'
})

function resolution(kind: SourceResolutionKind): ResolutionRead<any> | null {
  if (!result.value) return null
  if (kind === 'CHARACTER') return result.value.characters
  if (kind === 'SPEAKER') return result.value.speakers
  if (kind === 'SCENE') return result.value.scenes
  return result.value.props
}

function entities(kind: SourceResolutionKind): StableEntity[] {
  return (resolution(kind)?.content?.entities ?? []) as StableEntity[]
}

function unresolvedCount(kind: SourceResolutionKind): number {
  const content = resolution(kind)?.content
  if (!content) return 0
  let rows: Array<{ resolution_status: ResolutionStatus }> = []
  if (kind === 'CHARACTER') rows = content.observations
  else if (kind === 'SPEAKER') rows = content.attributions
  else if (kind === 'SCENE') rows = content.assignments
  else rows = content.observations
  return rows.filter((item) => item.resolution_status === 'UNKNOWN' || item.resolution_status === 'UNRESOLVED').length
}

function memberCount(kind: SourceResolutionKind, entity: StableEntity): number {
  if (kind === 'SPEAKER') return ((entity as any).utterance_ids ?? []).length
  return entity.shot_anchor_ids.length
}

function memberLabel(kind: SourceResolutionKind): string {
  return kind === 'SPEAKER' ? '句对白' : '镜头'
}

function linkedCharacterName(entity: StableEntity): string {
  const characterId = (entity as any).character_id as string | null | undefined
  if (!characterId) return '未绑定 Character'
  const target = result.value?.characters.content?.entities.find((item) => item.character_id === characterId)
  return target ? `${target.display_name} · ${shortId(characterId)}` : `Character ${shortId(characterId)}`
}

function sceneShotNumbers(entity: StableEntity): string {
  const assignments = result.value?.scenes.content?.assignments ?? []
  const wanted = new Set(entity.shot_anchor_ids)
  return assignments
    .filter((item) => wanted.has(item.shot_anchor_id))
    .map((item) => `#${String(item.shot_number).padStart(3, '0')}`)
    .join(' · ')
}

function shortId(value: string | null | undefined): string {
  if (!value) return '—'
  return value.length > 22 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value
}

function commandKey(): string {
  const suffix = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random()}`
  return `p9-source-resolution-${suffix}`.slice(0, 128)
}

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshResult(): Promise<void> {
  const [current, history, shotBreakdown] = await Promise.all([
    getSourceResolution(projectId.value),
    listSourceResolutionRevisions(projectId.value),
    getShotBreakdown(projectId.value),
  ])
  result.value = current
  revisions.value = history
  p8.value = shotBreakdown
}

function startPolling(taskId: string): void {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      const tasks = await listProjectTasks(projectId.value)
      const task = tasks.find((item) => item.id === taskId) ?? null
      activeTask.value = task
      if (!task || (task.status !== 'queued' && task.status !== 'running')) {
        stopPolling()
        await refreshResult()
      }
    } catch (error) {
      stopPolling()
      errorMessage.value = error instanceof Error ? error.message : 'P9 任务状态读取失败'
    }
  }, 1000)
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    project.value = await getProject(projectId.value)
    if (!visible.value) return
    await refreshResult()
    const tasks = await listProjectTasks(projectId.value)
    const running = tasks.find(
      (item) => (item.status === 'queued' || item.status === 'running') && item.task_name.includes('最终归一'),
    )
    if (running) {
      activeTask.value = running
      startPolling(running.id)
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P9 最终归一加载失败'
  } finally {
    loading.value = false
  }
}

async function runP9(): Promise<void> {
  if (taskActive.value || !p8Ready.value) return
  starting.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const task = await startSourceResolution(projectId.value, commandKey())
    activeTask.value = task
    startPolling(task.id)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P9 最终归一任务启动失败'
  } finally {
    starting.value = false
  }
}

function csv(value: string): string[] {
  return value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean)
}

function splitGroups(value: string): string[][] {
  return value
    .split('\n')
    .map((line) => csv(line))
    .filter((group) => group.length)
}

function resetManualForm(): void {
  manualEntityIds.value = ''
  manualTargetEntityId.value = ''
  manualReferenceIds.value = ''
  manualSplitGroups.value = ''
  manualCharacterId.value = ''
  manualDisplayName.value = ''
  manualReason.value = ''
}

async function submitAdjudication(): Promise<void> {
  const current = resolution(selectedKind.value)
  if (!current?.revision) {
    errorMessage.value = '当前类型还没有可裁决的 P9 revision。'
    return
  }
  if (!manualReason.value.trim()) {
    errorMessage.value = '人工裁决必须填写理由。'
    return
  }
  const payload: ManualResolutionCommand = {
    expected_revision: current.revision,
    operation: manualOperation.value,
    entity_ids: csv(manualEntityIds.value),
    target_entity_id: manualTargetEntityId.value.trim() || null,
    reference_ids: csv(manualReferenceIds.value),
    split_groups: splitGroups(manualSplitGroups.value),
    character_id: manualCharacterId.value.trim() || null,
    display_name: manualDisplayName.value.trim() || null,
    reason: manualReason.value.trim(),
  }
  adjudicating.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    result.value = await adjudicateSourceResolution(projectId.value, selectedKind.value, payload)
    revisions.value = await listSourceResolutionRevisions(projectId.value)
    successMessage.value = `${kindMeta[selectedKind.value].subtitle}人工裁决已生成新 revision；历史 revision 保留。`
    resetManualForm()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P9 人工裁决失败'
  } finally {
    adjudicating.value = false
  }
}

function revisionHistory(kind: SourceResolutionKind): SourceResolutionRevisionSummary[] {
  return revisions.value.filter((item) => item.resolution_kind === kind)
}

onMounted(load)
onBeforeUnmount(stopPolling)
</script>

<template>
  <section v-if="visible" class="resolution-workspace" data-testid="p9-source-resolution">
    <header class="workspace-header">
      <div>
        <p class="section-kicker">原片理解 · P9 最终归一</p>
        <div class="title-line">
          <h2>Speaker / Character / Scene / Prop</h2>
          <span class="status-pill" :class="aggregateStatus.toLowerCase()">{{ aggregateStatus }}</span>
        </div>
        <p class="workspace-subtitle">跨 Shot、跨 Episode 汇总完整原片证据，形成稳定 Source identity；证据不足保留 UNKNOWN / UNRESOLVED。</p>
      </div>
      <div class="workspace-actions">
        <button class="primary-action" type="button" :disabled="starting || taskActive || !p8Ready" @click="runP9">
          {{ starting ? '正在提交…' : aggregateStatus === 'CURRENT' ? '重新归一' : '运行最终归一' }}
        </button>
        <button class="ghost-action" type="button" :disabled="taskActive" @click="refreshResult">刷新</button>
      </div>
    </header>

    <div class="truth-strip">
      <b>Source Truth</b>
      <span>完整 Episode</span>
      <i>→</i>
      <span>P5 Shot 时间只读</span>
      <i>→</i>
      <span>P6 canonical 对白 / OCR 只读</span>
      <i>→</i>
      <span>P7/P8 仅作 candidate / facts</span>
    </div>

    <div class="preflight-strip" data-testid="p9-p8-preflight">
      <b>P8 SOURCE_SHOT_FACTS</b>
      <span v-if="p8">{{ p8.status }}{{ p8.revision == null ? '' : ` · rev ${p8.revision}` }}</span>
      <span v-else>读取中…</span>
      <em v-if="p8Ready">P9 前置已就绪</em>
      <small v-else>必须先得到 CURRENT P8；这里不会通过 GET 隐式启动任务。</small>
    </div>

    <p v-if="errorMessage" class="message error-message">{{ errorMessage }}</p>
    <p v-if="successMessage" class="message success-message">{{ successMessage }}</p>
    <p v-if="loading" class="loading-message">正在读取 P9 最终归一结果…</p>

    <template v-else>
      <div v-if="activeTask" class="task-progress">
        <div>
          <strong>{{ activeTask.task_name }}</strong>
          <span>{{ activeTask.status }} · attempt {{ activeTask.attempt }}/{{ activeTask.max_attempts }}</span>
        </div>
        <div class="progress-right">
          <b>{{ activeTask.progress_percent }}%</b>
          <div class="progress-track"><i :style="{ width: `${activeTask.progress_percent}%` }"></i></div>
        </div>
      </div>

      <div class="kind-grid">
        <article v-for="kind in (Object.keys(kindMeta) as SourceResolutionKind[])" :key="kind" class="kind-card" :class="resolution(kind)?.status.toLowerCase()">
          <div class="kind-heading">
            <div><small>{{ kindMeta[kind].title }}</small><strong>{{ kindMeta[kind].subtitle }}</strong></div>
            <span>{{ statusText[resolution(kind)?.status ?? 'NOT_BUILT'] }}</span>
          </div>
          <div class="kind-counts">
            <b>{{ entities(kind).length }}</b><span>stable identities</span>
            <b>{{ unresolvedCount(kind) }}</b><span>unknown / unresolved</span>
          </div>
          <small v-if="resolution(kind)?.revision">rev {{ resolution(kind)?.revision }} · {{ resolution(kind)?.provenance?.professional_skill_id }}@{{ resolution(kind)?.provenance?.professional_skill_version }}</small>
        </article>
      </div>

      <section v-for="kind in (Object.keys(kindMeta) as SourceResolutionKind[])" :key="`section-${kind}`" class="entity-section">
        <header class="entity-section-header">
          <div><span>{{ kindMeta[kind].title }}</span><h3>{{ kindMeta[kind].subtitle }}</h3></div>
          <div class="section-status"><b>{{ resolution(kind)?.status ?? 'NOT_BUILT' }}</b><small>{{ unresolvedCount(kind) }} 项未决</small></div>
        </header>

        <p v-if="resolution(kind)?.status === 'STALE'" class="stale-note">该类型当前只有历史 STALE revision，不能作为新的 Source Truth；请重新运行 P9 或按允许的人工裁决路径恢复。</p>

        <div v-if="entities(kind).length" class="entity-list">
          <article v-for="entity in entities(kind)" :key="entity.entity_id" class="entity-card">
            <div class="entity-main">
              <div class="entity-title">
                <strong>{{ entity.display_name }}</strong>
                <span :class="`resolution-${entity.resolution_status.toLowerCase()}`">{{ statusText[entity.resolution_status] }}</span>
              </div>
              <code>{{ entity.entity_id }}</code>
              <p v-if="kind === 'SPEAKER'" class="link-copy">↳ {{ linkedCharacterName(entity) }}</p>
              <p v-if="kind === 'SCENE' && sceneShotNumbers(entity)" class="member-copy">{{ sceneShotNumbers(entity) }}</p>
              <p v-if="entity.notes.length" class="notes-copy">{{ entity.notes.join('；') }}</p>
            </div>
            <dl class="entity-facts">
              <div><dt>置信度</dt><dd>{{ Math.round(entity.confidence * 100) }}%</dd></div>
              <div><dt>覆盖</dt><dd>{{ memberCount(kind, entity) }} {{ memberLabel(kind) }}</dd></div>
              <div><dt>候选</dt><dd>{{ entity.source_candidate_ids.length }}</dd></div>
              <div><dt>证据</dt><dd>{{ entity.evidence_refs.length }}</dd></div>
            </dl>
          </article>
        </div>
        <div v-else class="empty-state">{{ resolution(kind)?.status === 'NOT_BUILT' ? '尚未生成正式结果。' : '当前没有 stable identity；未决观察仍保留在 typed content 中。' }}</div>

        <details v-if="resolution(kind)?.content" class="technical-details">
          <summary>技术信息与 revision</summary>
          <div class="technical-grid">
            <span><b>Artifact</b>{{ shortId(resolution(kind)?.artifact_id) }}</span>
            <span><b>Schema</b>{{ resolution(kind)?.content?.schema_version }}</span>
            <span><b>Provider</b>{{ resolution(kind)?.provenance?.provider ?? '—' }}</span>
            <span><b>Model</b>{{ resolution(kind)?.provenance?.model ?? '—' }}</span>
            <span><b>Contract</b>{{ resolution(kind)?.provenance?.source_truth_contract ?? '—' }}</span>
            <span><b>ProviderJobs</b>{{ resolution(kind)?.provenance?.provider_jobs.length ?? 0 }}</span>
          </div>
          <p>历史：{{ revisionHistory(kind).map((item) => `rev ${item.revision} ${item.status}${item.adjudication ? ` · ${item.adjudication.operation}` : ''}`).join(' / ') || '—' }}</p>
        </details>
      </section>

      <details class="adjudication-panel">
        <summary>
          <div><strong>人工裁决 / 验收</strong><span>CONFIRM · MERGE · SPLIT · MARK_UNKNOWN · REASSIGN</span></div>
          <small>每次提交生成新 revision，不改历史结果</small>
        </summary>
        <form class="adjudication-form" @submit.prevent="submitAdjudication">
          <label><span>类型</span><select v-model="selectedKind"><option v-for="kind in (Object.keys(kindMeta) as SourceResolutionKind[])" :key="kind" :value="kind">{{ kind }} · {{ kindMeta[kind].subtitle }}</option></select></label>
          <label><span>操作</span><select v-model="manualOperation"><option value="CONFIRM">CONFIRM</option><option value="MERGE">MERGE</option><option value="SPLIT">SPLIT</option><option value="MARK_UNKNOWN">MARK_UNKNOWN</option><option value="REASSIGN">REASSIGN</option></select></label>
          <label class="wide"><span>entity_ids</span><input v-model="manualEntityIds" placeholder="多个 ID 用逗号分隔" /></label>
          <label><span>target_entity_id</span><input v-model="manualTargetEntityId" placeholder="REASSIGN 目标 identity" /></label>
          <label><span>display_name</span><input v-model="manualDisplayName" placeholder="可选人工名称" /></label>
          <label class="wide"><span>reference_ids</span><textarea v-model="manualReferenceIds" rows="2" placeholder="utterance_id / shot_anchor_id / shot:candidate；逗号或换行分隔"></textarea></label>
          <label class="wide"><span>split_groups</span><textarea v-model="manualSplitGroups" rows="3" placeholder="SPLIT 时每行一个 group，组内逗号分隔；必须完整覆盖旧 identity"></textarea></label>
          <label v-if="selectedKind === 'SPEAKER'"><span>Character link</span><input v-model="manualCharacterId" placeholder="P9 character_id；留空表示解除绑定" /></label>
          <label class="wide"><span>人工理由 *</span><textarea v-model="manualReason" rows="3" required placeholder="说明音画证据、拆分/合并依据或为什么保持 UNKNOWN"></textarea></label>
          <div class="form-footer wide">
            <span>expected_revision：{{ resolution(selectedKind)?.revision ?? '—' }}</span>
            <button class="primary-action" type="submit" :disabled="adjudicating || !resolution(selectedKind)?.revision">{{ adjudicating ? '正在生成新 revision…' : '提交人工裁决' }}</button>
          </div>
        </form>
      </details>

      <div v-if="aggregateStatus === 'NOT_BUILT'" class="empty-state main-empty">
        <strong>还没有 P9 最终归一结果</strong>
        <p>完整 Episode、P5、P6、P7、P8 均保持 CURRENT 后，使用上方显式 POST 命令运行 P9。</p>
      </div>
    </template>
  </section>
</template>

<style scoped>
.resolution-workspace { margin-top: 24px; padding: 28px; background: #fff; border: 1px solid #e7e9ee; border-radius: 18px; color: #172033; }
.workspace-header,.title-line,.workspace-actions,.task-progress,.kind-heading,.entity-section-header,.entity-title,.form-footer { display: flex; align-items: center; }
.workspace-header,.task-progress,.entity-section-header,.form-footer { justify-content: space-between; gap: 20px; }
.section-kicker { margin: 0 0 5px; color: #7b8495; font-size: 12px; font-weight: 700; }
.title-line { gap: 10px; } h2,h3,p { margin-top: 0; } h2 { margin-bottom: 0; font-size: 27px; } .workspace-subtitle { margin: 7px 0 0; color: #6d7688; font-size: 13px; }
.status-pill { padding: 5px 9px; border-radius: 999px; background: #f0f2f6; color: #646d7f; font-size: 11px; font-weight: 800; }.status-pill.current { background: #eaf8ef; color: #267a48; }.status-pill.stale,.status-pill.partial { background: #fff1dc; color: #9a6414; }
.workspace-actions { gap: 8px; }.primary-action,.ghost-action { border-radius: 10px; padding: 10px 15px; font: inherit; font-weight: 700; cursor: pointer; }.primary-action { border: 0; background: #202632; color: #fff; }.ghost-action { border: 1px solid #d9dde5; background: #fff; color: #333b49; }button:disabled { opacity: .45; cursor: not-allowed; }
.truth-strip,.preflight-strip { margin-top: 16px; display: flex; align-items: center; flex-wrap: wrap; gap: 9px; padding: 9px 12px; border-radius: 10px; background: #f7f8fa; color: #657083; font-size: 12px; }.truth-strip b,.preflight-strip b { color: #343d4d; }.truth-strip i { color: #adb3bd; font-style: normal; }.preflight-strip em { margin-left: auto; color: #267a48; font-style: normal; font-weight: 700; }.preflight-strip small { margin-left: auto; color: #9a6414; }
.message,.task-progress,.stale-note { margin-top: 14px; border-radius: 12px; padding: 12px 14px; }.error-message { background: #fff0f0; color: #a92b2b; }.success-message { background: #eef8f1; color: #267a48; }.stale-note { background: #fff6e5; color: #875f1f; }.loading-message { padding: 35px 0; text-align: center; color: #80899a; }
.task-progress { background: #f5f7fb; }.task-progress > div:first-child { display: grid; gap: 3px; }.progress-right { min-width: 240px; }.progress-track { height: 6px; margin-top: 5px; background: #e3e7ef; border-radius: 99px; overflow: hidden; }.progress-track i { display: block; height: 100%; background: #525f76; }
.kind-grid { display: grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap: 12px; margin-top: 22px; }.kind-card { padding: 14px; border: 1px solid #e5e8ee; border-radius: 13px; }.kind-card.current { border-color: #cde6d5; }.kind-card.stale { border-color: #ead4ad; }.kind-heading { justify-content: space-between; gap: 12px; }.kind-heading > div { display: grid; gap: 2px; }.kind-heading small { color: #8b94a4; }.kind-heading span { font-size: 11px; font-weight: 800; }.kind-counts { display: grid; grid-template-columns: auto 1fr; gap: 4px 8px; margin: 14px 0 8px; align-items: baseline; }.kind-counts b { font-size: 18px; }.kind-counts span { color: #788294; font-size: 11px; }
.entity-section { margin-top: 30px; }.entity-section-header { padding-bottom: 10px; border-bottom: 1px solid #eceef2; }.entity-section-header span { color: #8a93a2; font-size: 11px; }.entity-section-header h3 { margin: 2px 0 0; }.section-status { display: grid; justify-items: end; gap: 2px; }.section-status small { color: #8a93a2; }
.entity-list { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; margin-top: 12px; }.entity-card { display: grid; grid-template-columns: minmax(0,1fr) 160px; gap: 16px; padding: 14px; border: 1px solid #e7e9ee; border-radius: 12px; }.entity-title { gap: 8px; }.entity-title span { padding: 3px 6px; border-radius: 6px; background: #f0f2f6; font-size: 10px; }.resolution-manual_confirmed { background: #eaf8ef !important; color: #267a48; }.resolution-unknown,.resolution-unresolved { background: #fff3df !important; color: #8a631f; }.entity-main code { display: block; margin-top: 5px; color: #798294; font-size: 10px; overflow-wrap: anywhere; }.link-copy,.member-copy,.notes-copy { margin: 7px 0 0; color: #657083; font-size: 11px; line-height: 1.55; }.entity-facts { margin: 0; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }.entity-facts div { padding: 7px; border-radius: 8px; background: #f8f9fb; }.entity-facts dt { color: #9098a6; font-size: 9px; }.entity-facts dd { margin: 2px 0 0; font-size: 12px; font-weight: 700; }
.empty-state { margin-top: 12px; padding: 20px; border: 1px dashed #dfe3ea; border-radius: 12px; color: #788294; text-align: center; }.main-empty { margin-top: 24px; }.main-empty p { margin-bottom: 0; }
.technical-details,.adjudication-panel { margin-top: 12px; border: 1px solid #e6e9ef; border-radius: 12px; }.technical-details summary,.adjudication-panel summary { padding: 12px 14px; cursor: pointer; }.technical-grid { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 8px; padding: 0 14px 12px; }.technical-grid span { display: grid; gap: 2px; color: #606b7d; font-size: 11px; }.technical-grid b { color: #8a93a2; font-size: 9px; }.technical-details > p { padding: 0 14px 14px; margin: 0; color: #7d8595; font-size: 11px; }
.adjudication-panel { margin-top: 28px; }.adjudication-panel summary { display: flex; justify-content: space-between; gap: 20px; }.adjudication-panel summary div { display: grid; gap: 3px; }.adjudication-panel summary span,.adjudication-panel summary small { color: #80899a; font-size: 11px; }.adjudication-form { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 12px; padding: 4px 14px 16px; }.adjudication-form label { display: grid; gap: 5px; }.adjudication-form label > span { color: #717b8e; font-size: 11px; font-weight: 700; }.adjudication-form input,.adjudication-form select,.adjudication-form textarea { width: 100%; box-sizing: border-box; border: 1px solid #d9dde5; border-radius: 9px; padding: 9px 10px; background: #fff; color: #202735; font: inherit; font-size: 12px; }.adjudication-form textarea { resize: vertical; }.wide { grid-column: 1 / -1; }.form-footer > span { color: #818a9a; font-size: 11px; }
@media (max-width: 1050px) { .kind-grid { grid-template-columns: repeat(2,minmax(0,1fr)); }.entity-list { grid-template-columns: 1fr; } }
@media (max-width: 720px) { .resolution-workspace { padding: 18px; }.workspace-header,.task-progress,.entity-section-header,.adjudication-panel summary { align-items: flex-start; flex-direction: column; }.workspace-actions { width: 100%; }.kind-grid,.adjudication-form { grid-template-columns: 1fr; }.wide { grid-column: auto; }.entity-card { grid-template-columns: 1fr; }.technical-grid { grid-template-columns: 1fr; }.preflight-strip em,.preflight-strip small { margin-left: 0; }.progress-right { width: 100%; min-width: 0; } }
</style>
