import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as projectApi from '@/features/projects/api'
import P6AcceptancePanel from './P6AcceptancePanel.vue'

vi.mock('@/features/projects/api', () => ({
  adjudicateEpisodeDialogue: vi.fn(),
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
    text_source: 'ASR' as const,
    asr_text: '你好，世界。',
    ocr_text: null,
    ocr_span_numbers: [],
    adjudication_policy: null,
    adjudication_reason: null,
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
    expect(wrapper.text()).toContain('人工确认 / 修改')
    expect(wrapper.text()).not.toContain('字幕校正')
    wrapper.unmount()
  })

  it('shows audited subtitle correction and the original ASR text together', async () => {
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    vi.mocked(projectApi.listProjectEpisodes).mockResolvedValue([episode])
    vi.mocked(projectApi.getEpisodeSourceEvidence).mockResolvedValue({
      ...evidence,
      dialogue: [{
        ...evidence.dialogue[0],
        text: '乙阿姨',
        text_source: 'OCR_SUBTITLE_ADJUDICATED' as const,
        asr_text: '甲阿姨',
        ocr_text: '乙阿姨',
        ocr_span_numbers: [3, 4],
        adjudication_policy: 'ocr-subtitle-near-match-v1',
        adjudication_reason: 'HIGH_CONFIDENCE_TEMPORAL_SUBTITLE_NEAR_MATCH',
      }],
    })

    const wrapper = await mountPanel()
    const text = wrapper.text()
    expect(text).toContain('字幕校正')
    expect(text).toContain('乙阿姨')
    expect(text).toContain('ASR 原文：甲阿姨')
    expect(text).toContain('OCR span #3, #4')
    wrapper.unmount()
  })

  it('lets the user explicitly choose or edit canonical dialogue and only saves on command', async () => {
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    vi.mocked(projectApi.listProjectEpisodes).mockResolvedValue([episode])
    vi.mocked(projectApi.getEpisodeSourceEvidence).mockResolvedValue(evidence)
    vi.mocked(projectApi.adjudicateEpisodeDialogue).mockResolvedValue({
      ...evidence,
      revision: 2,
      artifact_revision: 2,
      dialogue: [{
        ...evidence.dialogue[0],
        id: 'dialogue-2',
        text: '人工确认后的台词',
        text_source: 'USER_EDITED' as const,
        adjudication_policy: 'human-dialogue-adjudication-v1',
        adjudication_reason: 'USER_SELECTED_CUSTOM',
      }],
    })

    const wrapper = await mountPanel()
    const editButton = wrapper.findAll('button').find((button) => button.text().includes('人工确认 / 修改'))
    expect(editButton).toBeTruthy()
    await editButton!.trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('使用 ASR 原文')
    expect(wrapper.text()).toContain('使用 OCR 字幕')
    expect(wrapper.text()).toContain('自定义文本')
    expect(projectApi.adjudicateEpisodeDialogue).not.toHaveBeenCalled()

    const customRadio = wrapper.find('input[type="radio"][value="CUSTOM"]')
    await customRadio.setValue(true)
    const textarea = wrapper.find('textarea')
    await textarea.setValue('人工确认后的台词')

    const saveButton = wrapper.findAll('button').find((button) => button.text().includes('保存为新 revision'))
    expect(saveButton).toBeTruthy()
    await saveButton!.trigger('click')
    await flushPromises()

    expect(projectApi.adjudicateEpisodeDialogue).toHaveBeenCalledTimes(1)
    expect(projectApi.adjudicateEpisodeDialogue).toHaveBeenCalledWith(
      'project-1',
      'episode-1',
      {
        expected_revision: 1,
        utterance_id: 'dialogue-1',
        choice: 'CUSTOM',
        custom_text: '人工确认后的台词',
      },
      expect.stringContaining('p6-human-episode-1-dialogue-1-'),
    )
    expect(wrapper.text()).toContain('人工确认后的台词')
    expect(wrapper.text()).toContain('人工确认')
    expect(wrapper.text()).toContain('已保存为 P6 rev 2')
    expect(wrapper.text()).toContain('P6 → P7 → P8')
    wrapper.unmount()
  })

  it('cancels manual editing without creating a revision', async () => {
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    vi.mocked(projectApi.listProjectEpisodes).mockResolvedValue([episode])
    vi.mocked(projectApi.getEpisodeSourceEvidence).mockResolvedValue(evidence)

    const wrapper = await mountPanel()
    const editButton = wrapper.findAll('button').find((button) => button.text().includes('人工确认 / 修改'))
    await editButton!.trigger('click')
    await flushPromises()

    const cancelButton = wrapper.findAll('button').find((button) => button.text() === '取消')
    expect(cancelButton).toBeTruthy()
    await cancelButton!.trigger('click')
    await flushPromises()

    expect(projectApi.adjudicateEpisodeDialogue).not.toHaveBeenCalled()
    expect(wrapper.text()).not.toContain('保存为新 revision')
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
