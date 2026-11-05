// 统一的 HTTP 客户端：API_BASE 来自 VITE_API_BASE（默认相对路径 /api，由 Vite 代理转发）。

export const API_BASE: string = (import.meta.env.VITE_API_BASE ?? '/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly method: string, public readonly path: string) {
    super(`${method} ${path} failed: ${status}`)
    this.name = 'ApiError'
  }
}

const DEFAULT_TIMEOUT_MS = 8000

async function request<T>(method: string, path: string, body?: unknown, timeoutMs = DEFAULT_TIMEOUT_MS): Promise<T> {
  const ctrl = new AbortController()
  const timer = window.setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      method,
      headers: body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: body !== undefined ? JSON.stringify(body) : undefined,
      signal: ctrl.signal,
      cache: 'no-store',
    })
    if (!res.ok) throw new ApiError(res.status, method, path)
    if (res.status === 204) return undefined as T
    return (await res.json()) as T
  } finally {
    window.clearTimeout(timer)
  }
}

export const apiGet  = <T>(path: string, timeoutMs?: number) => request<T>('GET', path, undefined, timeoutMs)
export const apiPost = <T>(path: string, body: unknown = {}, timeoutMs?: number) => request<T>('POST', path, body, timeoutMs)
export const apiDelete = <T>(path: string, timeoutMs?: number) => request<T>('DELETE', path, undefined, timeoutMs)

/** 404 → null，其余错误照抛 */
export async function apiGetOrNull<T>(path: string, timeoutMs?: number): Promise<T | null> {
  try {
    return await apiGet<T>(path, timeoutMs)
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) return null
    throw e
  }
}
