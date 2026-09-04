import { breakdownApi } from './api/breakdown'
import { sceneTimelineApi } from './api/scene-timeline'
import type { BackgroundTask } from './types/studio'

const PAGE_SELECTOR = '.breakdown-page-v2'
const FLASH_CLASS = 'single-shot-rerun-flash'
const WARNING_PANEL_CLASS = 'single-shot-rerun-warning-panel'
const RERUN_WARNING_MARKERS = ['单镜重拉', '跨越多个分镜']

let requestInFlight = false
let warningRequestSerial = 0
let lastWarningEpisodeId = ''
let warningRefreshTimer: ReturnType<typeof setTimeout> | null = null
let pageWasMounted = false

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

function relevantRerunWarnings(warnings: string[]): string[] {
  return Array.from(new Set(
    warnings
      .map((item) => String(item || '').trim())
      .filter((item) => item && RERUN_WARNING_MARKERS.some((marker) => item.includes(marker))),
  ))
}

function renderRerunWarnings(warnings: string[]): void {
  const page = document.querySelector<HTMLElement>(PAGE_SELECTOR)
  const heading = page?.querySelector<HTMLElement>('.page-heading-card')
  if (!page || !heading) return

  page.querySelector<HTMLElement>(`.${WARNING_PANEL_CLASS}`)?.remove()
  if (!warnings.length) return

  const panel = document.createElement('section')
  panel.className = WARNING_PANEL_CLASS
  panel.setAttribute('role', 'status')
  panel.setAttribute('aria-live', 'polite')

  const icon = document.createElement('span')
  icon.className = 'single-shot-rerun-warning-icon'
  icon.textContent = '!'

  const content = document.createElement('div')
  const title = document.createElement('strong')
  title.textContent = '当前拉片结果有需要注意的地方'
  content.appendChild(title)

  if (warnings.length === 1) {
    const paragraph = document.createElement('p')
    paragraph.textContent = warnings[0]
    content.appendChild(paragraph)
  } else {
    const list = document.createElement('ul')
    for (const warning of warnings) {
      const item = document.createElement('li')
      item.textContent = warning
      list.appendChild(item)
    }
    content.appendChild(list)
  }

  panel.append(icon, content)

  const flash = page.querySelector<HTMLElement>(`.${FLASH_CLASS}`)
  if (flash) flash.insertAdjacentElement('afterend', panel)
  else heading.insertAdjacentElement('afterend', panel)
}

async function refreshRerunWarnings(force = false): Promise<void> {
  const page = document.querySelector<HTMLElement>(PAGE_SELECTOR)
  if (!page) {
    pageWasMounted = false
    lastWarningEpisodeId = ''
    return
  }

  const episodeId = selectedEpisodeId()
  if (!episodeId) return
  if (!force && episodeId === lastWarningEpisodeId) return

  const serial = ++warningRequestSerial
  try {
    const timeline = await sceneTimelineApi.getEpisode(episodeId)
    if (serial !== warningRequestSerial || episodeId !== selectedEpisodeId()) return
    lastWarningEpisodeId = episodeId
    renderRerunWarnings(relevantRerunWarnings(timeline?.warnings || []))
  } catch {
    // 主页面本身已经负责 Timeline 读取错误；sidecar 不重复制造第二套错误状态。
  }
}

function scheduleWarningRefresh(force = false, delayMs = 120): void {
  if (warningRefreshTimer) window.clearTimeout(warningRefreshTimer)
  warningRefreshTimer = window.setTimeout(() => {
    warningRefreshTimer = null
    void refreshRerunWarnings(force)
  }, delayMs)
}

function handlePageMutation(): void {
  patchHelpCopy()
  const mounted = Boolean(document.querySelector(PAGE_SELECTOR))
  if (!mounted) {
    pageWasMounted = false
    lastWarningEpisodeId = ''
    return
  }
  const episodeId = selectedEpisodeId()
  if (!pageWasMounted || (episodeId && episodeId !== lastWarningEpisodeId)) {
    pageWasMounted = true
    scheduleWarningRefresh(false)
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

document.addEventListener('change', (event) => {
  const element = event.target
  if (!(element instanceof HTMLSelectElement)) return
  if (!element.matches(`${PAGE_SELECTOR} .heading-data-row select`)) return
  lastWarningEpisodeId = ''
  scheduleWarningRefresh(true, 180)
})

window.addEventListener('studio-task-finished', (event) => {
  const task = (event as CustomEvent<BackgroundTask>).detail
  if (!task || task.task_type !== 'SHOT_BREAKDOWN_P2') return
  if (task.episode_id !== selectedEpisodeId()) return
  // V2 页面会同时刷新正式 Timeline；稍后再读一次，只负责提取用户级安全提示。
  scheduleWarningRefresh(true, 350)
})

const observer = new MutationObserver(handlePageMutation)
observer.observe(document.documentElement, { childList: true, subtree: true })
handlePageMutation()

export {}
