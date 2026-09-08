import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiConnectionError, apiRequest } from './api'

function jsonResponse(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('apiRequest', () => {
  it('keeps structured backend errors as ApiError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponse(
          { error: { code: 'PROJECT_NOT_FOUND', message: '项目不存在', details: null } },
          404,
        ),
      ),
    )

    await expect(apiRequest('/projects/missing')).rejects.toMatchObject({
      name: 'ApiError',
      status: 404,
      code: 'PROJECT_NOT_FOUND',
      message: '项目不存在',
    })
  })

  it('turns html or other non-json responses into a readable protocol error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        ({
          ok: true,
          status: 200,
          json: async () => {
            throw new SyntaxError("Unexpected token '<'")
          },
        }) as unknown as Response,
      ),
    )

    await expect(apiRequest('/projects')).rejects.toMatchObject({
      name: 'ApiProtocolError',
      status: 200,
      message: '后端接口返回了非 JSON 内容。请检查前端 API 地址或代理配置。',
    })
  })

  it('turns fetch connection failures into a readable backend connection error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => {
        throw new TypeError('fetch failed')
      }),
    )

    await expect(apiRequest('/projects')).rejects.toBeInstanceOf(ApiConnectionError)
    await expect(apiRequest('/projects')).rejects.toThrow(
      '无法连接后端服务。请确认 FastAPI 已启动，并检查前端 API 代理配置。',
    )
  })
})
