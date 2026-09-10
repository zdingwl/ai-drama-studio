<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'

import { getProject } from '@/features/projects/api'
import {
  finalizeSourceVideoSnapshot,
  getSourceVideoSnapshot,
  type SourceVideoSnapshotRead,
} from '@/features/projects/sourceSnapshot'
import type { ProjectRead } from '@/features/projects/types'

const route = useRoute()
const projectId = computed(() => String(route.params.id ?? ''))
const project = ref<ProjectRead | null>(null)
const snapshot = ref<SourceVideoSnapshotRead | null>(null)
const loading = ref(true)
const confirming = ref(false)
const errorMessage = ref('')
const successMessage = ref('')

const visible = computed(() => project.value?.project_type === 'REPLICA' || project.value?.project_type === 'REDRAW')
const status = computed(() => snapshot.value?.status ?? 'NOT_BUILT')
const needsConfirmation = computed(() => status.value !== 'CURRENT')
const buttonText = computed(() => {
  if (confirming.value) return '正在确认…'
  return status.value === 'STALE' ? '重新确认当前结果' : '确认当前原片分析结果'
})

const statusTitle = computed(() => {
  if (status.value === 'CURRENT') return '当前原片分析结果已确认'
  if (status.value === 'STALE') return '原片分析结果已有更新，请重新确认'
  return '当前原片分析结果尚未确认'
})

const statusDescription = computed(() => {
  if (status.value === 'CURRENT') return '后续步骤会直接使用上面这套原片理解结果。'
  if (status.value === 'STALE') return '上面的原片理解结果发生过修改；重新确认后再供后续步骤使用。'
  return '确认只保存当前结果版本，不会重新分析原片，也不会再次调用模型。'
})

async function refresh(): Promise<void> {
  snapshot.value = await getSourceVideoSnapshot(projectId.value)
}

async function load(): Promise<void> {
  loading.value = true
  errorMessage.value = ''
  try {
    project.value = await getProject(projectId.value)
    if (visible.value) await refresh()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '原片分析结果状态读取失败'
  } finally {
    loading.value = false
  }
}

async function confirmCurrentResult(): Promise<void> {
  if (confirming.value || loading.value || !needsConfirmation.value) return
  confirming.value = true
  errorMessage.value = ''
  successMessage.value = ''
  try {
    snapshot.value = await finalizeSourceVideoSnapshot(projectId.value)
    successMessage.value = '当前原片分析结果已确认。'
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '当前原片分析结果确认失败'
  } finally {
    confirming.value = false
  }
}

onMounted(load)
</script>

<template>
  <section
    v-if="visible"
    class="result-approval"
    :class="status.toLowerCase()"
    data-testid="source-result-approval"
  >
    <div class="approval-copy">
      <span class="approval-icon" aria-hidden="true">{{ status === 'CURRENT' ? '✓' : status === 'STALE' ? '!' : '·' }}</span>
      <div>
        <strong>{{ statusTitle }}</strong>
        <p>{{ statusDescription }}</p>
      </div>
    </div>

    <button
      v-if="needsConfirmation"
      type="button"
      :disabled="loading || confirming"
      data-testid="source-result-confirm"
      @click="confirmCurrentResult"
    >
      {{ loading ? '正在读取…' : buttonText }}
    </button>

    <p v-if="errorMessage" class="approval-message error">{{ errorMessage }}</p>
    <p v-if="successMessage" class="approval-message success">{{ successMessage }}</p>
  </section>
</template>

<style scoped>
.result-approval {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 14px 18px;
  align-items: center;
  margin: 10px 24px 28px;
  padding: 14px 16px;
  border: 1px solid #dfe4eb;
  border-radius: 12px;
  background: #fafbfc;
  color: #273244;
}

.result-approval.current {
  border-color: #cfe6d7;
  background: #f4fbf6;
}

.result-approval.stale {
  border-color: #ecd8b5;
  background: #fffaf0;
}

.approval-copy {
  display: flex;
  align-items: center;
  gap: 11px;
  min-width: 0;
}

.approval-copy strong {
  display: block;
  font-size: 14px;
}

.approval-copy p {
  margin: 3px 0 0;
  color: #6a7484;
  font-size: 12px;
  line-height: 1.45;
}

.approval-icon {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  border-radius: 999px;
  background: #e8ebef;
  font-size: 13px;
  font-weight: 800;
}

.current .approval-icon {
  background: #dff2e5;
  color: #267a48;
}

.stale .approval-icon {
  background: #f8e8c8;
  color: #95631e;
}

button {
  border: 1px solid #d5dbe4;
  border-radius: 9px;
  padding: 8px 12px;
  background: #fff;
  color: #303949;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
}

button:disabled {
  cursor: not-allowed;
  opacity: .5;
}

.approval-message {
  grid-column: 1 / -1;
  margin: -2px 0 0 35px;
  font-size: 12px;
}

.approval-message.error {
  color: #a92b2b;
}

.approval-message.success {
  color: #267a48;
}

@media (max-width: 760px) {
  .result-approval {
    grid-template-columns: 1fr;
  }

  .result-approval button {
    width: 100%;
  }
}
</style>
