declare global {
  interface Window {
    __aiDramaAssetLightboxInstalled?: boolean
  }
}

const IMAGE_SELECTOR = [
  '.asset-matrix-v4 img',
  '.asset-library-dialog img',
  '.matrix-drawer img',
].join(',')

function installAssetImageLightbox(): void {
  if (typeof window === 'undefined' || window.__aiDramaAssetLightboxInstalled) return
  window.__aiDramaAssetLightboxInstalled = true

  let overlay: HTMLDivElement | null = null
  let preview: HTMLImageElement | null = null
  let scale = 1

  const applyScale = (): void => {
    if (!preview) return
    preview.style.transform = `scale(${scale})`
    const label = overlay?.querySelector<HTMLElement>('[data-lightbox-scale]')
    if (label) label.textContent = `${Math.round(scale * 100)}%`
  }

  const close = (): void => {
    overlay?.remove()
    overlay = null
    preview = null
    scale = 1
    document.body.classList.remove('asset-lightbox-open')
  }

  const zoom = (delta: number): void => {
    scale = Math.max(0.5, Math.min(4, Number((scale + delta).toFixed(2))))
    applyScale()
  }

  const open = (source: HTMLImageElement): void => {
    close()
    const src = source.currentSrc || source.src
    if (!src) return

    overlay = document.createElement('div')
    overlay.className = 'asset-image-lightbox'
    overlay.setAttribute('role', 'dialog')
    overlay.setAttribute('aria-modal', 'true')
    overlay.setAttribute('aria-label', '图片放大预览')

    const stage = document.createElement('div')
    stage.className = 'asset-image-lightbox-stage'

    preview = document.createElement('img')
    preview.src = src
    preview.alt = source.alt || '资产图片预览'
    preview.draggable = false
    stage.appendChild(preview)

    const controls = document.createElement('div')
    controls.className = 'asset-image-lightbox-controls'

    const button = (label: string, title: string, handler: () => void): HTMLButtonElement => {
      const item = document.createElement('button')
      item.type = 'button'
      item.textContent = label
      item.title = title
      item.addEventListener('click', (event) => {
        event.stopPropagation()
        handler()
      })
      return item
    }

    controls.appendChild(button('−', '缩小', () => zoom(-0.25)))
    const scaleLabel = document.createElement('span')
    scaleLabel.dataset.lightboxScale = 'true'
    scaleLabel.textContent = '100%'
    controls.appendChild(scaleLabel)
    controls.appendChild(button('+', '放大', () => zoom(0.25)))
    controls.appendChild(button('1:1', '恢复 100%', () => {
      scale = 1
      applyScale()
    }))
    controls.appendChild(button('原图', '在新窗口打开原图', () => {
      window.open(src, '_blank', 'noopener,noreferrer')
    }))
    controls.appendChild(button('×', '关闭', close))

    overlay.append(stage, controls)
    overlay.addEventListener('click', (event) => {
      if (event.target === overlay || event.target === stage) close()
    })
    overlay.addEventListener('wheel', (event) => {
      event.preventDefault()
      zoom(event.deltaY < 0 ? 0.15 : -0.15)
    }, { passive: false })

    document.body.appendChild(overlay)
    document.body.classList.add('asset-lightbox-open')
    applyScale()
  }

  document.addEventListener('click', (event) => {
    const target = event.target
    if (!(target instanceof HTMLImageElement)) return
    if (!target.matches(IMAGE_SELECTOR)) return
    event.preventDefault()
    event.stopPropagation()
    open(target)
  }, true)

  document.addEventListener('keydown', (event) => {
    if (!overlay) return
    if (event.key === 'Escape') close()
    else if (event.key === '+' || event.key === '=') zoom(0.25)
    else if (event.key === '-') zoom(-0.25)
    else if (event.key === '0') {
      scale = 1
      applyScale()
    }
  })
}

installAssetImageLightbox()

export {}
