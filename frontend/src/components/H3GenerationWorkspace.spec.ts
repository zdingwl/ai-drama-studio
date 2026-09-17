import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import H3GenerationWorkspace from './H3GenerationWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as productionApi from '@/features/projects/production'
import * as replicaApi from '@/features/projects/replicaFiveStep'
import type { GeneratedVideoRead } from '@/features/projects/production'
import type { TaskRead } from '@/features/projects/types'

vi.mock('@/features/projects/api', () => ({
  cancelProjectTask: vi.fn(),
  listProjectTasks: vi.fn(),
  resumeProjectTask: vi.fn(),
  retryProjectTask: vi.fn(),
}))

vi.mock('@/features/projects/production', () => ({
  getGeneratedVideo: vi.fn(),
  getVideoGenerationRuntimeReadiness: vi.fn(),
  listGenerationAttempts: vi.fn(),
  regenerateVideoSegment: vi.fn(),
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
    segments: [{
      generation_segment_id: 'segment-1',
      episode_id: 'episode-1',
      episode_order: 1,
      segment_number: 1,
      storyboard_shot_ids: ['shot-1'],
      start_us: 0,
      end_us: 4_000_000,
      duration_us: 4_000_000,
      output_ratio: '9:16',
      continuation_index: 1,
      continuation_count: 1,
      generation_prompt: 'H3 prompt',
      negative_prompt: '',
      prompt_skill_id: 'minimax-h3-prompting',
      prompt_skill_version: '1.1.0',
      prompt_contract: 'h3',
      model_id: 'MiniMax-H3',
      review_prompt_zh: '中文审核',
      reference_conditions: [],
      target_asset_refs: [],
      audio_generation_mode: 'NATIVE_AUDIO_VIDEO',
      dialogue_refs: [],
      sound_effects: [],
      ambience: [],
      requires_lip_sync: false,
    }],
  },
  provenance: null,
}

const currentVideo: GeneratedVideoRead = {
  status: 'CURRENT',
  artifact_id: 'video-2',
  revision: 2,
  content: {
    target_storyboard_artifact_id: 'storyboard-3',
    generation_segments_artifact_id: 'segments-5',
    target_assets_artifact_id: 'assets-5',
    clips: [{
      generation_segment_id: 'segment-1',
      episode_id: 'episode-1',
      episode_order: 1,
      segment_number: 1,
      planned_start_us: 0,
      planned_end_us: 4_000_000,
      planned_duration_us: 4_000_000,
      requires_lip_sync: false,
      selected_attempt_id: 'attempt-current',
      media_url: '/current.mp4',
      actual_duration_us: 4_000_000,
      width: 768,
      height: 1360,
    }],
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
  created_at: '2026-09-17T12:00:00Z',
  started_at: null,
  finished_at: null,
}

function mockReads(video: GeneratedVideoRead) {
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
  vi.mocked(productionApi.getGeneratedVideo).mockResolvedValue(video)
  vi.mocked(productionApi.startVideoGeneration).mockResolvedValue(queuedTask)
  vi.mocked(productionApi.regenerateVideoSegment).mockResolvedValue({
    ...queuedTask,
    id: 'segment-redo',
    task_type: 'P16_MINIMAX_H3_SEGMENT_REGENERATE',
    task_name: '重做视频分镜 · Segment 1',
  })
}

async function mountWorkspace() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: { template: '<main />' } }],
  })
  await router.push('/projects/project-1?episode=episode-1&ep=1')
  await router.isReady()
  const wrapper = mount(H3GenerationWorkspace, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('H3GenerationWorkspace current-version workflow', () => {
  it('uses generated video as the current version and only exposes per-segment redo', async () => {
    mockReads(currentVideo)
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('生成成功即作为当前版本')
    expect(wrapper.text()).toContain('重做该分镜')
    expect(wrapper.text()).not.toContain('确认正式视频')
    expect(wrapper.text()).not.toContain('拒绝并重新生成')

    const redo = wrapper.findAll('button').find(button => button.text() === '重做该分镜')
    expect(redo).toBeTruthy()
    await redo!.trigger('click')
    await flushPromises()

    expect(productionApi.regenerateVideoSegment).toHaveBeenCalledWith('project-1', 'segment-1')
    expect(productionApi.startVideoGeneration).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('starts a full generation only when there is no current generated video', async () => {
    mockReads({ status: 'NOT_BUILT', artifact_id: null, content: null })
    const wrapper = await mountWorkspace()

    const generate = wrapper.findAll('button').find(button => button.text() === '用 MiniMax H3 生成视频')
    expect(generate).toBeTruthy()
    expect(generate?.attributes('disabled')).toBeUndefined()

    await generate!.trigger('click')
    await flushPromises()

    expect(productionApi.startVideoGeneration).toHaveBeenCalledWith('project-1')
    expect(productionApi.regenerateVideoSegment).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
