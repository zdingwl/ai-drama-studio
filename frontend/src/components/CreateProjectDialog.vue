<script setup lang="ts">
import { reactive } from 'vue'
import type { CreateProjectPayload } from '../types/project'

defineProps<{ open: boolean; submitting: boolean; errorMessage?: string }>()
const emit = defineEmits<{ close: []; submit: [payload: CreateProjectPayload] }>()

const form = reactive<CreateProjectPayload>({
  name: '',
  source_language: '',
  target_language: 'en',
  target_region: 'US',
  workspace_root: '',
})

function submit(): void {
  emit('submit', {
    name: form.name,
    source_language: form.source_language || null,
    target_language: form.target_language,
    target_region: form.target_region,
    workspace_root: form.workspace_root || null,
  })
}
</script>

<template>
  <div v-if="open" class="dialog-mask">
    <form class="dialog" @submit.prevent="submit">
      <h2>新建项目</h2>
      <label>项目名称<input v-model="form.name" maxlength="100" required /></label>
      <label>原片语言<input v-model="form.source_language" placeholder="可留空，例如 zh" /></label>
      <label>目标语言<input v-model="form.target_language" required /></label>
      <label>目标地区<input v-model="form.target_region" required /></label>
      <label>存储位置<input v-model="form.workspace_root" placeholder="留空使用默认目录" /></label>
      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
      <div class="actions">
        <button type="button" :disabled="submitting" @click="emit('close')">取消</button>
        <button type="submit" :disabled="submitting">{{ submitting ? '创建中…' : '创建项目' }}</button>
      </div>
    </form>
  </div>
</template>
