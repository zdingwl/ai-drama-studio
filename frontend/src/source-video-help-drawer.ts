const HELP_TRIGGER_SELECTOR = '.source-video-page .help-button'
const DRAWER_BACKDROP_CLASS = 'source-video-help-backdrop'
const BODY_OPEN_CLASS = 'source-video-help-drawer-open'

let activeBackdrop: HTMLDivElement | null = null
let previousFocus: HTMLElement | null = null

function getFocusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => element.offsetParent !== null)
}

function closeHelpDrawer(): void {
  if (!activeBackdrop) return

  document.removeEventListener('keydown', handleDrawerKeydown, true)
  activeBackdrop.remove()
  activeBackdrop = null
  document.body.classList.remove(BODY_OPEN_CLASS)

  const focusTarget = previousFocus
  previousFocus = null
  if (focusTarget?.isConnected) focusTarget.focus()
}

function handleDrawerKeydown(event: KeyboardEvent): void {
  if (!activeBackdrop) return

  if (event.key === 'Escape') {
    event.preventDefault()
    closeHelpDrawer()
    return
  }

  if (event.key !== 'Tab') return
  const drawer = activeBackdrop.querySelector<HTMLElement>('.source-video-help-drawer')
  if (!drawer) return

  const focusable = getFocusableElements(drawer)
  if (!focusable.length) {
    event.preventDefault()
    drawer.focus()
    return
  }

  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  const current = document.activeElement

  if (event.shiftKey && current === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && current === last) {
    event.preventDefault()
    first.focus()
  }
}

function createHelpDrawer(): HTMLDivElement {
  const backdrop = document.createElement('div')
  backdrop.className = DRAWER_BACKDROP_CLASS
  backdrop.innerHTML = `
    <aside
      class="source-video-help-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="source-video-help-title"
      tabindex="-1"
    >
      <header class="source-video-help-head">
        <div>
          <p>原短剧视频</p>
          <h2 id="source-video-help-title">操作指引</h2>
          <span>按下面的顺序完成原剧视频整理和镜头检测。</span>
        </div>
        <button class="source-video-help-close" type="button" aria-label="关闭操作指引">×</button>
      </header>

      <div class="source-video-help-body">
        <section class="source-video-help-step">
          <b>1</b>
          <div>
            <h3>上传原剧视频</h3>
            <p>点击「上传视频」，可以一次选择多集视频，也可以直接拖拽文件到上传区域。支持 mp4 / mov / mkv。</p>
          </div>
        </section>

        <section class="source-video-help-step">
          <b>2</b>
          <div>
            <h3>调整剧集顺序</h3>
            <p>拖动视频左侧的排序手柄调整剧集顺序。调整后系统会自动保存，这里的顺序就是正式剧集顺序。</p>
          </div>
        </section>

        <section class="source-video-help-step">
          <b>3</b>
          <div>
            <h3>执行镜头检测</h3>
            <p>单集可以点击该行「镜头检测」。需要处理全部剧集时点击「批量镜头检测」，系统会按照正式剧集顺序依次处理，不会并行抢占资源。</p>
          </div>
        </section>

        <section class="source-video-help-step">
          <b>4</b>
          <div>
            <h3>查看检测状态</h3>
            <div class="source-video-help-statuses" aria-label="镜头检测状态说明">
              <span><i class="waiting"></i>未检测：还没有开始</span>
              <span><i class="queued"></i>排队中：等待处理</span>
              <span><i class="processing"></i>进行中：正在检测并显示进度</span>
              <span><i class="completed"></i>已完成：该集镜头结果可用</span>
              <span><i class="failed"></i>失败：查看错误后可重新检测</span>
            </div>
          </div>
        </section>

        <section class="source-video-help-step">
          <b>5</b>
          <div>
            <h3>替换或删除视频</h3>
            <p>替换原片后，该集旧的镜头检测、AI 拉片和下游结果会自动失效，需要重新检测。删除已经产生分析数据的视频时，确认后会连同该集对应的业务分析数据一起清理。</p>
          </div>
        </section>

        <section class="source-video-help-step">
          <b>6</b>
          <div>
            <h3>进入下一阶段</h3>
            <p>当前项目所有剧集都完成镜头检测后，左侧「AI 拉片」阶段会解锁。点击阶段入口即可进入，进入页面本身不会自动启动新的重任务。</p>
          </div>
        </section>

        <div class="source-video-help-note">
          <strong>提示</strong>
          <span>后台任务执行期间，上传、替换、删除和排序会暂时锁定，避免旧任务结果回写到已经变化的原片。</span>
        </div>
      </div>

      <footer class="source-video-help-actions">
        <button class="source-video-help-confirm" type="button">知道了</button>
      </footer>
    </aside>
  `
  return backdrop
}

function openHelpDrawer(trigger: HTMLElement): void {
  if (activeBackdrop) return

  previousFocus = trigger
  const backdrop = createHelpDrawer()
  activeBackdrop = backdrop
  document.body.classList.add(BODY_OPEN_CLASS)
  document.body.appendChild(backdrop)

  backdrop.querySelector<HTMLButtonElement>('.source-video-help-close')?.addEventListener('click', closeHelpDrawer)
  backdrop.querySelector<HTMLButtonElement>('.source-video-help-confirm')?.addEventListener('click', closeHelpDrawer)
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) closeHelpDrawer()
  })

  document.addEventListener('keydown', handleDrawerKeydown, true)
  requestAnimationFrame(() => {
    backdrop.classList.add('visible')
    backdrop.querySelector<HTMLButtonElement>('.source-video-help-close')?.focus()
  })
}

function findHelpTrigger(target: EventTarget | null): HTMLElement | null {
  if (!(target instanceof Element)) return null
  return target.closest<HTMLElement>(HELP_TRIGGER_SELECTOR)
}

document.addEventListener('click', (event) => {
  const trigger = findHelpTrigger(event.target)
  if (!trigger) return

  event.preventDefault()
  openHelpDrawer(trigger)
})

document.addEventListener('mouseover', (event) => {
  const trigger = findHelpTrigger(event.target)
  if (!trigger) return
  if (trigger.title !== '查看原短剧视频操作指引') trigger.title = '查看原短剧视频操作指引'
}, { passive: true })

export {}
