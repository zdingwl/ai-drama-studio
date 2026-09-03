const PAGE_SELECTOR = '.breakdown-page-v1'
const STAGE_SELECTOR = `${PAGE_SELECTOR} .stage-list .stage-item`

interface StageShellDefinition {
  label: string
  description: string
}

const STAGE_SHELL: StageShellDefinition[] = [
  { label: '原短剧视频', description: '上传、排序与镜头检测' },
  { label: 'AI 拉片', description: '剧情、对白与镜头理解' },
  { label: '原片确认', description: '人物 / 场景 / 道具确认' },
  { label: '视频重做', description: '本土化、配音与视频生成' },
  { label: '成片输出', description: '后期检查与最终导出' },
]

let observer: MutationObserver | null = null
let syncQueued = false

function syncStage(stage: HTMLElement, definition: StageShellDefinition): void {
  const title = stage.querySelector<HTMLElement>('.stage-copy > strong')
  if (title && title.textContent?.trim() !== definition.label) title.textContent = definition.label

  const details = Array.from(stage.querySelectorAll<HTMLElement>('.stage-copy > small'))
  const description = details[0]
  if (description && description.textContent?.trim() !== definition.description) {
    description.textContent = definition.description
  }

  details.slice(1).forEach((detail) => {
    detail.hidden = true
    detail.setAttribute('aria-hidden', 'true')
  })
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
    syncStage(stage, definition)
  })

  page.dataset.shellSynchronized = 'true'
}

function queueSynchronization(): void {
  if (syncQueued) return
  syncQueued = true
  queueMicrotask(synchronizeBreakdownShell)
}

if (typeof MutationObserver !== 'undefined') {
  observer = new MutationObserver(queueSynchronization)
  const app = document.getElementById('app')
  if (app) {
    observer.observe(app, {
      childList: true,
      subtree: true,
      characterData: true,
    })
  }
}

queueSynchronization()
window.addEventListener('popstate', queueSynchronization)

export {}
