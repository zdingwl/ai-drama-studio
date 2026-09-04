import { afterEach, describe, expect, it, vi } from 'vitest'
import { startQuietPolling } from './quietPolling'

afterEach(() => { vi.useRealTimers() })

describe('quiet progress polling', () => {
  it('pauses network requests while hidden and stops after disposal', async () => {
    vi.useFakeTimers()
    let visible = false
    const tick = vi.fn(async () => {})
    const stop = startQuietPolling(tick, () => visible)
    await vi.advanceTimersByTimeAsync(15000)
    expect(tick).not.toHaveBeenCalled()
    visible = true
    await vi.advanceTimersByTimeAsync(5000)
    expect(tick).toHaveBeenCalledTimes(1)
    stop()
    await vi.advanceTimersByTimeAsync(60000)
    expect(tick).toHaveBeenCalledTimes(1)
  })

  it('backs off on errors and resets delay after recovery', async () => {
    vi.useFakeTimers()
    const tick = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
    const stop = startQuietPolling(tick, () => true)
    await vi.advanceTimersByTimeAsync(5000)
    expect(tick).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(tick).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(5000)
    expect(tick).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(5000)
    expect(tick).toHaveBeenCalledTimes(3)
    stop()
  })

  it('never overlaps requests and aborts the pending request on disposal', async () => {
    vi.useFakeTimers()
    let signal: AbortSignal | undefined
    let finish: () => void = () => {}
    const tick = vi.fn((input: AbortSignal) => {
      signal = input
      return new Promise<void>((resolve) => { finish = resolve })
    })
    const stop = startQuietPolling(tick, () => true)
    await vi.advanceTimersByTimeAsync(60000)
    expect(tick).toHaveBeenCalledTimes(1)
    stop()
    expect(signal?.aborted).toBe(true)
    finish()
    await vi.advanceTimersByTimeAsync(60000)
    expect(tick).toHaveBeenCalledTimes(1)
  })
})
