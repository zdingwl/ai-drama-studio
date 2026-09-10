<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getProject } from '@/features/projects/api'
import {
  finalizeSourceVideoSnapshot,
  getSourceVideoSnapshot,
  listSourceVideoSnapshotRevisions,
  type FrozenArtifactRef,
  type SourceVideoSnapshotRead,
  type SourceVideoSnapshotRevisionSummary,
} from '@/features/projects/sourceSnapshot'
import type { ProjectRead } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const result = ref<SourceVideoSnapshotRead | null>(null)
const revisions = ref<SourceVideoSnapshotRevisionSummary[]>([])
const loading = ref(true)
const finalizing = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const visible = computed(() => project.value?.project_type === 'REPLICA' || project.value?.project_type === 'REDRAW')
const status = computed(() => result.value?.status ?? 'NOT_BUILT')
const content = computed(() => result.value?.content ?? null)
const provenance = computed(() => result.value?.provenance ?? null)
const canFinalize = computed(() => !loading.value && !finalizing.value)

const artifactLabels: Record<string, string> = {
  SOURCE_VIDEO: '完整 Episode / Source Truth',
  SHOT_ANCHORS: 'P5 Shot Anchors',
  SOURCE_DIALOGUE: 'P6 Canonical Dialogue / OCR',
  SOURCE_BIBLE: 'P7 Source Bible',
  STORY_SKELETON: 'P7 Story Skeleton',
  RHYTHM_SKELETON: 'P7 Rhythm Skeleton',
  SOURCE_SHOT_FACTS: 'P8 Source Shot Facts',
  SOURCE_CHARACTERS: 'P9 Characters',
  SOURCE_SPEAKERS: 'P9 Speakers',
  SOURCE_SCENES: 'P9 Scenes',
  SOURCE_PROPS: 'P9 Props',
}

const totals = computed(() => {
  const value = content.value
  if (!value) return { episodes: 0, shots: 0, dialogue: 0, ocr: 0, characters: 0, speakers: 0, scenes: 0, props: 0 }
  return {
    episodes: value.episodes.length,
    shots: value.episodes.reduce((sum, episode) => sum + episode.shot_anchors.length, 0),
    dialogue: value.episodes.reduce((sum, episode) => sum + episode.canonical_dialogue.length, 0),
    ocr: value.episodes.reduce((sum, episode) => sum + episode.canonical_visual_text.length, 0),
    characters: value.source_characters.entities.length,
    speakers: value.source_speakers.entities.length,
    scenes: value.source_scenes.entities.length,
    props: value.source_props.entities.length,
  }
})

function shortFingerprint(value: string | null | undefined): string {
  if (!value) return '—'
  return value.length > 18 ? `${value.slice(0, 9)}…${value.slice(-7)}` : value
}

function artifactLabel(item: FrozenArtifactRef): string {
  return artifactLabels[item.artifact_type] ?? item.artifact_type
}

async function refresh(): Promise<void> {
  errorMessage.value = ''
  const [current, history] = await Promise.all([
    getSourceVideoSnapshot(projectId.value),
    listSourceVideoSnapshotRevisions(projectId.value),
  ])
  result.value = current
  revisions.value = history
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    project.value = await getProject(projectId.value)
    if (visible.value) await refresh()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P10 原片分析定稿加载失败'
  } finally {
    loading.value = false
  }
}

async function finalize(): Promise<void> {
  if (!canFinalize.value) return
  finalizing.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const beforeRevision = result.value?.revision ?? null
    result.value = await finalizeSourceVideoSnapshot(projectId.value)
    revisions.value = await listSourceVideoSnapshotRevisions(projectId.value)
    successMessage.value = result.value.revision === beforeRevision
      ? `当前 Source 链未变化，继续使用 SOURCE_VIDEO_SNAPSHOT rev ${result.value.revision}。`
      : `原片分析已显式定稿为 SOURCE_VIDEO_SNAPSHOT rev ${result.value.revision}；没有重新调用模型。`
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P10 原片分析定稿失败'
  } finally {
    finalizing.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-if="visible" class="snapshot-workspace" data-testid="p10-source-video-snapshot">
    <header class="workspace-header">
      <div>
        <p class="section-kicker">原片理解 · P10 定稿</p>
        <div class="title-line">
          <h2>SourceVideoSnapshot / 原片分析定稿</h2>
          <span class="status-pill" :class="status.toLowerCase()">{{ status }}</span>
        </div>
        <p class="workspace-subtitle">冻结已经验收的 P5–P9 Source Facts，形成下游唯一正式 Source 边界；P10 不重新理解原片。</p>
      </div>
      <div class="workspace-actions">
        <button class="primary-action" type="button" :disabled="!canFinalize" @click="finalize">
          {{ finalizing ? '正在定稿…' : status === 'CURRENT' ? '重新检查并定稿' : '原片分析定稿' }}
        </button>
        <button class="ghost-action" type="button" :disabled="finalizing" @click="refresh">刷新</button>
      </div>
    </header>

    <div class="truth-strip">
      <b>永久 Source Truth</b><span>完整 Episode</span><i>→</i><span>P5 时间只读</span><i>→</i><span>P6 canonical / OCR 只读</span><i>→</i><span>P7/P8/P9 typed facts 冻结</span>
    </div>

    <div class="freeze-strip" data-testid="p10-provider-boundary">
      <b>DETERMINISTIC_FREEZE</b>
      <span>ProviderJobs：{{ provenance?.provider_jobs.length ?? 0 }}</span>
      <em>GET 只读 · POST 显式定稿</em>
    </div>

    <p v-if="status === 'STALE'" class="message stale-message">上游 CURRENT Source Artifact 已变化。这里保留旧 revision 供追溯，但不能作为新的正式 Source；请显式重新定稿。</p>
    <p v-if="errorMessage" class="message error-message">{{ errorMessage }}</p>
    <p v-if="successMessage" class="message success-message">{{ successMessage }}</p>
    <p v-if="loading" class="loading-message">正在读取 P10 Snapshot…</p>

    <template v-else-if="content">
      <div class="summary-grid">
        <article><b>{{ totals.episodes }}</b><span>Episodes</span></article>
        <article><b>{{ totals.shots }}</b><span>P5 Shots</span></article>
        <article><b>{{ totals.dialogue }}</b><span>P6 Dialogue</span></article>
        <article><b>{{ totals.ocr }}</b><span>P6 OCR</span></article>
        <article><b>{{ totals.characters }}</b><span>Characters</span></article>
        <article class="speaker-card"><b>{{ totals.speakers }}</b><span>Speakers · 独立冻结</span></article>
        <article><b>{{ totals.scenes }}</b><span>Scenes</span></article>
        <article><b>{{ totals.props }}</b><span>Props</span></article>
      </div>

      <section class="artifact-section">
        <header>
          <div><span>Frozen Inputs</span><h3>冻结的 CURRENT Source Artifact</h3></div>
          <small>rev {{ result?.revision }} · {{ shortFingerprint(result?.input_fingerprint) }}</small>
        </header>
        <div class="artifact-list">
          <article v-for="item in content.frozen_artifacts" :key="item.artifact_type" :class="{ speaker: item.artifact_type === 'SOURCE_SPEAKERS' }">
            <div><strong>{{ artifactLabel(item) }}</strong><code>{{ item.artifact_type }}</code></div>
            <span>rev {{ item.revision }}</span>
            <code>{{ shortFingerprint(item.input_fingerprint) }}</code>
          </article>
        </div>
      </section>

      <section class="episode-section">
        <header><div><span>Episode Truth</span><h3>P5 / P6 原值冻结</h3></div><small>不改 Shot 时间，不改 canonical 文本</small></header>
        <div class="episode-list">
          <article v-for="episode in content.episodes" :key="episode.episode_id">
            <div><strong>第 {{ episode.episode_order }} 集 · {{ episode.source_filename }}</strong><code>{{ shortFingerprint(episode.source_asset_sha256) }}</code></div>
            <dl>
              <div><dt>Shot</dt><dd>{{ episode.shot_anchors.length }}</dd></div>
              <div><dt>Dialogue</dt><dd>{{ episode.canonical_dialogue.length }}</dd></div>
              <div><dt>OCR</dt><dd>{{ episode.canonical_visual_text.length }}</dd></div>
              <div><dt>Evidence</dt><dd>{{ shortFingerprint(episode.source_evidence_fingerprint) }}</dd></div>
            </dl>
          </article>
        </div>
      </section>

      <details class="technical-details">
        <summary><strong>Provenance / Artifact Graph 验收信息</strong><small>{{ provenance?.snapshot_contract }}</small></summary>
        <div class="technical-grid">
          <span><b>Schema</b>{{ content.schema_version }}</span>
          <span><b>Source Truth Contract</b>{{ content.source_truth_contract }}</span>
          <span><b>Skill</b>{{ provenance?.professional_skill_id }}@{{ provenance?.professional_skill_version }}</span>
          <span><b>Publication</b>{{ provenance?.publication_mode }}</span>
          <span><b>Source Chain FP</b>{{ shortFingerprint(provenance?.source_chain_fingerprint) }}</span>
          <span><b>ProviderJobs</b>{{ provenance?.provider_jobs.length ?? 0 }}</span>
        </div>
      </details>

      <details class="technical-details revision-details">
        <summary><strong>Snapshot 历史 revision</strong><small>{{ revisions.length }} 条</small></summary>
        <div class="revision-list">
          <article v-for="item in revisions" :key="item.artifact_id">
            <b>rev {{ item.revision }}</b><span :class="item.status.toLowerCase()">{{ item.status }}</span><code>{{ shortFingerprint(item.input_fingerprint) }}</code><small>{{ item.created_at }}</small>
          </article>
        </div>
      </details>
    </template>

    <div v-else-if="!loading" class="empty-state">
      <strong>还没有 SOURCE_VIDEO_SNAPSHOT</strong>
      <p>只有在 P5、P6、P7、P8、P9 Character / Speaker / Scene / Prop 全部存在 CURRENT 正式结果时，显式点击“原片分析定稿”才会发布 Snapshot。</p>
      <small>页面打开和刷新不会自动创建 Artifact、Task 或 ProviderJob。</small>
    </div>
  </section>
</template>

<style scoped>
.snapshot-workspace { margin-top: 24px; padding: 28px; border: 1px solid #e7e9ee; border-radius: 18px; background: #fff; color: #172033; }
.workspace-header,.title-line,.workspace-actions,.truth-strip,.freeze-strip,.artifact-section header,.episode-section header,.technical-details summary { display:flex; align-items:center; }
.workspace-header,.artifact-section header,.episode-section header,.technical-details summary { justify-content:space-between; gap:20px; }
.section-kicker { margin:0 0 5px; color:#7b8495; font-size:12px; font-weight:700; }.title-line{gap:10px}.title-line h2{margin:0;font-size:27px}.workspace-subtitle{margin:7px 0 0;color:#6d7688;font-size:13px;line-height:1.55}
.workspace-actions{gap:8px}.primary-action,.ghost-action{border-radius:10px;padding:10px 15px;font:inherit;font-weight:700;cursor:pointer}.primary-action{border:0;background:#202632;color:#fff}.ghost-action{border:1px solid #d9dde5;background:#fff;color:#333b49}button:disabled{opacity:.45;cursor:not-allowed}
.status-pill{padding:5px 9px;border-radius:999px;background:#f0f2f6;color:#646d7f;font-size:11px;font-weight:800}.status-pill.current{background:#eaf8ef;color:#267a48}.status-pill.stale{background:#fff1dc;color:#9a6414}
.truth-strip,.freeze-strip{margin-top:16px;gap:9px;flex-wrap:wrap;padding:9px 12px;border-radius:10px;background:#f7f8fa;color:#657083;font-size:12px}.truth-strip b,.freeze-strip b{color:#343d4d}.truth-strip i{color:#adb3bd;font-style:normal}.freeze-strip em{margin-left:auto;color:#267a48;font-style:normal;font-weight:700}
.message{margin-top:14px;padding:12px 14px;border-radius:12px}.error-message{background:#fff0f0;color:#a92b2b}.success-message{background:#eef8f1;color:#267a48}.stale-message{background:#fff6e5;color:#875f1f}.loading-message{padding:35px 0;text-align:center;color:#80899a}
.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:22px}.summary-grid article{display:grid;gap:3px;padding:14px;border:1px solid #e5e8ee;border-radius:12px}.summary-grid b{font-size:22px}.summary-grid span{color:#778193;font-size:11px}.summary-grid .speaker-card{border-color:#cbd8f0;background:#f7f9fd}
.artifact-section,.episode-section{margin-top:28px}.artifact-section header span,.episode-section header span{color:#8a93a2;font-size:11px}.artifact-section h3,.episode-section h3{margin:2px 0 0}.artifact-section header small,.episode-section header small{color:#7b8495}
.artifact-list{display:grid;gap:7px;margin-top:12px}.artifact-list article{display:grid;grid-template-columns:minmax(0,1fr) auto auto;gap:14px;align-items:center;padding:11px 12px;border:1px solid #eceef2;border-radius:10px}.artifact-list article.speaker{border-color:#cbd8f0;background:#f7f9fd}.artifact-list article>div{display:grid;gap:2px}.artifact-list code,.episode-list code,.revision-list code{color:#7f899a;font-size:10px}.artifact-list span{font-size:12px;font-weight:700}
.episode-list{display:grid;gap:9px;margin-top:12px}.episode-list article{display:flex;justify-content:space-between;gap:20px;padding:13px;border:1px solid #eceef2;border-radius:11px}.episode-list article>div{display:grid;gap:3px}.episode-list dl{display:flex;gap:18px;margin:0}.episode-list dl div{display:grid;gap:2px;text-align:right}.episode-list dt{color:#8a93a2;font-size:10px}.episode-list dd{margin:0;font-size:12px;font-weight:700}
.technical-details{margin-top:18px;border:1px solid #eceef2;border-radius:12px;overflow:hidden}.technical-details summary{padding:12px 14px;cursor:pointer}.technical-details summary small{color:#858e9e}.technical-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;padding:14px;border-top:1px solid #eceef2}.technical-grid span{display:grid;gap:3px;color:#667084;font-size:11px}.technical-grid b{color:#323b4b;font-size:10px;text-transform:uppercase}
.revision-list{display:grid;gap:7px;padding:14px;border-top:1px solid #eceef2}.revision-list article{display:grid;grid-template-columns:auto auto minmax(0,1fr) auto;gap:10px;align-items:center}.revision-list span{font-size:10px;font-weight:800}.revision-list .current{color:#267a48}.revision-list .stale{color:#9a6414}.revision-list small{color:#8a93a2}
.empty-state{margin-top:22px;padding:18px;border:1px dashed #d7dce5;border-radius:12px;background:#fafbfc}.empty-state p{margin:7px 0;color:#667084;font-size:13px;line-height:1.55}.empty-state small{color:#8b94a4}
@media (max-width:900px){.workspace-header{align-items:flex-start;flex-direction:column}.summary-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.artifact-list article{grid-template-columns:1fr}.episode-list article{flex-direction:column}.episode-list dl{justify-content:flex-start}.technical-grid{grid-template-columns:1fr}.freeze-strip em{margin-left:0}.revision-list article{grid-template-columns:auto auto 1fr}.revision-list small{grid-column:1/-1}}
</style>
