<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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

const timeline = ref<SceneTimelinePayload | null>(null)
const selectedSceneOrdinal = ref<number | null>(null)
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

function selectScene(scene: SceneTimelineScene): void {
  selectedSceneOrdinal.value = scene.ordinal
  activeVideoOrdinal.value = null
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
    selectedSceneOrdinal.value = payload?.scenes[0]?.ordinal ?? null
  } catch (err) {
    if (serial !== requestSerial) return
    timeline.value = null
    selectedSceneOrdinal.value = null
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
    activeVideoOrdinal.value = null
    await loadEpisode(episodeId)
  },
  { immediate: true },
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
            <small>{{ scene.shots.length }} 个镜头</small>
          </button>
        </div>
      </aside>

      <main class="scene-reading-pane">
        <section class="scene-hero">
          <div class="scene-eyebrow">场景 {{ String(selectedScene.ordinal).padStart(2, '0') }}</div>
          <h2>{{ selectedScene.title }}</h2>
          <p v-if="selectedScene.story_summary" class="scene-story">{{ selectedScene.story_summary }}</p>

          <div v-if="sceneInfoTags(selectedScene.scene_info).length" class="scene-meta-row">
            <span v-for="item in sceneInfoTags(selectedScene.scene_info)" :key="item">{{ item }}</span>
          </div>
          <p v-if="selectedScene.scene_info.environment" class="scene-environment">
            {{ selectedScene.scene_info.environment }}
          </p>
        </section>

        <section v-if="selectedScene.people.length" class="scene-people-card">
          <header>
            <strong>本场人物</strong>
            <span>{{ selectedScene.people.length }} 人</span>
          </header>
          <div class="scene-people-list">
            <article v-for="person in selectedScene.people" :key="person.ref">
              <span class="person-avatar">人</span>
              <div>
                <strong>{{ person.display_name }}</strong>
                <p v-if="person.appearance">{{ person.appearance }}</p>
              </div>
            </article>
          </div>
        </section>

        <section class="scene-shots-section">
          <header class="shots-section-head">
            <div>
              <strong>镜头内容</strong>
              <span>{{ selectedScene.shots.length }} 个镜头 · {{ timelineDuration(selectedScene.duration_us) }}</span>
            </div>
          </header>

          <div class="shot-card-list">
            <article v-for="shot in selectedScene.shots" :key="shot.ordinal" class="timeline-shot-card">
              <header class="shot-card-head">
                <div>
                  <span>镜头 {{ String(shot.ordinal).padStart(4, '0') }}</span>
                  <strong>{{ timelineTime(shot.start_us) }} → {{ timelineTime(shot.end_us) }}</strong>
                </div>
                <small>{{ timelineDuration(shot.duration_us) }}</small>
              </header>

              <div class="shot-card-body">
                <div class="shot-media">
                  <video
                    v-if="activeVideoOrdinal === shot.ordinal && shot.reference_url"
                    :src="shot.reference_url"
                    :poster="shot.thumbnail_url || undefined"
                    controls
                    preload="metadata"
                  ></video>

                  <button
                    v-else-if="shot.reference_url"
                    type="button"
                    class="shot-preview-button"
                    :aria-label="`播放镜头 ${shot.ordinal}`"
                    @click="toggleVideo(shot)"
                  >
                    <img v-if="shot.thumbnail_url" :src="shot.thumbnail_url" :alt="`镜头 ${shot.ordinal} 缩略图`" loading="lazy" />
                    <span v-else class="shot-preview-placeholder">暂无缩略图</span>
                    <i>▶ 播放镜头</i>
                  </button>

                  <div v-else class="shot-preview-static">
                    <img v-if="shot.thumbnail_url" :src="shot.thumbnail_url" :alt="`镜头 ${shot.ordinal} 缩略图`" loading="lazy" />
                    <span v-else class="shot-preview-placeholder">暂无画面预览</span>
                  </div>

                  <button
                    v-if="activeVideoOrdinal === shot.ordinal && shot.reference_url"
                    type="button"
                    class="close-video-button"
                    @click="toggleVideo(shot)"
                  >收起视频</button>
                </div>

                <div class="shot-information">
                  <section v-if="shot.visual_description" class="shot-primary-description">
                    <span>画面</span>
                    <p>{{ shot.visual_description }}</p>
                  </section>

                  <div v-if="shot.people.length" class="shot-person-row">
                    <span>人物</span>
                    <div>
                      <b v-for="ref in shot.people" :key="ref">{{ personDisplayName(selectedScene.people, ref) }}</b>
                    </div>
                  </div>

                  <section v-if="shot.performance.length" class="shot-detail-block">
                    <h4>动作 / 表演</h4>
                    <ul>
                      <li v-for="(item, index) in shot.performance" :key="`${shot.ordinal}-performance-${index}`">
                        {{ performanceLabel(selectedScene, item) }}
                      </li>
                    </ul>
                  </section>

                  <section v-if="shot.dialogue.length" class="shot-detail-block dialogue-block">
                    <h4>对白</h4>
                    <div class="dialogue-list">
                      <article v-for="(item, index) in shot.dialogue" :key="`${shot.ordinal}-dialogue-${index}`">
                        <header>
                          <strong>{{ dialogueSpeaker(selectedScene, item) }}</strong>
                          <span>{{ timelineTime(item.start_us) }}</span>
                        </header>
                        <p>{{ item.text }}</p>
                      </article>
                    </div>
                  </section>

                  <section v-if="shot.props.length" class="shot-detail-block">
                    <h4>道具</h4>
                    <div class="prop-list">
                      <article v-for="(prop, index) in shot.props" :key="`${shot.ordinal}-prop-${index}`">
                        <strong>{{ prop.label }}</strong>
                        <span v-if="prop.interaction">{{ prop.interaction }}</span>
                      </article>
                    </div>
                  </section>

                  <section v-if="hasCinematography(shot)" class="shot-detail-block">
                    <h4>镜头语言</h4>
                    <div class="cinematography-list">
                      <span v-for="item in cinematographyItems(shot.cinematography)" :key="item">{{ item }}</span>
                    </div>
                  </section>

                  <section v-if="shot.on_screen_text.length" class="shot-detail-block">
                    <h4>画面文字</h4>
                    <div class="screen-text-list">
                      <article v-for="(item, index) in shot.on_screen_text" :key="`${shot.ordinal}-screen-${index}`">
                        <span>{{ timelineTime(item.start_us) }}</span>
                        <p>{{ item.text }}</p>
                      </article>
                    </div>
                  </section>
                </div>
              </div>
            </article>
          </div>
        </section>
      </main>
    </div>
  </section>
</template>

<style scoped>
.scene-timeline-results-v1 {
  min-height: 0;
  display: grid;
  gap: 12px;
  color: #263650;
}

.timeline-topbar {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: center;
  border: 1px solid #dfe5ef;
  border-radius: 14px;
  padding: 12px 14px;
  background: #fff;
  box-shadow: 0 6px 22px rgba(42, 59, 90, .04);
}
.timeline-topbar > div { min-width: 0; display: grid; gap: 3px; }
.timeline-topbar strong { overflow: hidden; color: #30435f; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.timeline-topbar span { color: #8190a4; font-size: 11px; }
.timeline-check-pill { flex: none; border-radius: 999px; padding: 6px 9px; background: #fff5dc; color: #96630e !important; font-weight: 800; }

.timeline-warning-list {
  display: grid;
  gap: 5px;
  border: 1px solid #eedca7;
  border-radius: 11px;
  padding: 9px 12px;
  background: #fffaf0;
  color: #805f20;
  font-size: 11px;
}
.timeline-alert,
.timeline-loading,
.timeline-empty { border: 1px solid #dfe5ef; border-radius: 13px; padding: 16px; background: #fff; }
.timeline-alert.danger { border-color: #efcccc; background: #fff4f4; color: #a34747; }
.timeline-loading { display: flex; gap: 8px; align-items: center; color: #6d7b90; font-size: 12px; }
.timeline-loading > span { width: 8px; height: 8px; border-radius: 50%; background: #5d82d6; box-shadow: 0 0 0 4px rgba(93, 130, 214, .12); }
.timeline-empty { display: grid; gap: 5px; place-items: center; min-height: 180px; text-align: center; }
.timeline-empty strong { color: #40516d; font-size: 14px; }
.timeline-empty p { margin: 0; color: #8995a7; font-size: 11px; }

.timeline-layout {
  min-height: 0;
  display: grid;
  grid-template-columns: 210px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}
.scene-navigator {
  position: sticky;
  top: 8px;
  max-height: calc(100vh - 170px);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  border: 1px solid #dfe5ef;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 6px 20px rgba(39, 55, 84, .035);
}
.scene-navigator > header { display: flex; justify-content: space-between; align-items: center; padding: 11px 12px; border-bottom: 1px solid #edf0f5; }
.scene-navigator > header strong { color: #40516c; font-size: 12px; }
.scene-navigator > header span { min-width: 24px; border-radius: 999px; padding: 3px 6px; background: #eef3fb; color: #657b9f; font-size: 10px; font-weight: 800; text-align: center; }
.scene-nav-list { min-height: 0; display: grid; gap: 5px; overflow: auto; padding: 7px; }
.scene-nav-item {
  width: 100%;
  display: grid;
  gap: 4px;
  border: 1px solid transparent;
  border-radius: 10px;
  padding: 9px 10px;
  background: transparent;
  color: #66758b;
  cursor: pointer;
  text-align: left;
}
.scene-nav-item:hover { background: #f7f9fc; }
.scene-nav-item.active { border-color: #b9ccef; background: #eef4ff; box-shadow: inset 3px 0 0 #5d82d6; }
.scene-nav-item > span { color: #909bad; font-size: 9px; font-weight: 850; letter-spacing: .03em; }
.scene-nav-item > strong { color: #3f506c; font-size: 12px; line-height: 1.4; }
.scene-nav-item > small { color: #8a96a7; font-size: 9px; }

.scene-reading-pane { min-width: 0; display: grid; gap: 12px; }
.scene-hero {
  display: grid;
  gap: 9px;
  border: 1px solid #dce5f2;
  border-radius: 16px;
  padding: 18px 20px;
  background: linear-gradient(145deg, #f8fbff 0%, #fff 60%);
  box-shadow: 0 8px 28px rgba(43, 66, 107, .05);
}
.scene-eyebrow { color: #6782af; font-size: 10px; font-weight: 900; letter-spacing: .08em; }
.scene-hero h2 { margin: 0; color: #263c5d; font-size: 22px; line-height: 1.2; }
.scene-story { max-width: 900px; margin: 0; color: #455874; font-size: 13px; line-height: 1.8; }
.scene-meta-row { display: flex; flex-wrap: wrap; gap: 6px; }
.scene-meta-row span { border-radius: 999px; padding: 5px 8px; background: #edf3fb; color: #587099; font-size: 10px; font-weight: 750; }
.scene-environment { margin: 0; border-left: 3px solid #cfdaea; padding-left: 9px; color: #78869a; font-size: 11px; line-height: 1.65; }

.scene-people-card { border: 1px solid #dfe5ef; border-radius: 14px; padding: 12px 14px; background: #fff; }
.scene-people-card > header { display: flex; gap: 8px; align-items: baseline; margin-bottom: 10px; }
.scene-people-card > header strong { color: #3e506c; font-size: 12px; }
.scene-people-card > header span { color: #8a96a7; font-size: 10px; }
.scene-people-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 8px; }
.scene-people-list article { min-width: 0; display: flex; gap: 10px; align-items: flex-start; border: 1px solid #edf0f5; border-radius: 10px; padding: 9px 10px; background: #fbfcfe; }
.person-avatar { flex: none; width: 30px; height: 30px; display: grid; place-items: center; border-radius: 50%; background: #eaf1fd; color: #5e78a6; font-size: 10px; font-weight: 900; }
.scene-people-list article > div { min-width: 0; display: grid; gap: 3px; }
.scene-people-list strong { color: #40516c; font-size: 11px; }
.scene-people-list p { margin: 0; color: #7d899b; font-size: 10px; line-height: 1.55; }

.scene-shots-section { display: grid; gap: 9px; }
.shots-section-head { display: flex; justify-content: space-between; align-items: end; padding: 0 2px; }
.shots-section-head > div { display: flex; gap: 8px; align-items: baseline; }
.shots-section-head strong { color: #354965; font-size: 13px; }
.shots-section-head span { color: #8a96a7; font-size: 10px; }
.shot-card-list { display: grid; gap: 10px; }
.timeline-shot-card { overflow: hidden; border: 1px solid #dfe5ef; border-radius: 15px; background: #fff; box-shadow: 0 6px 22px rgba(42, 59, 90, .035); }
.shot-card-head { display: flex; justify-content: space-between; gap: 10px; align-items: center; border-bottom: 1px solid #edf0f5; padding: 9px 12px; background: #fbfcfe; }
.shot-card-head > div { display: flex; gap: 9px; align-items: baseline; }
.shot-card-head span { color: #4f6588; font-size: 11px; font-weight: 900; }
.shot-card-head strong { color: #7b8798; font-size: 10px; font-weight: 700; }
.shot-card-head small { color: #8793a4; font-size: 9px; }
.shot-card-body { display: grid; grid-template-columns: minmax(260px, 34%) minmax(0, 1fr); gap: 0; }

.shot-media { position: relative; min-height: 205px; display: grid; place-items: stretch; overflow: hidden; border-right: 1px solid #edf0f5; background: #111a27; }
.shot-media video,
.shot-preview-button,
.shot-preview-static { width: 100%; min-height: 205px; aspect-ratio: 16 / 9; }
.shot-media video { display: block; background: #0c1119; object-fit: contain; }
.shot-preview-button { position: relative; border: 0; padding: 0; background: #111a27; cursor: pointer; overflow: hidden; }
.shot-preview-button img,
.shot-preview-static img { width: 100%; height: 100%; display: block; object-fit: cover; }
.shot-preview-button::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, transparent 45%, rgba(8, 14, 24, .62)); }
.shot-preview-button i { position: absolute; z-index: 1; right: 10px; bottom: 9px; border-radius: 999px; padding: 6px 9px; background: rgba(255, 255, 255, .92); color: #344c72; font-size: 10px; font-style: normal; font-weight: 900; }
.shot-preview-placeholder { min-height: 205px; display: grid; place-items: center; color: #7f8da3; font-size: 10px; }
.close-video-button { position: absolute; top: 8px; right: 8px; border: 1px solid rgba(255, 255, 255, .4); border-radius: 999px; padding: 5px 8px; background: rgba(17, 26, 39, .72); color: #fff; cursor: pointer; font-size: 9px; }

.shot-information { min-width: 0; display: grid; align-content: start; gap: 11px; padding: 13px 14px 14px; }
.shot-primary-description { display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 8px; align-items: start; }
.shot-primary-description > span,
.shot-person-row > span { color: #8a96a7; font-size: 10px; font-weight: 850; }
.shot-primary-description p { margin: 0; color: #30445f; font-size: 13px; font-weight: 650; line-height: 1.7; }
.shot-person-row { display: grid; grid-template-columns: 38px minmax(0, 1fr); gap: 8px; align-items: start; }
.shot-person-row > div { display: flex; flex-wrap: wrap; gap: 5px; }
.shot-person-row b { border-radius: 999px; padding: 4px 7px; background: #eef4ff; color: #5470a1; font-size: 9px; }
.shot-detail-block { display: grid; gap: 7px; border-top: 1px solid #edf0f5; padding-top: 9px; }
.shot-detail-block h4 { margin: 0; color: #718097; font-size: 10px; font-weight: 900; }
.shot-detail-block ul { display: grid; gap: 5px; margin: 0; padding-left: 17px; color: #4b5d76; font-size: 11px; line-height: 1.6; }

.dialogue-list { display: grid; gap: 6px; }
.dialogue-list article { display: grid; gap: 3px; border-radius: 9px; padding: 8px 9px; background: #f7f9fc; }
.dialogue-list header { display: flex; justify-content: space-between; gap: 10px; }
.dialogue-list strong { color: #526b94; font-size: 10px; }
.dialogue-list span { color: #9aa4b3; font-size: 9px; }
.dialogue-list p { margin: 0; color: #364a65; font-size: 12px; line-height: 1.65; }
.prop-list { display: flex; flex-wrap: wrap; gap: 6px; }
.prop-list article { display: flex; gap: 5px; align-items: center; border: 1px solid #e1e7ef; border-radius: 8px; padding: 5px 7px; background: #fafbfd; }
.prop-list strong { color: #56677f; font-size: 10px; }
.prop-list span { color: #8a95a6; font-size: 9px; }
.cinematography-list { display: flex; flex-wrap: wrap; gap: 5px; }
.cinematography-list span { border-radius: 7px; padding: 5px 7px; background: #f0f3f7; color: #657289; font-size: 9px; }
.screen-text-list { display: grid; gap: 5px; }
.screen-text-list article { display: grid; grid-template-columns: 50px minmax(0, 1fr); gap: 8px; }
.screen-text-list span { color: #99a3b1; font-size: 9px; }
.screen-text-list p { margin: 0; color: #526078; font-size: 10px; line-height: 1.55; }

@media (max-width: 980px) {
  .timeline-layout { grid-template-columns: 180px minmax(0, 1fr); }
  .shot-card-body { grid-template-columns: 1fr; }
  .shot-media { min-height: 0; border-right: 0; border-bottom: 1px solid #edf0f5; }
}

@media (max-width: 720px) {
  .timeline-layout { grid-template-columns: 1fr; }
  .scene-navigator { position: static; max-height: none; }
  .scene-nav-list { display: flex; overflow-x: auto; }
  .scene-nav-item { min-width: 180px; }
  .scene-hero { padding: 15px; }
  .scene-hero h2 { font-size: 19px; }
}

@media (max-width: 520px) {
  .timeline-topbar { align-items: flex-start; flex-direction: column; }
  .shot-card-head > div { display: grid; gap: 2px; }
  .scene-people-list { grid-template-columns: 1fr; }
  .shot-information { padding: 12px; }
  .shot-primary-description,
  .shot-person-row { grid-template-columns: 1fr; gap: 4px; }
}
</style>
