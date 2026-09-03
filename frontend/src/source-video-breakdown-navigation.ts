import { router } from './router'

const SOURCE_PAGE_SELECTOR = '.source-video-page'
const STAGE_ITEM_SELECTOR = `${SOURCE_PAGE_SELECTOR} .stage-list .stage-item`
const NEXT_STAGE_SELECTOR = `${SOURCE_PAGE_SELECTOR} .next-stage-card`
const LINK_CLASS = 'source-video-breakdown-link'
const LOCKED_CLASS = 'source-video-breakdown-locked'

const STAGE_ROUTE_BY_LABEL: Record<string, string> = {
  '原短剧视频': 'studio',
  'AI 拉片': 'breakdown',
  '原片确认': 'source-confirm',
  '视频重做': 'remake',
  '成片输出': 'output',
}

let observer: MutationObserver | null = null
let enhancementQueued = false

function isElement(value: EventTarget | null): value is Element {
  return value instanceof Element
}

function stageRoute(element: Element): string | null {
  if (!(element instanceof HTMLElement)) return null
  const label = element.querySelector('strong')?.textContent?.trim() || ''
  return STAGE_ROUTE_BY_LABEL[label] || null
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
    const routeName = stageRoute(element)
    if (!routeName) return
    const label = element.querySelector('strong')?.textContent?.trim() || '工作阶段'
    const isCurrentSourceStage = routeName === 'studio'
    setNavigationSemantics(element, isCurrentSourceStage || stageIsUnlocked(element), `进入${label}`)
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

async function enterRoute(routeName: string): Promise<void> {
  const projectId = currentProjectId()
  if (!projectId) return
  await router.push({ name: routeName, params: { projectId } })
}

function navigationTarget(target: EventTarget | null): { element: HTMLElement; routeName: string } | null {
  if (!isElement(target)) return null

  const stage = target.closest<HTMLElement>(STAGE_ITEM_SELECTOR)
  if (stage) {
    const routeName = stageRoute(stage)
    if (routeName && (routeName === 'studio' || stageIsUnlocked(stage))) return { element: stage, routeName }
  }

  const nextStage = target.closest<HTMLElement>(NEXT_STAGE_SELECTOR)
  if (nextStage && nextStageIsUnlocked(nextStage)) return { element: nextStage, routeName: 'breakdown' }

  return null
}

function activateFromEvent(event: Event): void {
  const target = navigationTarget(event.target)
  if (!target) return
  event.preventDefault()
  void enterRoute(target.routeName)
}

document.addEventListener('click', activateFromEvent)
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return
  const target = navigationTarget(event.target)
  if (!target || event.target !== target.element) return
  event.preventDefault()
  void enterRoute(target.routeName)
})

if (typeof MutationObserver !== 'undefined') {
  observer = new MutationObserver(queueEnhancement)
  const root = document.getElementById('app')
  if (root) observer.observe(root, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] })
}

queueEnhancement()
window.addEventListener('popstate', queueEnhancement)

export {}
