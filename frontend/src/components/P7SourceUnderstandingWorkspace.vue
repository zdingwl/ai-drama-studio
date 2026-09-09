<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import P7SourceBiblePanel from '@/components/P7SourceBiblePanel.vue'
import { getProject, updateProject } from '@/features/projects/api'
import type { ProjectRead, SourceUnderstandingProvider } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const selected = ref<SourceUnderstandingProvider>('DOUBAO_SEED_2_1_PRO_API')
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
const savedMessage = ref('')
const panelKey = ref(0)

const visible = computed(() => project.value?.project_type === 'REPLICA' || project.value?.project_type === 'REDRAW')
const changed = computed(() => Boolean(project.value && selected.value !== project.value.source_understanding_provider))

const options: Array<{
  value: SourceUnderstandingProvider
  title: string
  badge: string
  description: string
  detail: string
}> = [
  {
    value: 'DOUBAO_SEED_2_1_PRO_API',
    title: 'Doubao Seed 2.1 Pro',
    badge: '火山引擎 API',
    description: '国内云端调用，完整 Episode 通过方舟 Files API 进入整集多模态理解。',
    detail: '适合直接生产验收；需要后端配置 AI_DRAMA_P7_DOUBAO_API_KEY。',
  },
  {
    value: 'QWEN3_VL_LOCAL',
    title: 'Qwen3-VL-30B-A3B-Thinking',
    badge: '本地 / 局域网 vLLM',
    description: '应用连接你自己的 OpenAI-compatible vLLM 服务，完整 Episode 通过本地 file:// 路径读取。',
    detail: '模型权重不进入 Web 后端进程；GPU、量化和 tensor parallel 由本地推理服务自行配置。',
  },
]

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    project.value = await getProject(projectId.value)
    selected.value = project.value.source_understanding_provider
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P7 模型设置读取失败'
  } finally {
    loading.value = false
  }
}

async function saveProvider(): Promise<void> {
  if (!project.value || !changed.value || saving.value) return
  saving.value = true
  errorMessage.value = ''
  savedMessage.value = ''
  try {
    project.value = await updateProject(projectId.value, {
      source_understanding_provider: selected.value,
    })
    selected.value = project.value.source_understanding_provider
    savedMessage.value = '已切换 P7 模型。旧 SOURCE_BIBLE 及其 Story/Rhythm 已按 Artifact Graph 规则变为 STALE；P6 Source Evidence 保持不变。'
    panelKey.value += 1
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P7 模型设置保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-if="visible" class="provider-settings">
    <div class="heading">
      <div>
        <span class="eyebrow">P7 模型设置</span>
        <h2>整集多模态理解 Provider</h2>
        <p>模型只影响 Source Understanding；完整 Episode 仍是 Source Truth，P6 ASR/OCR 仍是 canonical 文字证据。</p>
      </div>
      <span class="current">项目级设置</span>
    </div>

    <p v-if="loading" class="muted">正在读取模型设置…</p>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    <p v-if="savedMessage" class="success">{{ savedMessage }}</p>

    <template v-if="!loading && project">
      <div class="provider-grid">
        <label
          v-for="option in options"
          :key="option.value"
          class="provider-card"
          :class="{ selected: selected === option.value }"
        >
          <input v-model="selected" type="radio" name="p7-provider" :value="option.value" />
          <div>
            <div class="provider-title">
              <strong>{{ option.title }}</strong>
              <span>{{ option.badge }}</span>
            </div>
            <p>{{ option.description }}</p>
            <small>{{ option.detail }}</small>
          </div>
        </label>
      </div>

      <div class="save-row">
        <span v-if="changed">切换 Provider 会使当前 SOURCE_BIBLE 及其 Story/Rhythm 失效，随后需要显式重新运行 P7。</span>
        <span v-else>当前项目已使用所选 Provider。</span>
        <button type="button" :disabled="!changed || saving" @click="saveProvider">
          {{ saving ? '正在保存…' : '保存模型选择' }}
        </button>
      </div>
    </template>
  </section>

  <P7SourceBiblePanel :key="panelKey" />
</template>

<style scoped>
.provider-settings {
  margin: 24px;
  padding: 22px;
  border: 1px solid #dce3ea;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 10px 28px rgba(20, 32, 45, 0.06);
}

.heading,
.provider-title,
.save-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.heading h2 {
  margin: 4px 0 8px;
  font-size: 20px;
}

.heading p,
.provider-card p {
  margin: 0;
  color: #5d6875;
  line-height: 1.6;
}

.eyebrow {
  color: #6b7280;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.current,
.provider-title span {
  border-radius: 999px;
  padding: 5px 9px;
  background: #eef2f6;
  color: #405064;
  font-size: 12px;
  white-space: nowrap;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}

.provider-card {
  display: flex;
  gap: 12px;
  padding: 16px;
  border: 1px solid #dce3ea;
  border-radius: 14px;
  cursor: pointer;
}

.provider-card.selected {
  border-color: #667085;
  box-shadow: inset 0 0 0 1px #667085;
}

.provider-card input {
  margin-top: 4px;
}

.provider-card small {
  display: block;
  margin-top: 8px;
  color: #7a8491;
  line-height: 1.5;
}

.save-row {
  margin-top: 16px;
  color: #667085;
  font-size: 13px;
}

button {
  flex: 0 0 auto;
  border: 0;
  border-radius: 10px;
  padding: 10px 16px;
  background: #202a36;
  color: #fff;
  cursor: pointer;
}

button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.error,
.success,
.muted {
  margin: 14px 0 0;
}

.error { color: #b42318; }
.success { color: #19725c; }
.muted { color: #667085; }

/* P7SourceBiblePanel still has its old provider fallback display. The project-level selector above
   is now authoritative, so hide that legacy line until the panel is refactored into the final UX. */
:deep(.p7-panel .provider-line) {
  display: none;
}

@media (max-width: 760px) {
  .provider-grid { grid-template-columns: 1fr; }
  .heading,
  .save-row { align-items: flex-start; flex-direction: column; }
  .provider-settings { margin: 16px; }
}
</style>
