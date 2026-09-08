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

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v3'

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (!(init?.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  })

  if (!response.ok) {
    const payload = (await response.json()) as ApiErrorPayload
    throw new ApiError(response.status, payload)
  }

  return (await response.json()) as T
}
