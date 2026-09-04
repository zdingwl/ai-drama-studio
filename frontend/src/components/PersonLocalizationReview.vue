<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import PersonEvidenceImageV1 from './PersonEvidenceImageV1.vue'
import type { PersonMark } from '../utils/personReviewGroups'

const props = withDefaults(defineProps<{ imageUrl: string; shotId: string; label: string; modelValue?: PersonMark | null; disabled?: boolean; allowSingle?: boolean }>(), { allowSingle: true })
const emit = defineEmits<{ 'update:modelValue': [PersonMark | null] }>()
const loaded = ref(false)
const start = ref<number[] | null>(null)
const draft = ref<number[] | null>(null)
const box = computed(() => draft.value || (props.modelValue?.image_url === props.imageUrl && props.modelValue.shot_id === props.shotId ? props.modelValue.box : null))
const singlePerson = computed(() => Boolean(box.value && props.modelValue?.source === 'MANUAL_SINGLE_PERSON' && !draft.value))
watch(() => [props.imageUrl, props.shotId], () => { loaded.value = false; start.value = null; draft.value = null })
function confirmSinglePerson() {
  if (!loaded.value || props.disabled || !props.imageUrl) return
  emit('update:modelValue', { shot_id: props.shotId, image_url: props.imageUrl, box: [0, 0, 1, 1], source: 'MANUAL_SINGLE_PERSON' })
}
function point(event: PointerEvent): number[] {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  return [Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)), Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height))]
}
function down(event: PointerEvent) {
  if (props.disabled || !loaded.value || event.button !== 0) return
  start.value = point(event); draft.value = null
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}
function move(event: PointerEvent) {
  if (!start.value) return
  const [x = 0, y = 0] = start.value, [endX = 0, endY = 0] = point(event)
  draft.value = [Math.min(x, endX), Math.min(y, endY), Math.abs(x - endX), Math.abs(y - endY)]
}
function up(event: PointerEvent) {
  if (!start.value) return
  move(event)
  if (draft.value && draft.value[2]! >= .02 && draft.value[3]! >= .02) emit('update:modelValue', { shot_id: props.shotId, image_url: props.imageUrl, box: [...draft.value], source: 'MANUAL_BOX' })
  start.value = null; draft.value = null
}
</script>

<template>
  <section class="localization">
    <header><strong>确认画面人物：{{ label }}</strong><span>{{ !allowSingle ? '请框出漏掉的人物，框外画面只作参考。' : singlePerson ? '已人工确认画面只有此人，直接确认右侧身份即可。' : '单人画面无需画框；多人画面请拖动框出需要确认的人。' }}</span></header>
    <div class="frame-area">
      <div v-if="imageUrl" class="frame" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="start = null; draft = null">
        <img :src="imageUrl" alt="框选待确认人物的原始关键帧" draggable="false" @load="loaded = true" @error="loaded = false" />
        <div v-if="box && loaded && !singlePerson" class="box" :style="{ left: `${box[0]! * 100}%`, top: `${box[1]! * 100}%`, width: `${box[2]! * 100}%`, height: `${box[3]! * 100}%` }"><span>待确认人物</span></div>
      </div>
      <p v-else>当前没有可定位的关键帧，请先补齐画面证据。</p>
    </div>
    <footer v-if="singlePerson && loaded"><strong>单人画面 · 无需框选</strong><button type="button" :disabled="disabled" @click="emit('update:modelValue', null)">改为多人框选</button></footer>
    <footer v-else-if="box && loaded"><div class="crop"><PersonEvidenceImageV1 :src="imageUrl" :box="box" alt="当前待确认人物裁剪图" /></div><div><strong>只确认框内这个人</strong><p>如框选不准，可直接重新拖动。定位不代表身份已确认。</p></div></footer>
    <footer v-else><button v-if="allowSingle" type="button" :disabled="disabled || !loaded" @click="confirmSinglePerson">画面只有此人，无需框选</button><span>{{ allowSingle ? '有其他人或无法判断时，请框选。' : '请在原图上拖动框出漏掉的人物。' }}</span></footer>
  </section>
</template>

<style scoped>
.localization footer button{border:1px solid #a9bfe3;background:#f1f6ff;color:#245a9f;padding:8px 12px;border-radius:7px;cursor:pointer;font-size:12px}.localization footer button:disabled{opacity:.45;cursor:not-allowed}
.localization{width:100%;min-width:0;background:#fff;color:#273b58}.localization header{display:grid;gap:5px;padding:12px}.localization header strong{font-size:13px}.localization header span,footer{font-size:11px;line-height:1.6;color:#63748b}.frame-area{display:flex;justify-content:center;background:#101824;overflow:hidden}.frame{position:relative;display:inline-flex;max-width:100%;overflow:hidden;touch-action:none;cursor:crosshair}.frame img{display:block;max-width:100%;max-height:48vh;width:auto;height:auto;user-select:none}.box{position:absolute;box-sizing:border-box;border:3px solid #448bff;box-shadow:0 0 0 2000px #061327a8;pointer-events:none}.box span{position:absolute;left:0;top:0;padding:2px 6px;background:#1769ff;color:#fff;font-size:10px;white-space:nowrap}.localization footer{display:flex;align-items:center;gap:12px;padding:12px}.crop{width:72px;height:90px;flex:none;background:#edf2f8;border-radius:6px;overflow:hidden}footer p{margin:4px 0}.frame-area>p{color:#fff;padding:20px}
</style>
