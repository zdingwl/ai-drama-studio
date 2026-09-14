import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ReplicaProductionWorkspace from './ReplicaProductionWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as productionApi from '@/features/projects/production'
import type { TaskRead } from '@/features/projects/types'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
  listProjectTasks: vi.fn(),
  retryProjectTask: vi.fn(),
  resumeProjectTask: vi.fn(),
}))

vi.mock('@/features/projects/production', () => ({
  getFinalOutput: vi.fn(),
  getGenerationSegments: vi.fn(),
  getGenerationSelection: vi.fn(),
  getTargetStoryboard: vi.fn(),
  getVideoGenerationRuntimeReadiness: vi.fn(),
  listGenerationAttempts: vi.fn(),
  listGenerationCandidates: vi.fn(),
  listPostCandidates: vi.fn(),
  listStoryboardCandidates: vi.fn(),
  reviewGeneration: vi.fn(),
  reviewPost: vi.fn(),
  reviewStoryboard: vi.fn(),
  startPostProduction: vi.fn(),
  startStoryboard: vi.fn(),
  startVideoGeneration: vi.fn(),
}))

const baseTask: TaskRead = {
  id: 'p16-task-1',
  project_id: 'project-1',
  task_type: 'P16_MINIMAX_H3_GENERATION',
  task_name: 'p16-generation',
  progress_percent: 0,
  status: 'queued',
  last_error: null,
  attempt: 0,
  max_attempts: 3,
  can_retry: false,
  can_cancel: true,
  can_resume: false,
  created_at: '2026-09-13T00:00:00Z',
  started_at: null,
  finished_at: null,
}

function mockReads(tasks: TaskRead[] = []) {
  vi.mocked(projectApi.getProject).mockResolvedValue({ id: 'project-1', project_type: 'REPLICA' } as Awaited<ReturnType<typeof projectApi.getProject>>)
  vi.mocked(projectApi.listProjectTasks).mockResolvedValue(tasks)
  vi.mocked(productionApi.getTargetStoryboard).mockResolvedValue({ status: 'CURRENT', artifact_id: 'storyboard-1', content: { shots: [] } })
  vi.mocked(productionApi.getGenerationSegments).mockResolvedValue({ status: 'CURRENT', artifact_id: 'segments-1', content: { segments: [] } })
  vi.mocked(productionApi.listStoryboardCandidates).mockResolvedValue([])
  vi.mocked(productionApi.listGenerationAttempts).mockResolvedValue([])
  vi.mocked(productionApi.listGenerationCandidates).mockResolvedValue([])
  vi.mocked(productionApi.getGenerationSelection).mockResolvedValue({ status: 'NOT_BUILT', artifact_id: null, content: null })
  vi.mocked(productionApi.listPostCandidates).mockResolvedValue([])
  vi.mocked(productionApi.getFinalOutput).mockResolvedValue({ status: 'NOT_BUILT', artifact_id: null, content: null })
  vi.mocked(productionApi.getVideoGenerationRuntimeReadiness).mockResolvedValue({
    runtime_mode: 'LOCAL_COMFYUI',
    state: 'READY',
    ready: true,
    provider: 'local-comfyui',
    model: 'MiniMaxAI/MiniMax-H3',
    base_url: 'http://127.0.0.1:8188',
    message: 'ComfyUI MiniMax-H3 已就绪。',
  })
}

async function mountGeneration() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: { template: '<main />' } }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(ReplicaProductionWorkspace, {
    props: { workspace: 'generation' },
    global: { plugins: [router] },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('ReplicaProductionWorkspace generation task state', () => {
  it('restores a running P16 task instead of showing an ungenerated state', async () => {
    mockReads([{ ...baseTask, status: 'running', progress_percent: 42, attempt: 1, started_at: '2026-09-13T00:00:01Z' }])

    const wrapper = await mountGeneration()

    expect(wrapper.text()).toContain('\u751f\u6210\u4e2d 42%')
    expect(wrapper.text()).not.toContain('\u89c6\u9891\u751f\u6210\u4efb\u52a1\u5df2\u542f\u52a8')
    const button = wrapper.findAll('button').find((item) => item.text().includes('\u751f\u6210\u4e2d 42%'))
    expect(button?.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('blocks generation when the local H3 runtime is not ready', async () => {
    mockReads()
    vi.mocked(productionApi.getVideoGenerationRuntimeReadiness).mockResolvedValue({
      runtime_mode: 'LOCAL_COMFYUI',
      state: 'UNAVAILABLE',
      ready: false,
      provider: 'local-comfyui',
      model: 'MiniMaxAI/MiniMax-H3',
      base_url: 'http://127.0.0.1:8188',
      message: 'ComfyUI 未启动，无法连接 http://127.0.0.1:8188。请先启动本机 ComfyUI。',
    })

    const wrapper = await mountGeneration()

    expect(wrapper.text()).toContain('ComfyUI 未启动')
    const button = wrapper.findAll('button').find((item) => item.text() === '等待生成服务')
    expect(button).toBeTruthy()
    expect(button?.attributes('disabled')).toBeDefined()
    expect(productionApi.startVideoGeneration).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('retries a failed P16 task through the task retry command', async () => {
    const failed: TaskRead = {
      ...baseTask,
      status: 'failed',
      progress_percent: 5,
      attempt: 1,
      can_retry: true,
      can_cancel: false,
      last_error: 'P16 local H3 runtime unavailable',
      started_at: '2026-09-13T00:00:01Z',
      finished_at: '2026-09-13T00:00:02Z',
    }
    mockReads([failed])
    vi.mocked(projectApi.retryProjectTask).mockResolvedValue({ ...failed, status: 'queued', last_error: null, can_retry: false, can_cancel: true, finished_at: null })

    const wrapper = await mountGeneration()
    expect(wrapper.text()).toContain('P16 local H3 runtime unavailable')

    const retry = wrapper.findAll('button').find((item) => item.text() === '\u91cd\u8bd5\u751f\u6210')
    expect(retry).toBeTruthy()
    await retry!.trigger('click')
    await flushPromises()

    expect(projectApi.retryProjectTask).toHaveBeenCalledWith('project-1', 'p16-task-1')
    expect(productionApi.startVideoGeneration).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('\u6392\u961f\u4e2d')
    wrapper.unmount()
  })

  it('labels a pre-ComfyUI SGLang failure as historical when ComfyUI is ready', async () => {
    const failed: TaskRead = {
      ...baseTask,
      status: 'failed',
      progress_percent: 5,
      attempt: 2,
      can_retry: true,
      can_cancel: false,
      last_error: 'P16 视频生成失败（P16_LOCAL_RUNTIME_CREATE_FAILED）：本地 H3 Runtime create 未返回 JSON',
      started_at: '2026-09-13T00:00:01Z',
      finished_at: '2026-09-13T00:00:02Z',
    }
    mockReads([failed])

    const wrapper = await mountGeneration()

    expect(wrapper.text()).toContain('可重试')
    expect(wrapper.text()).toContain('当前 ComfyUI 已就绪')
    expect(wrapper.text()).not.toContain('本地 H3 Runtime create 未返回 JSON')
    const note = wrapper.find('.generation-task-note')
    expect(note.classes()).not.toContain('failed')
    wrapper.unmount()
  })
})
