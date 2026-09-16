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
  getLocalizedStoryboard: vi.fn(),
  listAssetImageCandidates: vi.fn(),
  regenerateAssetImages: vi.fn(),
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
  vi.mocked(replicaApi.getLocalizedStoryboard).mockResolvedValue({ project_id: 'project-1', status: 'NOT_BUILT', artifact_id: null, revision: null, content: null })
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

  it('shows the localized-storyboard asset extraction stage before model prompt authoring starts', async () => {
    mockReads([{ ...runningTask, progress_percent: 0 }])

    const wrapper = await mountWorkspace()

    const progress = wrapper.get('[data-testid="asset-images-progress"]')
    expect(progress.text()).toContain('正在从本土化分镜提取实际使用的人物、场景和道具')
    expect(wrapper.text()).toContain('整段人物小传不会直接送进图片模型')

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
    expect(wrapper.text()).toContain('如果失败会直接显示失败原因')

    wrapper.unmount()
  })

  it('does not claim regeneration started when the backend returns the previous task', async () => {
    const completedTask: TaskRead = {
      ...runningTask,
      status: 'succeeded',
      progress_percent: 100,
      finished_at: '2026-09-15T00:49:53Z',
      can_cancel: false,
    }
    mockReads([completedTask])
    vi.mocked(replicaApi.getAssetImages).mockResolvedValue({
      project_id: 'project-1',
      status: 'CURRENT',
      artifact_id: 'assets-1',
      revision: 1,
      content: {
        target_storyboard_artifact_id: 'storyboard-1',
        target_language: 'en-US',
        target_region: 'US',
        visual_style: '写实电影感',
        assets: [],
      },
    })
    vi.mocked(replicaApi.regenerateAssetImages).mockResolvedValue(completedTask)

    const wrapper = await mountWorkspace()
    const regenerate = wrapper.findAll('button').find(button => button.text() === '重新生成资产图')
    expect(regenerate).toBeTruthy()
    await regenerate!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('没有创建新的资产图任务')
    expect(wrapper.text()).not.toContain('出图任务已启动')
    expect(replicaApi.regenerateAssetImages).toHaveBeenCalledWith('project-1')

    wrapper.unmount()
  })

  it('does not require a separate batch confirmation after assets become current', async () => {
    mockReads([])
    vi.mocked(replicaApi.getAssetImages).mockResolvedValue({
      project_id: 'project-1',
      status: 'CURRENT',
      artifact_id: 'assets-1',
      revision: 1,
      content: {
        target_storyboard_artifact_id: 'storyboard-1',
        target_language: 'en-US',
        target_region: 'US',
        visual_style: '写实电影感',
        assets: [{
          target_asset_id: 'asset-1',
          target_asset_revision: 1,
          asset_type: 'SCENE',
          target_entity_id: 'scene-1',
          display_name: '客厅',
          review_description_zh: '现代客厅',
          image_prompt: 'modern living room',
          negative_prompt: '',
          prompt_review_zh: '保持无人场景',
          image_model_id: 'Z-Image-Turbo',
          prompt_skill_id: 'z-image-turbo-asset-prompting',
          prompt_skill_version: '1.2.0',
          prompt_contract: 'z-image-turbo-replica-assets-v2',
          reference_media: [{
            reference_id: 'ref-1',
            role: 'LAYOUT',
            uri: '/ref.png',
            mime_type: 'image/png',
            sha256: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
            width: 1280,
            height: 736,
            storage_relpath: 'ref.png',
          }],
        }],
      },
    })

    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('当前可用')
    expect(wrapper.text()).not.toContain('确认资产图')
    expect(wrapper.text()).not.toContain('拒绝重做')
    expect(wrapper.findAll('button').some(button => button.text() === '重新生成资产图')).toBe(true)

    wrapper.unmount()
  })
})
