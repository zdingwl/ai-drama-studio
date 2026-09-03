import { router } from './router'

const PAGE_SELECTOR = '.breakdown-page-v1'
const STAGE_SELECTOR = `${PAGE_SELECTOR} .stage-list .stage-item`

interface StageShellDefinition {
  label: string
  description: string
  routeName: string
}

const STAGE_SHELL: StageShellDefinition[] = [
  { label: '原短剧视频', description: '上传、排序与镜头检测', routeName: 'studio' },
  { label: 'AI 拉片', description: '剧情、对白与镜头理解', routeName: 'breakdown' },
  { label: '原片确认', description: '人物 / 场景 / 道具确认', routeName: 'source-confirm' },
  { label: '视频重做', description: '本土化、配音与视频生成', routeName: 'remake' },
  { label: '成片输出', description: '后期检查与最终导出', routeName: 'output' },
]

let observer: MutationObserver | null = null
let syncQueued = false

function currentProjectId(): string {
  const value = router.currentRoute.value.params.projectId
  return typeof value === 'string' ? value.trim() : ''
}

function syncStage(stage: HTMLElement, definition: StageShellDefinition, index: number): void {
  const title = stage.querySelector<HTMLElement>('.stage-copy > strong')
  if (title && title.textContent?.trim() !== definition.label) title.textContent = definition.label

  const details = Array.from(stage.querySelectorAll<HTMLElement>('.stage-copy > small'))
  const description = details[0]
  if (description && description.textContent?.trim() !== definition.description) description.textContent = definition.description
  details.slice(1).forEach((detail) => {
    detail.hidden = true
    detail.setAttribute('aria-hidden', 'true')
  })

  stage.dataset.workflowRoute = definition.routeName
  stage.setAttribute('role', 'link')
  stage.setAttribute('aria-label', `进入${definition.label}`)
  stage.tabIndex = index === 1 ? -1 : 0
}

function synchronizeBreakdownShell(): void {
  syncQueued = false
  const page = document.querySelector<HTMLElement>(PAGE_SELECTOR)
  if (!page) return

  const stages = Array.from(document.querySelectorAll<HTMLElement>(STAGE_SELECTOR))
  stages.forEach((stage, index) => {
    const definition = STAGE_SHELL[index]
    if (!definition) {
      stage.hidden = true
      stage.setAttribute('aria-hidden', 'true')
      stage.tabIndex = -1
      return
    }
    stage.hidden = false
    stage.removeAttribute('aria-hidden')
    syncStage(stage, definition, index)
  })
  page.dataset.shellSynchronized = 'true'
}

function queueSynchronization(): void {
  if (syncQueued) return
  syncQueued = true
  queueMicrotask(synchronizeBreakdownShell)
}

function navigationStage(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element)) return null
  return target.closest<HTMLElement>(STAGE_SELECTOR)
}

async function navigate(stage: HTMLElement): Promise<void> {
  const routeName = stage.dataset.workflowRoute
  const projectId = currentProjectId()
  if (!routeName || !projectId || routeName === 'breakdown') return
  await router.push({ name: routeName, params: { projectId } })
}

document.addEventListener('click', (event) => {
  const stage = navigationStage(event.target)
  if (!stage || !stage.dataset.workflowRoute || stage.dataset.workflowRoute === 'breakdown') return
  event.preventDefault()
  void navigate(stage)
})
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return
  const stage = navigationStage(event.target)
  if (!stage || event.target !== stage) return
  event.preventDefault()
  void navigate(stage)
})

if (typeof MutationObserver !== 'undefined') {
  observer = new MutationObserver(queueSynchronization)
  const app = document.getElementById('app')
  if (app) observer.observe(app, { childList: true, subtree: true, characterData: true })
}

queueSynchronization()
window.addEventListener('popstate', queueSynchronization)

export {}
