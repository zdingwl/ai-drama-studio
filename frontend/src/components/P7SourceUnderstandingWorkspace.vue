<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import P7SourceBiblePanel from '@/components/P7SourceBiblePanel.vue'
import { getProject, updateProject } from '@/features/projects/api'
import {
  getP7RuntimeConfig,
  updateP7RuntimeConfig,
  type P7RuntimeConfig,
} from '@/features/projects/sourceBible'
import type { ProjectRead, SourceUnderstandingProvider } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const selected = ref<SourceUnderstandingProvider>('DOUBAO_SEED_2_1_PRO_API')
const runtimeDraft = ref<P7RuntimeConfig | null>(null)
const loading = ref(true)
const saving = ref(false)
const runtimeSaving = ref(false)
const errorMessage = ref('')
const savedMessage = ref('')
const runtimeSavedMessage = ref('')
const panelKey = ref(0)

const visible = computed(() => project.value?.project_type === 'REPLICA' || project.value?.project_type === 'REDRAW')
const changed = computed(() => Boolean(project.value && selected.value !== project.value.source_understanding_provider))

const options: Array<{
  value: SourceUnderstandingProvider
  title: string
  badge: string
  description: string
  detail: string
  recommended?: string
}> = [
  {
    value: 'DOUBAO_SEED_2_1_PRO_API',
    title: 'Doubao Seed 2.1 Pro',
    badge: '火山引擎 API',
    description: '国内云端生产档。完整 Episode 通过方舟 Files API 进入整集多模态理解。',
    detail: '运行时 API Key / Model / Base URL 可在下方直接配置并保存到本机 backend/.env。',
    recommended: '云端推荐',
  },
  {
    value: 'QWEN3_8_27B_LOCAL',
    title: 'Qwen3.8-27B',
    badge: '本地 / 局域网 vLLM',
    description: '本地高质量档。新一代原生视觉语言模型，直接读取完整 Episode 的 file:// 路径。',
    detail: '模型权重不进入 Web 后端进程；GPU、量化和 tensor parallel 由 vLLM 服务自行配置。',
    recommended: '本地推荐',
  },
  {
    value: 'QWEN3_VL_8B_THINKING_LOCAL',
    title: 'Qwen3-VL-8B-Thinking',
    badge: '本地低显存',
    description: '低显存兼容档。保留视频理解与推理能力，适合资源较小的单机部署。',
    detail: '仍使用完整 Episode + CURRENT P6 Evidence；资源不足时优先选这一档。',
  },
]

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    const [loadedProject, runtime] = await Promise.all([
      getProject(projectId.value),
      getP7RuntimeConfig(),
    ])
    project.value = loadedProject
    runtimeDraft.value = JSON.parse(JSON.stringify(runtime)) as P7RuntimeConfig
    const saved = project.value.source_understanding_provider
    // Compatibility for projects saved during the short-lived two-provider build.
    selected.value = saved === ('QWEN3_VL_LOCAL' as SourceUnderstandingProvider)
      ? 'QWEN3_VL_8B_THINKING_LOCAL'
      : saved
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

async function saveRuntimeConfig(): Promise<void> {
  if (!runtimeDraft.value || runtimeSaving.value) return
  runtimeSaving.value = true
  errorMessage.value = ''
  runtimeSavedMessage.value = ''
  try {
    const saved = await updateP7RuntimeConfig(runtimeDraft.value)
    runtimeDraft.value = JSON.parse(JSON.stringify(saved)) as P7RuntimeConfig
    runtimeSavedMessage.value = '运行时连接已保存到本机 backend/.env，并已立即加载。API Key 不进入数据库、Artifact、ProviderJob 或 Git。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'P7 运行时连接保存失败'
  } finally {
    runtimeSaving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section v-if="visible" class="provider-settings">
    <div class="heading">
      <div>
        <span class="eyebrow">P7 模型设置</span>
        <h2>整集多模态理解模型</h2>
        <p>模型只影响 Source Understanding；完整 Episode 仍是 Source Truth，P6 ASR/OCR 仍是 canonical 文字证据。</p>
      </div>
      <span class="current">项目级设置 · 三选一</span>
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
            <b v-if="option.recommended" class="recommend">{{ option.recommended }}</b>
            <p>{{ option.description }}</p>
            <small>{{ option.detail }}</small>
          </div>
        </label>
      </div>

      <div class="save-row">
        <span v-if="changed">切换模型会使当前 SOURCE_BIBLE 及其 Story/Rhythm 失效，随后需要显式重新运行 P7。</span>
        <span v-else>当前项目已使用所选模型。</span>
        <button type="button" :disabled="!changed || saving" @click="saveProvider">
          {{ saving ? '正在保存…' : '保存模型选择' }}
        </button>
      </div>

      <details class="runtime-config" open>
        <summary>
          <div>
            <strong>本机运行时连接配置</strong>
            <span>开发 / 人工验收入口 · 明文保存在本机 backend/.env</span>
          </div>
        </summary>

        <div v-if="runtimeDraft" class="runtime-body">
          <p class="runtime-note">
            这里是本地运行工具配置，不属于 Project 业务数据。保存后后端立即使用新值；刷新页面会直接回显当前明文配置。
          </p>
          <p v-if="runtimeSavedMessage" class="success">{{ runtimeSavedMessage }}</p>

          <div class="runtime-grid">
            <article class="runtime-card">
              <header>
                <strong>Doubao Seed 2.1 Pro</strong>
                <span>火山引擎 Ark</span>
              </header>
              <label>
                <span>Ark API Key</span>
                <input
                  v-model="runtimeDraft.doubao.api_key"
                  data-testid="doubao-api-key"
                  type="text"
                  autocomplete="off"
                  spellcheck="false"
                  placeholder="填入火山方舟 API Key"
                />
              </label>
              <label>
                <span>Model / Endpoint ID</span>
                <input v-model="runtimeDraft.doubao.model" data-testid="doubao-model" type="text" spellcheck="false" />
              </label>
              <label>
                <span>Base URL</span>
                <input v-model="runtimeDraft.doubao.base_url" data-testid="doubao-base-url" type="text" spellcheck="false" />
              </label>
              <div class="runtime-pair">
                <label>
                  <span>Video FPS</span>
                  <input v-model.number="runtimeDraft.doubao.video_fps" type="number" min="0.1" max="10" step="0.1" />
                </label>
                <label>
                  <span>Timeout / 秒</span>
                  <input v-model.number="runtimeDraft.doubao.request_timeout_seconds" type="number" min="1" step="1" />
                </label>
              </div>
            </article>

            <article class="runtime-card">
              <header>
                <strong>Qwen3.8-27B</strong>
                <span>本地 vLLM</span>
              </header>
              <label>
                <span>Base URL</span>
                <input v-model="runtimeDraft.qwen38.base_url" type="text" spellcheck="false" />
              </label>
              <label>
                <span>Model</span>
                <input v-model="runtimeDraft.qwen38.model" type="text" spellcheck="false" />
              </label>
              <label>
                <span>API Key（可选）</span>
                <input v-model="runtimeDraft.qwen38.api_key" type="text" autocomplete="off" spellcheck="false" />
              </label>
            </article>

            <article class="runtime-card">
              <header>
                <strong>Qwen3-VL-8B-Thinking</strong>
                <span>本地 vLLM</span>
              </header>
              <label>
                <span>Base URL</span>
                <input v-model="runtimeDraft.qwen3_vl_8b.base_url" type="text" spellcheck="false" />
              </label>
              <label>
                <span>Model</span>
                <input v-model="runtimeDraft.qwen3_vl_8b.model" type="text" spellcheck="false" />
              </label>
              <label>
                <span>API Key（可选）</span>
                <input v-model="runtimeDraft.qwen3_vl_8b.api_key" type="text" autocomplete="off" spellcheck="false" />
              </label>
            </article>
          </div>

          <div class="runtime-footer">
            <label>
              <span>本地 Qwen 请求超时 / 秒</span>
              <input v-model.number="runtimeDraft.qwen_request_timeout_seconds" type="number" min="1" step="1" />
            </label>
            <button type="button" :disabled="runtimeSaving" data-testid="save-runtime-config" @click="saveRuntimeConfig">
              {{ runtimeSaving ? '正在保存运行时配置…' : '保存运行时连接配置' }}
            </button>
          </div>
        </div>
      </details>
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
.save-row,
.runtime-card header,
.runtime-footer {
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
.provider-card p,
.runtime-note {
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
.provider-title span,
.recommend,
.runtime-card header span {
  border-radius: 999px;
  padding: 5px 9px;
  background: #eef2f6;
  color: #405064;
  font-size: 12px;
  white-space: nowrap;
}

.recommend {
  display: inline-block;
  margin: 8px 0;
  font-weight: 700;
}

.provider-grid,
.runtime-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
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

.runtime-config {
  margin-top: 20px;
  border-top: 1px solid #e6eaf0;
  padding-top: 18px;
}

.runtime-config summary {
  cursor: pointer;
  list-style: none;
}

.runtime-config summary::-webkit-details-marker { display: none; }
.runtime-config summary div { display: flex; flex-direction: column; gap: 3px; }
.runtime-config summary span { color: #7a8491; font-size: 12px; }
.runtime-body { margin-top: 14px; }
.runtime-note { font-size: 13px; }

.runtime-card {
  padding: 16px;
  border: 1px solid #dce3ea;
  border-radius: 14px;
  background: #fafbfc;
}

.runtime-card header { margin-bottom: 14px; }
.runtime-card label,
.runtime-footer label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 10px;
  color: #596575;
  font-size: 12px;
}

.runtime-card input,
.runtime-footer input {
  width: 100%;
  box-sizing: border-box;
  border: 1px solid #cfd6df;
  border-radius: 9px;
  padding: 9px 10px;
  background: #fff;
  color: #202a36;
  font: inherit;
}

.runtime-pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.runtime-footer {
  margin-top: 16px;
  align-items: flex-end;
}
.runtime-footer label { width: min(320px, 100%); margin-top: 0; }

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

/* Project-level selector above is authoritative. */
:deep(.p7-panel .provider-line) {
  display: none;
}

@media (max-width: 980px) {
  .provider-grid,
  .runtime-grid { grid-template-columns: 1fr; }
}

@media (max-width: 760px) {
  .heading,
  .save-row,
  .runtime-footer { align-items: flex-start; flex-direction: column; }
  .provider-settings { margin: 16px; }
  .runtime-pair { grid-template-columns: 1fr; }
}
</style>
