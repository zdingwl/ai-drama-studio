import { router } from './router'

const SOURCE_PAGE_SELECTOR = '.source-video-page'
const STAGE_ITEM_SELECTOR = `${SOURCE_PAGE_SELECTOR} .stage-list .stage-item`
const NEXT_STAGE_SELECTOR = `${SOURCE_PAGE_SELECTOR} .next-stage-card`
const LINK_CLASS = 'source-video-breakdown-link'
const LOCKED_CLASS = 'source-video-breakdown-locked'

let observer: MutationObserver | null = null
let enhancementQueued = false

function isElement(value: EventTarget | null): value is Element {
  return value instanceof Element
}

function isBreakdownStage(element: Element): element is HTMLElement {
  if (!(element instanceof HTMLElement)) return false
  const label = element.querySelector('strong')?.textContent?.trim()
  return label === 'AI 拉片'
}

function stageIsUnlocked(element: HTMLElement): boolean {
  return !element.classList.contains('stage-blocked') && !element.classList.contains('stage-waiting')
}

function nextStageIsUnlocked(element: HTMLElement): boolean {
  return element.querySelector('.next-state.ready') !== null
}

function setNavigationSemantics(element: HTMLElement, enabled: boolean, label: string): void {
  element.classList.toggle(LINK_CLASS, enabled)
  element.classList.toggle(LOCKED_CLASS, !enabled)
  element.setAttribute('role', enabled ? 'link' : 'group')
  element.setAttribute('aria-disabled', enabled ? 'false' : 'true')
  element.setAttribute('aria-label', enabled ? label : `${label}，当前未解锁`)
  if (enabled) element.tabIndex = 0
  else element.removeAttribute('tabindex')
}

function enhanceNavigationTargets(): void {
  enhancementQueued = false

  document.querySelectorAll<HTMLElement>(STAGE_ITEM_SELECTOR).forEach((element) => {
    if (!isBreakdownStage(element)) return
    setNavigationSemantics(element, stageIsUnlocked(element), '进入 AI 拉片')
  })

  document.querySelectorAll<HTMLElement>(NEXT_STAGE_SELECTOR).forEach((element) => {
    setNavigationSemantics(element, nextStageIsUnlocked(element), '进入下一阶段：AI 拉片')
  })
}

function queueEnhancement(): void {
  if (enhancementQueued) return
  enhancementQueued = true
  queueMicrotask(enhanceNavigationTargets)
}

function currentProjectId(): string {
  const routeProjectId = router.currentRoute.value.params.projectId
  return typeof routeProjectId === 'string' ? routeProjectId.trim() : ''
}

async function enterBreakdown(): Promise<void> {
  const projectId = currentProjectId()
  if (!projectId) return
  await router.push({ name: 'breakdown', params: { projectId } })
}

function navigationTarget(target: EventTarget | null): HTMLElement | null {
  if (!isElement(target)) return null

  const stage = target.closest<HTMLElement>(STAGE_ITEM_SELECTOR)
  if (stage && isBreakdownStage(stage) && stageIsUnlocked(stage)) return stage

  const nextStage = target.closest<HTMLElement>(NEXT_STAGE_SELECTOR)
  if (nextStage && nextStageIsUnlocked(nextStage)) return nextStage

  return null
}

function activateFromEvent(event: Event): void {
  const target = navigationTarget(event.target)
  if (!target) return
  event.preventDefault()
  void enterBreakdown()
}

document.addEventListener('click', activateFromEvent)
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return
  const target = navigationTarget(event.target)
  if (!target || event.target !== target) return
  event.preventDefault()
  void enterBreakdown()
})

if (typeof MutationObserver !== 'undefined') {
  observer = new MutationObserver(queueEnhancement)
  const root = document.getElementById('app')
  if (root) observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] })
}

queueEnhancement()
window.addEventListener('popstate', queueEnhancement)

export {}