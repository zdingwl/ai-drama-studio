import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SourceScriptStoryboardWorkspace from './SourceScriptStoryboardWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as sourceAnalysisApi from '@/features/projects/sourceAnalysis'
import type {
  SourceAnalysisStatusRead,
  SourceScriptRead,
  StoryboardDraftRead,
} from '@/features/projects/sourceAnalysis'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
}))

vi.mock('@/features/projects/sourceAnalysis', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/sourceAnalysis')>('@/features/projects/sourceAnalysis')
  return {
    ...actual,
    getSourceAnalysisStatus: vi.fn(),
    getSourceScript: vi.fn(),
    getStoryboardDraft: vi.fn(),
    startSourceAnalysis: vi.fn(),
    editStoryboardShot: vi.fn(),
  }
})

const readyStatus: SourceAnalysisStatusRead = {
  project_id: 'project-1',
  state: 'READY',
  progress_percent: 100,
  current_stage: '解析完成',
  task_id: 'task-1',
  can_retry: false,
  message: '原片解析完成，可以直接查看剧本和分镜。',
}

const script: SourceScriptRead = {
  project_id: 'project-1',
  state: 'READY',
  title: '原片剧本',
  scenes: [{
    scene_number: 1,
    episode_id: 'episode-1',
    scene_id: 'scene-1',
    scene_name: '徐然家客厅',
    start_us: 0,
    end_us: 2_000_000,
    character_names: ['徐然'],
    shots: [{
      episode_id: 'episode-1',
      shot_anchor_id: 'shot-1',
      shot_number: 1,
      start_us: 0,
      end_us: 2_000_000,
      duration_us: 2_000_000,
      action_summary: '徐然站在客厅里看向门口。',
      visual_description: '徐然站在客厅里看向门口。',
      shot_size: '中景',
      composition: '人物居中',
      angle_or_type: '平视',
      movement: '固定',
      focal_length_dof: '标准焦段',
      thumbnail_url: '/api/v3/projects/project-1/episodes/episode-1/shot-boundary/shots/shot-1/thumbnail',
      reference_clip_url: '/api/v3/projects/project-1/episodes/episode-1/shot-boundary/shots/shot-1/reference-clip',
      dialogues: [{
        utterance_id: 'utt-1',
        utterance_number: 1,
        start_us: 500_000,
        end_us: 1_000_000,
        speaker_id: 'speaker-1',
        speaker_name: '徐然',
        text: '你把东西放门口吧。',
        delivery: 'DIALOGUE',
      }],
    }],
  }],
  characters: [{ id: 'char-1', name: '徐然' }],
  props: [{ id: 'prop-1', name: '手机' }],
  character_assets: [{
    id: 'char-1',
    name: '徐然',
    related_shots: [{ episode_id: 'episode-1', episode_order: 1, shot_anchor_id: 'shot-1', shot_number: 1, thumbnail_url: '/thumb-1.jpg', reference_clip_url: '/clip-1.mp4' }],
    dialogue_count: 1,
    source_facts: ['手持手机'],
    representative_frame: { episode_id: 'episode-1', episode_order: 1, shot_anchor_id: 'shot-1', shot_number: 1, thumbnail_url: '/thumb-1.jpg', reference_clip_url: '/clip-1.mp4' },
  }],
  scene_assets: [{
    id: 'scene-1',
    name: '徐然家客厅',
    shot_ranges: ['#001'],
    related_shots: [{ episode_id: 'episode-1', episode_order: 1, shot_anchor_id: 'shot-1', shot_number: 1, thumbnail_url: '/thumb-1.jpg', reference_clip_url: '/clip-1.mp4' }],
    source_facts: [],
    representative_frame: { episode_id: 'episode-1', episode_order: 1, shot_anchor_id: 'shot-1', shot_number: 1, thumbnail_url: '/thumb-1.jpg', reference_clip_url: '/clip-1.mp4' },
  }],
  prop_assets: [{
    id: 'prop-1',
    name: '手机',
    related_shots: [{ episode_id: 'episode-1', episode_order: 1, shot_anchor_id: 'shot-1', shot_number: 1, thumbnail_url: '/thumb-1.jpg', reference_clip_url: '/clip-1.mp4' }],
    source_facts: [],
    representative_frame: { episode_id: 'episode-1', episode_order: 1, shot_anchor_id: 'shot-1', shot_number: 1, thumbnail_url: '/thumb-1.jpg', reference_clip_url: '/clip-1.mp4' },
  }],
}

const emptyDraft: StoryboardDraftRead = {
  project_id: 'project-1',
  status: 'NOT_BUILT',
  revision: null,
  base_source_current: true,
  overrides: [],
}

async function mountWorkspace(storyboardDraft: StoryboardDraftRead = emptyDraft) {
  vi.mocked(projectApi.getProject).mockResolvedValue({
    id: 'project-1',
    project_type: 'REPLICA',
  } as Awaited<ReturnType<typeof projectApi.getProject>>)
  vi.mocked(sourceAnalysisApi.getSourceAnalysisStatus).mockResolvedValue(readyStatus)
  vi.mocked(sourceAnalysisApi.getSourceScript).mockResolvedValue(script)
  vi.mocked(sourceAnalysisApi.getStoryboardDraft).mockResolvedValue(storyboardDraft)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', name: 'project-workspace', component: SourceScriptStoryboardWorkspace }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(SourceScriptStoryboardWorkspace, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('SourceScriptStoryboardWorkspace', () => {
  it('shows direct script results without exposing P5-P10 engineering vocabulary', async () => {
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('剧本与分镜')
    expect(wrapper.text()).toContain('原片剧本')
    expect(wrapper.text()).toContain('徐然家客厅')
    expect(wrapper.text()).toContain('你把东西放门口吧。')
    expect(wrapper.text()).not.toContain('P5')
    expect(wrapper.text()).not.toContain('P10')
    expect(wrapper.text()).not.toContain('SourceVideoSnapshot')
    expect(wrapper.text()).not.toContain('ProviderJob')
    expect(sourceAnalysisApi.startSourceAnalysis).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('edits a storyboard shot as an isolated working draft and closes the editor', async () => {
    const wrapper = await mountWorkspace()
    const storyboardTab = wrapper.findAll('button').find((button) => button.text() === '分镜')
    expect(storyboardTab).toBeTruthy()
    await storyboardTab!.trigger('click')

    expect(wrapper.get('.shot-media img').attributes('src')).toContain('/shot-1/thumbnail')
    expect(wrapper.text()).toContain('2.00 秒')
    expect(wrapper.text()).toContain('平视')
    expect(wrapper.text()).toContain('标准焦段')
    expect(wrapper.text()).toContain('你把东西放门口吧。')

    await wrapper.get('.shot-media').trigger('click')
    expect(wrapper.get('[data-testid="storyboard-reference-clip"] video').attributes('src')).toContain('/shot-1/reference-clip')
    await wrapper.get('[data-testid="storyboard-reference-clip"] button').trigger('click')

    const editButton = wrapper.findAll('button').find((button) => button.text() === '编辑分镜')
    expect(editButton).toBeTruthy()
    await editButton!.trigger('click')

    const editor = wrapper.get('[data-testid="storyboard-shot-editor"]')
    await editor.get('textarea').setValue('徐然拿起手机，转身走向门口。')

    vi.mocked(sourceAnalysisApi.editStoryboardShot).mockResolvedValue({
      project_id: 'project-1',
      status: 'CURRENT',
      revision: 1,
      base_source_current: true,
      overrides: [{
        shot_anchor_id: 'shot-1',
        visual_description: '徐然拿起手机，转身走向门口。',
        shot_size: '中景',
        composition: '人物居中',
        angle_or_type: '平视',
        movement: '固定',
        focal_length_dof: '标准焦段',
      }],
    })

    await editor.trigger('submit')
    await flushPromises()

    expect(sourceAnalysisApi.editStoryboardShot).toHaveBeenCalledWith('project-1', expect.objectContaining({
      expected_revision: null,
      shot_anchor_id: 'shot-1',
      visual_description: '徐然拿起手机，转身走向门口。',
    }))
    expect(wrapper.find('[data-testid="storyboard-shot-editor"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('分镜草稿已保存')
    expect(wrapper.text()).toContain('已修改')

    const scriptTab = wrapper.findAll('button').find((button) => button.text() === '原片剧本')
    await scriptTab!.trigger('click')
    expect(wrapper.text()).toContain('徐然站在客厅里看向门口。')
    expect(wrapper.text()).not.toContain('徐然拿起手机，转身走向门口。')
    wrapper.unmount()
  })

  it('archives a stale draft without applying its overrides to the new source', async () => {
    const staleDraft: StoryboardDraftRead = {
      project_id: 'project-1',
      status: 'STALE',
      revision: 4,
      base_source_current: true,
      overrides: [{
        shot_anchor_id: 'shot-1',
        visual_description: '旧草稿不应出现在新原片结果中。',
        shot_size: '特写',
        composition: '旧构图',
        angle_or_type: '旧角度',
        movement: '旧运动',
        focal_length_dof: '旧焦段',
      }],
    }
    const wrapper = await mountWorkspace(staleDraft)
    const storyboardTab = wrapper.findAll('button').find((button) => button.text() === '分镜')
    await storyboardTab!.trigger('click')

    expect(wrapper.text()).toContain('旧分镜草稿已归档')
    expect(wrapper.text()).toContain('徐然站在客厅里看向门口。')
    expect(wrapper.text()).not.toContain('旧草稿不应出现在新原片结果中。')
    expect(wrapper.text()).not.toContain('已修改')
    wrapper.unmount()
  })

  it('renders evidence-bound character, scene, and prop cards that can locate a source shot', async () => {
    const wrapper = await mountWorkspace()
    const assetsTab = wrapper.findAll('button').find((button) => button.text() === '人物 / 场景 / 道具')
    await assetsTab!.trigger('click')

    const assets = wrapper.get('[data-testid="source-assets-view"]')
    expect(assets.text()).toContain('1 个相关镜头 · 1 句对白')
    expect(assets.text()).toContain('手持手机')
    expect(assets.text()).toContain('#001')
    expect(assets.findAll('.asset-frame img')).toHaveLength(3)

    await assets.find('.asset-shots button').trigger('click')
    expect(wrapper.get('[data-testid="source-storyboard-view"]')).toBeTruthy()
    expect(wrapper.get('#source-shot-shot-1').classes()).toContain('focused-shot')
    wrapper.unmount()
  })
})
