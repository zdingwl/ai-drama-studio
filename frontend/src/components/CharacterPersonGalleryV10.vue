<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type { AssetWorkspace, BackgroundTask, CharacterGalleryImage } from '../types/studio'

const props = defineProps<{ projectId: string }>()

type GalleryImageView = CharacterGalleryImage & { candidateId: string }

type ShotGalleryGroup = {
  key: string
  shotId: string | null
  shotOrdinal: number | null
  episodeOrder: number | null
  images: GalleryImageView[]
}

type CharacterGallery = {
  assetId: string
  name: string
  candidateIds: string[]
  evidenceShotCount: number
  galleryImageCount: number
  visualEvidenceCount: number
  shotGroups: ShotGalleryGroup[]
}

const galleries = ref<CharacterGallery[]>([])
const loading = ref(false)
const error = ref('')

function groupByShot(images: GalleryImageView[]): ShotGalleryGroup[] {
  const groups = new Map<string, ShotGalleryGroup>()
  for (const image of images) {
    const key = image.shot_id || `unknown:${image.candidateId}:${image.index}`
    const group = groups.get(key) ?? {
      key,
      shotId: image.shot_id,
      shotOrdinal: image.shot_ordinal,
      episodeOrder: image.episode_order,
      images: [],
    }
    group.images.push(image)
    if (group.shotOrdinal === null && image.shot_ordinal !== null) group.shotOrdinal = image.shot_ordinal
    if (group.episodeOrder === null && image.episode_order !== null) group.episodeOrder = image.episode_order
    groups.set(key, group)
  }

  return [...groups.values()]
    .map((group) => ({
      ...group,
      images: [...group.images].sort((left, right) => (left.source_time_us ?? 0) - (right.source_time_us ?? 0)),
    }))
    .sort((left, right) => {
      const episode = (left.episodeOrder ?? 999999) - (right.episodeOrder ?? 999999)
      if (episode) return episode
      return (left.shotOrdinal ?? 999999) - (right.shotOrdinal ?? 999999)
    })
}

async function refresh(): Promise<void> {
  if (!props.projectId || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const workspace: AssetWorkspace = await api.getAssetWorkspace(props.projectId)
    const result: CharacterGallery[] = []
    let failedCandidates = 0

    for (const character of workspace.characters) {
      const candidateIds = [...new Set(character.source_candidate_ids ?? [])]
      const settled = await Promise.allSettled(candidateIds.map((candidateId) => api.getCharacterGallery(candidateId)))
      const images: GalleryImageView[] = []
      const evidenceShotIds = new Set<string>()
      let galleryImageCount = 0

      settled.forEach((item, index) => {
        if (item.status === 'rejected') {
          failedCandidates += 1
          return
        }
        const candidateId = candidateIds[index]
        item.value.evidence_shots.forEach((shot) => evidenceShotIds.add(shot.shot_id))
        galleryImageCount += item.value.gallery_image_count ?? item.value.images.filter((image) => image.source_kind !== 'track_representative').length
        images.push(...item.value.images.map((image) => ({ ...image, candidateId })))
      })
      result.push({
        assetId: character.id,
        name: character.name,
        candidateIds,
        evidenceShotCount: evidenceShotIds.size,
        galleryImageCount,
        visualEvidenceCount: images.length,
        shotGroups: groupByShot(images),
      })
    }
    galleries.value = result
    if (failedCandidates) error.value = `${failedCandidates} 个历史人物 Candidate 的 Evidence 无法读取；其余内容已正常展示。`
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物 Evidence 读取失败'
    galleries.value = []
  } finally {
    loading.value = false
  }
}

function shotLabel(group: ShotGalleryGroup): string {
  const shot = typeof group.shotOrdinal === 'number'
    ? `SHOT ${String(group.shotOrdinal).padStart(4, '0')}`
    : group.shotId || '未知 Shot'
  return typeof group.episodeOrder === 'number' && group.episodeOrder > 1
    ? `E${String(group.episodeOrder).padStart(2, '0')} · ${shot}`
    : shot
}

function classLabel(image: GalleryImageView): string {
  if (image.source_kind === 'track_representative') return 'Track 代表图'
  const value = image.instance_class
  return ({
    CLEAN: '清晰',
    OCCLUDED: '遮挡',
    CONTAMINATED: '同框干扰',
    PARTIAL: '局部',
  } as Record<string, string>)[value || ''] || value || 'Gallery 人物图'
}

function onTaskFinished(event: Event): void {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.project_id !== props.projectId || task.task_type !== 'ASSET_EXTRACTION_V3') return
  void refresh()
}

watch(() => props.projectId, () => void refresh())
onMounted(() => {
  window.addEventListener('studio-task-finished', onTaskFinished)
  void refresh()
})
onUnmounted(() => window.removeEventListener('studio-task-finished', onTaskFinished))
</script>

<template>
  <section v-if="loading || error || galleries.length" class="person-gallery-v10">
    <header>
      <div>
        <strong>人物图 Gallery · AI Evidence</strong>
        <span>按真实 Shot 展示人物 Evidence。Gallery 是身份代表子集；未入选 Gallery 的 Evidence Shot 会补一张持久化 Track 代表 crop，便于和 Final Binding 完整对照。</span>
      </div>
      <small v-if="loading">读取中…</small>
    </header>

    <p v-if="error" class="gallery-error">{{ error }}</p>
    <div v-for="gallery in galleries" :key="gallery.assetId" class="person-gallery-group">
      <div class="person-gallery-title">
        <strong>{{ gallery.name }}</strong>
        <span>{{ gallery.evidenceShotCount }} Evidence Shots · {{ gallery.galleryImageCount }} Gallery 代表图 · {{ gallery.visualEvidenceCount }} 张可视证据图</span>
      </div>

      <div v-if="gallery.shotGroups.length" class="person-gallery-shot-list">
        <section v-for="group in gallery.shotGroups" :key="group.key" class="person-gallery-shot-group">
          <div class="person-gallery-shot-head">
            <b>{{ shotLabel(group) }}</b>
            <span>{{ group.images.length }} 张 crop</span>
          </div>
          <div class="person-gallery-grid">
            <figure v-for="image in group.images" :key="`${image.candidateId}-${image.source_kind}-${image.index}-${image.url}`">
              <img :src="image.url" :alt="`${gallery.name} ${shotLabel(group)}`" loading="lazy" />
              <figcaption>
                <b>{{ classLabel(image) }}</b>
                <span v-if="image.source_time_us !== null">{{ (image.source_time_us / 1_000_000).toFixed(2) }}s</span>
              </figcaption>
            </figure>
          </div>
        </section>
      </div>
      <p v-else class="gallery-empty">当前人物没有可展示的 V10 Person Evidence。</p>
    </div>
  </section>
</template>

<style scoped>
.person-gallery-v10{margin:14px 22px 0;padding:12px;border:1px solid #d7e0ef;border-radius:12px;background:#fff}.person-gallery-v10>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.person-gallery-v10>header>div{display:grid;gap:2px}.person-gallery-v10>header strong{font-size:14px;color:#253a60}.person-gallery-v10>header span,.person-gallery-v10>header small{font-size:11px;color:#667892}.person-gallery-group{margin-top:12px;padding-top:10px;border-top:1px solid #edf0f5}.person-gallery-title{display:flex;align-items:center;gap:9px;margin-bottom:8px}.person-gallery-title strong{font-size:13px}.person-gallery-title span{font-size:10px;color:#708099}.person-gallery-shot-list{display:grid;gap:10px}.person-gallery-shot-group{padding:8px;border:1px solid #e4e9f1;border-radius:9px;background:#fafbfe}.person-gallery-shot-head{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:7px}.person-gallery-shot-head b{font-size:10px;color:#30415d}.person-gallery-shot-head span{font-size:9px;color:#7d899b}.person-gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,118px));gap:7px}.person-gallery-grid figure{margin:0;border:1px solid #e1e6ee;border-radius:8px;overflow:hidden;background:#fff}.person-gallery-grid img{display:block;width:100%;height:124px;object-fit:cover;background:#eef1f5}.person-gallery-grid figcaption{display:flex;align-items:center;justify-content:space-between;gap:4px;padding:5px 6px}.person-gallery-grid figcaption b{font-size:9px;color:#27384f}.person-gallery-grid figcaption span{font-size:9px;color:#7a8797}.gallery-error{color:#9b6200;background:#fff8e8;border:1px solid #f0d8a3;border-radius:7px;padding:7px 9px;font-size:11px}.gallery-empty{font-size:11px;color:#8a94a3}
</style>