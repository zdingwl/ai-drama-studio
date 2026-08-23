<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { CreateProjectPayload } from '../types/project'

const props = defineProps<{ open: boolean; submitting: boolean; errorMessage?: string }>()
const emit = defineEmits<{ close: []; submit: [payload: CreateProjectPayload] }>()

const initialForm = (): CreateProjectPayload => ({
  name: '',
  source_language: '',
  target_language: 'en',
  target_region: 'US',
  workspace_root: '',
})

const form = reactive<CreateProjectPayload>(initialForm())
const localError = ref('')

const canSubmit = computed(() => {
  return Boolean(form.name?.trim() && form.target_language?.trim() && form.target_region?.trim())
})

watch(
  () => props.open,
  (open) => {
    if (!open) return
    Object.assign(form, initialForm())
    localError.value = ''
  },
)

function close(): void {
  if (props.submitting) return
  emit('close')
}

function submit(): void {
  localError.value = ''
  if (!form.name?.trim()) {
    localError.value = '请输入项目名称'
    return
  }
  if (!form.target_language?.trim()) {
    localError.value = '请输入目标语言'
    return
  }
  if (!form.target_region?.trim()) {
    localError.value = '请输入目标地区'
    return
  }

  emit('submit', {
    name: form.name,
    source_language: form.source_language?.trim() || null,
    target_language: form.target_language,
    target_region: form.target_region,
    workspace_root: form.workspace_root?.trim() || null,
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="open" class="dialog-mask" @mousedown.self="close">
        <form class="dialog project-create-dialog" @submit.prevent="submit">
          <header class="dialog-header">
            <div>
              <span class="dialog-eyebrow">NEW PROJECT</span>
              <h2>新建项目</h2>
              <p>创建一个独立的本地短剧重制工作区</p>
            </div>
            <button type="button" class="dialog-close" :disabled="submitting" aria-label="关闭" @click="close">×</button>
          </header>

          <div class="create-project-type">
            <div class="type-icon">AI</div>
            <div>
              <strong>本地短剧重制项目</strong>
              <p>项目索引保存在本机 SQLite，项目文件使用独立 Workspace。</p>
            </div>
            <span class="selected-chip">已选择</span>
          </div>

          <section class="form-section">
            <div class="form-section-title">
              <span>01</span>
              <div><strong>基础信息</strong><small>定义项目在工作台中的身份</small></div>
            </div>
            <label class="field full-field">
              <span>项目名称 <b>*</b></span>
              <input v-model="form.name" maxlength="100" autocomplete="off" placeholder="例如：都市短剧英语重制版" />
              <small>最多 100 个字符，同名项目允许创建。</small>
            </label>
          </section>

          <section class="form-section">
            <div class="form-section-title">
              <span>02</span>
              <div><strong>本土化设置</strong><small>确定原片与目标市场的基础语言信息</small></div>
            </div>
            <div class="form-grid three-columns">
              <label class="field">
                <span>原片语言</span>
                <div class="input-with-prefix"><i>源</i><input v-model="form.source_language" placeholder="zh / ja / ko" /></div>
                <small>可留空，后续识别。</small>
              </label>
              <label class="field">
                <span>目标语言 <b>*</b></span>
                <div class="input-with-prefix"><i>语</i><input v-model="form.target_language" required placeholder="en" /></div>
                <small>使用稳定语言代码。</small>
              </label>
              <label class="field">
                <span>目标地区 <b>*</b></span>
                <div class="input-with-prefix"><i>地</i><input v-model="form.target_region" required placeholder="US" /></div>
                <small>使用稳定地区代码。</small>
              </label>
            </div>
          </section>

          <section class="form-section storage-section">
            <div class="form-section-title">
              <span>03</span>
              <div><strong>存储位置</strong><small>选择项目 Workspace 的根目录</small></div>
            </div>
            <label class="field full-field">
              <span>Workspace Root</span>
              <div class="path-input-wrap">
                <span class="folder-icon">▱</span>
                <input v-model="form.workspace_root" placeholder="留空使用默认目录" />
                <span class="default-path-chip">默认可用</span>
              </div>
              <small>留空时使用 Windows 用户目录下的 “AI Drama Studio Projects”。</small>
            </label>
          </section>

          <div v-if="localError || errorMessage" class="inline-alert dialog-error">
            <span>!</span>
            <div><strong>无法创建项目</strong><p>{{ localError || errorMessage }}</p></div>
          </div>

          <footer class="dialog-actions">
            <div class="dialog-security-note"><span>●</span> 本地创建 · 不上传项目文件</div>
            <div class="action-buttons">
              <button type="button" class="secondary-button" :disabled="submitting" @click="close">取消</button>
              <button type="submit" class="primary-button create-submit" :disabled="submitting || !canSubmit">
                <span v-if="submitting" class="button-spinner"></span>
                {{ submitting ? '正在创建…' : '创建项目' }}
              </button>
            </div>
          </footer>
        </form>
      </div>
    </Transition>
  </Teleport>
</template>
