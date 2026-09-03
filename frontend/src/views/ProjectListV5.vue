<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { projectManagementApi } from '../api/project-management'
import {
  PROJECT_LANGUAGE_OPTIONS,
  PROJECT_REGION_OPTIONS,
  normalizeProjectLanguage,
  normalizeProjectRegion,
  normalizeProjectTargetLanguage,
  projectLanguageLabel,
  projectRegionLabel,
} from '../constants/projectOptions'
import type {
  ManagedProject,
  ProjectManagementPayload,
  ProjectRedrawRule,
} from '../types/project-management'

type EditorMode = 'create' | 'edit'

const router = useRouter()
const projects = ref<ManagedProject[]>([])
const loading = ref(true)
const loadError = ref('')
const editorOpen = ref(false)
const editorMode = ref<EditorMode>('create')
const editingProjectId = ref<string | null>(null)
const saving = ref(false)
const formError = ref('')
const deleteTarget = ref<ManagedProject | null>(null)
const deleting = ref(false)
const deleteError = ref('')

const redrawRuleOptions: Array<{
  value: ProjectRedrawRule
  label: string
  detail: string
}> = [
  { value: 'CHARACTER', label: '人物', detail: '重新生成目标版本人物' },
  { value: 'SCENE', label: '场景', detail: '重新生成或本土化场景' },
  { value: 'LANGUAGE', label: '语言', detail: '翻译、本土化并使用目标语言' },
]

function createDefaultForm(): ProjectManagementPayload {
  return {
    name: '',
    source_language: 'zh',
    target_language: 'en',
    target_region: 'US',
    redraw_rules: ['CHARACTER', 'SCENE', 'LANGUAGE'],
  }
}

const form = ref<ProjectManagementPayload>(createDefaultForm())
const pageTitle = computed(() => editorMode.value === 'create' ? '新建项目' : '编辑项目')
const saveLabel = computed(() => editorMode.value === 'create' ? '创建项目' : '保存修改')

async function loadProjects(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    projects.value = await projectManagementApi.listProjects()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '项目列表读取失败'
  } finally {
    loading.value = false
  }
}

function openCreateEditor(): void {
  editorMode.value = 'create'
  editingProjectId.value = null
  form.value = createDefaultForm()
  formError.value = ''
  editorOpen.value = true
}

function openEditEditor(project: ManagedProject): void {
  editorMode.value = 'edit'
  editingProjectId.value = project.id
  form.value = {
    name: project.name,
    source_language: normalizeProjectLanguage(project.source_language),
    target_language: normalizeProjectTargetLanguage(project.target_language),
    target_region: normalizeProjectRegion(project.target_region),
    redraw_rules: project.redraw_rules.length
      ? [...project.redraw_rules]
      : ['CHARACTER', 'SCENE', 'LANGUAGE'],
  }
  formError.value = ''
  editorOpen.value = true
}

function closeEditor(): void {
  if (saving.value) return
  editorOpen.value = false
  formError.value = ''
}

function toggleRedrawRule(rule: ProjectRedrawRule): void {
  const current = new Set(form.value.redraw_rules)
  if (current.has(rule)) current.delete(rule)
  else current.add(rule)
  form.value.redraw_rules = redrawRuleOptions
    .map((option) => option.value)
    .filter((value) => current.has(value))
}

function validateForm(): string {
  if (!form.value.name.trim()) return '请输入项目标题'
  if (!form.value.redraw_rules.length) return '视频重绘规则至少选择一项'
  return ''
}

async function saveProject(): Promise<void> {
  if (saving.value) return
  const validationMessage = validateForm()
  if (validationMessage) {
    formError.value = validationMessage
    return
  }

  saving.value = true
  formError.value = ''
  const payload: ProjectManagementPayload = {
    ...form.value,
    name: form.value.name.trim(),
    redraw_rules: [...form.value.redraw_rules],
  }

  try {
    if (editorMode.value === 'create') {
      const created = await projectManagementApi.createProject(payload)
      projects.value = [created, ...projects.value.filter((item) => item.id !== created.id)]
    } else if (editingProjectId.value) {
      const updated = await projectManagementApi.updateProject(editingProjectId.value, payload)
      projects.value = projects.value.map((item) => item.id === updated.id ? updated : item)
    }
    editorOpen.value = false
  } catch (error) {
    formError.value = error instanceof Error ? error.message : '项目保存失败'
  } finally {
    saving.value = false
  }
}

function askDelete(project: ManagedProject): void {
  deleteTarget.value = project
  deleteError.value = ''
}

function closeDelete(): void {
  if (deleting.value) return
  deleteTarget.value = null
  deleteError.value = ''
}

async function confirmDelete(): Promise<void> {
  if (!deleteTarget.value || deleting.value) return
  deleting.value = true
  deleteError.value = ''
  const projectId = deleteTarget.value.id
  try {
    await projectManagementApi.deleteProject(projectId)
    projects.value = projects.value.filter((item) => item.id !== projectId)
    deleteTarget.value = null
  } catch (error) {
    deleteError.value = error instanceof Error ? error.message : '项目删除失败'
  } finally {
    deleting.value = false
  }
}

function openProject(project: ManagedProject): void {
  void router.push(`/projects/${project.id}`)
}

function redrawRuleLabel(rule: ProjectRedrawRule): string {
  return redrawRuleOptions.find((option) => option.value === rule)?.label || rule
}

function formatUpdatedAt(value: string): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

onMounted(() => {
  void loadProjects()
})
</script>

<template>
  <div class="project-page" @keydown.esc="editorOpen ? closeEditor() : closeDelete()">
    <header class="page-header">
      <div>
        <p class="eyebrow">AI Drama Studio</p>
        <h1>项目管理</h1>
        <p class="description">管理短剧重绘项目，创建项目后再进入后续视频导入和处理流程。</p>
      </div>
      <button class="primary-button" type="button" @click="openCreateEditor">
        <span aria-hidden="true">＋</span>
        新建项目
      </button>
    </header>

    <section class="project-panel">
      <div class="panel-head">
        <div>
          <h2>项目列表</h2>
          <span>{{ loading ? '正在读取…' : `共 ${projects.length} 个项目` }}</span>
        </div>
        <button v-if="loadError" class="text-button" type="button" @click="loadProjects">重新加载</button>
      </div>

      <div v-if="loadError" class="error-banner">
        <strong>项目列表加载失败</strong>
        <span>{{ loadError }}</span>
      </div>

      <div v-if="loading" class="loading-state">
        <span class="spinner" aria-hidden="true"></span>
        正在加载项目…
      </div>

      <div v-else-if="!projects.length && !loadError" class="empty-state">
        <div class="empty-icon" aria-hidden="true">＋</div>
        <h3>还没有项目</h3>
        <p>创建第一个短剧重绘项目后，会显示在这里。</p>
        <button class="primary-button" type="button" @click="openCreateEditor">新建项目</button>
      </div>

      <div v-else-if="projects.length" class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>标题</th>
              <th>原项目语言</th>
              <th>目标语言</th>
              <th>目标地区</th>
              <th>视频重绘规则</th>
              <th>更新时间</th>
              <th class="action-column">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="project in projects"
              :key="project.id"
              class="project-row"
              tabindex="0"
              @click="openProject(project)"
              @keydown.enter="openProject(project)"
            >
              <td>
                <div class="project-name">
                  <strong>{{ project.name }}</strong>
                  <span>点击进入项目</span>
                </div>
              </td>
              <td>{{ projectLanguageLabel(project.source_language) }}</td>
              <td>{{ projectLanguageLabel(project.target_language) }}</td>
              <td>{{ projectRegionLabel(project.target_region) }}</td>
              <td>
                <div class="rule-chips">
                  <span v-for="rule in project.redraw_rules" :key="rule">{{ redrawRuleLabel(rule) }}</span>
                </div>
              </td>
              <td class="date-cell">{{ formatUpdatedAt(project.updated_at) }}</td>
              <td class="actions" @click.stop @keydown.stop>
                <button type="button" class="row-action" @click="openEditEditor(project)">编辑</button>
                <button type="button" class="row-action danger" @click="askDelete(project)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div v-if="editorOpen" class="modal-backdrop" role="presentation" @click.self="closeEditor">
      <section class="modal-card editor-modal" role="dialog" aria-modal="true" :aria-label="pageTitle">
        <header class="modal-head">
          <div>
            <p class="eyebrow">项目设置</p>
            <h2>{{ pageTitle }}</h2>
          </div>
          <button class="close-button" type="button" :disabled="saving" aria-label="关闭" @click="closeEditor">×</button>
        </header>

        <form class="project-form" @submit.prevent="saveProject">
          <label class="field full-field">
            <span>标题</span>
            <input
              v-model="form.name"
              type="text"
              maxlength="200"
              autocomplete="off"
              placeholder="请输入项目标题"
              autofocus
            />
          </label>

          <label class="field">
            <span>原项目语言</span>
            <select v-model="form.source_language">
              <option v-for="option in PROJECT_LANGUAGE_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <label class="field">
            <span>目标语言</span>
            <select v-model="form.target_language">
              <option v-for="option in PROJECT_LANGUAGE_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <label class="field full-field">
            <span>目标地区</span>
            <select v-model="form.target_region">
              <option v-for="option in PROJECT_REGION_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <fieldset class="redraw-field full-field">
            <legend>视频重绘规则</legend>
            <p>选择这个项目需要重新处理的内容，可多选。</p>
            <div class="redraw-options">
              <label
                v-for="option in redrawRuleOptions"
                :key="option.value"
                :class="['redraw-option', { selected: form.redraw_rules.includes(option.value) }]"
              >
                <input
                  type="checkbox"
                  :checked="form.redraw_rules.includes(option.value)"
                  @change="toggleRedrawRule(option.value)"
                />
                <span class="check-mark" aria-hidden="true">✓</span>
                <span class="rule-copy">
                  <strong>{{ option.label }}</strong>
                  <small>{{ option.detail }}</small>
                </span>
              </label>
            </div>
          </fieldset>

          <div v-if="formError" class="form-error full-field">{{ formError }}</div>

          <footer class="modal-actions full-field">
            <button class="secondary-button" type="button" :disabled="saving" @click="closeEditor">取消</button>
            <button class="primary-button" type="submit" :disabled="saving">
              {{ saving ? '正在保存…' : saveLabel }}
            </button>
          </footer>
        </form>
      </section>
    </div>

    <div v-if="deleteTarget" class="modal-backdrop" role="presentation" @click.self="closeDelete">
      <section class="modal-card delete-modal" role="dialog" aria-modal="true" aria-label="删除项目">
        <div class="delete-icon" aria-hidden="true">!</div>
        <h2>删除项目</h2>
        <p>确定要删除项目 <strong>“{{ deleteTarget.name }}”</strong> 吗？</p>
        <p class="delete-note">删除后不会再显示在项目列表中。当前版本采用安全删除，不会立即清空原视频和已有处理数据。</p>
        <div v-if="deleteError" class="form-error">{{ deleteError }}</div>
        <footer class="modal-actions">
          <button class="secondary-button" type="button" :disabled="deleting" @click="closeDelete">取消</button>
          <button class="danger-button" type="button" :disabled="deleting" @click="confirmDelete">
            {{ deleting ? '正在删除…' : '确认删除' }}
          </button>
        </footer>
      </section>
    </div>
  </div>
</template>

<style scoped>
:global(body) {
  margin: 0;
  background: #f5f7fb;
  color: #172033;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
}

button,
input,
select {
  font: inherit;
}

button {
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: .62;
}

.project-page {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 42px clamp(24px, 5vw, 72px) 64px;
}

.page-header {
  max-width: 1500px;
  margin: 0 auto 24px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
}

.eyebrow {
  margin: 0 0 8px;
  color: #68758b;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: .08em;
  text-transform: uppercase;
}

.page-header h1 {
  margin: 0;
  font-size: clamp(28px, 3vw, 38px);
  line-height: 1.15;
  letter-spacing: -.03em;
}

.description {
  margin: 10px 0 0;
  color: #68758b;
  font-size: 15px;
  line-height: 1.7;
}

.primary-button,
.secondary-button,
.danger-button {
  min-height: 44px;
  border-radius: 10px;
  padding: 0 18px;
  border: 1px solid transparent;
  font-weight: 700;
  font-size: 14px;
}

.primary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  background: #275fe8;
  color: #fff;
  box-shadow: 0 8px 18px rgba(39, 95, 232, .18);
}

.primary-button:hover:not(:disabled) {
  background: #1f52ce;
}

.secondary-button {
  background: #fff;
  border-color: #d9e0eb;
  color: #354158;
}

.secondary-button:hover:not(:disabled) {
  background: #f7f9fc;
}

.danger-button {
  background: #d92d20;
  color: #fff;
}

.project-panel {
  max-width: 1500px;
  margin: 0 auto;
  overflow: hidden;
  border: 1px solid #e0e5ed;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 12px 38px rgba(25, 36, 56, .06);
}

.panel-head {
  min-height: 74px;
  box-sizing: border-box;
  padding: 18px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e8ecf2;
}

.panel-head h2 {
  margin: 0;
  font-size: 18px;
}

.panel-head span {
  display: block;
  margin-top: 4px;
  color: #7b8799;
  font-size: 13px;
}

.text-button {
  border: 0;
  background: transparent;
  color: #275fe8;
  font-weight: 700;
}

.error-banner,
.form-error {
  border: 1px solid #f2c8c4;
  background: #fff4f2;
  color: #b42318;
}

.error-banner {
  margin: 18px 22px 0;
  padding: 13px 15px;
  border-radius: 10px;
  display: grid;
  gap: 3px;
  font-size: 13px;
}

.loading-state,
.empty-state {
  min-height: 330px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #68758b;
}

.loading-state {
  gap: 10px;
  font-size: 14px;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #dce3ef;
  border-top-color: #275fe8;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  flex-direction: column;
  text-align: center;
  padding: 32px;
}

.empty-icon {
  width: 58px;
  height: 58px;
  display: grid;
  place-items: center;
  border-radius: 16px;
  background: #eef3ff;
  color: #275fe8;
  font-size: 30px;
}

.empty-state h3 {
  margin: 16px 0 7px;
  color: #263248;
  font-size: 18px;
}

.empty-state p {
  margin: 0 0 20px;
  font-size: 14px;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 1120px;
  border-collapse: collapse;
}

th,
td {
  padding: 17px 18px;
  border-bottom: 1px solid #edf0f5;
  text-align: left;
  vertical-align: middle;
  font-size: 14px;
}

th {
  background: #fafbfc;
  color: #67748a;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.project-row {
  outline: none;
  transition: background .15s ease;
  cursor: pointer;
}

.project-row:hover,
.project-row:focus-visible {
  background: #f8faff;
}

.project-row:last-child td {
  border-bottom: 0;
}

.project-name {
  min-width: 180px;
  display: grid;
  gap: 4px;
}

.project-name strong {
  color: #182238;
  font-size: 15px;
}

.project-name span,
.date-cell {
  color: #8490a2;
  font-size: 12px;
}

.rule-chips {
  min-width: 150px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rule-chips span {
  padding: 5px 8px;
  border-radius: 7px;
  background: #eef3ff;
  color: #315fc4;
  font-size: 12px;
  font-weight: 700;
}

.action-column {
  width: 120px;
}

.actions {
  white-space: nowrap;
}

.row-action {
  padding: 6px 8px;
  border: 0;
  background: transparent;
  color: #315fc4;
  font-size: 13px;
  font-weight: 700;
}

.row-action:hover {
  text-decoration: underline;
}

.row-action.danger {
  color: #c43228;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  box-sizing: border-box;
  padding: 24px;
  background: rgba(18, 25, 38, .52);
  backdrop-filter: blur(3px);
}

.modal-card {
  width: min(680px, 100%);
  max-height: calc(100vh - 48px);
  overflow-y: auto;
  box-sizing: border-box;
  border: 1px solid rgba(255, 255, 255, .6);
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(17, 28, 48, .25);
}

.editor-modal {
  padding: 24px;
}

.modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 22px;
}

.modal-head h2,
.delete-modal h2 {
  margin: 0;
  font-size: 23px;
  letter-spacing: -.02em;
}

.close-button {
  width: 38px;
  height: 38px;
  border: 0;
  border-radius: 9px;
  background: #f3f5f8;
  color: #627087;
  font-size: 24px;
  line-height: 1;
}

.project-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}

.full-field {
  grid-column: 1 / -1;
}

.field {
  display: grid;
  gap: 8px;
}

.field > span,
.redraw-field legend {
  color: #344158;
  font-size: 13px;
  font-weight: 800;
}

.field input,
.field select {
  width: 100%;
  min-height: 44px;
  box-sizing: border-box;
  border: 1px solid #d7deea;
  border-radius: 10px;
  background: #fff;
  color: #1c273a;
  padding: 0 12px;
  outline: none;
  font-size: 14px;
}

.field input:focus,
.field select:focus {
  border-color: #6f96ef;
  box-shadow: 0 0 0 3px rgba(39, 95, 232, .1);
}

.redraw-field {
  margin: 0;
  padding: 0;
  border: 0;
}

.redraw-field > p {
  margin: 7px 0 12px;
  color: #7a8799;
  font-size: 13px;
}

.redraw-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.redraw-option {
  position: relative;
  min-height: 82px;
  box-sizing: border-box;
  padding: 13px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  border: 1px solid #dfe4ec;
  border-radius: 11px;
  background: #fff;
  cursor: pointer;
  transition: .15s ease;
}

.redraw-option.selected {
  border-color: #7ca0ef;
  background: #f4f7ff;
}

.redraw-option input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.check-mark {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  display: grid;
  place-items: center;
  border: 1px solid #cbd4e2;
  border-radius: 6px;
  color: transparent;
  background: #fff;
  font-size: 13px;
  font-weight: 900;
}

.redraw-option.selected .check-mark {
  border-color: #275fe8;
  background: #275fe8;
  color: #fff;
}

.rule-copy {
  display: grid;
  gap: 5px;
}

.rule-copy strong {
  font-size: 14px;
}

.rule-copy small {
  color: #7d899b;
  font-size: 12px;
  line-height: 1.45;
}

.form-error {
  padding: 10px 12px;
  border-radius: 9px;
  font-size: 13px;
}

.modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 4px;
}

.delete-modal {
  width: min(480px, 100%);
  padding: 28px;
  text-align: center;
}

.delete-icon {
  width: 52px;
  height: 52px;
  margin: 0 auto 15px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #fff0ee;
  color: #d92d20;
  font-size: 24px;
  font-weight: 900;
}

.delete-modal > p {
  margin: 12px 0 0;
  color: #566279;
  font-size: 14px;
  line-height: 1.65;
}

.delete-modal .delete-note {
  color: #8490a2;
  font-size: 12px;
}

.delete-modal .form-error {
  margin-top: 14px;
  text-align: left;
}

.delete-modal .modal-actions {
  margin-top: 22px;
}

@media (max-width: 760px) {
  .project-page {
    padding: 24px 16px 40px;
  }

  .page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .page-header .primary-button {
    align-self: flex-start;
  }

  .project-form {
    grid-template-columns: 1fr;
  }

  .full-field {
    grid-column: auto;
  }

  .redraw-options {
    grid-template-columns: 1fr;
  }

  .editor-modal {
    padding: 20px;
  }
}
</style>
