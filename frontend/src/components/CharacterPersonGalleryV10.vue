<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { api } from '../api/client'
import type { AssetWorkspace, BackgroundTask } from '../types/studio'

const props = defineProps<{ projectId: string }>()

type GalleryImage = {
  index: number
  url: string
  shot_id: string | null
  source_time_us: number | null
  instance_id: string | null
  instance_class: string | null
  quality: number | null
  reliability: number | null
  seed_eligible: boolean | null
  face_visible: boolean | null
  feature_channels: string[]
}

type CharacterGallery = {
  assetId: string
  name: string
  candidateId: string
  images: GalleryImage[]
}

const galleries = ref<CharacterGallery[]>([])
const loading = ref(false)
const error = ref('')

async function getGallery(candidateId: string): Promise<GalleryImage[]> {
  const response = await fetch(`/api/content-analysis/characters/${candidateId}/gallery`)
  if (response.status === 404) return []
  if (!response.ok) throw new Error(`人物 Gallery 读取失败（${response.status}）`)
  const payload = await response.json() as { images?: GalleryImage[] }
  return Array.isArray(payload.images) ? payload.images : []
}

async function refresh(): Promise<void> {
  if (!props.projectId || loading.value) return
  loading.value = true
  error.value = ''
  try {
    const workspace: AssetWorkspace = await api.getAssetWorkspace(props.projectId)
    const result: CharacterGallery[] = []
    for (const character of workspace.characters) {
      const candidateId = character.source_candidate_ids?.[0]
      if (!candidateId) continue
      const images = await getGallery(candidateId)
      result.push({
        assetId: character.id,
        name: character.name,
        candidateId,
        images,
      })
    }
    galleries.value = result
  } catch (err) {
    error.value = err instanceof Error ? err.message : '人物 Gallery 读取失败'
    galleries.value = []
  } finally {
    loading.value = false
  }
}

function shotLabel(shotId: string | null): string {
  if (!shotId) return '未知 Shot'
  const match = shotId.match(/(\d+)$/)
  return match ? `SHOT ${String(Number(match[1])).padStart(4, '0')}` : shotId
}

function classLabel(value: string | null): string {
  return ({
    CLEAN: '清晰',
    OCCLUDED: '遮挡',
    CONTAMINATED: '同框干扰',
    PARTIAL: '局部',
  } as Record<string, string>)[value || ''] || value || '人物图'
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
        <strong>人物图 Gallery</strong>
        <span>这里展示模型实际分类到每个人物的单人 crop；不是 Shot 整帧。</span>
      </div>
      <small v-if="loading">读取中…</small>
    </header>

    <p v-if="error" class="gallery-error">{{ error }}</p>
    <div v-for="gallery in galleries" :key="gallery.assetId" class="person-gallery-group">
      <div class="person-gallery-title">
        <strong>{{ gallery.name }}</strong>
        <span>{{ gallery.images.length }} 张已分类人物图</span>
      </div>
      <div v-if="gallery.images.length" class="person-gallery-grid">
        <figure v-for="image in gallery.images" :key="`${gallery.candidateId}-${image.index}`">
          <img :src="image.url" :alt="`${gallery.name} ${shotLabel(image.shot_id)}`" loading="lazy" />
          <figcaption>
            <b>{{ shotLabel(image.shot_id) }}</b>
            <span>{{ classLabel(image.instance_class) }}</span>
          </figcaption>
        </figure>
      </div>
      <p v-else class="gallery-empty">当前人物没有可展示的 V10 单人物图 Gallery。</p>
    </div>
  </section>
</template>

<style scoped>
.person-gallery-v10{margin:14px 22px 0;padding:12px;border:1px solid #d7e0ef;border-radius:12px;background:#fff}.person-gallery-v10>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.person-gallery-v10>header>div{display:grid;gap:2px}.person-gallery-v10>header strong{font-size:14px;color:#253a60}.person-gallery-v10>header span,.person-gallery-v10>header small{font-size:11px;color:#667892}.person-gallery-group{margin-top:12px;padding-top:10px;border-top:1px solid #edf0f5}.person-gallery-title{display:flex;align-items:center;gap:9px;margin-bottom:8px}.person-gallery-title strong{font-size:13px}.person-gallery-title span{font-size:10px;color:#708099}.person-gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:8px}.person-gallery-grid figure{margin:0;border:1px solid #e1e6ee;border-radius:9px;overflow:hidden;background:#f7f9fc}.person-gallery-grid img{display:block;width:100%;height:132px;object-fit:cover;background:#eef1f5}.person-gallery-grid figcaption{display:grid;gap:1px;padding:5px 6px}.person-gallery-grid figcaption b{font-size:9px;color:#27384f}.person-gallery-grid figcaption span{font-size:9px;color:#7a8797}.gallery-error{color:#b33b3b;font-size:11px}.gallery-empty{font-size:11px;color:#8a94a3}
</style>
