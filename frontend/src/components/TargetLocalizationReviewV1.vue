<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { remakeApi } from '../api/remake'
import type {
  SceneLocalizationMapping,
  TargetCharacter,
  TargetDialogue,
  TargetDialogueBundle,
  TargetLocalizationBundle,
} from '../types/remake'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ changed: [] }>()

const bundle = ref<TargetLocalizationBundle | null>(null)
const dialogueBundle = ref<TargetDialogueBundle | null>(null)
const loading = ref(false)
const error = ref('')
const savingId = ref('')
const characterDrafts = reactive<Record<string, { target_name: string; appearance_profile: string; generation_prompt: string }>>({})
const sceneDrafts = reactive<Record<string, { decision: 'KEEP' | 'LOCALIZE'; target_label: string; target_description: string; reason: string }>>({})
const dialogueDrafts = reactive<Record<string, { translated_text: string; localized_text: string; final_text: string }>>({})

const reviewCharacters = computed(() => bundle.value?.target_characters.filter((item) => item.status === 'REVIEW') ?? [])
const reviewScenes = computed(() => bundle.value?.scene_mappings.filter((item) => item.status === 'REVIEW') ?? [])
const reviewDialogues = computed(() => dialogueBundle.value?.dialogues.filter((item) => item.status === 'REVIEW' && item.target_character_id) ?? [])
const hasReview = computed(() => reviewCharacters.value.length + reviewScenes.value.length + reviewDialogues.value.length > 0)

function syncDrafts(): void {
  for (const item of bundle.value?.target_characters ?? []) {
    characterDrafts[item.id] = {
      target_name: item.target_name === '待确认目标角色' ? '' : item.target_name,
      appearance_profile: item.appearance_profile.startsWith('等待本地模型') ? '' : item.appearance_profile,
      generation_prompt: item.generation_prompt.startsWith('等待目标人物') ? '' : item.generation_prompt,
    }
  }
  for (const item of bundle.value?.scene_mappings ?? []) {
    sceneDrafts[item.id] = {
      decision: item.decision === 'LOCALIZE' ? 'LOCALIZE' : 'KEEP',
      target_label: item.target_label ?? '',
      target_description: item.target_description ?? '',
      reason: item.reason ?? '',
    }
  }
  for (const item of dialogueBundle.value?.dialogues ?? []) {
    dialogueDrafts[item.id] = {
      translated_text: item.translated_text ?? '',
      localized_text: item.localized_text ?? '',
      final_text: item.final_text ?? '',
    }
  }
}

async function load(): Promise<void> {
  if (!props.projectId) return
  loading.value = true
  try {
    bundle.value = await remakeApi.getTargetLocalization(props.projectId)
    try {
      dialogueBundle.value = await remakeApi.getTargetDialogue(props.projectId)
    } catch {
      // TargetDialogue may legitimately not exist yet while R4 issues are still being fixed.
      dialogueBundle.value = null
    }
    syncDrafts()
    error.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : '目标人物/场景/对白读取失败'
  } finally {
    loading.value = false
  }
}

async function regenerate(): Promise<void> {
  loading.value = true
  try {
    bundle.value = await remakeApi.generateTargetLocalization(props.projectId)
    dialogueBundle.value = await remakeApi.generateTargetDialogue(props.projectId, true)
    syncDrafts()
    error.value = ''
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '自动重新生成出海方案失败'
  } finally {
    loading.value = false
  }
}

async function refreshDialogueDownstream(): Promise<void> {
  try {
    dialogueBundle.value = await remakeApi.generateTargetDialogue(props.projectId, true)
  } catch {
    // Remaining upstream review items can keep part of TargetDialogue unavailable; the
    // authoritative upstream edit is still saved and the next automatic run will continue.
  }
}

async function saveCharacter(item: TargetCharacter): Promise<void> {
  const draft = characterDrafts[item.id]
  if (!draft?.target_name.trim() || !draft.appearance_profile.trim() || !draft.generation_prompt.trim()) {
    error.value = '目标人物姓名、稳定外观设定和生成描述都必须填写'
    return
  }
  savingId.value = item.id
  try {
    await remakeApi.updateTargetCharacter(item.id, draft)
    await refreshDialogueDownstream()
    await load()
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '目标人物保存失败'
  } finally {
    savingId.value = ''
  }
}

async function removeCharacter(item: TargetCharacter): Promise<void> {
  savingId.value = item.id
  try {
    await remakeApi.deleteTargetCharacter(item.id)
    await regenerate()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '目标人物方案删除失败'
  } finally {
    savingId.value = ''
  }
}

async function saveScene(item: SceneLocalizationMapping): Promise<void> {
  const draft = sceneDrafts[item.id]
  if (!draft) return
  if (draft.decision === 'LOCALIZE' && !draft.target_description.trim()) {
    error.value = '选择“本土化场景”后必须填写目标场景描述'
    return
  }
  savingId.value = item.id
  try {
    await remakeApi.updateSceneLocalization(item.id, {
      decision: draft.decision,
      target_label: draft.decision === 'LOCALIZE' ? draft.target_label.trim() || null : null,
      target_description: draft.decision === 'LOCALIZE' ? draft.target_description.trim() : null,
      reason: draft.reason.trim() || '用户人工确认',
    })
    await load()
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '场景策略保存失败'
  } finally {
    savingId.value = ''
  }
}

async function removeScene(item: SceneLocalizationMapping): Promise<void> {
  savingId.value = item.id
  try {
    await remakeApi.deleteSceneLocalization(item.id)
    await regenerate()
  } catch (err) {
    error.value = err instanceof Error ? err.message : '场景方案删除失败'
  } finally {
    savingId.value = ''
  }
}

async function saveDialogue(item: TargetDialogue): Promise<void> {
  const draft = dialogueDrafts[item.id]
  if (!draft?.final_text.trim()) {
    error.value = '最终目标对白不能为空'
    return
  }
  savingId.value = item.id
  try {
    await remakeApi.updateTargetDialogue(item.id, {
      translated_text: draft.translated_text.trim() || null,
      localized_text: draft.localized_text.trim() || null,
      final_text: draft.final_text.trim(),
    })
    try {
      dialogueBundle.value = await remakeApi.materializeTargetDialogueAudio(props.projectId)
    } catch {
      // TTS runtime unavailable is infrastructure state, not another human-review task.
    }
    await load()
    emit('changed')
  } catch (err) {
    error.value = err instanceof Error ? err.message : '目标对白保存失败'
  } finally {
    savingId.value = ''
  }
}

function sourceDuration(item: TargetDialogue): string {
  const seconds = Math.max(0, item.source_end_us - item.source_start_us) / 1_000_000
  return `${seconds.toFixed(2)}s`
}

watch(() => props.projectId, () => void load())
onMounted(() => void load())
</script>

<template>
  <section v-if="loading || hasReview || error" class="target-review">
    <header>
      <div>
        <small>出海人物 / 场景 / 对白</small>
        <strong>只显示自动方案无法安全确定的内容</strong>
      </div>
      <button :disabled="loading" @click="regenerate">重新自动判断</button>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="loading && !bundle" class="empty">正在读取出海方案…</p>

    <div v-if="reviewCharacters.length" class="group">
      <h3>目标人物 · {{ reviewCharacters.length }}</h3>
      <article v-for="item in reviewCharacters" :key="item.id" class="card">
        <div class="source">
          <small>原人物</small>
          <strong>{{ item.source_character_name }}</strong>
          <span>→ {{ item.target_region }} / {{ item.target_language }}</span>
        </div>
        <label>
          <span>目标人物姓名</span>
          <input v-model="characterDrafts[item.id].target_name" placeholder="例如 Emma Miller" />
        </label>
        <label>
          <span>稳定外观设定</span>
          <textarea v-model="characterDrafts[item.id].appearance_profile" rows="3" placeholder="年龄层、气质、发型、体型、稳定身份特征…" />
        </label>
        <label>
          <span>生成身份描述</span>
          <textarea v-model="characterDrafts[item.id].generation_prompt" rows="3" placeholder="后续人物参考图和 H3 使用的稳定人物描述" />
        </label>
        <div class="actions">
          <button class="danger" :disabled="savingId === item.id" @click="removeCharacter(item)">删除并重算</button>
          <button class="primary" :disabled="savingId === item.id" @click="saveCharacter(item)">确认人物</button>
        </div>
      </article>
    </div>

    <div v-if="reviewScenes.length" class="group">
      <h3>场景策略 · {{ reviewScenes.length }}</h3>
      <article v-for="item in reviewScenes" :key="item.id" class="card">
        <div class="source">
          <small>原场景</small>
          <strong>{{ item.source_scene_name || '未命名原场景' }}</strong>
          <span>项目策略：{{ item.project_policy }}</span>
        </div>
        <div class="decision">
          <button :class="{ active: sceneDrafts[item.id].decision === 'KEEP' }" @click="sceneDrafts[item.id].decision = 'KEEP'">保留原场景</button>
          <button :class="{ active: sceneDrafts[item.id].decision === 'LOCALIZE' }" @click="sceneDrafts[item.id].decision = 'LOCALIZE'">本土化场景</button>
        </div>
        <template v-if="sceneDrafts[item.id].decision === 'LOCALIZE'">
          <label>
            <span>目标场景名称</span>
            <input v-model="sceneDrafts[item.id].target_label" placeholder="例如 American apartment living room" />
          </label>
          <label>
            <span>目标场景描述</span>
            <textarea v-model="sceneDrafts[item.id].target_description" rows="4" placeholder="符合目标地区，同时保持原场景空间功能、人物走位和镜头可执行性" />
          </label>
        </template>
        <label>
          <span>确认说明</span>
          <input v-model="sceneDrafts[item.id].reason" placeholder="可选" />
        </label>
        <div class="actions">
          <button class="danger" :disabled="savingId === item.id" @click="removeScene(item)">删除并重算</button>
          <button class="primary" :disabled="savingId === item.id" @click="saveScene(item)">确认场景</button>
        </div>
      </article>
    </div>

    <div v-if="reviewDialogues.length" class="group">
      <h3>目标对白 · {{ reviewDialogues.length }}</h3>
      <article v-for="item in reviewDialogues" :key="item.id" class="card dialogue-card">
        <div class="source">
          <small>原对白 · 原说话区间 {{ sourceDuration(item) }}</small>
          <strong>{{ item.source_text }}</strong>
          <span>{{ item.target_language }} · {{ item.target_region }} · 当前只确认文本，时长优化由下一阶段自动处理</span>
        </div>
        <label>
          <span>忠实翻译</span>
          <textarea v-model="dialogueDrafts[item.id].translated_text" rows="2" placeholder="保留原剧情事实和信息量" />
        </label>
        <label>
          <span>当地自然表达</span>
          <textarea v-model="dialogueDrafts[item.id].localized_text" rows="2" placeholder="符合目标地区真实说话方式" />
        </label>
        <label>
          <span>最终成片对白</span>
          <textarea v-model="dialogueDrafts[item.id].final_text" rows="3" placeholder="这句将进入 TTS 和后续口型/时长规划" />
        </label>
        <div class="actions">
          <button class="primary" :disabled="savingId === item.id" @click="saveDialogue(item)">确认对白</button>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.target-review { display: grid; gap: 12px; padding: 14px; border: 1px solid #dfe5ed; border-radius: 14px; background: #fff; }
.target-review > header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.target-review > header > div { display: grid; gap: 2px; }
.target-review small { color: #8793a4; font-size: 9px; }
.target-review strong { color: #42536a; font-size: 11px; }
.target-review header button, .actions button, .decision button { min-height: 32px; border: 1px solid #dce2e9; border-radius: 8px; padding: 0 10px; background: #fff; color: #617086; font-size: 9px; cursor: pointer; }
.group { display: grid; gap: 8px; }
.group h3 { margin: 2px 0; color: #506177; font-size: 11px; }
.card { display: grid; gap: 9px; padding: 12px; border: 1px solid #e4e8ee; border-radius: 10px; background: #fbfcfe; }
.dialogue-card { border-color: #e7dcc4; background: #fffdf8; }
.source { display: grid; gap: 2px; }
.source span { color: #8b96a5; font-size: 9px; }
label { display: grid; gap: 4px; }
label span { color: #6f7e91; font-size: 9px; font-weight: 750; }
input, textarea { width: 100%; box-sizing: border-box; border: 1px solid #dce2e9; border-radius: 7px; padding: 8px 9px; background: #fff; color: #405168; font: inherit; font-size: 10px; resize: vertical; }
.decision { display: flex; gap: 7px; }
.decision button.active { border-color: #91abe0; background: #eef4ff; color: #315aa9; }
.actions { display: flex; justify-content: flex-end; gap: 7px; }
.actions .primary { border-color: #3566d6; background: #3566d6; color: #fff; }
.actions .danger { color: #a45a5a; }
.error { margin: 0; padding: 8px 10px; border-radius: 7px; background: #fff2f2; color: #a94e4e; font-size: 10px; }
.empty { margin: 0; color: #8793a4; font-size: 10px; }
</style>
