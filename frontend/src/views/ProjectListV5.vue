<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { projectManagementApi } from '../api/project-management'
import {
  PROJECT_LANGUAGE_OPTIONS,
  getProjectRegionOptionsForLanguage,
  normalizeProjectLanguage,
  normalizeProjectRegionForLanguage,
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
  icon: string
}> = [
  { value: 'CHARACTER', label: '人物', detail: '重绘人物形象、服装等视觉元素', icon: '●' },
  { value: 'SCENE', label: '场景', detail: '重绘场景背景、道具及环境', icon: '▲' },
  { value: 'LANGUAGE', label: '语言', detail: '翻译并本地化对白与字幕', icon: '•••' },
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
const targetRegionOptions = computed(() => getProjectRegionOptionsForLanguage(form.value.target_language))

watch(
  () => form.value.target_language,
  (language) => {
    form.value.target_region = normalizeProjectRegionForLanguage(language, form.value.target_region)
  },
)

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
  const targetLanguage = normalizeProjectTargetLanguage(project.target_language)
  form.value = {
    name: project.name,
    source_language: normalizeProjectLanguage(project.source_language),
    target_language: targetLanguage,
    target_region: normalizeProjectRegionForLanguage(targetLanguage, project.target_region),
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
  if (!targetRegionOptions.value.some((option) => option.value === form.value.target_region)) {
    return '目标地区与目标语言不匹配，请重新选择目标地区'
  }
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
      <div class="page-heading">
        <div class="brand-line">
          <span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i></span>
          <span>AI Drama Studio</span>
        </div>
        <h1>项目管理</h1>
        <p class="description">在此页面，您可以创建、编辑和管理短剧重绘项目，统一维护项目语言、地区与重绘规则。</p>
      </div>
      <button class="primary-button create-button" type="button" @click="openCreateEditor">
        <span class="plus-icon" aria-hidden="true">＋</span>
        新建项目
      </button>
    </header>

    <section class="project-panel">
      <div class="panel-head">
        <div class="panel-title-row">
          <h2>项目列表</h2>
          <span class="count-badge">{{ loading ? '正在读取…' : `共 ${projects.length} 个项目` }}</span>
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
                  <span class="project-cover" aria-hidden="true">AI</span>
                  <div>
                    <strong>{{ project.name }}</strong>
                    <span>点击进入项目</span>
                  </div>
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
            <p class="modal-eyebrow">项目设置</p>
            <h2>{{ pageTitle }}</h2>
          </div>
          <button class="close-button" type="button" :disabled="saving" aria-label="关闭" @click="closeEditor">×</button>
        </header>

        <form class="project-form" @submit.prevent="saveProject">
          <label class="field full-field required-field">
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

          <label class="field required-field">
            <span>原项目语言</span>
            <select v-model="form.source_language">
              <option v-for="option in PROJECT_LANGUAGE_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <label class="field required-field">
            <span>目标语言</span>
            <select v-model="form.target_language">
              <option v-for="option in PROJECT_LANGUAGE_OPTIONS" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <label class="field full-field required-field region-field">
            <span class="field-label-row">
              <b>目标地区</b>
              <small>ⓘ 根据目标语言仅展示对应国家/地区</small>
            </span>
            <select v-model="form.target_region">
              <option v-for="option in targetRegionOptions" :key="option.value" :value="option.value">
                {{ option.label }}
              </option>
            </select>
          </label>

          <fieldset class="redraw-field full-field">
            <legend class="required-legend">视频重绘规则</legend>
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
                <span class="rule-icon" aria-hidden="true">{{ option.icon }}</span>
                <span class="rule-copy">
                  <strong>{{ option.label }}</strong>
                  <small>{{ option.detail }}</small>
                </span>
                <span class="check-mark" aria-hidden="true">✓</span>
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
:global(*) {
  box-sizing: border-box;
}

:global(body) {
  margin: 0;
  background: #f7f9fc;
  color: #161c2d;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  -webkit-font-smoothing: antialiased;
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
  padding: 28px clamp(28px, 3.5vw, 64px) 56px;
  background:
    radial-gradient(circle at 88% 0%, rgba(222, 234, 255, .58), transparent 28%),
    linear-gradient(180deg, #f9fbff 0%, #f7f9fc 240px, #f6f8fb 100%);
}

.page-header {
  width: min(1540px, 100%);
  margin: 0 auto 26px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 32px;
}

.page-heading {
  min-width: 0;
}

.brand-line {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 18px;
  color: #1769e8;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: -.01em;
}

.brand-mark {
  position: relative;
  width: 23px;
  height: 23px;
  display: inline-block;
}

.brand-mark i {
  position: absolute;
  width: 9px;
  height: 9px;
  border-radius: 3px;
  background: #2677f2;
  transform: rotate(32deg);
}

.brand-mark i:nth-child(1) { left: 1px; top: 1px; }
.brand-mark i:nth-child(2) { right: 1px; top: 7px; opacity: .82; }
.brand-mark i:nth-child(3) { left: 3px; bottom: 1px; opacity: .65; }

.page-header h1 {
  margin: 0;
  color: #111827;
  font-size: clamp(30px, 2.4vw, 38px);
  line-height: 1.15;
  font-weight: 800;
  letter-spacing: -.035em;
}

.description {
  max-width: 760px;
  margin: 13px 0 0;
  color: #6b7280;
  font-size: 14px;
  line-height: 1.75;
}

.primary-button,
.secondary-button,
.danger-button {
  min-height: 42px;
  border-radius: 8px;
  padding: 0 20px;
  border: 1px solid transparent;
  font-size: 14px;
  font-weight: 700;
  transition: background .16s ease, border-color .16s ease, box-shadow .16s ease, transform .16s ease;
}

.primary-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  background: #1268e9;
  color: #fff;
  box-shadow: 0 7px 18px rgba(18, 104, 233, .2);
}

.primary-button:hover:not(:disabled) {
  background: #075cd5;
  box-shadow: 0 9px 24px rgba(18, 104, 233, .24);
}

.create-button {
  min-width: 142px;
  min-height: 46px;
  margin-bottom: 3px;
  font-size: 15px;
}

.plus-icon {
  font-size: 22px;
  font-weight: 400;
  line-height: 1;
}

.secondary-button {
  min-width: 106px;
  background: #fff;
  border-color: #d8dee8;
  color: #4b5565;
  box-shadow: 0 1px 2px rgba(16, 24, 40, .02);
}

.secondary-button:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #cbd3df;
}

.danger-button {
  background: #e5484d;
  color: #fff;
}

.project-panel {
  width: min(1540px, 100%);
  min-height: 540px;
  margin: 0 auto;
  overflow: hidden;
  border: 1px solid #e0e5ee;
  border-radius: 12px;
  background: rgba(255, 255, 255, .96);
  box-shadow: 0 6px 24px rgba(17, 24, 39, .055);
}

.panel-head {
  min-height: 76px;
  padding: 18px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid #e9edf3;
}

.panel-title-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.panel-head h2 {
  margin: 0;
  color: #1f2937;
  font-size: 18px;
  line-height: 1;
  font-weight: 750;
}

.count-badge {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 12px;
  border-radius: 999px;
  background: #f0f2f6;
  color: #697386;
  font-size: 12px;
  font-weight: 600;
}

.text-button {
  border: 0;
  background: transparent;
  color: #1769e8;
  font-size: 13px;
  font-weight: 700;
}

.error-banner,
.form-error {
  border: 1px solid #f2c8c4;
  background: #fff4f2;
  color: #b42318;
}

.error-banner {
  margin: 18px 24px 0;
  padding: 13px 15px;
  border-radius: 8px;
  display: grid;
  gap: 3px;
  font-size: 13px;
}

.loading-state,
.empty-state {
  min-height: 390px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #6b7280;
}

.loading-state {
  gap: 10px;
  font-size: 14px;
}

.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #dce3ef;
  border-top-color: #1769e8;
  border-radius: 50%;
  animation: spin .8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-state {
  flex-direction: column;
  text-align: center;
  padding: 42px;
}

.empty-icon {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  border-radius: 14px;
  background: #edf4ff;
  color: #1769e8;
  font-size: 28px;
}

.empty-state h3 {
  margin: 16px 0 7px;
  color: #263248;
  font-size: 18px;
}

.empty-state p {
  margin: 0 0 20px;
  font-size: 13px;
}

.table-wrap {
  padding: 0 20px 22px;
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 1160px;
  border-collapse: separate;
  border-spacing: 0;
  border: 1px solid #e4e8ef;
  border-radius: 8px;
  overflow: hidden;
}

th,
td {
  padding: 15px 16px;
  border-bottom: 1px solid #e9edf3;
  text-align: left;
  vertical-align: middle;
  font-size: 13px;
}

th {
  height: 48px;
  padding-top: 0;
  padding-bottom: 0;
  background: #fafbfc;
  color: #667085;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.project-row {
  height: 78px;
  outline: none;
  background: #fff;
  transition: background .15s ease;
  cursor: pointer;
}

.project-row:hover,
.project-row:focus-visible {
  background: #f8fbff;
}

.project-row:last-child td {
  border-bottom: 0;
}

.project-name {
  min-width: 215px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.project-cover {
  width: 42px;
  height: 52px;
  flex: 0 0 42px;
  display: grid;
  place-items: center;
  border: 1px solid #d9e1ee;
  border-radius: 6px;
  background: linear-gradient(150deg, #22365a, #557ba8 52%, #d9e7f7);
  color: rgba(255, 255, 255, .9);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .08em;
  box-shadow: 0 2px 5px rgba(15, 23, 42, .12);
}

.project-name > div {
  min-width: 0;
  display: grid;
  gap: 5px;
}

.project-name strong {
  overflow: hidden;
  color: #222b3a;
  font-size: 14px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-name > div > span,
.date-cell {
  color: #8a94a6;
  font-size: 11px;
}

.rule-chips {
  min-width: 150px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.rule-chips span {
  padding: 4px 8px;
  border: 1px solid #d7e6ff;
  border-radius: 999px;
  background: #eef5ff;
  color: #2670de;
  font-size: 11px;
  font-weight: 650;
}

.action-column {
  width: 124px;
}

.actions {
  white-space: nowrap;
}

.row-action {
  padding: 6px 7px;
  border: 0;
  background: transparent;
  color: #1769e8;
  font-size: 12px;
  font-weight: 700;
}

.row-action:hover {
  text-decoration: underline;
}

.row-action.danger {
  color: #e5484d;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  padding: 28px;
  background: rgba(42, 52, 68, .34);
  backdrop-filter: blur(2px);
}

.modal-card {
  width: min(720px, 100%);
  max-height: calc(100vh - 56px);
  overflow-y: auto;
  border: 1px solid #e6eaf0;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 22px 55px rgba(28, 39, 57, .22), 0 4px 14px rgba(28, 39, 57, .1);
}

.editor-modal {
  padding: 26px 28px 24px;
}

.modal-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
}

.modal-eyebrow {
  margin: 0 0 8px;
  color: #1769e8;
  font-size: 13px;
  font-weight: 700;
}

.modal-head h2,
.delete-modal h2 {
  margin: 0;
  color: #111827;
  font-size: 24px;
  line-height: 1.2;
  font-weight: 800;
  letter-spacing: -.025em;
}

.close-button {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #344054;
  font-size: 26px;
  font-weight: 300;
  line-height: 1;
}

.close-button:hover:not(:disabled) {
  background: #f4f6f8;
}

.project-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 19px 18px;
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
  color: #344054;
  font-size: 13px;
  font-weight: 700;
}

.required-field > span:not(.field-label-row)::before,
.required-legend::before,
.field-label-row b::before {
  content: '*';
  margin-right: 5px;
  color: #e5484d;
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.field-label-row b {
  font-size: 13px;
  font-weight: 700;
}

.field-label-row small {
  color: #8a94a6;
  font-size: 11px;
  font-weight: 500;
}

.field input,
.field select {
  width: 100%;
  min-height: 42px;
  border: 1px solid #d6dce6;
  border-radius: 7px;
  background: #fff;
  color: #273142;
  padding: 0 13px;
  outline: none;
  font-size: 13px;
  transition: border-color .15s ease, box-shadow .15s ease;
}

.field input::placeholder {
  color: #a4adbb;
}

.field input:focus,
.field select:focus {
  border-color: #6b9df2;
  box-shadow: 0 0 0 3px rgba(23, 105, 232, .09);
}

.region-field {
  margin-top: 1px;
}

.redraw-field {
  margin: 1px 0 0;
  padding: 0;
  border: 0;
}

.redraw-options {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin-top: 10px;
}

.redraw-option {
  position: relative;
  min-height: 92px;
  padding: 15px 14px;
  display: flex;
  align-items: center;
  gap: 11px;
  border: 1px solid #dfe5ee;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: border-color .15s ease, background .15s ease, box-shadow .15s ease;
}

.redraw-option:hover {
  border-color: #adc7f6;
}

.redraw-option.selected {
  border-color: #367cf0;
  background: #f6f9ff;
  box-shadow: inset 0 0 0 1px rgba(54, 124, 240, .08);
}

.redraw-option input {
  position: absolute;
  opacity: 0;
  pointer-events: none;
}

.rule-icon {
  width: 42px;
  height: 42px;
  flex: 0 0 42px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #eaf3ff;
  color: #1769e8;
  font-size: 14px;
  font-weight: 900;
}

.redraw-option:nth-child(2) .rule-icon {
  font-size: 17px;
}

.redraw-option:nth-child(3) .rule-icon {
  font-size: 12px;
  letter-spacing: -1px;
}

.check-mark {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 17px;
  height: 17px;
  display: grid;
  place-items: center;
  border: 1px solid #cbd5e1;
  border-radius: 50%;
  background: #fff;
  color: transparent;
  font-size: 10px;
  font-weight: 900;
}

.redraw-option.selected .check-mark {
  border-color: #1769e8;
  background: #1769e8;
  color: #fff;
}

.rule-copy {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.rule-copy strong {
  color: #263143;
  font-size: 14px;
  font-weight: 750;
}

.rule-copy small {
  color: #7e8999;
  font-size: 10px;
  line-height: 1.55;
}

.form-error {
  padding: 10px 12px;
  border-radius: 7px;
  font-size: 12px;
}

.modal-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding-top: 3px;
}

.modal-actions .primary-button {
  min-width: 116px;
}

.delete-modal {
  width: min(470px, 100%);
  padding: 28px;
  text-align: center;
}

.delete-icon {
  width: 50px;
  height: 50px;
  margin: 0 auto 15px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #fff0ee;
  color: #d92d20;
  font-size: 23px;
  font-weight: 900;
}

.delete-modal > p {
  margin: 12px 0 0;
  color: #566279;
  font-size: 13px;
  line-height: 1.7;
}

.delete-modal .delete-note {
  color: #8490a2;
  font-size: 11px;
}

.delete-modal .form-error {
  margin-top: 14px;
  text-align: left;
}

.delete-modal .modal-actions {
  margin-top: 22px;
}

@media (max-width: 900px) {
  .project-page {
    padding: 24px 18px 42px;
  }

  .page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .create-button {
    align-self: flex-start;
  }
}

@media (max-width: 700px) {
  .modal-backdrop {
    padding: 14px;
  }

  .editor-modal {
    padding: 22px 18px;
  }

  .project-form {
    grid-template-columns: 1fr;
  }

  .full-field {
    grid-column: auto;
  }

  .field-label-row {
    align-items: flex-start;
    flex-direction: column;
    gap: 4px;
  }

  .redraw-options {
    grid-template-columns: 1fr;
  }
}
</style>
