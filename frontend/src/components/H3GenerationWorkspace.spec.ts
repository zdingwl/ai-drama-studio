import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import H3GenerationWorkspace from './H3GenerationWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as productionApi from '@/features/projects/production'
import * as replicaApi from '@/features/projects/replicaFiveStep'
import type { GenerationCandidate } from '@/features/projects/production'
import type { TaskRead } from '@/features/projects/types'

vi.mock('@/features/projects/api', () => ({
  listProjectTasks: vi.fn(),
  resumeProjectTask: vi.fn(),
  retryProjectTask: vi.fn(),
}))

vi.mock('@/features/projects/production', () => ({
  getGenerationSelection: vi.fn(),
  getVideoGenerationRuntimeReadiness: vi.fn(),
  listGenerationAttempts: vi.fn(),
  listGenerationCandidates: vi.fn(),
  reviewGeneration: vi.fn(),
  startVideoGeneration: vi.fn(),
}))

vi.mock('@/features/projects/replicaFiveStep', () => ({
  getH3Prompts: vi.fn(),
}))

const currentPrompts = {
  project_id: 'project-1',
  status: 'CURRENT' as const,
  artifact_id: 'segments-5',
  revision: 5,
  content: {
    target_storyboard_artifact_id: 'storyboard-3',
    target_assets_artifact_id: 'assets-5',
    segments: [],
  },
  provenance: null,
}

const oldCandidate: GenerationCandidate = {
  id: 'candidate-old',
  generation_sequence: 1,
  review_status: 'NEEDS_REVIEW',
  content: {
    target_storyboard_artifact_id: 'storyboard-3',
    generation_segments_artifact_id: 'segments-4',
    target_assets_artifact_id: 'assets-4',
    clips: [{
      generation_segment_id: 'segment-1',
      episode_id: 'episode-1',
      episode_order: 1,
      segment_number: 1,
      planned_start_us: 0,
      planned_end_us: 4_000_000,
      planned_duration_us: 4_000_000,
      requires_lip_sync: false,
      selected_attempt_id: 'attempt-old',
      media_url: '/old.mp4',
      actual_duration_us: 4_000_000,
      width: 768,
      height: 1360,
    }],
  },
}

const currentCandidate: GenerationCandidate = {
  ...oldCandidate,
  id: 'candidate-current',
  generation_sequence: 2,
  content: {
    ...oldCandidate.content,
    generation_segments_artifact_id: 'segments-5',
    target_assets_artifact_id: 'assets-5',
  },
}

const queuedTask: TaskRead = {
  id: 'p16-task-new',
  project_id: 'project-1',
  task_type: 'P16_MINIMAX_H3_GENERATION',
  task_name: '生成视频并执行技术质检',
  progress_percent: 0,
  status: 'queued',
  last_error: null,
  attempt: 0,
  max_attempts: 3,
  can_retry: false,
  can_cancel: true,
  can_resume: false,
  created_at: '2026-09-15T12:00:00Z',
  started_at: null,
  finished_at: null,
}

function mockReads(candidates: GenerationCandidate[]) {
  vi.mocked(replicaApi.getH3Prompts).mockResolvedValue(currentPrompts)
  vi.mocked(productionApi.getVideoGenerationRuntimeReadiness).mockResolvedValue({
    runtime_mode: 'LOCAL_COMFYUI',
    state: 'READY',
    ready: true,
    provider: 'local-comfyui',
    model: 'MiniMax-H3',
    base_url: 'http://127.0.0.1:8188',
    message: 'ready',
  })
  vi.mocked(projectApi.listProjectTasks).mockResolvedValue([])
  vi.mocked(productionApi.listGenerationAttempts).mockResolvedValue([])
  vi.mocked(productionApi.listGenerationCandidates).mockResolvedValue(candidates)
  vi.mocked(productionApi.getGenerationSelection).mockResolvedValue({ status: 'NOT_BUILT', artifact_id: null, content: null })
  vi.mocked(productionApi.startVideoGeneration).mockResolvedValue(queuedTask)
  vi.mocked(productionApi.reviewGeneration).mockResolvedValue({})
}

async function mountWorkspace() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: { template: '<main />' } }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(H3GenerationWorkspace, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('H3GenerationWorkspace stale candidate handling', () => {
  it('does not let an old NEEDS_REVIEW candidate block regeneration from current assets/prompts', async () => {
    mockReads([oldCandidate])
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('检测到 1 个旧生成候选')
    expect(wrapper.text()).toContain('不会阻塞当前重新生成')
    expect(wrapper.text()).not.toContain('确认正式视频')
    const regenerate = wrapper.findAll('button').find(button => button.text() === '重新生成视频')
    expect(regenerate).toBeTruthy()
    expect(regenerate?.attributes('disabled')).toBeUndefined()

    await regenerate!.trigger('click')
    await flushPromises()

    expect(productionApi.startVideoGeneration).toHaveBeenCalledWith('project-1')
    expect(productionApi.reviewGeneration).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps a current candidate reviewable and reject-and-regenerate actually starts a new task', async () => {
    mockReads([currentCandidate])
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('确认正式视频')
    expect(wrapper.text()).not.toContain('旧生成候选')
    const reject = wrapper.findAll('button').find(button => button.text() === '拒绝并重新生成')
    expect(reject).toBeTruthy()

    await reject!.trigger('click')
    await flushPromises()

    expect(productionApi.reviewGeneration).toHaveBeenCalledWith(
      'project-1',
      currentCandidate,
      false,
      expect.any(String),
    )
    expect(productionApi.startVideoGeneration).toHaveBeenCalledWith('project-1')
    expect(wrapper.text()).toContain('新一轮 MiniMax H3 生成任务已启动')
    wrapper.unmount()
  })
})
