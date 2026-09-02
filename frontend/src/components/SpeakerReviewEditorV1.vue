<script setup lang="ts">
import { computed, ref } from 'vue'
import { remakeApi } from '../api/remake'
import type { ReviewIssue } from '../types/remake'

interface SpeakerCandidate {
  person_key: string
  display_name?: string | null
  appearance?: string | null
  character_id?: string | null
  character_name?: string | null
  cover_url?: string | null
  visible_in_shot?: boolean
  in_performance?: boolean
}

interface CurrentSpeaker {
  person_key: string
  display_name?: string | null
  character_id?: string | null
  character_name?: string | null
}

interface SpeakerSuggestion {
  dialogue_key: string
  source_text: string
  dialogue_start_us?: number
  dialogue_end_us?: number
  current_speakers?: CurrentSpeaker[]
  candidate_people?: SpeakerCandidate[]
  episode_order?: number
  episode_title?: string
  scene_key?: string
  scene_ordinal?: number
  scene_title?: string | null
  shot_key?: string
  shot_ordinal?: number
  shot_start_us?: number
  shot_end_us?: number
  thumbnail_url?: string | null
  reference_url?: string | null
  automatic_resolution_method?: string | null
  automatic_resolution_reason?: string | null
}

interface SpeakerCard {
  issue: ReviewIssue
  info: SpeakerSuggestion
}

const props = defineProps<{
  issues: ReviewIssue[]
}>()

const emit = defineEmits<{
  changed: []
  openAssetEditor: []
}>()

const selectedByIssue = ref<Record<string, string>>({})
const expandedVideo = ref<Record<string, boolean>>({})
const savingIssueId = ref('')
const errors = ref<Record<string, string>>({})

const speakerIssues = computed(() => props.issues.filter((item) => item.issue_type === 'SPEAKER'))

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function suggestion(issue: ReviewIssue): SpeakerSuggestion | null {
  if (!isRecord(issue.ai_suggestion)) return null
  const value = issue.ai_suggestion
  if (typeof value.dialogue_key !== 'string' || typeof value.source_text !== 'string') return null
  return value as unknown as SpeakerSuggestion
}

const cards = computed<SpeakerCard[]>(() => speakerIssues.value.flatMap((issue) => {
  const info = suggestion(issue)
  return info ? [{ issue, info }] : []
}))
const legacyIssues = computed(() => speakerIssues.value.filter((issue) => suggestion(issue) === null))

function candidates(info: SpeakerSuggestion): SpeakerCandidate[] {
  return info.candidate_people?.filter((item) => item?.person_key) ?? []
}

function selectedPersonKey(issue: ReviewIssue, info: SpeakerSuggestion): string {
  if (selectedByIssue.value[issue.id]) return selectedByIssue.value[issue.id]
  const current = info.current_speakers ?? []
  return current.length === 1 ? current[0].person_key : ''
}

function choose(issue: ReviewIssue, personKey: string): void {
  selectedByIssue.value = { ...selectedByIssue.value, [issue.id]: personKey }
  errors.value = { ...errors.value, [issue.id]: '' }
}

function toggleVideo(issueId: string): void {
  expandedVideo.value = { ...expandedVideo.value, [issueId]: !expandedVideo.value[issueId] }
}

function formatTime(us?: number): string {
  const totalMs = Math.max(0, Math.round(Number(us || 0) / 1000))
  const minutes = Math.floor(totalMs / 60_000)
  const seconds = Math.floor((totalMs % 60_000) / 1000)
  const millis = totalMs % 1000
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}.${String(millis).padStart(3, '0')}`
}

function locationLabel(info: SpeakerSuggestion): string {
  const episode = info.episode_order ? `第 ${String(info.episode_order).padStart(2, '0')} 集` : (info.episode_title || '当前剧集')
  const scene = info.scene_title || (info.scene_ordinal ? `场景 ${info.scene_ordinal}` : '当前场景')
  const shot = info.shot_ordinal ? `镜头 ${info.shot_ordinal}` : '当前镜头'
  return `${episode} · ${scene} · ${shot}`
}

function personTitle(person: SpeakerCandidate): string {
  return person.character_name || person.display_name || '未命名人物'
}

async function save(issue: ReviewIssue, info: SpeakerSuggestion): Promise<void> {
  const personKey = selectedPersonKey(issue, info)
  if (!personKey || savingIssueId.value) {
    errors.value = { ...errors.value, [issue.id]: '请先选择这句对白真正的说话人' }
    return
  }
  savingIssueId.value = issue.id
  errors.value = { ...errors.value, [issue.id]: '' }
  try {
    await remakeApi.resolveSpeakerReviewIssue(issue.id, personKey)
    emit('changed')
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('studio-project-truth-changed', {
        detail: { project_id: issue.project_id },
      }))
    }
  } catch (err) {
    errors.value = {
      ...errors.value,
      [issue.id]: err instanceof Error ? err.message : '说话人保存失败',
    }
  } finally {
    savingIssueId.value = ''
  }
}
</script>

<template>
  <section v-if="speakerIssues.length" class="speaker-review">
    <header class="section-head">
      <div>
        <small>需要你确认</small>
        <strong>这句台词是谁说的？</strong>
        <p>每一条都已经定位到具体剧集、场景、镜头和对白。可以直接查看对应镜头，选择人物后保存；保存的是原片真实说话人，不是单纯关闭提示。</p>
      </div>
      <span>{{ speakerIssues.length }} 条</span>
    </header>

    <div class="cards">
      <article v-for="card in cards" :key="card.issue.id" class="speaker-card">
        <div class="where">
          <div>
            <small>位置</small>
            <strong>{{ locationLabel(card.info) }}</strong>
            <span>{{ formatTime(card.info.dialogue_start_us) }} – {{ formatTime(card.info.dialogue_end_us) }}</span>
          </div>
          <button v-if="card.info.reference_url" class="ghost" @click="toggleVideo(card.issue.id)">
            {{ expandedVideo[card.issue.id] ? '收起镜头' : '查看对应镜头' }}
          </button>
        </div>

        <div v-if="expandedVideo[card.issue.id] && card.info.reference_url" class="video-wrap">
          <video :src="card.info.reference_url" controls preload="metadata" />
        </div>
        <img v-else-if="card.info.thumbnail_url" class="thumbnail" :src="card.info.thumbnail_url" alt="对应镜头缩略图" />

        <div class="dialogue">
          <small>原对白</small>
          <strong>{{ card.info.source_text || '（无文本）' }}</strong>
          <span>{{ card.issue.reason }}</span>
        </div>

        <div class="choice">
          <div class="choice-title">
            <div><small>直接修改</small><strong>选择真正的说话人</strong></div>
            <span v-if="card.info.automatic_resolution_reason">自动判断未通过：{{ card.info.automatic_resolution_reason }}</span>
          </div>

          <div v-if="candidates(card.info).length" class="people">
            <button
              v-for="person in candidates(card.info)"
              :key="person.person_key"
              :class="{ selected: selectedPersonKey(card.issue, card.info) === person.person_key }"
              @click="choose(card.issue, person.person_key)"
            >
              <img v-if="person.cover_url" :src="person.cover_url" alt="" />
              <span v-else class="avatar">{{ personTitle(person).slice(0, 1) }}</span>
              <div>
                <strong>{{ personTitle(person) }}</strong>
                <small v-if="person.display_name && person.display_name !== person.character_name">识别名：{{ person.display_name }}</small>
                <small v-if="person.appearance">{{ person.appearance }}</small>
                <p>
                  <i v-if="person.in_performance">表演指向</i>
                  <i v-if="person.visible_in_shot">镜头内</i>
                  <i v-if="!person.character_id" class="warn">尚未归属最终人物</i>
                </p>
              </div>
            </button>
          </div>

          <div v-else class="no-people">
            <span>当前场景没有可直接选择的人物，需要先修正原片人物绑定。</span>
            <button class="ghost" @click="emit('openAssetEditor')">打开人物绑定</button>
          </div>

          <p v-if="errors[card.issue.id]" class="error">{{ errors[card.issue.id] }}</p>
          <div class="save-row">
            <span>选中后会写入 SourceDramaSnapshot，并自动重新判断这条待确认。</span>
            <button
              class="save"
              :disabled="!selectedPersonKey(card.issue, card.info) || savingIssueId === card.issue.id"
              @click="save(card.issue, card.info)"
            >
              {{ savingIssueId === card.issue.id ? '保存中…' : '确认说话人' }}
            </button>
          </div>
        </div>
      </article>

      <article v-for="issue in legacyIssues" :key="issue.id" class="speaker-card legacy">
        <strong>这条旧记录缺少镜头定位信息</strong>
        <span>刷新页面后系统会用当前 SourceDramaSnapshot 自动重建，不需要重新拉片。</span>
      </article>
    </div>
  </section>
</template>

<style scoped>
.speaker-review{overflow:hidden;border:1px solid #d8e2ef;border-radius:13px;background:#fff}.section-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:15px 16px;border-bottom:1px solid #e7ebf1}.section-head>div{display:grid;gap:3px}.section-head small,.where small,.dialogue small,.choice-title small{font-size:9px;color:#8491a2}.section-head strong{font-size:13px;color:#354a65}.section-head p{max-width:900px;margin:0;color:#77869a;font-size:10px;line-height:1.6}.section-head>span{flex:none;padding:5px 9px;border-radius:99px;background:#fff3d7;color:#956412;font-size:9px;font-weight:800}.cards{display:grid;gap:10px;padding:12px}.speaker-card{overflow:hidden;border:1px solid #e2e7ee;border-radius:11px;background:#fbfcfe}.where{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:11px 12px;border-bottom:1px solid #e9edf2;background:#f6f8fb}.where>div{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}.where strong{font-size:11px;color:#344b69}.where span{font-size:9px;color:#8290a2}.ghost{min-height:30px;padding:0 10px;border:1px solid #d3dce8;border-radius:7px;background:#fff;color:#5f7189;font-size:9px;cursor:pointer}.video-wrap{padding:10px 12px;background:#10141b}.video-wrap video{display:block;width:min(100%,760px);max-height:430px;margin:auto;background:#000}.thumbnail{display:block;width:190px;max-height:120px;object-fit:cover;margin:10px 12px 0;border-radius:8px;border:1px solid #dde3eb}.dialogue{display:grid;gap:4px;padding:13px 14px}.dialogue strong{font-size:15px;line-height:1.5;color:#263c59}.dialogue span{font-size:9px;color:#8a6b39}.choice{display:grid;gap:10px;padding:0 14px 14px}.choice-title{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;padding-top:2px;border-top:1px dashed #dfe5ed}.choice-title>div{display:grid;gap:2px;padding-top:10px}.choice-title strong{font-size:11px;color:#3a506d}.choice-title>span{font-size:9px;color:#8a96a7}.people{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:8px}.people>button{display:grid;grid-template-columns:42px minmax(0,1fr);gap:9px;align-items:start;padding:9px;border:1px solid #dce3ec;border-radius:9px;background:#fff;text-align:left;cursor:pointer}.people>button:hover{border-color:#9fb5dc}.people>button.selected{border-color:#527fd1;box-shadow:0 0 0 2px rgba(82,127,209,.12);background:#f3f7ff}.people img,.avatar{width:42px;height:52px;border-radius:7px;object-fit:cover;background:#edf2f8}.avatar{display:grid;place-items:center;color:#607694;font-size:15px;font-weight:800}.people>button>div{min-width:0;display:grid;gap:2px}.people strong{font-size:11px;color:#334a67}.people small{font-size:8px;line-height:1.45;color:#8390a1;overflow:hidden;text-overflow:ellipsis}.people p{display:flex;flex-wrap:wrap;gap:4px;margin:3px 0 0}.people i{padding:2px 5px;border-radius:99px;background:#eaf3ff;color:#4c70a5;font-size:8px;font-style:normal}.people i.warn{background:#fff1df;color:#a36b28}.no-people{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px;border-radius:8px;background:#fff5e7;color:#8c6531;font-size:9px}.error{margin:0;padding:8px 10px;border-radius:7px;background:#fff1f1;color:#a54e4e;font-size:9px}.save-row{display:flex;align-items:center;justify-content:space-between;gap:12px}.save-row>span{font-size:9px;color:#8592a3}.save{min-height:34px;padding:0 13px;border:0;border-radius:7px;background:#3566d6;color:#fff;font-size:9px;font-weight:800;cursor:pointer}.save:disabled{opacity:.45;cursor:not-allowed}.legacy{display:grid;gap:4px;padding:14px}.legacy strong{font-size:11px;color:#624d32}.legacy span{font-size:9px;color:#8a765c}@media(max-width:760px){.section-head,.where,.choice-title,.save-row,.no-people{align-items:stretch;flex-direction:column}.people{grid-template-columns:1fr}.thumbnail{width:calc(100% - 24px);max-height:220px}}
</style>
