/**
 * 不重叠的轮询器：上一轮完成后再等 intervalMs 发下一轮；失败按指数退避（≤ maxBackoffMs）。
 * 永不自行停止——后端重启只会让它暂时失败，恢复后自动续上。
 */
export interface PollerOptions {
  name: string
  intervalMs: number
  maxBackoffMs?: number
  /** 返回 false 表示本轮不算成功（不重置退避），但也不算失败 */
  fn: (sentAt: number) => Promise<void | boolean>
  onError?: (err: unknown, failures: number) => void
  onSuccess?: () => void
}

export interface PollerHandle {
  stop: () => void
  /** 立刻跑一轮（不等计时） */
  kick: () => void
  readonly failures: number
}

export function startPoller(opts: PollerOptions): PollerHandle {
  let stopped = false
  let timer: number | null = null
  let failures = 0
  let running = false
  const maxBackoff = opts.maxBackoffMs ?? 5000

  const schedule = (ms: number) => {
    if (stopped) return
    if (timer !== null) window.clearTimeout(timer)
    timer = window.setTimeout(run, ms)
  }

  const run = async () => {
    if (stopped || running) return
    running = true
    timer = null
    const sentAt = performance.now()
    let delay = opts.intervalMs
    try {
      const ok = await opts.fn(sentAt)
      if (ok !== false) {
        failures = 0
        opts.onSuccess?.()
      }
    } catch (err) {
      failures++
      opts.onError?.(err, failures)
      delay = Math.min(maxBackoff, opts.intervalMs * Math.pow(2, Math.min(6, failures)))
    } finally {
      running = false
      schedule(delay)
    }
  }

  schedule(0)

  return {
    stop: () => { stopped = true; if (timer !== null) window.clearTimeout(timer) },
    kick: () => { if (!running) schedule(0) },
    get failures() { return failures },
  }
}
