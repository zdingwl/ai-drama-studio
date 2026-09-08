import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ProjectWorkspaceView from './ProjectWorkspaceView.vue'

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
  await router.push('/projects/project-p5')
  await router.isReady()
  const wrapper = mount(ProjectWorkspaceView, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

const project = {
  id: 'project-p5',
  name: '真实短剧 P5',
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
  project_id: 'project-p5',
  project_type: 'REPLICA',
  skill_id: 'project.replica',
  skill_title: '复刻短剧',
  workflow_revision: 1,
  steps: [],
}

const episode = {
  id: 'episode-1',
  project_id: 'project-p5',
  source_asset: { id: 'asset-1', original_filename: 'episode-01.mp4' },
  episode_order: 1,
  duration_us: 3_000_000,
  width: 1080,
  height: 1920,
  codec_name: 'h264',
  avg_frame_rate: '30/1',
  has_audio: true,
  created_at: '2026-09-08T00:00:00Z',
}

const boundary = {
  episode_id: 'episode-1',
  episode_order: 1,
  source_filename: 'episode-01.mp4',
  status: 'NOT_BUILT',
  revision: null,
  artifact_revision: null,
  shot_count: 0,
  shots: [],
}

const queuedTask = {
  id: 'task-p5',
  project_id: 'project-p5',
  task_name: '第 1 集：镜头技术预处理',
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

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ProjectWorkspaceView P5 shot boundary', () => {
  it('loads uploaded episodes through read-only GETs and starts processing only after explicit POST', async () => {
    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/api/v3/projects/project-p5') && method === 'GET') return response(project)
      if (url.endsWith('/api/v3/projects/project-p5/plan') && method === 'GET') return response(plan)
      if (url.endsWith('/api/v3/projects/project-p5/tasks') && method === 'GET') return response([])
      if (url.endsWith('/api/v3/projects/project-p5/sources/episodes') && method === 'GET') return response([episode])
      if (url.endsWith('/api/v3/projects/project-p5/episodes/episode-1/shot-boundary') && method === 'GET') return response(boundary)
      if (url.endsWith('/api/v3/projects/project-p5/episodes/episode-1/commands/shot-boundary') && method === 'POST') {
        return response(queuedTask, 202)
      }
      throw new Error(`unexpected request: ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = await mountWorkspace()
    expect(fetchMock.mock.calls).toHaveLength(3)
    expect(fetchMock.mock.calls.every(([, init]) => ((init as RequestInit | undefined)?.method ?? 'GET') === 'GET')).toBe(true)
    expect(wrapper.text()).toContain('这里只识别切镜时间')
    expect(wrapper.text()).toContain('系统不会因为打开或刷新页面自动开始处理')

    const loadButton = wrapper.findAll('button').find((button) => button.text() === '读取已上传剧集')
    await loadButton?.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('第 1 集 · episode-01.mp4')
    expect(wrapper.text()).toContain('尚未处理')
    const preStartCalls = fetchMock.mock.calls.map(([input, init]) => ({
      url: String(input),
      method: (init as RequestInit | undefined)?.method ?? 'GET',
    }))
    expect(preStartCalls.filter((call) => call.method === 'POST')).toHaveLength(0)

    const startButton = wrapper.findAll('button').find((button) => button.text() === '开始处理这一集')
    await startButton?.trigger('click')
    await flushPromises()

    const commandCall = fetchMock.mock.calls.find(([input, init]) => (
      String(input).endsWith('/api/v3/projects/project-p5/episodes/episode-1/commands/shot-boundary')
      && (init as RequestInit | undefined)?.method === 'POST'
    ))
    expect(commandCall).toBeTruthy()
    const headers = new Headers((commandCall?.[1] as RequestInit | undefined)?.headers)
    expect(headers.get('Idempotency-Key')).toMatch(/^p5-shot-episode-1-/)
    expect(wrapper.text()).toContain('第 1 集：镜头技术预处理')

    expect(wrapper.text()).not.toContain('FFmpeg')
    expect(wrapper.text()).not.toContain('fingerprint')
    expect(wrapper.text()).not.toContain('ProviderJob')
    expect(wrapper.text()).not.toContain('adaptive_threshold')
    wrapper.unmount()
  })
})
