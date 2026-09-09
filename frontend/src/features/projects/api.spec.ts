import { afterEach, describe, expect, it, vi } from 'vitest'

import { getProject, getProjectPlan } from './api'

function response(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('project plan reads', () => {
  it('reuses the in-flight project read and skips /plan when current_plan_id is null', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/api/v3/projects/project-1')) {
        return response({ id: 'project-1', current_plan_id: null })
      }
      throw new Error(`unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const [project, plan] = await Promise.all([
      getProject('project-1'),
      getProjectPlan('project-1'),
    ])

    expect(project.id).toBe('project-1')
    expect(plan).toBeNull()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls.some(([input]) => String(input).endsWith('/plan'))).toBe(false)
  })

  it('still reads the canonical /plan endpoint when a current plan pointer exists', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request) => {
      const url = String(input)
      if (url.endsWith('/api/v3/projects/project-2')) {
        return response({ id: 'project-2', current_plan_id: 'plan-2' })
      }
      if (url.endsWith('/api/v3/projects/project-2/plan')) {
        return response({
          project_id: 'project-2',
          project_type: 'REPLICA',
          skill_id: 'project.replica',
          skill_title: '复刻短剧',
          workflow_revision: 1,
          steps: [],
        })
      }
      throw new Error(`unexpected request: ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const [project, plan] = await Promise.all([
      getProject('project-2'),
      getProjectPlan('project-2'),
    ])

    expect(project.id).toBe('project-2')
    expect(plan?.project_id).toBe('project-2')
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith('/plan'))).toHaveLength(1)
  })
})
