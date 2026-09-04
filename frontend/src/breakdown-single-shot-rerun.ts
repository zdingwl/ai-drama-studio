import { breakdownApi } from './api/breakdown'

const PAGE_SELECTOR = '.breakdown-page-v2'
const FLASH_CLASS = 'single-shot-rerun-flash'

let requestInFlight = false

function selectedEpisodeId(): string {
  return (document.querySelector<HTMLSelectElement>(`${PAGE_SELECTOR} .heading-data-row select`)?.value || '').trim()
}

function selectedShotOrdinal(): number {
  const title = document.querySelector<HTMLElement>(`${PAGE_SELECTOR} .shot-workbench-header h2`)?.textContent || ''
  const match = title.match(/Shot\s+(\d+)/i)
  return match ? Number(match[1]) : 0
}

function isSingleShotButton(target: EventTarget | null): HTMLButtonElement | null {
  if (!(target instanceof Element)) return null
  if (!target.closest(PAGE_SELECTOR)) return null
  const button = target.closest<HTMLButtonElement>('button')
  if (!button) return null
  if (button.matches('.current-shot-action')) return button
  if (button.closest('.shot-workbench-header') && button.textContent?.includes('重新拉片')) return button
  return null
}

function removeFlash(): void {
  document.querySelector<HTMLElement>(`${PAGE_SELECTOR} .${FLASH_CLASS}`)?.remove()
}

function showFlash(message: string, tone: 'success' | 'danger' | 'warning' = 'success'): void {
  const page = document.querySelector<HTMLElement>(PAGE_SELECTOR)
  const heading = page?.querySelector<HTMLElement>('.page-heading-card')
  if (!page || !heading) return
  removeFlash()
  const element = document.createElement('div')
  element.className = `${FLASH_CLASS} message ${tone}`
  element.textContent = message
  heading.insertAdjacentElement('afterend', element)
  window.setTimeout(() => element.remove(), tone === 'success' ? 5000 : 9000)
}

function patchHelpCopy(): void {
  for (const paragraph of Array.from(document.querySelectorAll<HTMLElement>(`${PAGE_SELECTOR} .help-dialog p`))) {
    const copy = paragraph.textContent || ''
    if (!copy.includes('当前分镜拉片')) continue
    paragraph.textContent = '3. “当前分镜拉片 / 重新拉片”只重跑当前 Shot：ASR/OCR 只处理当前分镜，VLM 最多读取前后相邻镜头作为上下文；不会重跑整集，也不会自动改写共享 Scene 边界或人物身份。'
  }
}

async function startSelectedShot(button: HTMLButtonElement): Promise<void> {
  if (requestInFlight || button.disabled) return
  const episodeId = selectedEpisodeId()
  const shotOrdinal = selectedShotOrdinal()
  if (!episodeId || shotOrdinal <= 0) {
    showFlash('无法确定当前剧集或分镜，请刷新页面后重试。', 'danger')
    return
  }

  requestInFlight = true
  const previousText = button.textContent || ''
  button.disabled = true
  button.textContent = '启动中…'
  removeFlash()
  try {
    await breakdownApi.startShot(episodeId, shotOrdinal)
    showFlash(`Shot ${String(shotOrdinal).padStart(2, '0')} 单镜拉片任务已启动；整集其他分镜不会重跑。`)
  } catch (reason) {
    showFlash(reason instanceof Error ? reason.message : '当前分镜拉片启动失败，请稍后重试。', 'danger')
  } finally {
    requestInFlight = false
    // Vue 收到 studio-task-created 后会把按钮切到正式 disabled 状态；若请求失败则恢复可点。
    if (button.isConnected) {
      button.textContent = previousText
      const running = Boolean(document.querySelector(`${PAGE_SELECTOR} .running-pill`))
      if (!running) button.disabled = false
    }
  }
}

document.addEventListener('click', (event) => {
  const button = isSingleShotButton(event.target)
  if (!button) return
  event.preventDefault()
  event.stopPropagation()
  event.stopImmediatePropagation()
  void startSelectedShot(button)
}, true)

const observer = new MutationObserver(() => patchHelpCopy())
observer.observe(document.documentElement, { childList: true, subtree: true })

export {}
