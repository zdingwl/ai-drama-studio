import type { ApiErrorPayload } from '../types/project'

export const API_BASE_URL = 'http://127.0.0.1:8000'

/**
 * F01 统一 HTTP 请求入口。
 *
 * 业务作用：统一拼接本地 FastAPI 地址、解析 JSON，并把后端标准 error envelope
 * 转换成前端 Error。它不决定页面跳转、不修改 Pinia 状态，也不包含创建项目业务规则。
 */
export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  })

  const payload = (await response.json()) as T | ApiErrorPayload
  if (!response.ok) {
    const apiError = payload as ApiErrorPayload
    const error = new Error(apiError.error?.message || '请求失败')
    ;(error as Error & { code?: string }).code = apiError.error?.code
    throw error
  }
  return payload as T
}
