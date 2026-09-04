/** 串行轮询：隐藏时不请求，失败退避，停止时取消在途请求。 */
export function startQuietPolling(
  tick: (signal: AbortSignal) => Promise<void>,
  visible: () => boolean,
  delay = 5000,
) {
  let stopped = false
  let failures = 0
  let controller: AbortController | null = null
  let timer: ReturnType<typeof setTimeout>
  async function run() {
    if (stopped) return
    if (visible()) {
      controller = new AbortController()
      try { await tick(controller.signal); failures = 0 }
      catch { failures = Math.min(failures + 1, 4) }
      finally { controller = null }
    }
    if (!stopped) timer = setTimeout(run, Math.min(delay * 2 ** failures, 60000))
  }
  timer = setTimeout(run, delay)
  return () => { stopped = true; clearTimeout(timer); controller?.abort() }
}
