<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { personImageViewport } from '../utils/personImageViewport'
const props = defineProps<{ src: string; alt: string; box?: number[] | null }>()
const size = ref<[number, number] | null>(null)
watch(() => props.src, () => { size.value = null })
function loaded(event: Event) { const img = event.target as HTMLImageElement; size.value = [img.naturalWidth, img.naturalHeight] }
const viewBox = computed(() => personImageViewport(size.value, props.box))
</script>
<template>
  <span class="person-evidence-image">
    <img v-show="!viewBox" :src="src" :alt="alt" @load="loaded" />
    <svg v-if="viewBox && size" :viewBox="viewBox" preserveAspectRatio="xMidYMid meet" role="img" :aria-label="alt"><image :href="src" :width="size[0]" :height="size[1]" /></svg>
  </span>
</template>
<style scoped>
.person-evidence-image{display:block;position:relative;width:100%;height:100%;overflow:hidden;background:#f0f2f5}
.person-evidence-image>img,.person-evidence-image>svg{display:block;width:100%;height:100%;max-width:none;max-height:none;object-fit:contain;border:0;border-radius:0}
</style>
