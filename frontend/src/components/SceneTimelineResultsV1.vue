<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { breakdownApi } from '../api/breakdown'
import { sceneTimelineApi } from '../api/scene-timeline'
import type { BreakdownRunSummary } from '../types/breakdown'
import type {
  SceneTimelineDialogue,
  SceneTimelinePayload,
  SceneTimelinePerformance,
  SceneTimelineScene,
  SceneTimelineShot,
} from '../types/scene-timeline'
import type { Episode } from '../types/studio'
import {
  cinematographyItems,
  personDisplayName,
  sceneInfoTags,
  timelineDuration,
  timelineTime,
} from '../utils/sceneTimelineUi'

const props = defineProps<{
  episodes: Episode[]
  selectedEpisodeId: string
}>()

const emit = defineEmits<{
  (event: 'run-context', run: BreakdownRunSummary | null): void
}>()

const route = useRoute()
const router = useRouter()
const timeline = ref<SceneTimelinePayload | null>(null)
const selectedSceneOrdinal = ref<number | null>(null)
const selectedShotOrdinal = ref<number | null>(null)
const activeVideoOrdinal = ref<number | null>(null)
const loading = ref(false)
const error = ref('')
let requestSerial = 0

const currentEpisode = computed(() => props.episodes.find((item) => item.id === props.selectedEpisodeId) ?? null)
const selectedScene = computed(() => {
  const payload = timeline.value
  if (!payload) return null
  return payload.scenes.find((scene) => scene.ordinal === selectedSceneOrdinal.value) ?? payload.scenes[0] ?? null
})
const selectedShot = computed(() => {
  const scene = selectedScene.value
  if (!scene) return null
  return scene.shots.find((shot) => shot.ordinal === selectedShotOrdinal.value) ?? scene.shots[0] ?? null
})
const selectedShotIndex = computed(() => {
  if (!selectedScene.value || !selectedShot.value) return -1
  return selectedScene.value.shots.findIndex((shot) => shot.ordinal === selectedShot.value?.ordinal)
})
const canSelectPreviousShot = computed(() => selectedShotIndex.value > 0)
const canSelectNextShot = computed(() => (
  selectedScene.value !== null
  && selectedShotIndex.value >= 0
  && selectedShotIndex.value < selectedScene.value.shots.length - 1
))

function routeOrdinal(value: unknown): number | null {
  const numeric = Number(value)
  return Number.isInteger(numeric) && numeric > 0 ? numeric : null
}

function episodeLabel(): string {
  const episode = currentEpisode.value
  if (!episode) return '拉片结果'
  return `E${String(episode.sort_order).padStart(2, '0')} · ${episode.title}`
}

function peopleNames(scene: SceneTimelineScene, refs: string[]): string {
  return Array.from(new Set(refs.map((ref) => personDisplayName(scene.people, ref)))).join('、')
}

function performanceLabel(scene: SceneTimelineScene, item: SceneTimelinePerformance): string {
  const names = peopleNames(scene, item.people)
  return names ? `${names}：${item.text}` : item.text
}

function dialogueSpeaker(scene: SceneTimelineScene, item: SceneTimelineDialogue): string {
  const names = peopleNames(scene, item.speakers)
  return names || '对白'
}

function hasCinematography(shot: SceneTimelineShot): boolean {
  return cinematographyItems(shot.cinematography).length > 0
}

function compactShotMeta(shot: SceneTimelineShot): string[] {
  const items: string[] = []
  if (shot.people.length) items.push(`${shot.people.length} 人`)
  if (shot.dialogue.length) items.push(`${shot.dialogue.length} 条对白`)
  if (shot.props.length) items.push(`${shot.props.length} 个道具`)
  if (shot.on_screen_text.length) items.push(`${shot.on_screen_text.length} 条画面文字`)
  return items
}

function writeSelectionToRoute(sceneOrdinal: number | null, shotOrdinal: number | null): void {
  const nextQuery = { ...route.query }
  if (sceneOrdinal) nextQuery.scene = String(sceneOrdinal)
  else delete nextQuery.scene
  if (shotOrdinal) nextQuery.shot = String(shotOrdinal)
  else delete nextQuery.shot

  const currentScene = String(route.query.scene || '')
  const currentShot = String(route.query.shot || '')
  if (currentScene === String(sceneOrdinal || '') && currentShot === String(shotOrdinal || '')) return
  void router.replace({ query: nextQuery })
}

function syncSelectionFromRoute(payload = timeline.value): void {
  if (!payload?.scenes.length) {
    selectedSceneOrdinal.value = null
    selectedShotOrdinal.value = null
    return
  }

  const requestedSceneOrdinal = routeOrdinal(route.query.scene)
  const requestedShotOrdinal = routeOrdinal(route.query.shot)
  const requestedScene = payload.scenes.find((scene) => scene.ordinal === requestedSceneOrdinal)
  const shotScene = requestedShotOrdinal
    ? payload.scenes.find((scene) => scene.shots.some((shot) => shot.ordinal === requestedShotOrdinal))
    : null
  const scene = requestedScene ?? shotScene ?? payload.scenes[0]
  const shot = scene.shots.find((item) => item.ordinal === requestedShotOrdinal) ?? scene.shots[0] ?? null

  selectedSceneOrdinal.value = scene.ordinal
  selectedShotOrdinal.value = shot?.ordinal ?? null
  activeVideoOrdinal.value = null
  writeSelectionToRoute(scene.ordinal, shot?.ordinal ?? null)
}

function selectScene(scene: SceneTimelineScene): void {
  selectedSceneOrdinal.value = scene.ordinal
  selectedShotOrdinal.value = scene.shots[0]?.ordinal ?? null
  activeVideoOrdinal.value = null
  writeSelectionToRoute(scene.ordinal, selectedShotOrdinal.value)
}

function selectShot(shot: SceneTimelineShot): void {
  selectedShotOrdinal.value = shot.ordinal
  activeVideoOrdinal.value = null
  writeSelectionToRoute(selectedScene.value?.ordinal ?? null, shot.ordinal)
}

function selectAdjacentShot(offset: -1 | 1): void {
  const scene = selectedScene.value
  if (!scene || selectedShotIndex.value < 0) return
  const shot = scene.shots[selectedShotIndex.value + offset]
  if (shot) selectShot(shot)
}

function toggleVideo(shot: SceneTimelineShot): void {
  if (!shot.reference_url) return
  activeVideoOrdinal.value = activeVideoOrdinal.value === shot.ordinal ? null : shot.ordinal
}

async function loadRunContext(episodeId: string, serial: number): Promise<void> {
  try {
    const runs = await breakdownApi.listRuns(episodeId)
    if (serial !== requestSerial) return
    emit('run-context', runs.find((item) => item.is_current) ?? runs[0] ?? null)
  } catch {
    if (serial === requestSerial) emit('run-context', null)
  }
}

async function loadEpisode(episodeId: string): Promise<void> {
  if (!episodeId) {
    timeline.value = null
    selectedSceneOrdinal.value = null
    selectedShotOrdinal.value = null
    activeVideoOrdinal.value = null
    emit('run-context', null)
    return
  }

  const serial = ++requestSerial
  loading.value = true
  error.value = ''
  activeVideoOrdinal.value = null

  void loadRunContext(episodeId, serial)

  try {
    const payload = await sceneTimelineApi.getEpisode(episodeId)
    if (serial !== requestSerial) return
    timeline.value = payload
    syncSelectionFromRoute(payload)
  } catch (err) {
    if (serial !== requestSerial) return
    timeline.value = null
    selectedSceneOrdinal.value = null
    selectedShotOrdinal.value = null
    error.value = err instanceof Error ? err.message : '拉片结果读取失败'
  } finally {
    if (serial === requestSerial) loading.value = false
  }
}

watch(
  () => props.selectedEpisodeId,
  async (episodeId) => {
    timeline.value = null
    selectedSceneOrdinal.value = null
    selectedShotOrdinal.value = null
    activeVideoOrdinal.value = null
    await loadEpisode(episodeId)
  },
  { immediate: true },
)

watch(
  () => [route.query.scene, route.query.shot],
  () => {
    if (timeline.value) syncSelectionFromRoute()
  },
)
</script>

<template>
  <section class="scene-timeline-results-v1">
    <div v-if="error" class="timeline-alert danger">{{ error }}</div>
    <div v-if="loading" class="timeline-loading"><span></span>正在读取拉片结果…</div>

    <template v-if="timeline">
      <header class="timeline-topbar">
        <div>
          <strong>{{ episodeLabel() }}</strong>
          <span>{{ timeline.scene_count }} 个场景 · {{ timeline.shot_count }} 个镜头</span>
        </div>
        <span v-if="timeline.status === 'READY_WITH_WARNINGS'" class="timeline-check-pill">部分内容建议检查</span>
      </header>

      <div v-if="timeline.warnings.length" class="timeline-warning-list">
        <span v-for="warning in timeline.warnings" :key="warning">{{ warning }}</span>
      </div>
    </template>

    <div v-if="!timeline && !loading && !error" class="timeline-empty">
      <strong>还没有可查看的拉片结果</strong>
      <p>完成镜头切分后，点击上方“重新拉片本集”生成结果。</p>
    </div>

    <div v-else-if="timeline && !timeline.scenes.length" class="timeline-empty">
      <strong>本集暂时没有场景内容</strong>
      <p>当前拉片结果没有可展示的场景和镜头。</p>
    </div>

    <div v-else-if="timeline && selectedScene" class="timeline-layout">
      <aside class="scene-navigator">
        <header>
          <strong>场景</strong>
          <span>{{ timeline.scene_count }}</span>
        </header>
        <div class="scene-nav-list">
          <button
            v-for="scene in timeline.scenes"
            :key="scene.ordinal"
            type="button"
            :class="['scene-nav-item', { active: scene.ordinal === selectedScene.ordinal }]"
            @click="selectScene(scene)"
          >
            <span>场景 {{ String(scene.ordinal).padStart(2, '0') }}</span>
            <strong>{{ scene.title }}</strong>
            <small>{{ scene.shots.length }} 个镜头 · {{ timelineDuration(scene.duration_us) }}</small>
          </button>
        </div>
      </aside>

      <main class="scene-reading-pane">
        <section class="scene-hero">
          <div class="scene-title-row">
            <div>
              <div class="scene-eyebrow">场景 {{ String(selectedScene.ordinal).padStart(2, '0') }}</div>
              <h2>{{ selectedScene.title }}</h2>
            </div>
            <span>{{ selectedScene.shots.length }} 个镜头 · {{ timelineDuration(selectedScene.duration_us) }}</span>
          </div>

          <p v-if="selectedScene.story_summary" class="scene-story">{{ selectedScene.story_summary }}</p>

          <div v-if="sceneInfoTags(selectedScene.scene_info).length" class="scene-meta-row">
            <span v-for="item in sceneInfoTags(selectedScene.scene_info)" :key="item">{{ item }}</span>
          </div>
          <p v-if="selectedScene.scene_info.environment" class="scene-environment">{{ selectedScene.scene_info.environment }}</p>

          <div v-if="selectedScene.people.length" class="scene-person-strip">
            <span class="scene-person-label">本场人物</span>
            <div>
              <span v-for="person in selectedScene.people" :key="person.ref" :title="person.appearance || undefined">
                {{ person.display_name }}
              </span>
            </div>
          </div>
        </section>

        <section class="scene-shots-section">
          <header class="shots-section-head">
            <div>
              <strong>镜头列表</strong>
              <span>点选镜头，在右侧查看完整内容</span>
            </div>
          </header>

          <div class="compact-shot-list">
            <button
              v-for="shot in selectedScene.shots"
              :key="shot.ordinal"
              type="button"
              :class="['compact-shot-row', { active: selectedShot?.ordinal === shot.ordinal }]"
              @click="selectShot(shot)"
            >
              <span class="compact-shot-thumb">
                <img v-if="shot.thumbnail_url" :src="shot.thumbnail_url" :alt="`镜头 ${shot.ordinal} 缩略图`" loading="lazy" />
                <i v-else>无预览</i>
              </span>

              <span class="compact-shot-main">
                <span class="compact-shot-title">
                  <strong>镜头 {{ String(shot.ordinal).padStart(4, '0') }}</strong>
                  <small>{{ timelineTime(shot.start_us) }} → {{ timelineTime(shot.end_us) }} · {{ timelineDuration(shot.duration_us) }}</small>
                </span>
                <b v-if="shot.visual_description">{{ shot.visual_description }}</b>
                <b v-else>暂无画面描述</b>
                <span v-if="shot.people.length" class="compact-shot-people">{{ peopleNames(selectedScene, shot.people) }}</span>
                <span v-if="compactShotMeta(shot).length" class="compact-shot-meta">
                  <i v-for="item in compactShotMeta(shot)" :key="item">{{ item }}</i>
                </span>
              </span>

              <span class="compact-shot-arrow">›</span>
            </button>
          </div>
        </section>
      </main>

      <aside v-if="selectedShot" class="shot-inspector">
        <header class="inspector-head">
          <div>
            <span>镜头详情</span>
            <strong>镜头 {{ String(selectedShot.ordinal).padStart(4, '0') }}</strong>
            <small>{{ timelineTime(selectedShot.start_us) }} → {{ timelineTime(selectedShot.end_us) }}</small>
          </div>
          <div class="inspector-stepper">
            <button :disabled="!canSelectPreviousShot" title="上一镜" @click="selectAdjacentShot(-1)">‹</button>
            <button :disabled="!canSelectNextShot" title="下一镜" @click="selectAdjacentShot(1)">›</button>
          </div>
        </header>

        <div class="inspector-scroll">
          <div class="inspector-media">
            <video
              v-if="activeVideoOrdinal === selectedShot.ordinal && selectedShot.reference_url"
              :src="selectedShot.reference_url"
              :poster="selectedShot.thumbnail_url || undefined"
              controls
              autoplay
              preload="metadata"
            ></video>
            <button
              v-else-if="selectedShot.reference_url"
              type="button"
              class="inspector-preview-button"
              @click="toggleVideo(selectedShot)"
            >
              <img v-if="selectedShot.thumbnail_url" :src="selectedShot.thumbnail_url" :alt="`镜头 ${selectedShot.ordinal} 缩略图`" />
              <span v-else>暂无画面预览</span>
              <i>▶ 播放镜头</i>
            </button>
            <div v-else class="inspector-preview-static">
              <img v-if="selectedShot.thumbnail_url" :src="selectedShot.thumbnail_url" :alt="`镜头 ${selectedShot.ordinal} 缩略图`" />
              <span v-else>暂无画面预览</span>
            </div>
          </div>

          <section v-if="selectedShot.visual_description" class="inspector-primary-block">
            <span>画面内容</span>
            <p>{{ selectedShot.visual_description }}</p>
          </section>

          <section v-if="selectedShot.people.length" class="inspector-block">
            <h4>人物</h4>
            <div class="inspector-chips">
              <span v-for="ref in selectedShot.people" :key="ref">{{ personDisplayName(selectedScene.people, ref) }}</span>
            </div>
          </section>

          <section v-if="selectedShot.performance.length" class="inspector-block">
            <h4>动作 / 表演</h4>
            <ul>
              <li v-for="(item, index) in selectedShot.performance" :key="`${selectedShot.ordinal}-performance-${index}`">
                {{ performanceLabel(selectedScene, item) }}
              </li>
            </ul>
          </section>

          <section v-if="selectedShot.dialogue.length" class="inspector-block">
            <h4>对白</h4>
            <div class="inspector-dialogue-list">
              <article v-for="(item, index) in selectedShot.dialogue" :key="`${selectedShot.ordinal}-dialogue-${index}`">
                <header>
                  <strong>{{ dialogueSpeaker(selectedScene, item) }}</strong>
                  <span>{{ timelineTime(item.start_us) }}</span>
                </header>
                <p>{{ item.text }}</p>
              </article>
            </div>
          </section>

          <section v-if="selectedShot.props.length" class="inspector-block">
            <h4>道具</h4>
            <div class="inspector-prop-list">
              <article v-for="(prop, index) in selectedShot.props" :key="`${selectedShot.ordinal}-prop-${index}`">
                <strong>{{ prop.label }}</strong>
                <span v-if="prop.interaction">{{ prop.interaction }}</span>
              </article>
            </div>
          </section>

          <section v-if="selectedShot.on_screen_text.length" class="inspector-block">
            <h4>画面文字</h4>
            <div class="inspector-screen-text-list">
              <article v-for="(item, index) in selectedShot.on_screen_text" :key="`${selectedShot.ordinal}-screen-${index}`">
                <span>{{ timelineTime(item.start_us) }}</span>
                <p>{{ item.text }}</p>
              </article>
            </div>
          </section>

          <details v-if="hasCinematography(selectedShot)" class="inspector-advanced">
            <summary>镜头语言</summary>
            <div class="inspector-chips">
              <span v-for="item in cinematographyItems(selectedShot.cinematography)" :key="item">{{ item }}</span>
            </div>
          </details>
        </div>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.scene-timeline-results-v1 {
  min-height: 0;
  display: grid;
  gap: 10px;
  color: #263650;
}
.timeline-topbar {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  border: 1px solid #dfe5ef;
  border-radius: 12px;
  padding: 10px 12px;
  background: #fff;
  box-shadow: 0 4px 16px rgba(42, 59, 90, .035);
}
.timeline-topbar > div { min-width: 0; display: grid; gap: 2px; }
.timeline-topbar strong { overflow: hidden; color: #30435f; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.timeline-topbar span { color: #8190a4; font-size: 10px; }
.timeline-check-pill { flex: none; border-radius: 999px; padding: 5px 8px; background: #fff5dc; color: #96630e !important; font-weight: 800; }
.timeline-warning-list {
  display: grid;
  gap: 4px;
  border: 1px solid #eedca7;
  border-radius: 10px;
  padding: 8px 10px;
  background: #fffaf0;
  color: #805f20;
  font-size: 10px;
}
.timeline-alert,
.timeline-loading,
.timeline-empty { border: 1px solid #dfe5ef; border-radius: 12px; padding: 14px; background: #fff; }
.timeline-alert.danger { border-color: #efcccc; background: #fff4f4; color: #a34747; }
.timeline-loading { display: flex; gap: 8px; align-items: center; color: #6d7b90; font-size: 11px; }
.timeline-loading > span { width: 8px; height: 8px; border-radius: 50%; background: #5d82d6; box-shadow: 0 0 0 4px rgba(93, 130, 214, .12); }
.timeline-empty { display: grid; gap: 5px; place-items: center; min-height: 180px; text-align: center; }
.timeline-empty strong { color: #40516d; font-size: 14px; }
.timeline-empty p { margin: 0; color: #8995a7; font-size: 11px; }

.timeline-layout {
  min-height: 0;
  display: grid;
  grid-template-columns: 176px minmax(420px, 1fr) minmax(330px, 390px);
  gap: 10px;
  align-items: start;
}
.scene-navigator,
.shot-inspector {
  position: sticky;
  top: 8px;
  max-height: calc(100vh - 184px);
  overflow: hidden;
  border: 1px solid #dfe5ef;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 5px 18px rgba(39, 55, 84, .035);
}
.scene-navigator { display: grid; grid-template-rows: auto minmax(0, 1fr); }
.scene-navigator > header { display: flex; justify-content: space-between; align-items: center; padding: 10px 11px; border-bottom: 1px solid #edf0f5; }
.scene-navigator > header strong { color: #40516c; font-size: 11px; }
.scene-navigator > header span { min-width: 23px; border-radius: 999px; padding: 2px 6px; background: #eef3fb; color: #657b9f; font-size: 9px; font-weight: 800; text-align: center; }
.scene-nav-list { min-height: 0; display: grid; gap: 4px; overflow: auto; padding: 6px; }
.scene-nav-item {
  width: 100%;
  display: grid;
  gap: 3px;
  border: 1px solid transparent;
  border-radius: 9px;
  padding: 8px 9px;
  background: transparent;
  color: #66758b;
  cursor: pointer;
  text-align: left;
}
.scene-nav-item:hover { background: #f7f9fc; }
.scene-nav-item.active { border-color: #b9ccef; background: #eef4ff; box-shadow: inset 3px 0 0 #5d82d6; }
.scene-nav-item > span { color: #909bad; font-size: 8px; font-weight: 850; letter-spacing: .03em; }
.scene-nav-item > strong { color: #3f506c; font-size: 11px; line-height: 1.35; }
.scene-nav-item > small { color: #8a96a7; font-size: 8px; }

.scene-reading-pane { min-width: 0; display: grid; gap: 9px; }
.scene-hero {
  display: grid;
  gap: 8px;
  border: 1px solid #dce5f2;
  border-radius: 13px;
  padding: 13px 15px;
  background: linear-gradient(145deg, #f8fbff 0%, #fff 60%);
  box-shadow: 0 5px 18px rgba(43, 66, 107, .04);
}
.scene-title-row { display: flex; justify-content: space-between; gap: 12px; align-items: end; }
.scene-title-row > div { min-width: 0; }
.scene-title-row > span { flex: none; color: #8a96a7; font-size: 9px; }
.scene-eyebrow { color: #6782af; font-size: 9px; font-weight: 900; letter-spacing: .07em; }
.scene-hero h2 { margin: 2px 0 0; color: #263c5d; font-size: 18px; line-height: 1.2; }
.scene-story { margin: 0; color: #455874; font-size: 11px; line-height: 1.65; }
.scene-meta-row { display: flex; flex-wrap: wrap; gap: 5px; }
.scene-meta-row span { border-radius: 999px; padding: 4px 7px; background: #edf3fb; color: #587099; font-size: 9px; font-weight: 750; }
.scene-environment { margin: 0; border-left: 3px solid #cfdaea; padding-left: 8px; color: #78869a; font-size: 10px; line-height: 1.55; }
.scene-person-strip { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 7px; align-items: center; padding-top: 2px; }
.scene-person-label { color: #8a96a7; font-size: 9px; font-weight: 800; }
.scene-person-strip > div { display: flex; flex-wrap: wrap; gap: 5px; }
.scene-person-strip > div > span { border: 1px solid #e1e7f0; border-radius: 999px; padding: 3px 7px; background: #fff; color: #4d617f; font-size: 9px; font-weight: 750; }

.scene-shots-section { display: grid; gap: 7px; }
.shots-section-head { display: flex; justify-content: space-between; align-items: end; padding: 0 2px; }
.shots-section-head > div { display: flex; gap: 7px; align-items: baseline; }
.shots-section-head strong { color: #354965; font-size: 12px; }
.shots-section-head span { color: #8a96a7; font-size: 9px; }
.compact-shot-list { display: grid; gap: 6px; }
.compact-shot-row {
  width: 100%;
  min-width: 0;
  display: grid;
  grid-template-columns: 116px minmax(0, 1fr) 18px;
  gap: 10px;
  align-items: center;
  border: 1px solid #dfe5ef;
  border-radius: 11px;
  padding: 7px;
  background: #fff;
  box-shadow: 0 3px 12px rgba(42, 59, 90, .025);
  text-align: left;
  cursor: pointer;
  transition: .15s ease;
}
.compact-shot-row:hover { border-color: #c8d5e8; transform: translateY(-1px); }
.compact-shot-row.active { border-color: #8fa9df; background: #f7faff; box-shadow: inset 3px 0 0 #5d82d6, 0 4px 14px rgba(61, 95, 158, .07); }
.compact-shot-thumb { width: 116px; aspect-ratio: 16 / 9; overflow: hidden; display: grid; place-items: center; border-radius: 8px; background: #17202d; }
.compact-shot-thumb img { width: 100%; height: 100%; display: block; object-fit: cover; }
.compact-shot-thumb i { color: #8290a4; font-size: 9px; font-style: normal; }
.compact-shot-main { min-width: 0; display: grid; gap: 3px; }
.compact-shot-title { display: flex; gap: 7px; align-items: baseline; }
.compact-shot-title strong { flex: none; color: #405879; font-size: 10px; }
.compact-shot-title small { overflow: hidden; color: #8995a6; font-size: 8px; text-overflow: ellipsis; white-space: nowrap; }
.compact-shot-main > b { display: -webkit-box; overflow: hidden; color: #31445f; font-size: 11px; font-weight: 650; line-height: 1.5; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.compact-shot-people { overflow: hidden; color: #65758d; font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.compact-shot-meta { display: flex; flex-wrap: wrap; gap: 4px; }
.compact-shot-meta i { border-radius: 999px; padding: 2px 5px; background: #f0f3f7; color: #7c899a; font-size: 8px; font-style: normal; }
.compact-shot-arrow { color: #a0adbd; font-size: 21px; font-weight: 300; text-align: center; }

.shot-inspector { display: grid; grid-template-rows: auto minmax(0, 1fr); }
.inspector-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; padding: 10px 11px; border-bottom: 1px solid #edf0f5; background: #fbfcfe; }
.inspector-head > div:first-child { min-width: 0; display: grid; gap: 1px; }
.inspector-head span { color: #8995a6; font-size: 8px; font-weight: 850; letter-spacing: .05em; }
.inspector-head strong { color: #334967; font-size: 12px; }
.inspector-head small { color: #8a96a7; font-size: 8px; }
.inspector-stepper { display: flex; gap: 4px; }
.inspector-stepper button { width: 28px; height: 28px; border: 1px solid #dce3ec; border-radius: 7px; background: #fff; color: #526782; font-size: 18px; line-height: 1; }
.inspector-stepper button:disabled { opacity: .35; }
.inspector-scroll { min-height: 0; overflow: auto; padding: 9px; display: grid; gap: 8px; align-content: start; }
.inspector-media { overflow: hidden; border-radius: 9px; background: #111a27; }
.inspector-media video,
.inspector-preview-button,
.inspector-preview-static { width: 100%; aspect-ratio: 16 / 9; }
.inspector-media video { display: block; object-fit: contain; background: #0c1119; }
.inspector-preview-button { position: relative; display: block; border: 0; padding: 0; overflow: hidden; background: #111a27; cursor: pointer; }
.inspector-preview-button img,
.inspector-preview-static img { width: 100%; height: 100%; display: block; object-fit: cover; }
.inspector-preview-button::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, transparent 44%, rgba(8, 14, 24, .64)); }
.inspector-preview-button span,
.inspector-preview-static span { height: 100%; display: grid; place-items: center; color: #8290a4; font-size: 9px; }
.inspector-preview-button i { position: absolute; z-index: 1; right: 9px; bottom: 8px; border-radius: 999px; padding: 5px 8px; background: rgba(255, 255, 255, .92); color: #344c72; font-size: 9px; font-style: normal; font-weight: 900; }
.inspector-preview-static { display: grid; place-items: center; }
.inspector-primary-block,
.inspector-block,
.inspector-advanced { border: 1px solid #e3e8ef; border-radius: 9px; padding: 9px 10px; background: #fff; }
.inspector-primary-block { display: grid; gap: 4px; background: #f8fbff; }
.inspector-primary-block > span { color: #7184a2; font-size: 8px; font-weight: 850; }
.inspector-primary-block p { margin: 0; color: #30445f; font-size: 11px; font-weight: 650; line-height: 1.6; }
.inspector-block { display: grid; gap: 7px; }
.inspector-block h4 { margin: 0; color: #586a84; font-size: 9px; font-weight: 900; }
.inspector-block ul { display: grid; gap: 5px; margin: 0; padding-left: 17px; }
.inspector-block li { color: #40516a; font-size: 10px; line-height: 1.55; }
.inspector-chips { display: flex; flex-wrap: wrap; gap: 5px; }
.inspector-chips span { border-radius: 999px; padding: 3px 6px; background: #edf2f8; color: #536984; font-size: 9px; }
.inspector-dialogue-list,
.inspector-prop-list,
.inspector-screen-text-list { display: grid; gap: 6px; }
.inspector-dialogue-list article { border-left: 3px solid #b8c8e4; padding: 2px 0 2px 8px; }
.inspector-dialogue-list header { display: flex; justify-content: space-between; gap: 8px; }
.inspector-dialogue-list strong { color: #4b6180; font-size: 9px; }
.inspector-dialogue-list span,
.inspector-screen-text-list span { color: #9aa5b4; font-size: 8px; }
.inspector-dialogue-list p,
.inspector-screen-text-list p { margin: 3px 0 0; color: #2f4058; font-size: 10px; line-height: 1.55; }
.inspector-prop-list article { display: flex; justify-content: space-between; gap: 8px; border-radius: 7px; padding: 6px 7px; background: #f7f9fc; }
.inspector-prop-list strong { color: #465c79; font-size: 9px; }
.inspector-prop-list span { color: #77859a; font-size: 9px; text-align: right; }
.inspector-screen-text-list article { border-radius: 7px; padding: 6px 7px; background: #f7f9fc; }
.inspector-advanced > summary { color: #697a91; font-size: 9px; font-weight: 850; cursor: pointer; }
.inspector-advanced[open] > summary { margin-bottom: 8px; }

@media (max-width: 1480px) {
  .timeline-layout { grid-template-columns: 160px minmax(390px, 1fr) minmax(310px, 350px); }
  .compact-shot-row { grid-template-columns: 100px minmax(0, 1fr) 16px; gap: 8px; }
  .compact-shot-thumb { width: 100px; }
}
</style>
