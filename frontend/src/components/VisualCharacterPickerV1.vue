<script setup lang="ts">
import { computed, ref } from 'vue'

type CharacterOption = {
  id: string
  name: string
  cover_url?: string | null
  cover_box?: number[] | null
  confidence?: number | null
  shot_ids?: string[]
  shot_count?: number
  episode_count?: number
}

const props = defineProps<{
  modelValue: string
  characters: CharacterOption[]
  suggestedCharacterId?: string | null
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const search = ref('')

const filtered = computed(() => {
  const keyword = search.value.trim().toLowerCase()
  const rows = !keyword
    ? props.characters
    : props.characters.filter((item) => item.name.toLowerCase().includes(keyword))
  const suggestedId = props.suggestedCharacterId || ''
  return [...rows].sort((a, b) => {
    if (a.id === suggestedId && b.id !== suggestedId) return -1
    if (b.id === suggestedId && a.id !== suggestedId) return 1
    return Number(b.shot_count ?? b.shot_ids?.length ?? 0) - Number(a.shot_count ?? a.shot_ids?.length ?? 0)
  })
})

function choose(id: string): void {
  if (props.disabled) return
  emit('update:modelValue', props.modelValue === id ? '' : id)
}

function shotCount(item: CharacterOption): number {
  return Number(item.shot_count ?? item.shot_ids?.length ?? 0)
}

function coverStyle(item: CharacterOption): Record<string, string> {
  const box = item.cover_box
  if (!box || box.length !== 4 || !box.every(Number.isFinite)) return {}
  const [x, y, width, height] = box as [number, number, number, number]
  if (width <= 0 || height <= 0) return {}
  return {
    position: 'absolute', objectFit: 'fill', maxWidth: 'none',
    width: `${100 / width}%`, height: `${100 / height}%`,
    left: `${-100 * x / width}%`, top: `${-100 * y / height}%`,
  }
}
</script>

<template>
  <section class="visual-character-picker">
    <div class="picker-toolbar">
      <span>选择已有正式人物</span>
      <input v-model="search" type="search" placeholder="搜索人物" aria-label="搜索已有正式人物" />
    </div>

    <div v-if="filtered.length" class="character-grid">
      <button
        v-for="character in filtered"
        :key="character.id"
        type="button"
        :disabled="disabled"
        :class="['character-option', {
          selected: modelValue === character.id,
          suggested: suggestedCharacterId === character.id,
        }]"
        @click="choose(character.id)"
      >
        <div class="character-image">
          <img v-if="character.cover_url" :src="character.cover_url" :style="coverStyle(character)" :alt="`${character.name} 人物参考图`" loading="lazy" />
          <span v-else>{{ character.name.slice(0, 1) || '人' }}</span>
          <i v-if="modelValue === character.id">✓</i>
        </div>
        <div class="character-copy">
          <strong>{{ character.name }}</strong>
          <small>{{ shotCount(character) }} 个分镜<template v-if="character.episode_count"> · {{ character.episode_count }} 集</template></small>
        </div>
        <em v-if="suggestedCharacterId === character.id">AI 推荐</em>
      </button>
    </div>
    <div v-else class="picker-empty">没有匹配的正式人物。</div>
  </section>
</template>

<style scoped>
.visual-character-picker{display:grid;gap:8px}.picker-toolbar{display:flex;align-items:center;justify-content:space-between;gap:10px}.picker-toolbar>span{color:#62728a;font-size:9px;font-weight:800}.picker-toolbar input{width:min(180px,48%);height:32px;border:1px solid #d9e1eb;border-radius:7px;padding:0 9px;background:#fff;color:#40516b;font-size:9px;outline:none}.picker-toolbar input:focus{border-color:#79a2ef;box-shadow:0 0 0 3px rgba(23,105,255,.08)}.character-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(112px,1fr));gap:8px;max-height:320px;overflow:auto;padding:1px}.character-option{position:relative;min-width:0;display:grid;grid-template-rows:132px auto;gap:7px;padding:7px;border:1px solid #dce3ec;border-radius:10px;background:#fff;color:#40516b;text-align:left;cursor:pointer}.character-option:hover:not(:disabled){border-color:#9db8e7;background:#f9fbff}.character-option.selected{border-color:#1769ff;box-shadow:0 0 0 2px rgba(23,105,255,.12);background:#f3f7ff}.character-option.suggested:not(.selected){border-color:#b7c9e8}.character-option:disabled{opacity:.55;cursor:not-allowed}.character-image{position:relative;overflow:hidden;display:grid;place-items:center;border-radius:8px;background:#eef2f7;color:#6f7f95;font-size:22px;font-weight:850}.character-image img{display:block;width:100%;height:100%;object-fit:cover}.character-image i{position:absolute;right:6px;top:6px;width:22px;height:22px;display:grid;place-items:center;border-radius:50%;background:#1769ff;color:#fff;font-size:12px;font-style:normal;font-weight:900;box-shadow:0 2px 8px rgba(23,105,255,.3)}.character-copy{min-width:0;display:grid;gap:2px}.character-copy strong{overflow:hidden;color:#304764;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.character-copy small{color:#8793a3;font-size:8px}.character-option em{position:absolute;left:12px;top:12px;padding:3px 6px;border-radius:99px;background:rgba(255,244,218,.95);color:#9b691d;font-size:8px;font-style:normal;font-weight:850}.picker-empty{padding:16px;border:1px dashed #dbe2eb;border-radius:8px;color:#8793a3;font-size:9px;text-align:center}@media(max-width:760px){.picker-toolbar{align-items:stretch;flex-direction:column}.picker-toolbar input{width:100%}.character-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.character-option{grid-template-rows:150px auto}}
</style>
