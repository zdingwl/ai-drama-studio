export interface ApiErrorPayload {
  error: {
    code: string
    message: string
    details: unknown
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(status: number, payload: ApiErrorPayload) {
    super(payload.error.message)
    this.name = 'ApiError'
    this.status = status
    this.code = payload.error.code
    this.details = payload.error.details
  }
}

export class ApiConnectionError extends Error {
  constructor() {
    super('无法连接后端服务。请确认 FastAPI 已启动，并检查前端 API 代理配置。')
    this.name = 'ApiConnectionError'
  }
}

export class ApiProtocolError extends Error {
  readonly status: number

  constructor(status: number) {
    super(
      status >= 500
        ? `后端接口暂时不可用（HTTP ${status}）。请确认 FastAPI 已启动，并检查前端 API 代理配置。`
        : '后端接口返回了非 JSON 内容。请检查前端 API 地址或代理配置。',
    )
    this.name = 'ApiProtocolError'
    this.status = status
  }
}

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v3'

async function readJson<T>(response: Response): Promise<T> {
  try {
    return (await response.json()) as T
  } catch {
    throw new ApiProtocolError(response.status)
  }
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
    })
  } catch {
    throw new ApiConnectionError()
  }

  if (!response.ok) {
    const payload = await readJson<ApiErrorPayload>(response)
    if (!payload?.error?.code || !payload.error.message) {
      throw new ApiProtocolError(response.status)
    }
    throw new ApiError(response.status, payload)
  }

  return readJson<T>(response)
}
