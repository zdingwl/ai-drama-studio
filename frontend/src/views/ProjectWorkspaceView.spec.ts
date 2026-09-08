import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { TaskRead } from '@/features/projects/types'

import ProjectWorkspaceView from './ProjectWorkspaceView.vue'

const project = {
  id: 'project-1',
  name: '美国版短剧',
  project_type: 'REPLICA',
  source_language: 'zh-CN',
  target_language: 'en-US',
  target_region: 'US',
  scene_strategy: 'MIXED',
  audio_policy: 'REGENERATE_AUDIO',
  status: 'ACTIVE',
  workflow_revision: 1,
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
}

const plan = {
  project_id: 'project-1',
  project_type: 'REPLICA',
  skill_id: 'project.replica',
  skill_title: '复刻短剧',
  workflow_revision: 1,
  steps: [
    {
      id: 'source_input',
      phase: '输入',
      title: '导入原片',
      description: '登记原始短剧 Episode。',
      status: 'READY',
      capabilities: [],
      requires: [],
      produces: ['SOURCE_VIDEO'],
      missing_artifacts: [],
    },
    {
      id: 'shot_boundary',
      phase: '原片理解',
      title: '镜头边界',
      description: '后续阶段能力，P4 不执行。',
      status: 'WAITING_CAPABILITY',
      capabilities: ['SHOT_BOUNDARY'],
      requires: ['SOURCE_VIDEO'],
      produces: ['SHOT_ANCHORS'],
      missing_artifacts: [],
    },
  ],
}

const tasks: TaskRead[] = [
  {
    id: 'task-failed',
    project_id: 'project-1',
    task_name: '原片准备任务',
    progress_percent: 35,
    status: 'failed',
    last_error: '媒体准备失败',
    attempt: 1,
    max_attempts: 3,
    can_retry: true,
    can_cancel: false,
    can_resume: false,
    created_at: '2026-09-08T00:00:00Z',
    started_at: '2026-09-08T00:01:00Z',
    finished_at: '2026-09-08T00:02:00Z',
  },
  {
    id: 'task-running',
    project_id: 'project-1',
    task_name: '执行中任务',
    progress_percent: 60,
    status: 'running',
    last_error: null,
    attempt: 1,
    max_attempts: 3,
    can_retry: false,
    can_cancel: true,
    can_resume: false,
    created_at: '2026-09-08T00:00:00Z',
    started_at: '2026-09-08T00:01:00Z',
    finished_at: null,
  },
  {
    id: 'task-interrupted',
    project_id: 'project-1',
    task_name: '可继续任务',
    progress_percent: 72,
    status: 'interrupted',
    last_error: '任务执行器心跳中断，可从最近检查点继续',
    attempt: 1,
    max_attempts: 3,
    can_retry: false,
    can_cancel: true,
    can_resume: true,
    created_at: '2026-09-08T00:00:00Z',
    started_at: '2026-09-08T00:01:00Z',
    finished_at: null,
  },
]

function response(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
}

async function mountWorkspace() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: ProjectWorkspaceView }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(ProjectWorkspaceView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProjectWorkspaceView P4 task status', () => {
  it('shows user-facing task status, manual acceptance controls and keeps initial GET requests read-only', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/api/v3/projects/project-1') && method === 'GET') return response(project)
      if (url.endsWith('/api/v3/projects/project-1/plan') && method === 'GET') return response(plan)
      if (url.endsWith('/api/v3/projects/project-1/tasks') && method === 'GET') return response(tasks)
      throw new Error(`unexpected request: ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('开发验收工具')
    expect(wrapper.text()).toContain('测试正常完成')
    expect(wrapper.text()).toContain('测试失败 → 重试')
    expect(wrapper.text()).toContain('测试中断 → 继续')
    expect(wrapper.text()).toContain('测试防重复提交')
    expect(wrapper.text()).toContain('不调用真实模型')
    expect(wrapper.text()).toContain('任务状态')
    expect(wrapper.text()).toContain('原片准备任务')
    expect(wrapper.text()).toContain('35%')
    expect(wrapper.text()).toContain('失败')
    expect(wrapper.text()).toContain('媒体准备失败')
    expect(wrapper.text()).toContain('重试')
    expect(wrapper.text()).toContain('取消')
    expect(wrapper.text()).toContain('继续')
    expect(wrapper.text()).toContain('等待能力接入')

    expect(wrapper.text()).not.toContain('ProviderJob')
    expect(wrapper.text()).not.toContain('payload_fingerprint')
    expect(wrapper.text()).not.toContain('mock-provider')
    expect(wrapper.text()).not.toContain('checkpoint_json')
    expect(wrapper.text()).not.toContain('Idempotency-Key')

    const calls = fetchMock.mock.calls.map(([input, init]) => ({
      url: String(input),
      method: (init as RequestInit | undefined)?.method ?? 'GET',
    }))
    expect(calls).toHaveLength(3)
    expect(calls.every((call) => call.method === 'GET')).toBe(true)
    wrapper.unmount()
  })

  it('starts P4 acceptance only through an explicit POST command with idempotency protection', async () => {
    const acceptanceTask: TaskRead = {
      id: 'task-acceptance',
      project_id: 'project-1',
      task_name: 'P4 验收：正常执行与安全调用',
      progress_percent: 0,
      status: 'queued',
      last_error: null,
      attempt: 0,
      max_attempts: 3,
      can_retry: false,
      can_cancel: true,
      can_resume: false,
      created_at: '2026-09-08T00:00:00Z',
      started_at: null,
      finished_at: null,
    }
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/api/v3/projects/project-1') && method === 'GET') return response(project)
      if (url.endsWith('/api/v3/projects/project-1/plan') && method === 'GET') return response(plan)
      if (url.endsWith('/api/v3/projects/project-1/tasks') && method === 'GET') return response([])
      if (url.endsWith('/api/v3/projects/project-1/commands/p4-acceptance/success') && method === 'POST') {
        return response(acceptanceTask, 202)
      }
      throw new Error(`unexpected request: ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountWorkspace()
    const button = wrapper.findAll('.acceptance-actions button').find((item) => item.text() === '测试正常完成')
    await button?.trigger('click')
    await flushPromises()

    const acceptanceCall = fetchMock.mock.calls.find(([input, init]) => (
      String(input).endsWith('/api/v3/projects/project-1/commands/p4-acceptance/success')
      && (init as RequestInit | undefined)?.method === 'POST'
    ))
    expect(acceptanceCall).toBeTruthy()
    const headers = new Headers((acceptanceCall?.[1] as RequestInit | undefined)?.headers)
    expect(headers.get('Idempotency-Key')).toMatch(/^p4-success-/)
    expect(wrapper.text()).toContain('P4 验收：正常执行与安全调用')
    wrapper.unmount()
  })

  it('verifies duplicate submission with a dedicated task and exactly one new task', async () => {
    const existingTask: TaskRead = {
      id: 'task-existing-success',
      project_id: 'project-1',
      task_name: 'P4 验收：正常执行与安全调用',
      progress_percent: 100,
      status: 'succeeded',
      last_error: null,
      attempt: 1,
      max_attempts: 3,
      can_retry: false,
      can_cancel: false,
      can_resume: false,
      created_at: '2026-09-08T00:00:00Z',
      started_at: '2026-09-08T00:00:01Z',
      finished_at: '2026-09-08T00:00:05Z',
    }
    const dedupeTask: TaskRead = {
      id: 'task-dedupe',
      project_id: 'project-1',
      task_name: 'P4 验收：防重复提交',
      progress_percent: 100,
      status: 'succeeded',
      last_error: null,
      attempt: 1,
      max_attempts: 3,
      can_retry: false,
      can_cancel: false,
      can_resume: false,
      created_at: '2026-09-08T00:01:00Z',
      started_at: '2026-09-08T00:01:01Z',
      finished_at: '2026-09-08T00:01:05Z',
    }
    let taskListReads = 0
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/api/v3/projects/project-1') && method === 'GET') return response(project)
      if (url.endsWith('/api/v3/projects/project-1/plan') && method === 'GET') return response(plan)
      if (url.endsWith('/api/v3/projects/project-1/tasks') && method === 'GET') {
        taskListReads += 1
        return response(taskListReads <= 2 ? [existingTask] : [dedupeTask, existingTask])
      }
      if (url.endsWith('/api/v3/projects/project-1/commands/p4-acceptance/dedupe') && method === 'POST') {
        return response(dedupeTask, 202)
      }
      throw new Error(`unexpected request: ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountWorkspace()
    const button = wrapper.findAll('.acceptance-actions button').find((item) => item.text() === '测试防重复提交')
    await button?.trigger('click')
    await flushPromises()

    const dedupeCalls = fetchMock.mock.calls.filter(([input, init]) => (
      String(input).endsWith('/api/v3/projects/project-1/commands/p4-acceptance/dedupe')
      && (init as RequestInit | undefined)?.method === 'POST'
    ))
    expect(dedupeCalls).toHaveLength(2)
    const firstHeaders = new Headers((dedupeCalls[0]?.[1] as RequestInit | undefined)?.headers)
    const secondHeaders = new Headers((dedupeCalls[1]?.[1] as RequestInit | undefined)?.headers)
    expect(firstHeaders.get('Idempotency-Key')).toMatch(/^p4-dedupe-/)
    expect(secondHeaders.get('Idempotency-Key')).toBe(firstHeaders.get('Idempotency-Key'))
    expect(wrapper.text()).toContain('重复提交保护：通过。本次两次相同提交只新增了 1 个“防重复提交”任务。')
    expect(wrapper.findAll('.task-card').filter((card) => card.text().includes('P4 验收：防重复提交'))).toHaveLength(1)
    expect(wrapper.findAll('.task-card').filter((card) => card.text().includes('P4 验收：正常执行与安全调用'))).toHaveLength(1)
    wrapper.unmount()
  })

  it('uses explicit POST commands for retry, cancel and resume', async () => {
    const updated = new Map<string, TaskRead>([
      ['task-failed', { ...tasks[0], status: 'queued', last_error: null, can_retry: false, can_cancel: true }],
      ['task-running', { ...tasks[1], status: 'running', can_cancel: false }],
      ['task-interrupted', { ...tasks[2], status: 'queued', last_error: null, can_resume: false, can_cancel: true }],
    ])

    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/api/v3/projects/project-1') && method === 'GET') return response(project)
      if (url.endsWith('/api/v3/projects/project-1/plan') && method === 'GET') return response(plan)
      if (url.endsWith('/api/v3/projects/project-1/tasks') && method === 'GET') return response(tasks)
      if (url.endsWith('/api/v3/projects/project-1/tasks/task-failed/commands/retry') && method === 'POST') {
        return response(updated.get('task-failed'))
      }
      if (url.endsWith('/api/v3/projects/project-1/tasks/task-running/commands/cancel') && method === 'POST') {
        return response(updated.get('task-running'))
      }
      if (url.endsWith('/api/v3/projects/project-1/tasks/task-interrupted/commands/resume') && method === 'POST') {
        return response(updated.get('task-interrupted'))
      }
      throw new Error(`unexpected request: ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountWorkspace()
    const findTaskCard = (taskName: string) => wrapper.findAll('.task-card').find((card) => card.text().includes(taskName))

    await findTaskCard('原片准备任务')?.findAll('button').find((button) => button.text() === '重试')?.trigger('click')
    await flushPromises()
    await findTaskCard('执行中任务')?.findAll('button').find((button) => button.text() === '取消')?.trigger('click')
    await flushPromises()
    await findTaskCard('可继续任务')?.findAll('button').find((button) => button.text() === '继续')?.trigger('click')
    await flushPromises()

    const postCalls = fetchMock.mock.calls
      .map(([input, init]) => ({ url: String(input), method: (init as RequestInit | undefined)?.method ?? 'GET' }))
      .filter((call) => call.method === 'POST')

    expect(postCalls.map((call) => call.url)).toEqual([
      '/api/v3/projects/project-1/tasks/task-failed/commands/retry',
      '/api/v3/projects/project-1/tasks/task-running/commands/cancel',
      '/api/v3/projects/project-1/tasks/task-interrupted/commands/resume',
    ])
    wrapper.unmount()
  })
})
