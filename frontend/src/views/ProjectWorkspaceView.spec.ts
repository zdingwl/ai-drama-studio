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
      status: 'COMPLETED',
      capabilities: ['SOURCE_VIDEO_INGEST'],
      requires: [],
      produces: ['SOURCE_VIDEO'],
      missing_artifacts: [],
    },
    {
      id: 'shot_boundary',
      phase: '理解',
      title: '镜头技术锚点',
      description: '从完整 Episode 建立镜头时间锚点。',
      status: 'READY',
      capabilities: ['MEDIA_PREFLIGHT', 'SHOT_BOUNDARY'],
      requires: ['SOURCE_VIDEO'],
      produces: ['SHOT_ANCHORS'],
      missing_artifacts: [],
    },
    {
      id: 'source_dialogue',
      phase: '理解',
      title: '原片对白与文字证据',
      description: '直接读取完整 Episode 的连续时间轴。',
      status: 'WAITING_CAPABILITY',
      capabilities: ['SOURCE_DIALOGUE_EVIDENCE'],
      requires: ['SOURCE_VIDEO'],
      produces: ['SOURCE_DIALOGUE'],
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

const uploadedEpisode = {
  id: 'episode-1',
  project_id: 'project-1',
  source_asset: {
    id: 'asset-1',
    original_filename: 'ep01.mp4',
  },
  episode_order: 1,
  duration_us: 12_000_000,
  width: 1080,
  height: 1920,
  codec_name: 'h264',
  avg_frame_rate: '30/1',
  has_audio: true,
  created_at: '2026-09-08T00:00:00Z',
}

const notBuiltShotBoundary = {
  episode_id: 'episode-1',
  episode_order: 1,
  source_filename: 'ep01.mp4',
  status: 'NOT_BUILT',
  revision: null,
  artifact_revision: null,
  shot_count: 0,
  shots: [],
}

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

function baseGetResponse(url: string, method: string, taskRows: TaskRead[] = tasks): Response | null {
  if (url.endsWith('/api/v3/projects/project-1') && method === 'GET') return response(project)
  if (url.endsWith('/api/v3/projects/project-1/plan') && method === 'GET') return response(plan)
  if (url.endsWith('/api/v3/projects/project-1/tasks') && method === 'GET') return response(taskRows)
  if (url.endsWith('/api/v3/projects/project-1/sources/episodes') && method === 'GET') return response([])
  return null
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProjectWorkspaceView source-understanding workflow', () => {
  it('auto-reads episodes with GET, shows upload when empty, and never auto-starts processing', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      const result = baseGetResponse(url, method)
      if (result) return result
      throw new Error(`unexpected request: ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('原片理解')
    expect(wrapper.text()).toContain('上传原片')
    expect(wrapper.text()).toContain('还没有原片')
    expect(wrapper.text()).toContain('上传完成后剧集列表会自动出现')
    expect(wrapper.text()).not.toContain('读取已上传剧集')
    expect(wrapper.text()).not.toContain('视频技术预处理')

    expect(wrapper.text()).toContain('开发验收工具')
    expect(wrapper.text()).toContain('任务状态')
    expect(wrapper.text()).toContain('原片准备任务')
    expect(wrapper.text()).toContain('能力待接入')
    expect(wrapper.text()).toContain('产品执行计划')

    expect(wrapper.text()).not.toContain('ProviderJob')
    expect(wrapper.text()).not.toContain('payload_fingerprint')
    expect(wrapper.text()).not.toContain('checkpoint_json')
    expect(wrapper.text()).not.toContain('Idempotency-Key')

    const calls = fetchMock.mock.calls.map(([input, init]) => ({
      url: String(input),
      method: (init as RequestInit | undefined)?.method ?? 'GET',
    }))
    expect(calls).toHaveLength(4)
    expect(calls.every((call) => call.method === 'GET')).toBe(true)
    expect(calls.some((call) => call.url.endsWith('/sources/episodes'))).toBe(true)
    wrapper.unmount()
  })

  it('uploads real episode input from the source-understanding workspace without auto-starting shot anchors', async () => {
    let episodeReads = 0
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/api/v3/projects/project-1') && method === 'GET') return response(project)
      if (url.endsWith('/api/v3/projects/project-1/plan') && method === 'GET') return response(plan)
      if (url.endsWith('/api/v3/projects/project-1/tasks') && method === 'GET') return response([])
      if (url.endsWith('/api/v3/projects/project-1/sources/episodes') && method === 'GET') {
        episodeReads += 1
        return response(episodeReads === 1 ? [] : [uploadedEpisode])
      }
      if (url.endsWith('/api/v3/projects/project-1/sources/videos') && method === 'POST') {
        return response([uploadedEpisode], 201)
      }
      if (url.endsWith('/api/v3/projects/project-1/episodes/episode-1/shot-boundary') && method === 'GET') {
        return response(notBuiltShotBoundary)
      }
      throw new Error(`unexpected request: ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountWorkspace()
    const input = wrapper.find('input[type="file"]')
    const file = new File(['video-bytes'], 'ep01.mp4', { type: 'video/mp4' })
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    await flushPromises()

    const uploadCall = fetchMock.mock.calls.find(([inputValue, init]) => (
      String(inputValue).endsWith('/api/v3/projects/project-1/sources/videos')
      && (init as RequestInit | undefined)?.method === 'POST'
    ))
    expect(uploadCall).toBeTruthy()
    expect((uploadCall?.[1] as RequestInit | undefined)?.body).toBeInstanceOf(FormData)
    expect(wrapper.text()).toContain('第 1 集 · ep01.mp4')
    expect(wrapper.text()).toContain('完整 Episode 始终是原片事实源')
    expect(wrapper.text()).toContain('生成技术锚点')

    const shotBoundaryPosts = fetchMock.mock.calls.filter(([inputValue, init]) => (
      String(inputValue).includes('/commands/shot-boundary')
      && (init as RequestInit | undefined)?.method === 'POST'
    ))
    expect(shotBoundaryPosts).toHaveLength(0)
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
      const result = baseGetResponse(url, method, [])
      if (result) return result
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
      if (url.endsWith('/api/v3/projects/project-1/sources/episodes') && method === 'GET') return response([])
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
      const result = baseGetResponse(url, method)
      if (result) return result
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
