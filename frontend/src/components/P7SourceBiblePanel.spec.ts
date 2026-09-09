import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as projectApi from '@/features/projects/api'
import * as sourceBibleApi from '@/features/projects/sourceBible'
import type { SourceBibleRead } from '@/features/projects/sourceBible'
import P7SourceBiblePanel from './P7SourceBiblePanel.vue'

vi.mock('@/features/projects/api', () => ({
  getEpisodeSourceEvidence: vi.fn(),
  getProject: vi.fn(),
  listProjectEpisodes: vi.fn(),
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/sourceBible', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/sourceBible')>('@/features/projects/sourceBible')
  return {
    ...actual,
    editSourceBible: vi.fn(),
    getSourceBible: vi.fn(),
    listSourceBibleRevisions: vi.fn(),
    startSourceBible: vi.fn(),
  }
})

const sourceBible: SourceBibleRead = {
  project_id: 'project-p7',
  status: 'CURRENT',
  artifact_id: 'source-bible-artifact-revision-2',
  revision: 2,
  input_fingerprint: 'input-fingerprint-p7-v2',
  story_skeleton_artifact_id: 'story-current',
  rhythm_skeleton_artifact_id: 'rhythm-current',
  content: {
    schema_version: '1.1',
    title: '源作概览分析',
    episodes: [
      {
        material_baseline: {
          episode_id: 'episode-1',
          episode_order: 1,
          source_filename: '真实短剧.mp4',
          media_duration_us: 66_360_000,
          width: 1080,
          height: 1920,
          aspect_ratio: '9:16',
          avg_frame_rate: '25/1',
          codec_name: 'h264',
          has_audio: true,
          effective_content_range: { start_us: 0, end_us: 66_360_000 },
          visual_format_notes: ['竖屏短剧'],
        },
        overall_analysis: {
          story_summary: '邻里冲突逐步升级并牵动婚姻关系。',
          story_background: '现代住宅楼内发生的邻里与家庭冲突。',
          story_background_grounding: {
            support_level: 'FACT',
            dialogue_evidence_ids: ['dialogue-1'],
            visual_text_evidence_ids: [],
            video_time_ranges: [],
            note: null,
          },
          genre: ['都市现实', '家庭伦理', '邻里冲突'],
          world_rules: [],
          world_rule_groundings: [],
          narrative_structure: '由邻里事件引出家庭内部矛盾。',
          audiovisual_style: '竖屏近景与反应镜头为主。',
          rhythm_overview: '冲突密集，结尾留悬念。',
        },
        timed_script: [
          {
            segment_number: 1,
            time_range: { start_us: 0, end_us: 21_210_000 },
            visual_description: '徐然与邻居发生争执。',
            story_summary: '开场建立邻里冲突。',
            narrative_function: 'HOOK / CONFLICT',
            dialogue_evidence_ids: ['dialogue-1', 'dialogue-2'],
            visual_text_evidence_ids: ['ocr-1'],
          },
        ],
        characters: [],
        relationships: [],
        scenes: [],
        key_props: [],
        story_events: [],
        emotion_timeline: [],
        story_skeleton: {
          premise: '一次邻里纠纷暴露家庭矛盾。',
          central_conflict: '主角同时面对邻居与伴侣的压力。',
          beats: [],
        },
        rhythm_skeleton: {
          overall_pace: '快节奏冲突推进。',
          phases: [],
        },
      },
    ],
  },
  provenance: {
    source_video_artifact_id: 'source-video-artifact-long-id',
    source_video_fingerprint: 'source-video-fingerprint-long-id',
    source_dialogue_artifact_id: 'source-dialogue-artifact-long-id',
    source_dialogue_fingerprint: 'source-dialogue-fingerprint-long-id',
    shot_anchors_artifact_id: 'shot-anchors-artifact-long-id',
    shot_anchors_fingerprint: 'shot-anchors-fingerprint-long-id',
    episode_evidence_sets: [
      {
        episode_id: 'episode-1',
        source_evidence_set_id: 'evidence-set-1',
        evidence_fingerprint: 'evidence-fingerprint-1',
      },
    ],
    provider_jobs: [
      {
        provider_job_id: 'provider-job-1234567890abcdef',
        episode_id: 'episode-1',
        provider: 'volcengine-ark',
        model: 'doubao-seed-2-1-pro-260628',
        payload_fingerprint: 'provider-payload-fingerprint',
        remote_job_id: 'remote-response-1234567890',
      },
    ],
    provider: 'volcengine-ark',
    model: 'doubao-seed-2-1-pro-260628',
    prompt_version: 'p7-source-bible-v2',
    schema_version: '1.1',
    professional_skill_id: 'source-video-understanding',
    professional_skill_version: '1.1.0',
    grounding_contract: 'grounded-source-truth-v2',
    generated_by_task_id: 'task-p7-1234567890',
    edit_parent_artifact_id: null,
  },
}

async function mountPanel() {
  vi.mocked(projectApi.getProject).mockResolvedValue({
    id: 'project-p7',
    project_type: 'REPLICA',
  } as Awaited<ReturnType<typeof projectApi.getProject>>)
  vi.mocked(projectApi.listProjectEpisodes).mockResolvedValue([
    { id: 'episode-1' } as Awaited<ReturnType<typeof projectApi.listProjectEpisodes>>[number],
  ])
  vi.mocked(projectApi.listProjectTasks).mockResolvedValue([])
  vi.mocked(projectApi.getEpisodeSourceEvidence).mockResolvedValue({
    dialogue: [
      { id: 'dialogue-1', start_us: 270_000, end_us: 1_000_000, text: '第一句对白' },
      { id: 'dialogue-2', start_us: 1_100_000, end_us: 1_800_000, text: '第二句对白' },
    ],
    visual_text: [
      { id: 'ocr-1', start_us: 800_000, end_us: 1_500_000, text: '502业主' },
    ],
  } as Awaited<ReturnType<typeof projectApi.getEpisodeSourceEvidence>>)
  vi.mocked(sourceBibleApi.getSourceBible).mockResolvedValue(sourceBible)
  vi.mocked(sourceBibleApi.listSourceBibleRevisions).mockResolvedValue([
    {
      artifact_id: 'source-bible-artifact-revision-2',
      revision: 2,
      status: 'CURRENT',
      input_fingerprint: 'input-fingerprint-p7-v2',
      created_at: '2026-09-09T00:00:00Z',
      edit_parent_artifact_id: null,
    },
  ])

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: P7SourceBiblePanel }],
  })
  await router.push('/projects/project-p7')
  await router.isReady()
  const wrapper = mount(P7SourceBiblePanel, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('P7SourceBiblePanel review presentation', () => {
  it('separates genre from source-internal world rules', async () => {
    const wrapper = await mountPanel()

    expect(wrapper.text()).toContain('类型')
    expect(wrapper.text()).toContain('都市现实')
    expect(wrapper.text()).toContain('世界规则')
    expect(wrapper.text()).toContain('无明确片内世界规则')
    expect(wrapper.text()).not.toContain('类型 / 世界规则')
    wrapper.unmount()
  })

  it('keeps canonical Evidence collapsed by default and shows counts in the summary', async () => {
    const wrapper = await mountPanel()

    const disclosure = wrapper.get('.evidence-disclosure')
    expect(disclosure.attributes('open')).toBeUndefined()
    expect(disclosure.get('summary').text()).toContain('证据 · 对白 2 条 · OCR 1 条')
    expect(disclosure.get('summary').text()).toContain('查看依据')
    wrapper.unmount()
  })

  it('renders the complete P7 audit contract in Revision / Provenance', async () => {
    const wrapper = await mountPanel()
    const provenance = wrapper.get('.provenance')
    const text = provenance.text()

    expect(text).toContain('volcengine-ark')
    expect(text).toContain('doubao-seed-2-1-pro-260628')
    expect(text).toContain('p7-source-bible-v2')
    expect(text).toContain('source-video-understanding@1.1.0')
    expect(text).toContain('grounded-source-truth-v2')
    expect(text).toContain('ProviderJob')
    expect(text).toContain('Schema')
    expect(text).toContain('1.1')
    wrapper.unmount()
  })
})
