import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import AssetImagesWorkspace from './AssetImagesWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as replicaApi from '@/features/projects/replicaFiveStep'
import type { TaskRead } from '@/features/projects/types'

vi.mock('@/features/projects/api', () => ({
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/replicaFiveStep', () => ({
  getAssetImages: vi.fn(),
  listAssetImageCandidates: vi.fn(),
  reviewAssetImages: vi.fn(),
  startAssetImages: vi.fn(),
}))

const runningTask: TaskRead = {
  id: 'asset-task-1',
  project_id: 'project-1',
  task_type: 'replica.asset-images',
  task_name: '提取并生成资产图',
  progress_percent: 42,
  status: 'running',
  last_error: null,
  attempt: 1,
  max_attempts: 3,
  can_retry: false,
  can_cancel: true,
  can_resume: false,
  created_at: '2026-09-14T09:30:00Z',
  started_at: '2026-09-14T09:30:01Z',
  finished_at: null,
}

function mockReads(tasks: TaskRead[] = []) {
  vi.mocked(replicaApi.getAssetImages).mockResolvedValue({
    project_id: 'project-1',
    status: 'NOT_BUILT',
    artifact_id: null,
    revision: null,
    content: null,
  })
  vi.mocked(replicaApi.listAssetImageCandidates).mockResolvedValue([])
  vi.mocked(projectApi.listProjectTasks).mockResolvedValue(tasks)
}

async function mountWorkspace() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: { template: '<main />' } }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(AssetImagesWorkspace, {
    global: { plugins: [router] },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('AssetImagesWorkspace task progress', () => {
  it('restores and displays a running asset task with real progress', async () => {
    mockReads([runningTask])

    const wrapper = await mountWorkspace()

    const progress = wrapper.get('[data-testid="asset-images-progress"]')
    expect(progress.text()).toContain('正在生成')
    expect(progress.text()).toContain('42%')
    expect(progress.text()).toContain('ComfyUI / Z-Image Turbo')
    const track = progress.get('[role="progressbar"]')
    expect(track.attributes('aria-valuenow')).toBe('42')
    expect(track.get('.progress-value').attributes('style')).toContain('width: 42%')
    const generate = wrapper.findAll('button').find(button => button.text().includes('资产生成中 42%'))
    expect(generate).toBeTruthy()
    expect(generate?.attributes('disabled')).toBeDefined()
    expect(wrapper.text()).toContain('正面全身 + 侧面全身 + 背面全身 + 面部特写')

    wrapper.unmount()
  })

  it('shows the Doubao Flux prompt compilation stage before local image rendering starts', async () => {
    mockReads([{ ...runningTask, progress_percent: 0 }])

    const wrapper = await mountWorkspace()

    const progress = wrapper.get('[data-testid="asset-images-progress"]')
    expect(progress.text()).toContain('火山引擎 Doubao')
    expect(progress.text()).toContain('Flux.1 Schnell')
    expect(wrapper.text()).toContain('正在生成资产图；完成后会在这里显示待审核的人物、场景和道具参考图。')

    wrapper.unmount()
  })

  it('shows worker failure details instead of silently returning to the empty state', async () => {
    const failedTask: TaskRead = {
      ...runningTask,
      status: 'failed',
      progress_percent: 0,
      last_error: '资产图生成失败（ASSET_IMAGE_RUNTIME_NOT_READY）：无法连接本地 ComfyUI：http://127.0.0.1:8188',
      finished_at: '2026-09-14T09:31:00Z',
      can_cancel: false,
      can_retry: true,
    }
    mockReads([failedTask])

    const wrapper = await mountWorkspace()

    const progress = wrapper.get('[data-testid="asset-images-progress"]')
    expect(progress.text()).toContain('生成失败')
    expect(progress.text()).toContain('ASSET_IMAGE_RUNTIME_NOT_READY')
    expect(progress.text()).toContain('无法连接本地 ComfyUI')
    const retry = wrapper.findAll('button').find(button => button.text() === '重试生成资产图')
    expect(retry).toBeTruthy()
    expect(retry?.attributes('disabled')).toBeUndefined()

    wrapper.unmount()
  })

  it('shows progress immediately after starting a new asset task', async () => {
    mockReads([])
    const queuedTask = { ...runningTask, status: 'queued' as const, progress_percent: 0, started_at: null }
    vi.mocked(replicaApi.startAssetImages).mockResolvedValue(queuedTask)

    const wrapper = await mountWorkspace()
    const generate = wrapper.findAll('button').find(button => button.text() === '提取并生成资产图')
    expect(generate).toBeTruthy()
    await generate!.trigger('click')
    await flushPromises()

    expect(replicaApi.startAssetImages).toHaveBeenCalledWith('project-1')
    const progress = wrapper.get('[data-testid="asset-images-progress"]')
    expect(progress.text()).toContain('排队中')
    expect(progress.text()).toContain('0%')
    expect(wrapper.text()).toContain('失败原因会直接显示')

    wrapper.unmount()
  })
})
