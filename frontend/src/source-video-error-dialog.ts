declare global {
  interface Window {
    __aiDramaSourceVideoErrorDialogInstalled?: boolean
  }
}

const PAGE_SELECTOR = '.source-video-page'
const STATUS_SELECTOR = '.process-status'
const FAILED_PILL_SELECTOR = '.status-pill.status-failed'
const TRIGGER_CLASS = 'source-video-error-trigger'

function installSourceVideoErrorDialog(): void {
  if (typeof window === 'undefined' || window.__aiDramaSourceVideoErrorDialogInstalled) return
  window.__aiDramaSourceVideoErrorDialogInstalled = true

  let overlay: HTMLDivElement | null = null

  const close = (): void => {
    overlay?.remove()
    overlay = null
    document.body.classList.remove('source-video-error-dialog-open')
  }

  const copyText = async (text: string): Promise<boolean> => {
    if (!text) return false
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
        return true
      }
    } catch {
      // Clipboard API 可能因浏览器权限或非 HTTPS 环境不可用，继续走兼容方案。
    }

    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.left = '-9999px'
    textarea.style.top = '0'
    document.body.appendChild(textarea)
    textarea.select()
    let copied = false
    try {
      copied = document.execCommand('copy')
    } finally {
      textarea.remove()
    }
    return copied
  }

  const open = (trigger: HTMLButtonElement): void => {
    close()

    const errorText = trigger.dataset.error || '未提供错误详情'
    const taskLabel = trigger.dataset.taskLabel || '任务'
    const episodeLabel = trigger.dataset.episodeLabel || ''

    overlay = document.createElement('div')
    overlay.className = 'source-video-error-dialog-backdrop'
    overlay.setAttribute('role', 'presentation')

    const dialog = document.createElement('section')
    dialog.className = 'source-video-error-dialog'
    dialog.setAttribute('role', 'dialog')
    dialog.setAttribute('aria-modal', 'true')
    dialog.setAttribute('aria-labelledby', 'source-video-error-dialog-title')
    dialog.tabIndex = -1

    const header = document.createElement('header')
    header.className = 'source-video-error-dialog-head'

    const heading = document.createElement('div')
    const eyebrow = document.createElement('p')
    eyebrow.textContent = taskLabel
    const title = document.createElement('h2')
    title.id = 'source-video-error-dialog-title'
    title.textContent = '错误详情'
    const episode = document.createElement('span')
    episode.textContent = episodeLabel
    heading.append(eyebrow, title)
    if (episodeLabel) heading.appendChild(episode)

    const closeButton = document.createElement('button')
    closeButton.type = 'button'
    closeButton.className = 'source-video-error-dialog-close'
    closeButton.setAttribute('aria-label', '关闭错误详情')
    closeButton.textContent = '×'
    closeButton.addEventListener('click', close)

    header.append(heading, closeButton)

    const body = document.createElement('div')
    body.className = 'source-video-error-dialog-body'
    const label = document.createElement('div')
    label.className = 'source-video-error-dialog-label'
    label.textContent = '完整错误信息'
    const errorBox = document.createElement('pre')
    errorBox.className = 'source-video-error-dialog-message'
    errorBox.textContent = errorText
    body.append(label, errorBox)

    const footer = document.createElement('footer')
    footer.className = 'source-video-error-dialog-actions'

    const cancelButton = document.createElement('button')
    cancelButton.type = 'button'
    cancelButton.className = 'source-video-error-dialog-secondary'
    cancelButton.textContent = '关闭'
    cancelButton.addEventListener('click', close)

    const copyButton = document.createElement('button')
    copyButton.type = 'button'
    copyButton.className = 'source-video-error-dialog-primary'
    copyButton.textContent = '复制错误信息'
    copyButton.addEventListener('click', async () => {
      const copied = await copyText(errorText)
      const original = '复制错误信息'
      copyButton.textContent = copied ? '已复制' : '复制失败'
      window.setTimeout(() => {
        if (copyButton.isConnected) copyButton.textContent = original
      }, 1500)
    })

    footer.append(cancelButton, copyButton)
    dialog.append(header, body, footer)
    overlay.appendChild(dialog)

    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) close()
    })

    document.body.appendChild(overlay)
    document.body.classList.add('source-video-error-dialog-open')
    dialog.focus()
  }

  const taskLabelForStatus = (status: HTMLElement): string => {
    const cell = status.closest('td') as HTMLTableCellElement | null
    if (!cell) return '任务失败'
    if (cell.cellIndex === 4) return '镜头检测失败'
    if (cell.cellIndex === 5) return '拉片分析失败'
    return '任务失败'
  }

  const episodeLabelForStatus = (status: HTMLElement): string => {
    const row = status.closest('tr')
    const filename = row?.querySelector<HTMLElement>('.video-copy strong')?.textContent?.trim() || ''
    return filename
  }

  const syncFailureTriggers = (): void => {
    document.querySelectorAll<HTMLElement>(`${PAGE_SELECTOR} ${STATUS_SELECTOR}`).forEach((status) => {
      const failed = status.querySelector<HTMLElement>(FAILED_PILL_SELECTOR)
      const detail = status.querySelector<HTMLElement>(':scope > small')
      let trigger = status.querySelector<HTMLButtonElement>(`:scope > .${TRIGGER_CLASS}`)

      if (!failed || !detail) {
        if (detail?.hidden) detail.hidden = false
        trigger?.remove()
        return
      }

      const errorText = detail.getAttribute('title')?.trim() || detail.textContent?.trim() || ''
      if (!errorText) {
        if (detail.hidden) detail.hidden = false
        trigger?.remove()
        return
      }

      if (!detail.hidden) detail.hidden = true
      if (!trigger) {
        trigger = document.createElement('button')
        trigger.type = 'button'
        trigger.className = TRIGGER_CLASS
        trigger.textContent = '查看错误'
        trigger.addEventListener('click', () => open(trigger as HTMLButtonElement))
        status.appendChild(trigger)
      }

      trigger.dataset.error = errorText
      trigger.dataset.taskLabel = taskLabelForStatus(status)
      trigger.dataset.episodeLabel = episodeLabelForStatus(status)
      trigger.title = '查看完整错误信息'
    })
  }

  const observer = new MutationObserver(() => syncFailureTriggers())
  observer.observe(document.body, {
    subtree: true,
    childList: true,
    characterData: true,
    attributes: true,
    attributeFilter: ['class', 'title'],
  })

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && overlay) close()
  })

  syncFailureTriggers()
}

installSourceVideoErrorDialog()

export {}
