<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  src: string
  atUs: number
  label: string
  subtitle?: string
}>()

const emit = defineEmits<{
  open: [src: string, title: string]
}>()

const videoRef = ref<HTMLVideoElement | null>(null)
const canvasRef = ref<HTMLCanvasElement | null>(null)
const loading = ref(true)
const failed = ref(false)
const captureUrl = ref('')
let objectUrl = ''

function clearObjectUrl(): void {
  if (objectUrl) URL.revokeObjectURL(objectUrl)
  objectUrl = ''
}

function drawFrame(): void {
  const video = videoRef.value
  const canvas = canvasRef.value
  if (!video || !canvas || !video.videoWidth || !video.videoHeight) return
  const width = 640
  const height = Math.max(1, Math.round(width * video.videoHeight / video.videoWidth))
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(video, 0, 0, width, height)
  captureUrl.value = canvas.toDataURL('image/jpeg', 0.92)
  loading.value = false
  failed.value = false
}

function seekToTarget(): void {
  const video = videoRef.value
  if (!video) return
  const duration = Number.isFinite(video.duration) ? video.duration : 0
  const requested = Math.max(0, props.atUs / 1_000_000)
  const target = duration > 0 ? Math.min(requested, Math.max(0, duration - 0.001)) : requested
  if (Math.abs(video.currentTime - target) < 0.001 && video.readyState >= 2) {
    drawFrame()
    return
  }
  video.currentTime = target
}

function openPreview(): void {
  if (captureUrl.value) emit('open', captureUrl.value, `${props.label}${props.subtitle ? ` · ${props.subtitle}` : ''}`)
}

function reload(): void {
  loading.value = true
  failed.value = false
  captureUrl.value = ''
  clearObjectUrl()
  const video = videoRef.value
  if (!video) return
  video.load()
}

function onError(): void {
  loading.value = false
  failed.value = true
}

watch(() => [props.src, props.atUs], reload)

onMounted(reload)
onBeforeUnmount(clearObjectUrl)
</script>

<template>
  <button class="shot-frame-v4" type="button" :disabled="failed" @click.stop="openPreview">
    <video
      ref="videoRef"
      class="shot-frame-v4-source"
      :src="src"
      muted
      playsinline
      preload="auto"
      @loadedmetadata="seekToTarget"
      @seeked="drawFrame"
      @loadeddata="seekToTarget"
      @error="onError"
    ></video>
    <canvas ref="canvasRef"></canvas>
    <span v-if="loading" class="shot-frame-v4-loading">取帧中…</span>
    <span v-else-if="failed" class="shot-frame-v4-loading">无法取帧</span>
    <div class="shot-frame-v4-caption">
      <strong>{{ label }}</strong>
      <small v-if="subtitle">{{ subtitle }}</small>
      <i>点击放大</i>
    </div>
  </button>
</template>

<style scoped>
.shot-frame-v4 {
  position: relative;
  min-width: 0;
  display: block;
  padding: 0;
  overflow: hidden;
  border: 1px solid #dce3ed;
  border-radius: 9px;
  background: #10131a;
  cursor: zoom-in;
  text-align: left;
}
.shot-frame-v4:disabled { cursor: default; }
.shot-frame-v4-source {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
  pointer-events: none;
}
.shot-frame-v4 canvas {
  width: 100%;
  aspect-ratio: 16 / 9;
  display: block;
  object-fit: contain;
  background: #090b10;
}
.shot-frame-v4-loading {
  position: absolute;
  inset: 0 0 34px;
  display: grid;
  place-items: center;
  color: #cbd2dd;
  font-size: 11px;
}
.shot-frame-v4-caption {
  min-height: 34px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  padding: 5px 7px;
  background: #fff;
  color: #303b4e;
}
.shot-frame-v4-caption strong { font-size: 10px; }
.shot-frame-v4-caption small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #7a8596;
  font-size: 9px;
}
.shot-frame-v4-caption i {
  color: #5271ad;
  font-size: 8px;
  font-style: normal;
}
</style>
