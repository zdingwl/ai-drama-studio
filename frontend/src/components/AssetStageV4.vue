<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { ContentAnalysisRun, Episode, F05ModelStatus, Shot } from '../types/studio'
import AssetReviewMatrixV4 from './AssetReviewMatrixV4.vue'

const props = defineProps<{
  projectId: string
  episodes: Episode[]
}>()

type UnresolvedShot = {
  shotId: string
  episodeOrder: number
  shotOrdinal: number
  candidateLabel: string
}

type UnresolvedCandidate = {
  id: string
  label: string
  coverUrl: string | null
  shotCount: number
  trackCount: number
  shots: string[]
}

type CharacterModelStatus = F05ModelStatus & {
  tracking_runtime?: {
    ready?: boolean
    tracker?: string | null
    package?: string
    frame_rate?: number
    error?: string
  }
  final_policy?: string
}

const status = ref<CharacterModelStatus | null>(null)
const loading = ref(true)
const preparing = ref(false)
const error = ref('')
const unresolvedShots = ref<UnresolvedShot[]>([])
const unresolvedCandidates = ref<UnresolvedCandidate[]>([])
const resolvedCount = ref(0)
const unresolvedEvidenceCount = ref(0)
const analysisProfile = ref('')

const missingModels = computed(() => (status.value?.models ?? []).filter((item) => !item.ready))
const unresolvedPreview = computed(() => unresolvedShots.value.slice(0, 12))
const runtimeLabel = computed(() => {
  const runtime = status.value?.runtime
  if (!runtime) return '运行时未知'
  if (runtime.device === 'GPU') return `GPU · CUDA · ${runtime.provider || 'CUDAExecutionProvider'}`
  return `CPU fallback · ${runtime.provider || 'CPUExecutionProvider'}`
})
const trackingLabel = computed(() => {
  const tracking = status.value?.tracking_runtime
  if (!tracking) return 'MOT 未知'
  if (!tracking.ready) return 'MOT 未准备'
  return `${tracking.tracker || 'Mature MOT'} · ${tracking.frame_rate || 12}fps`
})

async function refreshModelStatus(): Promise<void> {
  try {
    status.value = await api.getF05ModelStatus() as CharacterModelStatus
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物模型状态读取失败'
  } finally {
    loading.value = false
  }
}

/**
 * V9D UI contract:
 * - Final Character count comes from resolved_character_candidates;
 * - UNRESOLVED is an explicit Evidence class and is shown separately;
 * - face_visible is NOT an identity/final gate anymore.
 */
async function refreshPersonCompleteness(): Promise<void> {
  try {
    const analysis: ContentAnalysisRun | null = await api.getCurrentContentAnalysis(props.projectId)
    if (!analysis) {
      unresolvedShots.value = []
      unresolvedCandidates.value = []
      resolvedCount.value = 0
      unresolvedEvidenceCount.value = 0
      analysisProfile.value = ''
      return
    }
    analysisProfile.value = analysis.profile_version || ''
    resolvedCount.value = Number(analysis.counts?.resolved_character_candidates || 0)
    unresolvedEvidenceCount.value = Number(analysis.counts?.unresolved_character_candidates || 0)

    const groups = await Promise.all(props.episodes.map((episode) => api.listShots(episode.id)))
    const shotMeta = new Map<string, { episodeOrder: number; shotOrdinal: number }>()
    props.episodes.forEach((episode, episodeIndex) => {
      const episodeShots: Shot[] = groups[episodeIndex] ?? []
      for (const shot of episodeShots) {
        shotMeta.set(shot.id, { episodeOrder: episode.sort_order, shotOrdinal: shot.ordinal })
      }
    })

    const seenShots = new Set<string>()
    const shotResult: UnresolvedShot[] = []
    const candidateResult: UnresolvedCandidate[] = []

    for (const candidate of analysis.characters) {
      // V9 persistence explicitly labels unresolved Evidence. Do not infer identity from Face visibility.
      if (!candidate.auto_label.startsWith('待解析人物')) continue

      const shotLabels: string[] = []
      const candidateShotIds = new Set<string>()
      for (const track of candidate.tracks) {
        candidateShotIds.add(track.shot_id)
        const meta = shotMeta.get(track.shot_id)
        if (!meta) continue
        shotLabels.push(`E${String(meta.episodeOrder).padStart(2, '0')} · SHOT ${String(meta.shotOrdinal).padStart(4, '0')}`)

        if (seenShots.has(track.shot_id)) continue
        seenShots.add(track.shot_id)
        shotResult.push({
          shotId: track.shot_id,
          episodeOrder: meta.episodeOrder,
          shotOrdinal: meta.shotOrdinal,
          candidateLabel: candidate.auto_label,
        })
      }

      candidateResult.push({
        id: candidate.id,
        label: candidate.auto_label,
        coverUrl: candidate.cover_url,
        shotCount: candidateShotIds.size || candidate.shot_count,
        trackCount: candidate.track_count,
        shots: [...new Set(shotLabels)].slice(0, 6),
      })
    }

    unresolvedCandidates.value = candidateResult
    unresolvedShots.value = shotResult.sort((left, right) => (
      left.episodeOrder - right.episodeOrder || left.shotOrdinal - right.shotOrdinal
    ))
  } catch {
    unresolvedShots.value = []
    unresolvedCandidates.value = []
  }
}

async function prepareModels(): Promise<void> {
  preparing.value = true
  error.value = ''
  try {
    status.value = await api.prepareF05Models() as CharacterModelStatus
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物 V9 模型准备失败'
  } finally {
    preparing.value = false
  }
}

onMounted(async () => {
  await Promise.all([refreshModelStatus(), refreshPersonCompleteness()])
})
</script>

<template>
  <div class="asset-stage-v4">
    <div v-if="!loading && status && !status.ready" class="character-v4-banner warning">
      <div>
        <strong>人物识别 V9 运行时未准备完整</strong>
        <span>V9 需要 YOLOX / YuNet-SFace / YoutuReID + Mature MOT。未准备完整时不要重新提取资产，旧 Current 会继续保留。</span>
        <small v-if="missingModels.length">缺少模型：{{ missingModels.map((item) => item.filename).join('、') }}</small>
        <small v-if="status.tracking_runtime && !status.tracking_runtime.ready">MOT：{{ status.tracking_runtime.error || 'trackers/supervision 未准备' }}</small>
      </div>
      <button :disabled="preparing" @click="prepareModels">{{ preparing ? '正在准备模型…' : '准备人物 V9 模型' }}</button>
    </div>

    <div v-else-if="!loading && status?.ready" class="character-v4-banner ready">
      <div>
        <strong>人物识别 V9D · READY · {{ runtimeLabel }} · {{ trackingLabel }}</strong>
        <span>多人先拆 Person Instance → CLEAN 人物图多通道特征 → Person Gallery Confirm-then-Absorb → Confirmed Gallery 才发布 Final Character。</span>
        <small>ReID / 上下身服装 / Body / Face(可选) 分通道判断；整帧、单张脸、单条 Track 都不能直接创建人物。</small>
        <small v-if="analysisProfile">当前 Asset Run：{{ analysisProfile }}</small>
        <small v-if="status.runtime?.fallback">⚠ CUDA 未实际启用，当前已自动降级 CPU；结果逻辑不变，但分析会明显变慢。</small>
      </div>
    </div>

    <div v-if="resolvedCount || unresolvedEvidenceCount" class="character-v4-banner identity-summary">
      <div>
        <strong>Person Gallery：{{ resolvedCount }} 个 Final Character · {{ unresolvedEvidenceCount }} 个待解析 Evidence</strong>
        <span>Final 数量只来自 Confirmed Person Gallery；无脸但 Gallery 稳定的人物可以发布，UNRESOLVED 永远不计入人物数量。</span>
      </div>
    </div>

    <section v-if="unresolvedCandidates.length" class="unresolved-evidence-panel">
      <div class="unresolved-evidence-head">
        <div>
          <strong>待解析人物 Evidence</strong>
          <span>{{ unresolvedCandidates.length }} 个身份尚未确认，只保留证据，不会生成额外人物卡片。</span>
        </div>
        <em>{{ unresolvedShots.length }} Shots</em>
      </div>
      <div class="unresolved-candidate-grid">
        <article v-for="item in unresolvedCandidates" :key="item.id" class="unresolved-candidate-card">
          <div class="unresolved-cover">
            <img v-if="item.coverUrl" :src="item.coverUrl" :alt="item.label" />
            <span v-else>UNRESOLVED</span>
          </div>
          <div class="unresolved-card-body">
            <strong>{{ item.label }}</strong>
            <small>{{ item.shotCount }} Shots · {{ item.trackCount }} Tracks</small>
            <div class="unresolved-card-shots">
              <span v-for="shot in item.shots" :key="shot">{{ shot }}</span>
            </div>
          </div>
        </article>
      </div>
    </section>

    <div v-if="unresolvedShots.length" class="character-v4-banner unresolved">
      <div>
        <strong>⚠ {{ unresolvedShots.length }} 个 Shot 含待解析人物 Evidence</strong>
        <span>这些人物实例继续保留用于后续 Gallery 吸收或人工确认，但不会自动制造新的 Final Character。</span>
        <div class="unresolved-shot-list">
          <span v-for="item in unresolvedPreview" :key="item.shotId">
            E{{ String(item.episodeOrder).padStart(2, '0') }} · SHOT {{ String(item.shotOrdinal).padStart(4, '0') }}
          </span>
          <em v-if="unresolvedShots.length > unresolvedPreview.length">+{{ unresolvedShots.length - unresolvedPreview.length }}</em>
        </div>
      </div>
    </div>

    <div v-if="error" class="character-v4-error">{{ error }}</div>
    <AssetReviewMatrixV4 :project-id="props.projectId" :episodes="props.episodes" />
  </div>
</template>

<style scoped>
.asset-stage-v4{min-height:100%}.character-v4-banner{margin:14px 22px 0;padding:10px 13px;border:1px solid;border-radius:11px;display:flex;align-items:center;justify-content:space-between;gap:16px;font-size:12px}.character-v4-banner>div{min-width:0;display:grid;gap:2px}.character-v4-banner strong{font-size:13px}.character-v4-banner span,.character-v4-banner small{line-height:1.45}.character-v4-banner.warning{background:#fff9eb;border-color:#f1d58d;color:#73510b}.character-v4-banner.warning span,.character-v4-banner.warning small{color:#8b6a25}.character-v4-banner.ready{background:#effbf5;border-color:#bfe7d2;color:#176a45}.character-v4-banner.ready span{color:#49806a}.character-v4-banner.ready small{color:#557c6b}.character-v4-banner.identity-summary{background:#f1f6ff;border-color:#c7d7f7;color:#2754a5}.character-v4-banner.identity-summary span{color:#5873a5}.character-v4-banner.unresolved{background:#fff8ee;border-color:#efc982;color:#7b4d08}.character-v4-banner.unresolved span{color:#835f28}.character-v4-banner button{flex:0 0 auto;border:0;border-radius:8px;padding:8px 12px;background:#2f60e8;color:#fff;font-weight:750;cursor:pointer}.character-v4-banner button:disabled{opacity:.6;cursor:wait}.character-v4-error{margin:8px 22px 0;padding:8px 11px;border-radius:8px;background:#fff0f0;color:#b53a3a;font-size:12px}.unresolved-shot-list{display:flex;flex-wrap:wrap;gap:5px;margin-top:5px}.unresolved-shot-list span,.unresolved-shot-list em{padding:3px 7px;border-radius:999px;background:#fff;border:1px solid #efd7a9;font-style:normal;font-size:10px;font-weight:700;color:#815a18}.unresolved-evidence-panel{margin:14px 22px 0;border:1px solid #efcf98;border-radius:12px;background:#fffaf2;padding:12px}.unresolved-evidence-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.unresolved-evidence-head>div{display:grid;gap:2px}.unresolved-evidence-head strong{font-size:13px;color:#734c10}.unresolved-evidence-head span{font-size:11px;color:#8a6a39}.unresolved-evidence-head em{font-size:10px;font-style:normal;font-weight:800;color:#8b5c16;background:#fff;border:1px solid #efd6aa;border-radius:999px;padding:4px 8px}.unresolved-candidate-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:10px}.unresolved-candidate-card{display:grid;grid-template-columns:72px minmax(0,1fr);gap:9px;border:1px solid #ead8b8;border-radius:10px;background:#fff;padding:7px}.unresolved-cover{width:72px;height:72px;border-radius:8px;overflow:hidden;background:#f4eee4;display:flex;align-items:center;justify-content:center}.unresolved-cover img{width:100%;height:100%;object-fit:cover}.unresolved-cover span{font-size:8px;font-weight:800;color:#9b825c}.unresolved-card-body{min-width:0;display:grid;align-content:start;gap:3px}.unresolved-card-body strong{font-size:12px;color:#61410d}.unresolved-card-body small{font-size:10px;color:#99784a}.unresolved-card-shots{display:flex;flex-wrap:wrap;gap:3px;margin-top:2px}.unresolved-card-shots span{font-size:8px;color:#775b33;background:#faf5ec;border-radius:5px;padding:2px 4px}
</style>