import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as projectApi from '@/features/projects/api'
import P6AcceptancePanel from './P6AcceptancePanel.vue'

vi.mock('@/features/projects/api', () => ({
  getEpisodeSourceEvidence: vi.fn(),
  getProject: vi.fn(),
  listProjectEpisodes: vi.fn(),
  listProjectTasks: vi.fn(),
  startEpisodeSourceEvidence: vi.fn(),
}))

const project = {
  id: 'project-1',
  name: 'P6 验收项目',
  project_type: 'REPLICA' as const,
  source_language: 'zh-CN',
  target_language: 'en-US',
  target_region: 'US',
  scene_strategy: 'MIXED' as const,
  audio_policy: 'REGENERATE_AUDIO' as const,
  visual_style: null,
  source_understanding_provider: 'DOUBAO_SEED_2_1_PRO_API' as const,
  status: 'ACTIVE' as const,
  workflow_revision: 1,
  created_at: '2026-09-08T00:00:00Z',
  updated_at: '2026-09-08T00:00:00Z',
}

const episode = {
  id: 'episode-1',
  project_id: 'project-1',
  source_asset: { id: 'asset-1', original_filename: 'real-drama.mp4' },
  episode_order: 1,
  duration_us: 2_000_000,
  width: 1080,
  height: 1920,
  codec_name: 'h264',
  avg_frame_rate: '24/1',
  has_audio: true,
  created_at: '2026-09-08T00:00:00Z',
}

const evidence = {
  episode_id: 'episode-1',
  episode_order: 1,
  source_filename: 'real-drama.mp4',
  status: 'CURRENT' as const,
  revision: 1,
  artifact_revision: 1,
  dialogue_count: 1,
  visual_text_count: 1,
  raw_asr_segment_count: 2,
  raw_ocr_observation_count: 4,
  dialogue: [{
    id: 'dialogue-1',
    utterance_number: 1,
    start_us: 700_000,
    end_us: 1_300_000,
    text: '你好，世界。',
    language: 'zh',
    projected_shot_numbers: [1, 2],
  }],
  visual_text: [{
    id: 'visual-1',
    span_number: 1,
    start_us: 100_000,
    end_us: 900_000,
    text: '画面字幕',
    confidence: 0.99,
  }],
}

const notBuiltEvidence = {
  ...evidence,
  status: 'NOT_BUILT' as const,
  revision: null,
  artifact_revision: null,
  dialogue_count: 0,
  visual_text_count: 0,
  raw_asr_segment_count: 0,
  raw_ocr_observation_count: 0,
  dialogue: [],
  visual_text: [],
}

async function mountPanel() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', name: 'project-workspace', component: P6AcceptancePanel }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(P6AcceptancePanel, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('P6AcceptancePanel', () => {
  it('shows canonical dialogue, OCR and cross-shot projection for human acceptance', async () => {
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    vi.mocked(projectApi.listProjectEpisodes).mockResolvedValue([episode])
    vi.mocked(projectApi.getEpisodeSourceEvidence).mockResolvedValue(evidence)

    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('P6 开发验收 · Source Evidence')
    expect(wrapper.text()).toContain('CURRENT · 当前有效')
    expect(wrapper.text()).toContain('你好，世界。')
    expect(wrapper.text()).toContain('Shot 1, 2')
    expect(wrapper.text()).toContain('画面字幕')
    wrapper.unmount()
  })

  it('starts a real source-evidence command for the selected full Episode', async () => {
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    vi.mocked(projectApi.listProjectEpisodes).mockResolvedValue([episode])
    vi.mocked(projectApi.getEpisodeSourceEvidence).mockResolvedValue(notBuiltEvidence)
    vi.mocked(projectApi.startEpisodeSourceEvidence).mockResolvedValue({
      id: 'task-1',
      project_id: 'project-1',
      task_name: '第 1 集：对白与画面文字证据',
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
    })

    const wrapper = await mountPanel()
    const runButton = wrapper.findAll('button').find((button) => button.text().includes('运行真实 ASR + OCR'))
    expect(runButton).toBeTruthy()
    await runButton!.trigger('click')
    await flushPromises()

    expect(projectApi.startEpisodeSourceEvidence).toHaveBeenCalledTimes(1)
    expect(projectApi.startEpisodeSourceEvidence).toHaveBeenCalledWith(
      'project-1',
      'episode-1',
      expect.stringContaining('p6-acceptance-episode-1-'),
    )
    expect(wrapper.text()).toContain('第 1 集：对白与画面文字证据')
    wrapper.unmount()
  })

  it('auto-refreshes NOT_BUILT evidence so a task retried from the shared task card becomes visible', async () => {
    vi.useFakeTimers()
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    vi.mocked(projectApi.listProjectEpisodes).mockResolvedValue([episode])
    vi.mocked(projectApi.getEpisodeSourceEvidence)
      .mockResolvedValueOnce(notBuiltEvidence)
      .mockResolvedValue(evidence)

    const wrapper = await mountPanel()
    expect(wrapper.text()).toContain('NOT_BUILT · 尚未提取')

    await vi.advanceTimersByTimeAsync(2600)
    await flushPromises()

    expect(projectApi.getEpisodeSourceEvidence).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('CURRENT · 当前有效')
    expect(wrapper.text()).toContain('你好，世界。')
    wrapper.unmount()
  })
})
