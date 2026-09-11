<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getProject, listProjectTasks } from '@/features/projects/api'
import {
  getReplicaTargetBible,
  startReplicaTargetBible,
  type PreservationLock,
  type ReplicaTargetBibleRead,
} from '@/features/projects/targetBible'
import type { ProjectRead, TaskRead } from '@/features/projects/types'

type TargetSection = 'overview' | 'characters' | 'scenes' | 'props' | 'rules'
type LockGroupId = 'story' | 'rhythm' | 'shots'

const route = useRoute()
const project = ref<ProjectRead | null>(null)
const result = ref<ReplicaTargetBibleRead | null>(null)
const activeTask = ref<TaskRead | null>(null)
const loading = ref(false)
const starting = ref(false)
const errorMessage = ref('')
const activeSection = ref<TargetSection>('overview')
let pollTimer: number | null = null

const projectId = computed(() => String(route.params.id || ''))
const visible = computed(() => project.value?.project_type === 'REPLICA')
const statusText = computed(() => {
  if (activeTask.value && ['queued', 'running', 'interrupted'].includes(activeTask.value.status)) {
    return `正在生成目标设定 ${activeTask.value.progress_percent}%`
  }
  if (!result.value || result.value.status === 'NOT_BUILT') return '尚未生成目标设定'
  if (result.value.status === 'STALE') return '原片或目标配置已有更新，需要重新生成目标设定'
  return '目标设定已就绪'
})
const actionLabel = computed(() => result.value?.status === 'STALE' ? '重新生成目标设定' : '生成目标设定')
const showAction = computed(() => {
  if (starting.value) return false
  if (activeTask.value && ['queued', 'running'].includes(activeTask.value.status)) return false
  return !result.value || result.value.status !== 'CURRENT'
})
const plan = computed(() => result.value?.adaptation_plan.content ?? null)
const bible = computed(() => result.value?.target_bible.content ?? null)

const regionLabels: Record<string, string> = {
  US: '美国',
  UK: '英国',
  JP: '日本',
  KR: '韩国',
  CA: '加拿大',
  AU: '澳大利亚',
}
const languageLabels: Record<string, string> = {
  'en-US': 'English (US)',
  'en-GB': 'English (UK)',
  'ja-JP': '日本語',
  'ko-KR': '한국어',
  'zh-CN': '简体中文',
}
const sceneStrategyLabels: Record<string, string> = {
  MIXED: '混合本土化',
  PRESERVE: '保留原场景',
  LOCALIZE: '完整本土化',
}
const lockLabels: Record<string, string> = {
  STORY_MAINLINE: '故事主线',
  HOOK: '开场钩子',
  CONFLICT: '核心冲突',
  REVERSAL: '反转',
  INFORMATION_REVEAL: '信息揭示',
  EMOTIONAL_PEAK: '情绪峰值',
  PAYOFF: '回报 / 爽点',
  CLIFFHANGER: '结尾悬念',
  STORY_BEAT_TIMING: '剧情节拍',
  SHOT_RHYTHM: '镜头节奏',
  SCENE_ORDER: '场景顺序',
  SHOT_LOGIC: '镜头顺序',
  ACTION_RHYTHM: '动作与对白节奏',
}

const storyLockCategories = new Set([
  'STORY_MAINLINE', 'HOOK', 'CONFLICT', 'REVERSAL', 'INFORMATION_REVEAL', 'EMOTIONAL_PEAK', 'PAYOFF', 'CLIFFHANGER',
])
const rhythmLockCategories = new Set(['STORY_BEAT_TIMING', 'SHOT_RHYTHM', 'ACTION_RHYTHM'])
const shotLockCategories = new Set(['SCENE_ORDER', 'SHOT_LOGIC'])

const targetRegionLabel = computed(() => {
  const value = bible.value?.target_region || project.value?.target_region || ''
  return regionLabels[value] || value
})
const targetLanguageLabel = computed(() => {
  const value = bible.value?.target_language || project.value?.target_language || ''
  return languageLabels[value] || value
})
const sceneStrategyLabel = computed(() => {
  const value = plan.value?.scene_strategy || project.value?.scene_strategy || ''
  return sceneStrategyLabels[value] || value
})
const lockGroups = computed(() => {
  const locks = plan.value?.preservation_locks ?? []
  const groups: Array<{ id: LockGroupId; title: string; description: string; items: PreservationLock[] }> = [
    {
      id: 'story',
      title: '故事锁定',
      description: '主线、冲突、反转、情绪峰值与结尾悬念保持原片叙事功能和顺序。',
      items: locks.filter((item) => storyLockCategories.has(item.category)),
    },
    {
      id: 'rhythm',
      title: '节奏锁定',
      description: '剧情节拍、镜头节奏和动作 / 对白反应节奏保持原片基线。',
      items: locks.filter((item) => rhythmLockCategories.has(item.category)),
    },
    {
      id: 'shots',
      title: '镜头与场次锁定',
      description: '场次和镜头只做目标地区表达替换，不新增、删除、合并或重排。',
      items: locks.filter((item) => shotLockCategories.has(item.category)),
    },
  ]
  return groups.filter((group) => group.items.length > 0)
})
const targetTabs = computed(() => [
  { id: 'overview' as const, label: '概览', count: null },
  { id: 'characters' as const, label: '人物', count: bible.value?.characters.length ?? 0 },
  { id: 'scenes' as const, label: '场景', count: bible.value?.scenes.length ?? 0 },
  { id: 'props' as const, label: '道具', count: bible.value?.props.length ?? 0 },
  { id: 'rules' as const, label: '连续性', count: null },
])

function lockLabel(category: string): string {
  return lockLabels[category] || category.replace(/_/g, ' ')
}

function lockSummary(item: PreservationLock): string {
  if (item.category === 'SCENE_ORDER') return '场景连续顺序已锁定，目标地区替换不会改变场次先后关系。'
  if (item.category === 'SHOT_LOGIC') {
    const count = item.source_summary.match(/(\d+)\s*(?:个\s*)?(?:Source\s*)?Shot/i)?.[1]
    return count ? `${count} 个镜头的顺序、镜头功能与反应链已锁定。` : '镜头顺序、镜头功能与反应链已锁定。'
  }
  return item.source_summary
}

function lockConstraint(item: PreservationLock): string {
  if (item.category === 'SCENE_ORDER') return '保持原片场次连续顺序，本土化只替换场景语境。'
  if (item.category === 'SHOT_LOGIC') return '保持原片镜头顺序、镜头功能与反应链，不新增、删除或重排镜头。'
  if (item.category === 'STORY_BEAT_TIMING') return '保持剧情节拍的相对时间位置，后续只做必要的最小时间适配。'
  return item.constraint
}

function clearPoll() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

async function refreshResult() {
  if (!projectId.value || !visible.value) return
  result.value = await getReplicaTargetBible(projectId.value)
}

async function pollTask() {
  if (!activeTask.value || !projectId.value) return
  const tasks = await listProjectTasks(projectId.value)
  const current = tasks.find((item) => item.id === activeTask.value?.id)
  if (!current) return
  activeTask.value = current
  if (current.status === 'succeeded') {
    clearPoll()
    await refreshResult()
  } else if (current.status === 'failed' || current.status === 'cancelled') {
    clearPoll()
    errorMessage.value = current.last_error || '目标设定生成失败，请重试。'
    await refreshResult()
  }
}

function beginPoll() {
  clearPoll()
  pollTimer = window.setInterval(() => {
    void pollTask()
  }, 1500)
}

async function load() {
  clearPoll()
  result.value = null
  activeTask.value = null
  activeSection.value = 'overview'
  errorMessage.value = ''
  if (!projectId.value) return
  loading.value = true
  try {
    project.value = await getProject(projectId.value)
    if (project.value.project_type === 'REPLICA') {
      await refreshResult()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标设定加载失败。'
  } finally {
    loading.value = false
  }
}

async function start() {
  if (!projectId.value || !visible.value) return
  starting.value = true
  errorMessage.value = ''
  try {
    const key = typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `target-bible-${Date.now()}`
    activeTask.value = await startReplicaTargetBible(projectId.value, key)
    if (activeTask.value.status === 'succeeded') {
      await refreshResult()
    } else if (activeTask.value.status === 'failed') {
      errorMessage.value = activeTask.value.last_error || '目标设定生成失败，请重试。'
    } else {
      beginPoll()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '目标设定生成失败。'
  } finally {
    starting.value = false
  }
}

watch(projectId, () => {
  void load()
}, { immediate: true })

onBeforeUnmount(clearPoll)
</script>

<template>
  <section v-if="visible" class="target-bible-workspace" data-testid="target-bible-workspace">
    <div class="target-header">
      <div>
        <p class="eyebrow">目标版本</p>
        <h2>目标设定</h2>
        <p class="target-subtitle">保留原片故事与节奏，把人物、场景、道具和文化语境转换成适合目标地区的版本。</p>
      </div>
      <div class="target-actions">
        <span class="status-pill" :class="result?.status?.toLowerCase()">{{ statusText }}</span>
        <button v-if="showAction" type="button" class="primary-action" :disabled="loading || starting" @click="start">
          {{ starting ? '正在启动…' : actionLabel }}
        </button>
      </div>
    </div>

    <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
    <p v-if="loading" class="empty-state">正在读取目标设定…</p>

    <template v-else-if="bible && plan">
      <section class="target-hero">
        <div class="version-line">
          <strong>{{ targetRegionLabel }}</strong>
          <span>·</span>
          <strong>{{ targetLanguageLabel }}</strong>
          <span>·</span>
          <strong>{{ sceneStrategyLabel }}</strong>
        </div>
        <p>故事和节奏保持原片基线，人物、场景、道具与文化表达按目标地区重新设计。</p>
        <div class="quick-facts">
          <span>{{ bible.characters.length }} 位人物</span>
          <span>{{ bible.scenes.length }} 个场景</span>
          <span>{{ bible.props.length }} 个关键道具</span>
          <span>{{ plan.preservation_locks.length }} 项保留规则</span>
        </div>
        <details class="long-copy">
          <summary>查看完整本土化说明</summary>
          <p>{{ bible.adaptation_summary }}</p>
        </details>
      </section>

      <nav class="target-tabs" aria-label="目标设定内容">
        <button
          v-for="tab in targetTabs"
          :key="tab.id"
          type="button"
          :class="{ active: activeSection === tab.id }"
          @click="activeSection = tab.id"
        >
          {{ tab.label }}<span v-if="tab.count !== null"> {{ tab.count }}</span>
        </button>
      </nav>

      <div v-if="activeSection === 'overview'" class="section-stack" data-testid="target-overview">
        <section class="summary-card">
          <div class="section-heading">
            <div><p class="section-kicker">改编边界</p><h3>必须保留</h3></div>
            <p>这些内容来自已确认的原片故事与节奏，本土化不会重写它们。</p>
          </div>
          <div class="lock-groups">
            <details v-for="group in lockGroups" :key="group.id" class="lock-group" :open="group.id === 'story'">
              <summary>
                <span><strong>{{ group.title }}</strong><small>{{ group.description }}</small></span>
                <em>{{ group.items.length }} 项</em>
              </summary>
              <div class="lock-list">
                <article v-for="item in group.items" :key="item.lock_id" class="lock-row">
                  <strong>{{ lockLabel(item.category) }}</strong>
                  <p>{{ lockSummary(item) }}</p>
                  <small>{{ lockConstraint(item) }}</small>
                </article>
              </div>
            </details>
          </div>
        </section>

        <section class="summary-card world-card">
          <div class="section-heading compact">
            <div><p class="section-kicker">背景与文化</p><h3>目标世界</h3></div>
          </div>
          <p class="world-summary">{{ bible.target_world.setting_summary }}</p>
          <div class="context-grid">
            <details>
              <summary>文化语境</summary>
              <p>{{ bible.target_world.cultural_context }}</p>
            </details>
            <details>
              <summary>社会语境</summary>
              <p>{{ bible.target_world.social_context }}</p>
            </details>
          </div>
          <ul class="principles">
            <li v-for="item in bible.target_world.localization_principles" :key="item">{{ item }}</li>
          </ul>
          <details class="long-copy visual-copy">
            <summary>查看完整视觉方向</summary>
            <p>{{ bible.visual_style }}</p>
          </details>
        </section>
      </div>

      <section v-else-if="activeSection === 'characters'" class="entity-section" data-testid="target-characters">
        <div class="section-heading compact"><div><p class="section-kicker">角色本土化</p><h3>人物</h3></div></div>
        <div class="entity-grid">
          <article v-for="item in bible.characters" :key="item.target_character_id" class="entity-card">
            <p class="source-label">原片：{{ item.source_display_name }}</p>
            <h4>{{ item.display_name }}</h4>
            <p>{{ item.localized_identity }}</p>
            <details>
              <summary>外形与连续性</summary>
              <p><strong>外形方向：</strong>{{ item.appearance_direction }}</p>
              <ul v-if="item.personality_constraints.length">
                <li v-for="rule in item.personality_constraints" :key="rule">{{ rule }}</li>
              </ul>
              <ul v-if="item.continuity_rules.length">
                <li v-for="rule in item.continuity_rules" :key="rule">{{ rule }}</li>
              </ul>
            </details>
          </article>
        </div>
      </section>

      <section v-else-if="activeSection === 'scenes'" class="entity-section" data-testid="target-scenes">
        <div class="section-heading compact"><div><p class="section-kicker">环境本土化</p><h3>场景</h3></div></div>
        <div class="entity-grid">
          <article v-for="item in bible.scenes" :key="item.target_scene_id" class="entity-card">
            <p class="source-label">原片：{{ item.source_display_name }}</p>
            <h4>{{ item.display_name }}</h4>
            <p>{{ item.localized_setting }}</p>
            <details>
              <summary>视觉与连续性</summary>
              <p><strong>视觉方向：</strong>{{ item.visual_direction }}</p>
              <ul v-if="item.continuity_rules.length">
                <li v-for="rule in item.continuity_rules" :key="rule">{{ rule }}</li>
              </ul>
            </details>
          </article>
        </div>
      </section>

      <section v-else-if="activeSection === 'props'" class="entity-section" data-testid="target-props">
        <div class="section-heading compact"><div><p class="section-kicker">物件本土化</p><h3>关键道具</h3></div></div>
        <div class="entity-grid">
          <article v-for="item in bible.props" :key="item.target_prop_id" class="entity-card">
            <p class="source-label">原片：{{ item.source_display_name }}</p>
            <h4>{{ item.display_name }}</h4>
            <p>{{ item.localized_form }}</p>
            <details v-if="item.continuity_rules.length">
              <summary>连续性要求</summary>
              <ul><li v-for="rule in item.continuity_rules" :key="rule">{{ rule }}</li></ul>
            </details>
          </article>
        </div>
      </section>

      <section v-else class="summary-card rules-card" data-testid="target-rules">
        <div class="section-heading compact"><div><p class="section-kicker">跨场一致性</p><h3>连续性与表达规则</h3></div></div>
        <div class="rules-columns">
          <div>
            <h4>连续性</h4>
            <ul><li v-for="item in bible.continuity_rules" :key="item">{{ item }}</li></ul>
          </div>
          <div>
            <h4>后续对白风格</h4>
            <ul><li v-for="item in bible.dialogue_style_rules" :key="item">{{ item }}</li></ul>
          </div>
        </div>
      </section>
    </template>

    <div v-else-if="!loading" class="empty-state">
      <p>原片解析完成后，可以基于已确认的故事和节奏生成目标地区的人物、场景、道具与文化设定。</p>
    </div>
  </section>
</template>

<style scoped>
.target-bible-workspace {
  margin: 28px auto 0;
  max-width: 1240px;
  padding: 24px;
  border: 1px solid var(--border-color, #e5e7eb);
  border-radius: 18px;
  background: var(--surface-color, #fff);
}
.target-header { display: flex; gap: 24px; justify-content: space-between; align-items: flex-start; }
.eyebrow, .section-kicker { margin: 0 0 4px; font-size: 12px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; opacity: .55; }
h2, h3, h4, p { margin-top: 0; }
.target-subtitle { max-width: 760px; opacity: .7; }
.target-actions { display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }
.status-pill { padding: 6px 10px; border-radius: 999px; background: #f3f4f6; font-size: 13px; white-space: nowrap; }
.status-pill.current { background: #ecfdf5; }
.status-pill.stale { background: #fff7ed; }
.primary-action { border: 0; border-radius: 10px; padding: 10px 16px; font-weight: 700; cursor: pointer; background: #111827; color: #fff; }
.primary-action:disabled { cursor: default; opacity: .55; }
.error-message { margin-top: 16px; padding: 10px 12px; border-radius: 10px; background: #fef2f2; }
.empty-state { margin: 18px 0 0; padding: 22px; border-radius: 12px; background: #f9fafb; opacity: .72; }
.target-hero { margin-top: 22px; padding: 22px; border-radius: 16px; background: #f8fafc; }
.version-line { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; font-size: 18px; }
.target-hero > p { max-width: 760px; margin-bottom: 14px; color: #475569; }
.quick-facts { display: flex; flex-wrap: wrap; gap: 8px; }
.quick-facts span { padding: 6px 10px; border-radius: 999px; background: #fff; border: 1px solid #e5e7eb; font-size: 13px; }
.long-copy { margin-top: 14px; }
details summary { cursor: pointer; font-weight: 700; }
details p { margin-top: 10px; line-height: 1.65; }
.target-tabs { display: flex; gap: 6px; margin-top: 20px; padding: 5px; border-radius: 12px; background: #f3f4f6; overflow-x: auto; }
.target-tabs button { flex: 0 0 auto; border: 0; border-radius: 9px; padding: 9px 14px; background: transparent; cursor: pointer; font-weight: 700; color: #64748b; }
.target-tabs button.active { background: #fff; color: #111827; box-shadow: 0 1px 3px rgb(15 23 42 / 10%); }
.section-stack { display: grid; gap: 18px; }
.summary-card, .entity-section { margin-top: 20px; padding: 20px; border: 1px solid #eef0f3; border-radius: 16px; }
.section-heading { display: flex; justify-content: space-between; gap: 24px; align-items: flex-start; margin-bottom: 14px; }
.section-heading h3 { margin-bottom: 0; }
.section-heading > p { max-width: 580px; margin-bottom: 0; color: #64748b; }
.section-heading.compact { margin-bottom: 16px; }
.lock-groups { display: grid; gap: 10px; }
.lock-group { border: 1px solid #e5e7eb; border-radius: 12px; background: #fafafa; overflow: hidden; }
.lock-group > summary { display: flex; justify-content: space-between; gap: 16px; padding: 14px 16px; list-style: none; }
.lock-group > summary::-webkit-details-marker { display: none; }
.lock-group > summary span { display: grid; gap: 3px; }
.lock-group > summary small { color: #64748b; font-weight: 400; }
.lock-group > summary em { font-style: normal; color: #64748b; white-space: nowrap; }
.lock-list { border-top: 1px solid #e5e7eb; }
.lock-row { display: grid; grid-template-columns: minmax(110px, 150px) minmax(0, 1fr); gap: 4px 18px; padding: 13px 16px; border-bottom: 1px solid #eef0f3; }
.lock-row:last-child { border-bottom: 0; }
.lock-row strong { grid-row: 1 / 3; }
.lock-row p { margin-bottom: 2px; line-height: 1.55; }
.lock-row small { color: #64748b; line-height: 1.5; }
.world-summary { max-width: 900px; line-height: 1.7; }
.context-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin-top: 14px; }
.context-grid details { padding: 12px 14px; border-radius: 12px; background: #f8fafc; }
.principles { margin: 16px 0 0; padding-left: 20px; columns: 2; column-gap: 28px; }
.principles li { break-inside: avoid; margin-bottom: 7px; }
.visual-copy { padding-top: 14px; border-top: 1px solid #eef0f3; }
.entity-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }
.entity-card { padding: 16px; border-radius: 14px; background: #f8fafc; min-width: 0; }
.source-label { margin-bottom: 5px; color: #64748b; font-size: 13px; }
.entity-card h4 { margin-bottom: 8px; font-size: 19px; }
.entity-card > p:not(.source-label) { line-height: 1.6; }
.entity-card details { margin-top: 12px; padding-top: 10px; border-top: 1px solid #e5e7eb; }
ul { margin: 8px 0 0; padding-left: 20px; }
li { line-height: 1.55; }
.rules-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
.rules-columns > div { padding: 16px; border-radius: 12px; background: #f8fafc; }
@media (max-width: 720px) {
  .target-bible-workspace { padding: 18px; }
  .target-header, .section-heading { flex-direction: column; }
  .target-actions { align-items: stretch; width: 100%; }
  .context-grid, .rules-columns { grid-template-columns: 1fr; }
  .principles { columns: 1; }
  .lock-row { grid-template-columns: 1fr; }
  .lock-row strong { grid-row: auto; }
}
</style>
