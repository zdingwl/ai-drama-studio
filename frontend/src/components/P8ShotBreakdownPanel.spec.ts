import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import P8ShotBreakdownPanel from './P8ShotBreakdownPanel.vue'
import * as projectApi from '@/features/projects/api'
import * as shotApi from '@/features/projects/shotBreakdown'
import type { ShotBreakdownRead } from '@/features/projects/shotBreakdown'
import * as sourceBibleApi from '@/features/projects/sourceBible'
import type { SourceBibleRead } from '@/features/projects/sourceBible'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/shotBreakdown', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/shotBreakdown')>('@/features/projects/shotBreakdown')
  return {
    ...actual,
    getShotBreakdown: vi.fn(),
    listShotBreakdownRevisions: vi.fn(),
    startShotBreakdown: vi.fn(),
  }
})

vi.mock('@/features/projects/sourceBible', () => ({
  getSourceBible: vi.fn(),
}))

const currentSourceBible: SourceBibleRead = {
  project_id: 'project-p8',
  status: 'CURRENT',
  artifact_id: 'source-bible-current',
  revision: 4,
  input_fingerprint: 'source-bible-current-fingerprint',
  content: null,
  provenance: null,
  story_skeleton_artifact_id: 'story-current',
  rhythm_skeleton_artifact_id: 'rhythm-current',
}

const speaker = { id: 'char-lead', label: '未命名女性A' }

const breakdown: ShotBreakdownRead = {
  project_id: 'project-p8',
  status: 'CURRENT',
  artifact_id: 'source-shot-facts-rev1',
  revision: 1,
  input_fingerprint: 'p8-fingerprint',
  content: {
    schema_version: '1.1',
    title: '逐镜精细拉片',
    episodes: [
      {
        episode_id: 'episode-1',
        episode_order: 1,
        source_filename: '真实短剧.mp4',
        shots: [
          {
            shot_anchor_id: 'shot-anchor-1',
            shot_number: 1,
            start_us: 0,
            end_us: 1_000_000,
            duration_us: 1_000_000,
            visual_description: '女主近景看向画外角色，神情警惕。',
            camera_language: {
              shot_size: '近景',
              composition: '人物位于画面右侧，保留视线空间',
              angle_or_type: '平视反应镜头',
              movement: '固定机位',
              focal_length_dof: '浅景深，面部清晰，背景轻微虚化',
            },
            bindings: {
              characters: [{ id: 'char-lead', label: '未命名女性A' }],
              scenes: [{ id: 'scene-room', label: '室内会面空间' }],
              props: [{ id: 'prop-phone', label: '手机' }],
              unresolved_subject_notes: [],
            },
            dialogue: [
              {
                utterance_id: 'utterance-cross-shot',
                utterance_number: 3,
                utterance_start_us: 700_000,
                utterance_end_us: 1_300_000,
                overlap_start_us: 700_000,
                overlap_end_us: 1_000_000,
                text: '这句话跨过两个镜头。',
                language: 'zh',
                delivery: 'DIALOGUE',
                speaker,
              },
            ],
            sound_effects: ['轻微衣物摩擦声'],
            ambience: ['室内底噪'],
            visual_text_evidence_ids: ['ocr-1'],
          },
          {
            shot_anchor_id: 'shot-anchor-2',
            shot_number: 2,
            start_us: 1_000_000,
            end_us: 2_000_000,
            duration_us: 1_000_000,
            visual_description: '切到对方反应镜头，角色保持沉默。',
            camera_language: {
              shot_size: '特写',
              composition: '面部居中',
              angle_or_type: '平视反应镜头',
              movement: '固定机位',
              focal_length_dof: '浅景深',
            },
            bindings: {
              characters: [],
              scenes: [{ id: 'scene-room', label: '室内会面空间' }],
              props: [],
              unresolved_subject_notes: ['画面内另一角色尚待 P9 最终归一'],
            },
            dialogue: [
              {
                utterance_id: 'utterance-cross-shot',
                utterance_number: 3,
                utterance_start_us: 700_000,
                utterance_end_us: 1_300_000,
                overlap_start_us: 1_000_000,
                overlap_end_us: 1_300_000,
                text: '这句话跨过两个镜头。',
                language: 'zh',
                delivery: 'OFFSCREEN',
                speaker,
              },
            ],
            sound_effects: [],
            ambience: ['室内底噪'],
            visual_text_evidence_ids: [],
          },
        ],
      },
    ],
  },
  provenance: {
    source_video_artifact_id: 'source-video-long-id',
    source_video_fingerprint: 'source-video-fingerprint',
    source_bible_artifact_id: 'source-bible-long-id',
    source_bible_fingerprint: 'source-bible-fingerprint',
    shot_anchors_artifact_id: 'shot-anchors-long-id',
    shot_anchors_fingerprint: 'shot-anchors-fingerprint',
    source_dialogue_artifact_id: 'source-dialogue-long-id',
    source_dialogue_fingerprint: 'source-dialogue-fingerprint',
    episode_inputs: [
      {
        episode_id: 'episode-1',
        shot_boundary_set_id: 'boundary-1',
        shot_boundary_fingerprint: 'boundary-fingerprint',
        source_evidence_set_id: 'evidence-1',
        source_evidence_fingerprint: 'evidence-fingerprint',
      },
    ],
    provider_jobs: [
      {
        provider_job_id: 'provider-job-1',
        episode_id: 'episode-1',
        provider: 'volcengine-ark',
        model: 'doubao-seed-2-1-pro-260628',
        payload_fingerprint: 'provider-payload-fingerprint',
        remote_job_id: 'remote-job-1',
      },
    ],
    provider: 'volcengine-ark',
    model: 'doubao-seed-2-1-pro-260628',
    prompt_version: 'p8-shot-breakdown-v2',
    schema_version: '1.1',
    professional_skill_id: 'shot-breakdown',
    professional_skill_version: '1.1.0',
    source_truth_contract: 'source-bible-shot-facts-v2',
    generated_by_task_id: 'task-p8-1',
    supersedes_artifact_id: null,
  },
}

async function mountPanel(sourceBible: SourceBibleRead = currentSourceBible) {
  vi.mocked(projectApi.getProject).mockResolvedValue({
    id: 'project-p8',
    project_type: 'REPLICA',
  } as Awaited<ReturnType<typeof projectApi.getProject>>)
  vi.mocked(projectApi.listProjectTasks).mockResolvedValue([])
  vi.mocked(shotApi.getShotBreakdown).mockResolvedValue(breakdown)
  vi.mocked(shotApi.listShotBreakdownRevisions).mockResolvedValue([
    {
      artifact_id: 'source-shot-facts-rev1',
      revision: 1,
      status: 'CURRENT',
      input_fingerprint: 'p8-fingerprint',
      created_at: '2026-09-09T00:00:00Z',
      supersedes_artifact_id: null,
    },
  ])
  vi.mocked(sourceBibleApi.getSourceBible).mockResolvedValue(sourceBible)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: P8ShotBreakdownPanel }],
  })
  await router.push('/projects/project-p8')
  await router.isReady()
  const wrapper = mount(P8ShotBreakdownPanel, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('P8ShotBreakdownPanel', () => {
  it('renders the product storyboard rows with playable P5 thumbnails and speaker names', async () => {
    const wrapper = await mountPanel()
    const text = wrapper.text()

    expect(text).toContain('逐镜分镜表')
    expect(text).toContain('镜头编号')
    expect(text).toContain('源片段')
    expect(text).toContain('时长')
    expect(text).toContain('画面描述')
    expect(text).toContain('镜头语言')
    expect(text).toContain('绑定主体')
    expect(text).toContain('对白 / 旁白')
    expect(text).toContain('音效')
    expect(text).toContain('未命名女性A')
    expect(text).toContain('室内会面空间')
    expect(text).toContain('这句话跨过两个镜头。')
    expect(wrapper.get('[data-testid="p8-source-bible-preflight"]').text()).toContain('CURRENT · rev 4')
    expect(wrapper.get('[data-testid="p8-source-bible-preflight"]').text()).toContain('P8 前置已就绪')
    const dialogueLines = wrapper.findAll('.dialogue-line')
    expect(dialogueLines).toHaveLength(2)
    expect(dialogueLines[0]?.text()).toContain('未命名女性A')
    expect(dialogueLines[0]?.text()).toContain('对白')
    expect(dialogueLines[1]?.text()).toContain('未命名女性A')
    expect(dialogueLines[1]?.text()).toContain('画外对白')

    const thumbnail = wrapper.findAll('.shot-media-button img')[0]
    expect(thumbnail?.attributes('src')).toBe('/api/v3/projects/project-p8/episodes/episode-1/shot-boundary/shots/shot-anchor-1/thumbnail')
    wrapper.unmount()
  })

  it('shows an explicit unconfirmed speaker instead of guessing from visible characters', async () => {
    const noSpeaker = structuredClone(breakdown)
    const line = noSpeaker.content?.episodes[0]?.shots[0]?.dialogue[0]
    if (line) line.speaker = null
    vi.mocked(shotApi.getShotBreakdown).mockResolvedValue(noSpeaker)

    const wrapper = await mountPanel()
    expect(wrapper.findAll('.dialogue-line')[0]?.text()).toContain('说话人未确认')
    wrapper.unmount()
  })

  it('keeps initial loading read-only and starts the heavy job only after explicit click', async () => {
    const wrapper = await mountPanel()

    expect(shotApi.startShotBreakdown).not.toHaveBeenCalled()
    vi.mocked(shotApi.startShotBreakdown).mockResolvedValue({
      id: 'task-p8-new',
      project_id: 'project-p8',
      task_name: '带 Source Bible 的逐镜精细拉片',
      progress_percent: 0,
      status: 'queued',
      last_error: null,
      attempt: 0,
      max_attempts: 3,
      can_retry: false,
      can_cancel: true,
      can_resume: false,
      created_at: '2026-09-09T00:00:00Z',
      started_at: null,
      finished_at: null,
    })

    const runButton = wrapper.get('.primary-action')
    expect(runButton.text()).toContain('重新分析')
    expect(runButton.attributes('disabled')).toBeUndefined()
    await runButton.trigger('click')
    await flushPromises()

    expect(shotApi.startShotBreakdown).toHaveBeenCalledTimes(1)
    expect(shotApi.startShotBreakdown).toHaveBeenCalledWith('project-p8', expect.stringContaining('p8-shot-breakdown-'))
    wrapper.unmount()
  })

  it('blocks P8 and explains the P7 recovery path when SOURCE_BIBLE is NOT_BUILT', async () => {
    const wrapper = await mountPanel({
      project_id: 'project-p8',
      status: 'NOT_BUILT',
      artifact_id: null,
      revision: null,
      input_fingerprint: null,
      content: null,
      provenance: null,
      story_skeleton_artifact_id: null,
      rhythm_skeleton_artifact_id: null,
    })

    const preflight = wrapper.get('[data-testid="p8-source-bible-preflight"]')
    expect(preflight.text()).toContain('NOT_BUILT')
    expect(preflight.text()).toContain('请先在上方「源作概览分析」')
    expect(wrapper.get('.dependency-alert').text()).toContain('暂不可运行')

    const runButton = wrapper.get('.primary-action')
    expect(runButton.attributes('disabled')).toBeDefined()
    await runButton.trigger('click')
    await flushPromises()
    expect(shotApi.startShotBreakdown).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('distinguishes a STALE P7 revision from a never-built SOURCE_BIBLE', async () => {
    const wrapper = await mountPanel({
      ...currentSourceBible,
      status: 'STALE',
      artifact_id: 'source-bible-stale',
      revision: 3,
      input_fingerprint: 'source-bible-stale-fingerprint',
      story_skeleton_artifact_id: null,
      rhythm_skeleton_artifact_id: null,
    })

    const preflight = wrapper.get('[data-testid="p8-source-bible-preflight"]')
    expect(preflight.text()).toContain('STALE · rev 3')
    expect(preflight.text()).toContain('已失效')
    expect(preflight.text()).toContain('重新运行整集原片理解')
    wrapper.unmount()
  })

  it('opens the exact P5 Reference Clip route for local shot inspection', async () => {
    const wrapper = await mountPanel()
    const clipButton = wrapper.findAll('.clip-button')[0]
    await clipButton?.trigger('click')

    const video = wrapper.get('.preview-dialog video')
    expect(video.attributes('src')).toBe('/api/v3/projects/project-p8/episodes/episode-1/shot-boundary/shots/shot-anchor-1/reference-clip')
    expect(wrapper.get('.preview-dialog').text()).toContain('源片段用于当前镜头的局部核对')
    wrapper.unmount()
  })
})
