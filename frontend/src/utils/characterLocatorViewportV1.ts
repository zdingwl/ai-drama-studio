const LOCATOR_CANVAS_SELECTOR = '.source-confirm-dialog .identity-review .locator-canvas'

type LocatorCanvas = HTMLElement & {
  dataset: DOMStringMap & { locatorFitted?: string }
}

function px(value: number): string {
  return `${Math.max(1, Math.floor(value))}px`
}

function fitLocatorCanvas(canvas: LocatorCanvas): void {
  const image = canvas.querySelector<HTMLImageElement>(':scope > img')
  if (!image || !image.complete || image.naturalWidth <= 0 || image.naturalHeight <= 0) return

  const modal = canvas.closest<HTMLElement>('.locator-modal')
  if (!modal) return

  const header = modal.querySelector<HTMLElement>(':scope > header')
  const shots = modal.querySelector<HTMLElement>(':scope > .locator-shots')
  const footer = modal.querySelector<HTMLElement>(':scope > footer')

  const modalWidth = Math.max(280, modal.clientWidth || window.innerWidth - 48)
  const horizontalPadding = 32
  const maxWidth = Math.max(240, Math.min(760, modalWidth - horizontalPadding))

  const chromeHeight =
    (header?.getBoundingClientRect().height || 68) +
    (shots?.getBoundingClientRect().height || 0) +
    (footer?.getBoundingClientRect().height || 56) +
    40
  const maxHeight = Math.max(240, window.innerHeight - chromeHeight - 32)

  const scale = Math.min(
    maxWidth / image.naturalWidth,
    maxHeight / image.naturalHeight,
    1,
  )
  const renderWidth = image.naturalWidth * scale
  const renderHeight = image.naturalHeight * scale

  // 这里必须用 important 覆盖历史设计稿 CSS；canvas 边界即图片边界，
  // CharacterAssetsWorkbenchV1 才能继续按 getBoundingClientRect() 计算准确的 0~1 框选坐标。
  canvas.style.setProperty('width', px(renderWidth), 'important')
  canvas.style.setProperty('height', px(renderHeight), 'important')
  canvas.style.setProperty('min-width', '0', 'important')
  canvas.style.setProperty('min-height', '0', 'important')
  canvas.style.setProperty('max-width', 'none', 'important')
  canvas.style.setProperty('max-height', 'none', 'important')
  canvas.style.setProperty('display', 'block', 'important')
  canvas.style.setProperty('margin-left', 'auto', 'important')
  canvas.style.setProperty('margin-right', 'auto', 'important')

  image.style.setProperty('width', '100%', 'important')
  image.style.setProperty('height', '100%', 'important')
  image.style.setProperty('max-width', 'none', 'important')
  image.style.setProperty('max-height', 'none', 'important')
  image.style.setProperty('object-fit', 'fill', 'important')
  image.style.setProperty('transform', 'none', 'important')

  canvas.dataset.locatorFitted = `${image.naturalWidth}x${image.naturalHeight}@${Math.round(renderWidth)}x${Math.round(renderHeight)}`
}

function fitAllLocatorCanvases(): void {
  document.querySelectorAll<LocatorCanvas>(LOCATOR_CANVAS_SELECTOR).forEach(fitLocatorCanvas)
}

/**
 * 多人镜头框选画布尺寸同步器。
 *
 * locator 弹窗是按需挂载的，不能只在 App mounted 时计算；这里通过捕获图片 load
 * 和 MutationObserver 覆盖首次打开、切换 Shot、缓存图片立即完成等情况。
 */
export function installCharacterLocatorViewportV1(): () => void {
  let resizeFrame = 0

  const scheduleFit = () => {
    window.cancelAnimationFrame(resizeFrame)
    resizeFrame = window.requestAnimationFrame(fitAllLocatorCanvases)
  }

  const handleImageLoad = (event: Event) => {
    const target = event.target
    if (!(target instanceof HTMLImageElement)) return
    const canvas = target.closest<LocatorCanvas>(LOCATOR_CANVAS_SELECTOR)
    if (canvas) fitLocatorCanvas(canvas)
  }

  const observer = new MutationObserver((records) => {
    for (const record of records) {
      for (const node of record.addedNodes) {
        if (!(node instanceof HTMLElement)) continue
        if (node.matches(LOCATOR_CANVAS_SELECTOR) || node.querySelector(LOCATOR_CANVAS_SELECTOR)) {
          scheduleFit()
          return
        }
      }
    }
  })

  document.addEventListener('load', handleImageLoad, true)
  window.addEventListener('resize', scheduleFit)
  observer.observe(document.body, { childList: true, subtree: true })
  scheduleFit()

  return () => {
    document.removeEventListener('load', handleImageLoad, true)
    window.removeEventListener('resize', scheduleFit)
    observer.disconnect()
    window.cancelAnimationFrame(resizeFrame)
  }
}
