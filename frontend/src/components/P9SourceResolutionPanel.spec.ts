import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import P9SourceResolutionPanel from './P9SourceResolutionPanel.vue'
import * as projectApi from '@/features/projects/api'
import * as shotApi from '@/features/projects/shotBreakdown'
import * as resolutionApi from '@/features/projects/sourceResolution'
import type { SourceResolutionRead } from '@/features/projects/sourceResolution'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/shotBreakdown', () => ({
  getShotBreakdown: vi.fn(),
}))

vi.mock('@/features/projects/sourceResolution', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/sourceResolution')>('@/features/projects/sourceResolution')
  return {
    ...actual,
    getSourceResolution: vi.fn(),
    listSourceResolutionRevisions: vi.fn(),
    startSourceResolution: vi.fn(),
    adjudicateSourceResolution: vi.fn(),
  }
})

const notBuilt: SourceResolutionRead = {
  project_id: 'project-p9',
  characters: { status: 'NOT_BUILT', artifact_id: null, revision: null, input_fingerprint: null, content: null, provenance: null },
  speakers: { status: 'NOT_BUILT', artifact_id: null, revision: null, input_fingerprint: null, content: null, provenance: null },
  scenes: { status: 'NOT_BUILT', artifact_id: null, revision: null, input_fingerprint: null, content: null, provenance: null },
  props: { status: 'NOT_BUILT', artifact_id: null, revision: null, input_fingerprint: null, content: null, provenance: null },
}

const current: SourceResolutionRead = {
  project_id: 'project-p9',
  characters: {
    status: 'CURRENT', artifact_id: 'chars-1', revision: 1, input_fingerprint: 'chars-fp', provenance: null,
    content: {
      schema_version: '1.0', title: '人物最终归一',
      entities: [{
        entity_id: 'character-stable-1', character_id: 'character-stable-1', display_name: '王桂香', aliases: [],
        source_candidate_ids: ['p7-char-1'], episode_ids: ['ep-1'], shot_anchor_ids: ['shot-1'], evidence_refs: [],
        confidence: 0.98, resolution_status: 'RESOLVED', notes: [],
      }],
      observations: [{ shot_anchor_id: 'shot-1', source_candidate_id: 'p7-char-1', character_id: 'character-stable-1', resolution_status: 'RESOLVED', reason: null }],
    },
  },
  speakers: {
    status: 'CURRENT', artifact_id: 'speakers-1', revision: 1, input_fingerprint: 'speakers-fp', provenance: null,
    content: {
      schema_version: '1.0', title: '说话人最终归因',
      entities: [{
        entity_id: 'speaker-stable-1', speaker_id: 'speaker-stable-1', display_name: 'Speaker A', aliases: [],
        source_candidate_ids: ['p7-char-1'], episode_ids: ['ep-1'], shot_anchor_ids: ['shot-1'], evidence_refs: [],
        confidence: 0.7, resolution_status: 'UNRESOLVED', notes: [], character_id: null,
        utterance_ids: ['utt-1'], source_candidate_character_ids: ['p7-char-1'],
      }],
      attributions: [{ episode_id: 'ep-1', utterance_id: 'utt-1', utterance_number: 1, start_us: 0, end_us: 500000, text: '你来了。', speaker_id: null, resolution_status: 'UNRESOLVED', reason: '音画证据不足' }],
    },
  },
  scenes: { status: 'CURRENT', artifact_id: 'scenes-1', revision: 1, input_fingerprint: 'scenes-fp', provenance: null, content: { schema_version: '1.0', title: '场景最终归一', entities: [], assignments: [] } },
  props: { status: 'CURRENT', artifact_id: 'props-1', revision: 1, input_fingerprint: 'props-fp', provenance: null, content: { schema_version: '1.0', title: '关键道具最终归一', entities: [], observations: [] } },
}

async function mountPanel(value: SourceResolutionRead = notBuilt, p8Status: 'CURRENT' | 'STALE' = 'CURRENT') {
  vi.mocked(projectApi.getProject).mockResolvedValue({ id: 'project-p9', project_type: 'REPLICA' } as Awaited<ReturnType<typeof projectApi.getProject>>)
  vi.mocked(projectApi.listProjectTasks).mockResolvedValue([])
  vi.mocked(shotApi.getShotBreakdown).mockResolvedValue({
    project_id: 'project-p9', status: p8Status, artifact_id: 'facts-1', revision: 6, input_fingerprint: 'facts-fp', content: null, provenance: null,
  })
  vi.mocked(resolutionApi.getSourceResolution).mockResolvedValue(value)
  vi.mocked(resolutionApi.listSourceResolutionRevisions).mockResolvedValue([])

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: P9SourceResolutionPanel }],
  })
  await router.push('/projects/project-p9')
  await router.isReady()
  const wrapper = mount(P9SourceResolutionPanel, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('P9SourceResolutionPanel', () => {
  it('keeps initial loading read-only and starts P9 only after the explicit button click', async () => {
    const wrapper = await mountPanel()
    expect(resolutionApi.startSourceResolution).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="p9-p8-preflight"]').text()).toContain('P9 前置已就绪')

    vi.mocked(resolutionApi.startSourceResolution).mockResolvedValue({
      id: 'task-p9', project_id: 'project-p9', task_name: 'Speaker / Character / Scene / Prop 最终归一',
      progress_percent: 0, status: 'queued', last_error: null, attempt: 0, max_attempts: 3,
      can_retry: false, can_cancel: true, can_resume: false, created_at: '2026-09-10T00:00:00Z', started_at: null, finished_at: null,
    })

    const runButton = wrapper.get('.workspace-actions .primary-action')
    expect(runButton.attributes('disabled')).toBeUndefined()
    await runButton.trigger('click')
    await flushPromises()

    expect(resolutionApi.startSourceResolution).toHaveBeenCalledTimes(1)
    expect(resolutionApi.startSourceResolution).toHaveBeenCalledWith('project-p9', expect.stringContaining('p9-source-resolution-'))
    wrapper.unmount()
  })

  it('blocks the heavy command when P8 is stale', async () => {
    const wrapper = await mountPanel(notBuilt, 'STALE')
    const runButton = wrapper.get('.workspace-actions .primary-action')
    expect(runButton.attributes('disabled')).toBeDefined()
    await runButton.trigger('click')
    await flushPromises()
    expect(resolutionApi.startSourceResolution).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="p9-p8-preflight"]').text()).toContain('不会通过 GET 隐式启动任务')
    wrapper.unmount()
  })

  it('renders Speaker and Character as separate identity layers and preserves unresolved state', async () => {
    const wrapper = await mountPanel(current)
    const text = wrapper.text()
    expect(text).toContain('人物身份')
    expect(text).toContain('王桂香')
    expect(text).toContain('说话人归因')
    expect(text).toContain('Speaker A')
    expect(text).toContain('未绑定 Character')
    expect(text).toContain('待裁决')
    expect(text).toContain('unknown / unresolved')
    wrapper.unmount()
  })
})
