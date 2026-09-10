import { nextTick, watchEffect } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { getProject, getProjectPlan, listProjectTasks } from './api'

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

describe('project task reads', () => {
  it('shares one reactive no-store task snapshot so sibling panels stay in sync', async () => {
    const runningTask = {
      id: 'task-live',
      project_id: 'project-task-sync',
      task_name: '整集多模态原片理解 / 源作概览分析',
      progress_percent: 5,
      status: 'running',
      last_error: null,
      attempt: 1,
      max_attempts: 3,
      can_retry: false,
      can_cancel: true,
      can_resume: false,
      created_at: '2026-09-10T00:00:00Z',
      started_at: '2026-09-10T00:00:01Z',
      finished_at: null,
    }
    const finishedTask = {
      ...runningTask,
      progress_percent: 100,
      status: 'succeeded',
      can_cancel: false,
      finished_at: '2026-09-10T00:00:30Z',
    }
    let reads = 0
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      if (!url.endsWith('/api/v3/projects/project-task-sync/tasks')) {
        throw new Error(`unexpected request: ${url}`)
      }
      reads += 1
      expect(init?.cache).toBe('no-store')
      return response(reads === 1 ? [runningTask] : [finishedTask])
    })
    vi.stubGlobal('fetch', fetchMock)

    const workspaceSnapshot = await listProjectTasks('project-task-sync')
    let observedProgress = -1
    const stop = watchEffect(() => {
      observedProgress = workspaceSnapshot[0]?.progress_percent ?? -1
    })

    expect(observedProgress).toBe(5)

    const siblingPanelSnapshot = await listProjectTasks('project-task-sync')
    await nextTick()

    expect(siblingPanelSnapshot).toBe(workspaceSnapshot)
    expect(workspaceSnapshot[0]?.status).toBe('succeeded')
    expect(workspaceSnapshot[0]?.progress_percent).toBe(100)
    expect(observedProgress).toBe(100)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    stop()
  })
})
