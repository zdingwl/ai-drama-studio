<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  SOURCE_LANGUAGE_OPTIONS,
  TARGET_LANGUAGE_OPTIONS,
  TARGET_REGION_OPTIONS,
} from '../constants/project-options'
import type { ProjectImportStage } from '../stores/project'
import type { CreateProjectPayload } from '../types/project'

const props = withDefaults(
  defineProps<{
    open: boolean
    submitting: boolean
    errorMessage?: string
    stage?: ProjectImportStage
    uploadProgress?: number
  }>(),
  {
    errorMessage: '',
    stage: 'idle',
    uploadProgress: 0,
  },
)

const emit = defineEmits<{
  close: []
  submit: [payload: CreateProjectPayload, file: File]
}>()

const initialForm = (): CreateProjectPayload => ({
  name: '',
  source_language: '',
  target_language: 'en',
  target_region: 'US',
  workspace_root: '',
})

const form = reactive<CreateProjectPayload>(initialForm())
const localError = ref('')
const sourceFile = ref<File | null>(null)
const sourceInput = ref<HTMLInputElement | null>(null)

const canSubmit = computed(() => {
  return Boolean(form.name?.trim() && sourceFile.value && form.target_language && form.target_region)
})

const stageLabel = computed(() => {
  if (props.stage === 'creating') return '正在创建项目工作区…'
  if (props.stage === 'uploading') return `正在导入原片… ${props.uploadProgress}%`
  if (props.stage === 'initializing') return '正在生成 Proxy、分析音频和缩略图…'
  if (props.stage === 'ready') return '导入和初始化完成'
  return ''
})

watch(
  () => props.open,
  (open) => {
    if (!open) return
    Object.assign(form, initialForm())
    localError.value = ''
    sourceFile.value = null
    if (sourceInput.value) sourceInput.value.value = ''
  },
)

function close(): void {
  if (props.submitting) return
  emit('close')
}

function chooseSource(): void {
  if (props.submitting) return
  sourceInput.value?.click()
}

function onSourceSelected(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  sourceFile.value = file
  if (!file) return

  if (!form.name?.trim()) {
    const withoutExtension = file.name.replace(/\.[^.]+$/, '').trim()
    form.name = withoutExtension.slice(0, 100) || '短剧重制项目'
  }
}

function formatFileSize(size: number): string {
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / (1024 * 1024)).toFixed(1)} MB`
  return `${(size / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function submit(): void {
  localError.value = ''
  if (!form.name?.trim()) {
    localError.value = '请输入项目名称'
    return
  }
  if (!sourceFile.value) {
    localError.value = '请选择要导入的原片视频'
    return
  }
  if (!form.target_language) {
    localError.value = '请选择目标语言'
    return
  }
  if (!form.target_region) {
    localError.value = '请选择目标地区'
    return
  }

  emit(
    'submit',
    {
      name: form.name,
      source_language: form.source_language || null,
      target_language: form.target_language,
      target_region: form.target_region,
      workspace_root: form.workspace_root?.trim() || null,
    },
    sourceFile.value,
  )
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="open" class="dialog-mask" @mousedown.self="close">
        <form class="dialog project-create-dialog import-source-dialog" @submit.prevent="submit">
          <header class="dialog-header">
            <div>
              <span class="dialog-eyebrow">IMPORT SOURCE</span>
              <h2>导入原片</h2>
              <p>一次完成项目创建、原片导入和分析资产初始化</p>
            </div>
            <button type="button" class="dialog-close" :disabled="submitting" aria-label="关闭" @click="close">×</button>
          </header>

          <div class="create-project-type">
            <div class="type-icon">01</div>
            <div>
              <strong>Workflow 01 · 导入原片</strong>
              <p>底层会自动完成 Project、Source、Proxy、WAV、Thumbnail 和时间映射。</p>
            </div>
            <span class="selected-chip">一步完成</span>
          </div>

          <section class="form-section">
            <div class="form-section-title">
              <span>01</span>
              <div><strong>选择原片</strong><small>视频同时作为项目初始化的输入</small></div>
            </div>

            <input
              ref="sourceInput"
              class="hidden-file-input"
              type="file"
              accept="video/*,.mp4,.mov,.mkv,.webm,.m4v,.avi"
              :disabled="submitting"
              @change="onSourceSelected"
            />

            <button type="button" class="source-file-picker" :disabled="submitting" @click="chooseSource">
              <span class="source-file-icon">▶</span>
              <span v-if="sourceFile" class="source-file-copy">
                <strong>{{ sourceFile.name }}</strong>
                <small>{{ formatFileSize(sourceFile.size) }} · 点击可重新选择</small>
              </span>
              <span v-else class="source-file-copy">
                <strong>选择原片视频</strong>
                <small>MP4 / MOV / MKV / WebM 等 FFmpeg 可读取格式</small>
              </span>
              <b>{{ sourceFile ? '更换' : '选择文件' }}</b>
            </button>
          </section>

          <section class="form-section">
            <div class="form-section-title">
              <span>02</span>
              <div><strong>项目信息</strong><small>选择视频后会自动用文件名填充项目名称，可继续修改</small></div>
            </div>
            <label class="field full-field">
              <span>项目名称 <b>*</b></span>
              <input v-model="form.name" maxlength="100" autocomplete="off" placeholder="例如：都市短剧英语重制版" :disabled="submitting" />
            </label>
          </section>

          <section class="form-section">
            <div class="form-section-title">
              <span>03</span>
              <div><strong>本土化设置</strong><small>固定选项使用标准代码保存</small></div>
            </div>
            <div class="form-grid three-columns">
              <label class="field">
                <span>原片语言</span>
                <div class="input-with-prefix select-with-prefix">
                  <i>源</i>
                  <select v-model="form.source_language" aria-label="原片语言" :disabled="submitting">
                    <option v-for="item in SOURCE_LANGUAGE_OPTIONS" :key="item.value || 'auto'" :value="item.value">
                      {{ item.label }}
                    </option>
                  </select>
                </div>
              </label>

              <label class="field">
                <span>目标语言 <b>*</b></span>
                <div class="input-with-prefix select-with-prefix">
                  <i>语</i>
                  <select v-model="form.target_language" required aria-label="目标语言" :disabled="submitting">
                    <option v-for="item in TARGET_LANGUAGE_OPTIONS" :key="item.value" :value="item.value">
                      {{ item.label }}
                    </option>
                  </select>
                </div>
              </label>

              <label class="field">
                <span>目标地区 <b>*</b></span>
                <div class="input-with-prefix select-with-prefix">
                  <i>地</i>
                  <select v-model="form.target_region" required aria-label="目标地区" :disabled="submitting">
                    <option v-for="item in TARGET_REGION_OPTIONS" :key="item.value" :value="item.value">
                      {{ item.label }}
                    </option>
                  </select>
                </div>
              </label>
            </div>
          </section>

          <section class="form-section storage-section">
            <div class="form-section-title">
              <span>04</span>
              <div><strong>存储位置</strong><small>留空使用系统默认项目目录</small></div>
            </div>
            <label class="field full-field">
              <span>Workspace Root</span>
              <div class="path-input-wrap">
                <span class="folder-icon">▱</span>
                <input v-model="form.workspace_root" placeholder="留空使用默认目录" :disabled="submitting" />
                <span class="default-path-chip">默认可用</span>
              </div>
            </label>
          </section>

          <section v-if="submitting" class="import-progress-panel" aria-live="polite">
            <div class="import-progress-head">
              <span class="button-spinner"></span>
              <div><strong>{{ stageLabel }}</strong><small>请保持本地后端运行，不需要再进入其它初始化页面。</small></div>
            </div>
            <div class="workflow-progress-line">
              <span :class="{ done: ['uploading', 'initializing', 'ready'].includes(stage) }">创建项目</span>
              <span :class="{ done: ['initializing', 'ready'].includes(stage) }">导入原片</span>
              <span :class="{ done: stage === 'ready' }">生成分析资产</span>
            </div>
            <div v-if="stage === 'uploading'" class="upload-progress-track">
              <i :style="{ width: `${uploadProgress}%` }"></i>
            </div>
          </section>

          <div v-if="localError || errorMessage" class="inline-alert dialog-error">
            <span>!</span>
            <div><strong>导入未完成</strong><p>{{ localError || errorMessage }}</p></div>
          </div>

          <footer class="dialog-actions">
            <div class="dialog-security-note"><span>●</span> 全程本地处理 · 原片不上传云端</div>
            <div class="action-buttons">
              <button type="button" class="secondary-button" :disabled="submitting" @click="close">取消</button>
              <button type="submit" class="primary-button create-submit" :disabled="submitting || !canSubmit">
                <span v-if="submitting" class="button-spinner"></span>
                {{ submitting ? '正在导入并初始化…' : '创建并导入' }}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.import-source-dialog {
  width: min(760px, calc(100vw - 40px));
}

.hidden-file-input {
  display: none;
}

.source-file-picker {
  width: 100%;
  min-height: 78px;
  display: grid;
  grid-template-columns: 42px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px dashed #35445a;
  border-radius: 10px;
  background: #0d141f;
  color: #dbe2ec;
  text-align: left;
  cursor: pointer;
}

.source-file-picker:hover:not(:disabled) {
  border-color: #6878ff;
  background: #111927;
}

.source-file-picker:disabled {
  cursor: default;
  opacity: 0.72;
}

.source-file-icon {
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  border-radius: 9px;
  background: #1b2434;
  color: #8e9aff;
  font-size: 13px;
}

.source-file-copy {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.source-file-copy strong,
.source-file-copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-file-copy strong {
  font-size: 12px;
}

.source-file-copy small {
  color: #778397;
  font-size: 10px;
}

.source-file-picker b {
  color: #9ca6ff;
  font-size: 10px;
  font-weight: 600;
}

.import-progress-panel {
  margin: 14px 20px 0;
  padding: 13px 14px;
  border: 1px solid #263247;
  border-radius: 9px;
  background: #0b111b;
}

.import-progress-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.import-progress-head div {
  display: grid;
  gap: 3px;
}

.import-progress-head strong {
  color: #dce3ee;
  font-size: 11px;
}

.import-progress-head small {
  color: #6f7b8e;
  font-size: 9px;
}

.workflow-progress-line {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 12px;
}

.workflow-progress-line span {
  padding-top: 7px;
  border-top: 2px solid #273246;
  color: #667286;
  font-size: 9px;
}

.workflow-progress-line span.done {
  border-top-color: #737fff;
  color: #b9c0ff;
}

.upload-progress-track {
  height: 3px;
  margin-top: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: #1b2432;
}

.upload-progress-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: #737fff;
  transition: width 120ms linear;
}

.select-with-prefix {
  position: relative;
}

.select-with-prefix::after {
  content: '⌄';
  position: absolute;
  right: 10px;
  top: 50%;
  transform: translateY(-52%);
  color: #6f7b8d;
  font-size: 10px;
  pointer-events: none;
}

.select-with-prefix select {
  width: 100%;
  height: 38px;
  min-width: 0;
  padding: 0 30px 0 10px;
  border: 0;
  outline: 0;
  color: #dbe2ec;
  background: transparent;
  font: inherit;
  font-size: 10px;
  appearance: none;
  cursor: pointer;
}

.select-with-prefix select:disabled {
  cursor: default;
}

.select-with-prefix select option {
  color: #dbe2ec;
  background: #111824;
}
</style>
