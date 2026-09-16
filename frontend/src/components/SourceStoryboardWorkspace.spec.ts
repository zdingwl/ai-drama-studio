import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SourceStoryboardWorkspace from './SourceStoryboardWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as sourceAnalysisApi from '@/features/projects/sourceAnalysis'
import type { SourceAnalysisStatusRead, SourceScriptRead, StoryboardDraftRead } from '@/features/projects/sourceAnalysis'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
}))

vi.mock('@/features/projects/sourceAnalysis', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/sourceAnalysis')>()
  return {
    ...actual,
    editStoryboardShot: vi.fn(),
    getSourceAnalysisStatus: vi.fn(),
    getSourceScript: vi.fn(),
    getStoryboardDraft: vi.fn(),
    startSourceAnalysis: vi.fn(),
  }
})

const readyStatus: SourceAnalysisStatusRead = {
  project_id: 'project-1',
  state: 'READY',
  progress_percent: 100,
  current_stage: '解析完成',
  task_id: null,
  can_retry: false,
  message: '原片分析已完成',
  script_ready: true,
  visual_enrichment_ready: true,
}

const source: SourceScriptRead = {
  project_id: 'project-1',
  state: 'READY',
  title: '测试原片',
  source_script_artifact_id: 'source-script-1',
  visual_enrichment_ready: true,
  scenes: [{
    scene_number: 1,
    episode_id: 'episode-1',
    scene_id: 'scene-1',
    scene_name: '王桂香家客厅',
    start_us: 0,
    end_us: 2_000_000,
    character_names: ['玛吉'],
    shots: [{
      episode_id: 'episode-1',
      shot_anchor_id: 'shot-1',
      shot_number: 1,
      start_us: 0,
      end_us: 2_000_000,
      duration_us: 2_000_000,
      action_summary: '镜头固定，蓝色玫瑰位于茶几中央。',
      visual_description: '客厅茶几中央摆放着一束蓝色玫瑰。',
      shot_size: '中景',
      composition: '中心构图',
      angle_or_type: '平视',
      movement: '固定镜头',
      focal_length_dof: '标准焦段，中等景深',
      thumbnail_url: '/thumb.jpg',
      reference_clip_url: '/clip.mp4',
      dialogues: [{
        utterance_id: 'utt-1',
        utterance_number: 1,
        start_us: 200_000,
        end_us: 800_000,
        speaker_id: 'speaker-1',
        speaker_name: '玛吉',
        text: 'Marge?',
        delivery: 'NORMAL',
      }],
    }],
  }],
  characters: [],
  props: [],
  character_assets: [],
  scene_assets: [],
  prop_assets: [],
}

const emptyDraft: StoryboardDraftRead = {
  project_id: 'project-1',
  status: 'NOT_BUILT',
  revision: null,
  base_source_current: true,
  overrides: [],
}

async function mountWorkspace() {
  vi.mocked(projectApi.getProject).mockResolvedValue({ id: 'project-1', project_type: 'REPLICA' } as Awaited<ReturnType<typeof projectApi.getProject>>)
  vi.mocked(sourceAnalysisApi.getSourceAnalysisStatus).mockResolvedValue(readyStatus)
  vi.mocked(sourceAnalysisApi.getSourceScript).mockResolvedValue(source)
  vi.mocked(sourceAnalysisApi.getStoryboardDraft).mockResolvedValue(emptyDraft)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id/:workspace', name: 'project-workspace', component: SourceStoryboardWorkspace }],
  })
  await router.push('/projects/project-1/source?episode=episode-1&ep=1')
  await router.isReady()
  const wrapper = mount(SourceStoryboardWorkspace, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('SourceStoryboardWorkspace editable analysis', () => {
  it('re-analyzes only the episode selected by the workspace route', async () => {
    vi.mocked(sourceAnalysisApi.startSourceAnalysis).mockResolvedValue(readyStatus)
    const wrapper = await mountWorkspace()

    const reanalyze = wrapper.findAll('button').find(button => button.text() === '重新分析')
    expect(reanalyze).toBeDefined()
    await reanalyze!.trigger('click')
    await flushPromises()

    expect(sourceAnalysisApi.startSourceAnalysis).toHaveBeenCalledWith(
      'project-1',
      expect.stringMatching(/^source-storyboard-/),
      'episode-1',
    )
    expect(sourceAnalysisApi.getSourceAnalysisStatus).toHaveBeenCalledWith('project-1', 'episode-1')

    wrapper.unmount()
  })

  it('saves human corrections as a storyboard working draft and can restore the original analysis', async () => {
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('直接点击内容即可修改')
    expect(wrapper.text()).toContain('光标离开后自动保存')
    expect(wrapper.text()).toContain('原片对白 只读')
    expect(sourceAnalysisApi.getSourceAnalysisStatus).toHaveBeenCalledWith('project-1', 'episode-1')
    expect(sourceAnalysisApi.getStoryboardDraft).toHaveBeenCalledWith('project-1')
    expect(wrapper.find('[data-testid="source-shot-editor"]').exists()).toBe(false)

    await wrapper.get('button[data-edit-field="visual_description"]').trigger('click')
    const editor = wrapper.get('textarea[data-edit-field="visual_description"]')
    await editor.setValue('客厅茶几中央摆放着一束蓝色玫瑰，花瓶略偏画面右侧。')

    vi.mocked(sourceAnalysisApi.editStoryboardShot).mockResolvedValueOnce({ 
      project_id: 'project-1',
      status: 'CURRENT',
      revision: 1,
      base_source_current: true,
      overrides: [{
        shot_anchor_id: 'shot-1',
        visual_description: '客厅茶几中央摆放着一束蓝色玫瑰，花瓶略偏画面右侧。',
        shot_size: '中景',
        composition: '中心构图',
        angle_or_type: '平视',
        movement: '固定镜头',
        focal_length_dof: '标准焦段，中等景深',
      }],
    })

    await editor.trigger('blur')
    await flushPromises()

    expect(sourceAnalysisApi.editStoryboardShot).toHaveBeenCalledWith('project-1', expect.objectContaining({
      expected_revision: null,
      shot_anchor_id: 'shot-1',
      visual_description: '客厅茶几中央摆放着一束蓝色玫瑰，花瓶略偏画面右侧。',
      shot_size: '中景',
      composition: '中心构图',
      angle_or_type: '平视',
      movement: '固定镜头',
      focal_length_dof: '标准焦段，中等景深',
    }))
    expect(wrapper.find('textarea[data-edit-field="visual_description"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('已人工修改')
    expect(wrapper.text()).toContain('已自动保存')
    expect(wrapper.text()).toContain('1 镜人工修订')
    expect(wrapper.text()).toContain('花瓶略偏画面右侧')

    vi.mocked(sourceAnalysisApi.editStoryboardShot).mockResolvedValueOnce({
      project_id: 'project-1',
      status: 'CURRENT',
      revision: 2,
      base_source_current: true,
      overrides: [],
    })
    await wrapper.findAll('button').find(button => button.text() === '恢复分析结果')!.trigger('click')
    await flushPromises()

    expect(sourceAnalysisApi.editStoryboardShot).toHaveBeenLastCalledWith('project-1', {
      expected_revision: 1,
      shot_anchor_id: 'shot-1',
      reset_to_source: true,
    })
    expect(wrapper.text()).toContain('客厅茶几中央摆放着一束蓝色玫瑰。')
    expect(wrapper.text()).not.toContain('花瓶略偏画面右侧')
    expect(wrapper.text()).not.toContain('已人工修改')

    wrapper.unmount()
  })
})
