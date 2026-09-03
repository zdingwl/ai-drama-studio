import { sceneTimelineApi, type SceneTimelineManualShotEdit } from './api/scene-timeline'

const PAGE_SELECTOR = '.breakdown-page-v2'
const SUPPORTED_SECTIONS = new Set(['内容概要', '动作与表演', '镜头语言', '画面'])

interface EditorField {
  key: string
  label: string
  value: string
  textarea?: boolean
}

interface EditorContext {
  episodeId: string
  shotOrdinal: number
  title: string
  fields: EditorField[]
  dialogueIndex?: number
}

let modal: HTMLElement | null = null
let saving = false

function text(value: string | null | undefined): string {
  const normalized = String(value || '').trim()
  return normalized === '—' || normalized.startsWith('暂无') || normalized === '未独立识别' ? '' : normalized
}

function selectedEpisodeId(): string {
  return (document.querySelector<HTMLSelectElement>(`${PAGE_SELECTOR} .heading-data-row select`)?.value || '').trim()
}

function selectedShotOrdinal(): number {
  const title = document.querySelector<HTMLElement>(`${PAGE_SELECTOR} .shot-workbench-header h2`)?.textContent || ''
  const match = title.match(/Shot\s+(\d+)/i)
  return match ? Number(match[1]) : 0
}

function sectionTitle(button: HTMLElement): string {
  const card = button.closest<HTMLElement>('.info-card')
  return card?.querySelector<HTMLElement>('.info-card-title h3')?.textContent?.trim() || ''
}

function fieldValue(card: HTMLElement, label: string): string {
  for (const row of Array.from(card.querySelectorAll<HTMLElement>('.field-list > div'))) {
    const key = row.querySelector<HTMLElement>('dt')?.textContent?.trim()
    if (key === label) return text(row.querySelector<HTMLElement>('dd')?.textContent)
  }
  return ''
}

function contextForSection(button: HTMLElement): EditorContext | null {
  const episodeId = selectedEpisodeId()
  const shotOrdinal = selectedShotOrdinal()
  if (!episodeId || shotOrdinal <= 0) return null

  const title = sectionTitle(button)
  if (!SUPPORTED_SECTIONS.has(title)) return null
  const card = button.closest<HTMLElement>('.info-card')
  if (!card) return null

  if (title === '内容概要') {
    return {
      episodeId,
      shotOrdinal,
      title,
      fields: [{
        key: 'summary',
        label: '内容概要',
        value: text(card.querySelector<HTMLElement>('.summary-paragraph')?.textContent),
        textarea: true,
      }],
    }
  }

  if (title === '动作与表演') {
    return {
      episodeId,
      shotOrdinal,
      title,
      fields: [{ key: 'performance_text', label: '动作与表演', value: fieldValue(card, '动作'), textarea: true }],
    }
  }

  if (title === '镜头语言') {
    return {
      episodeId,
      shotOrdinal,
      title,
      fields: [
        { key: 'shot_type', label: '景别', value: fieldValue(card, '景别') },
        { key: 'composition', label: '构图', value: fieldValue(card, '构图'), textarea: true },
        { key: 'camera_motion', label: '运镜', value: fieldValue(card, '运镜') },
      ],
    }
  }

  return {
    episodeId,
    shotOrdinal,
    title,
    fields: [
      { key: 'time_of_day', label: '时间', value: fieldValue(card, '时间') },
      { key: 'interior_exterior', label: '空间', value: fieldValue(card, '空间') },
      { key: 'environment', label: '环境 / 氛围', value: fieldValue(card, '氛围'), textarea: true },
    ],
  }
}

function contextForDialogue(button: HTMLElement): EditorContext | null {
  const article = button.closest<HTMLElement>('.dialogue-list article')
  if (!article) return null
  const episodeId = selectedEpisodeId()
  const shotOrdinal = selectedShotOrdinal()
  if (!episodeId || shotOrdinal <= 0) return null
  const articles = Array.from(document.querySelectorAll<HTMLElement>(`${PAGE_SELECTOR} .dialogue-list article`))
  const index = articles.indexOf(article)
  if (index < 0) return null
  return {
    episodeId,
    shotOrdinal,
    title: `对白 ${String(index + 1).padStart(2, '0')}`,
    dialogueIndex: index,
    fields: [{ key: 'dialogue_text', label: '最终源对白', value: article.querySelector<HTMLElement>('p')?.textContent?.trim() || '', textarea: true }],
  }
}

function closeModal(): void {
  modal?.remove()
  modal = null
  saving = false
}

function payloadFrom(context: EditorContext, form: HTMLFormElement): SceneTimelineManualShotEdit {
  const values = new FormData(form)
  if (context.dialogueIndex !== undefined) {
    return { dialogues: [{ index: context.dialogueIndex, text: String(values.get('dialogue_text') || '') }] }
  }
  if (context.title === '画面') {
    return {
      scene: {
        time_of_day: String(values.get('time_of_day') || ''),
        interior_exterior: String(values.get('interior_exterior') || ''),
        environment: String(values.get('environment') || ''),
      },
    }
  }
  const result: SceneTimelineManualShotEdit = {}
  for (const field of context.fields) {
    const value = String(values.get(field.key) || '')
    if (field.key === 'summary') result.summary = value
    if (field.key === 'performance_text') result.performance_text = value
    if (field.key === 'shot_type') result.shot_type = value
    if (field.key === 'composition') result.composition = value
    if (field.key === 'camera_motion') result.camera_motion = value
  }
  return result
}

function openModal(context: EditorContext): void {
  closeModal()
  const backdrop = document.createElement('div')
  backdrop.className = 'breakdown-manual-editor-backdrop'
  const fieldHtml = context.fields.map((field) => `
    <label class="breakdown-manual-editor-field">
      <span>${field.label}</span>
      ${field.textarea
        ? `<textarea name="${field.key}" rows="${field.key === 'summary' || field.key === 'performance_text' || field.key === 'dialogue_text' ? 5 : 3}"></textarea>`
        : `<input name="${field.key}" type="text" />`}
    </label>
  `).join('')
  backdrop.innerHTML = `
    <section class="breakdown-manual-editor-dialog" role="dialog" aria-modal="true" aria-label="编辑${context.title}">
      <header>
        <div><strong>编辑${context.title}</strong><span>Shot ${String(context.shotOrdinal).padStart(2, '0')} · 人工修改会覆盖当前拉片显示，但不会改写 AI 原始证据</span></div>
        <button type="button" data-editor-close aria-label="关闭">×</button>
      </header>
      <form>
        <div class="breakdown-manual-editor-fields">${fieldHtml}</div>
        <p class="breakdown-manual-editor-error" hidden></p>
        <footer>
          <button type="button" class="editor-cancel" data-editor-close>取消</button>
          <button type="submit" class="editor-save">保存修改</button>
        </footer>
      </form>
    </section>
  `
  document.body.appendChild(backdrop)
  modal = backdrop

  const form = backdrop.querySelector<HTMLFormElement>('form')!
  for (const field of context.fields) {
    const input = form.elements.namedItem(field.key)
    if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement) input.value = field.value
  }

  backdrop.querySelectorAll<HTMLElement>('[data-editor-close]').forEach((element) => {
    element.addEventListener('click', closeModal)
  })
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) closeModal()
  })
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    if (saving) return
    const saveButton = form.querySelector<HTMLButtonElement>('.editor-save')!
    const error = form.querySelector<HTMLElement>('.breakdown-manual-editor-error')!
    saving = true
    saveButton.disabled = true
    saveButton.textContent = '保存中…'
    error.hidden = true
    try {
      await sceneTimelineApi.editShot(context.episodeId, context.shotOrdinal, payloadFrom(context, form))
      closeModal()
      window.location.reload()
    } catch (reason) {
      saving = false
      saveButton.disabled = false
      saveButton.textContent = '保存修改'
      error.textContent = reason instanceof Error ? reason.message : '保存失败，请稍后重试'
      error.hidden = false
    }
  })

  const first = form.querySelector<HTMLInputElement | HTMLTextAreaElement>('input, textarea')
  requestAnimationFrame(() => first?.focus())
}

function supportedEditButton(target: EventTarget | null): { button: HTMLElement; context: EditorContext } | null {
  if (!(target instanceof Element)) return null
  const page = target.closest(PAGE_SELECTOR)
  if (!page) return null
  const button = target.closest<HTMLElement>('button')
  if (!button || !button.textContent?.includes('编辑')) return null
  const dialogue = contextForDialogue(button)
  if (dialogue) return { button, context: dialogue }
  const section = contextForSection(button)
  return section ? { button, context: section } : null
}

document.addEventListener('click', (event) => {
  const match = supportedEditButton(event.target)
  if (!match) return
  event.preventDefault()
  event.stopPropagation()
  event.stopImmediatePropagation()
  openModal(match.context)
}, true)

document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && modal) closeModal()
})

export {}
