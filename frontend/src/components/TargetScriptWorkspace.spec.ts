import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TargetScriptWorkspace from './TargetScriptWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as targetBibleApi from '@/features/projects/targetBible'
import * as targetScriptApi from '@/features/projects/targetScript'
import type { ReplicaTargetBibleRead } from '@/features/projects/targetBible'
import type { ReplicaTargetScriptRead } from '@/features/projects/targetScript'
import type { ProjectRead, TaskRead } from '@/features/projects/types'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/targetBible', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/targetBible')>('@/features/projects/targetBible')
  return { ...actual, getReplicaTargetBible: vi.fn() }
})

vi.mock('@/features/projects/targetScript', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/targetScript')>('@/features/projects/targetScript')
  return {
    ...actual,
    getReplicaTargetScript: vi.fn(),
    startReplicaTargetScript: vi.fn(),
  }
})

const replicaProject = {
  id: 'project-1',
  name: 'Replica demo',
  project_type: 'REPLICA',
  source_language: 'zh-CN',
  target_language: 'en-US',
  target_region: 'US',
  scene_strategy: 'MIXED',
  audio_policy: 'REGENERATE_AUDIO',
  visual_style: null,
  source_understanding_provider: 'DOUBAO_SEED_2_1_PRO_API',
  status: 'ACTIVE',
  workflow_revision: 1,
  created_at: '2026-09-11T00:00:00Z',
  updated_at: '2026-09-11T00:00:00Z',
} satisfies ProjectRead

const currentBible = {
  project_id: 'project-1',
  status: 'CURRENT',
  source_snapshot_artifact_id: 'snapshot-1',
  source_snapshot_revision: 1,
  adaptation_plan: { status: 'CURRENT', artifact_id: 'plan-1', revision: 1, input_fingerprint: 'a'.repeat(64), content: null },
  target_bible: { status: 'CURRENT', artifact_id: 'bible-1', revision: 1, input_fingerprint: 'b'.repeat(64), content: null },
} as ReplicaTargetBibleRead

const notBuiltBible = {
  ...currentBible,
  status: 'NOT_BUILT',
  source_snapshot_artifact_id: null,
  source_snapshot_revision: null,
} as ReplicaTargetBibleRead

const notBuiltScript: ReplicaTargetScriptRead = {
  project_id: 'project-1',
  status: 'NOT_BUILT',
  artifact_id: null,
  revision: null,
  input_fingerprint: null,
  content: null,
}

const currentScript: ReplicaTargetScriptRead = {
  project_id: 'project-1',
  status: 'CURRENT',
  artifact_id: 'script-1',
  revision: 1,
  input_fingerprint: 'c'.repeat(64),
  content: {
    schema_version: '1.0',
    title: '目标剧本与对白',
    target_language: 'en-US',
    target_region: 'US',
    source_snapshot_artifact_id: 'snapshot-1',
    adaptation_plan_artifact_id: 'plan-1',
    target_bible_artifact_id: 'bible-1',
    episodes: [{
      episode_id: 'ep-1',
      episode_order: 1,
      dialogue: [{
        utterance_id: 'utt-1',
        utterance_number: 1,
        source_start_us: 1_000_000,
        source_end_us: 2_000_000,
        source_text: '你别替我做决定。',
        source_language: 'zh-CN',
        target_character_id: 'tchr-1',
        translation_text: "Don't make decisions for me.",
        localization_text: "Don't decide that for me.",
        final_target_dialogue: "Don't decide for me.",
        localization_notes: ['自然美式口语'],
      }],
    }],
  },
}

async function mountWorkspace(
  project: ProjectRead,
  bible: ReplicaTargetBibleRead,
  script: ReplicaTargetScriptRead,
) {
  vi.mocked(projectApi.getProject).mockResolvedValue(project)
  vi.mocked(targetBibleApi.getReplicaTargetBible).mockResolvedValue(bible)
  vi.mocked(targetScriptApi.getReplicaTargetScript).mockResolvedValue(script)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', name: 'project-workspace', component: TargetScriptWorkspace }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(TargetScriptWorkspace, {
    attachTo: document.body,
    global: { plugins: [router] },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('TargetScriptWorkspace', () => {
  it('loads with GET only and offers an explicit P12 action after P11 is CURRENT', async () => {
    const wrapper = await mountWorkspace(replicaProject, currentBible, notBuiltScript)

    expect(targetScriptApi.startReplicaTargetScript).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('可以生成目标剧本')
    expect(wrapper.findAll('button').some((item) => item.text() === '生成目标剧本')).toBe(true)
    expect(wrapper.text()).toContain('页面刷新不会自动启动生成')
    wrapper.unmount()
  })

  it('starts P12 only after the user clicks generate', async () => {
    vi.mocked(targetScriptApi.startReplicaTargetScript).mockResolvedValue({
      id: 'task-1',
      project_id: 'project-1',
      task_name: '生成目标剧本与对白',
      progress_percent: 100,
      status: 'succeeded',
      last_error: null,
      attempt: 1,
      max_attempts: 3,
      can_retry: false,
      can_cancel: false,
      can_resume: false,
      created_at: '2026-09-11T00:00:00Z',
      started_at: '2026-09-11T00:00:01Z',
      finished_at: '2026-09-11T00:00:02Z',
    } satisfies TaskRead)
    vi.mocked(targetScriptApi.getReplicaTargetScript)
      .mockResolvedValueOnce(notBuiltScript)
      .mockResolvedValueOnce(currentScript)

    const wrapper = await mountWorkspace(replicaProject, currentBible, notBuiltScript)
    const button = wrapper.findAll('button').find((item) => item.text() === '生成目标剧本')
    expect(button).toBeTruthy()
    await button!.trigger('click')
    await flushPromises()

    expect(targetScriptApi.startReplicaTargetScript).toHaveBeenCalledTimes(1)
    expect(targetScriptApi.startReplicaTargetScript).toHaveBeenCalledWith('project-1', expect.any(String))
    expect(wrapper.text()).toContain('目标剧本已就绪')
    expect(wrapper.text()).toContain("Don't decide for me.")
    wrapper.unmount()
  })

  it('keeps P12 blocked in the product UI when P11 is not CURRENT', async () => {
    const wrapper = await mountWorkspace(replicaProject, notBuiltBible, notBuiltScript)
    expect(wrapper.text()).toContain('等待当前有效的目标设定')
    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(targetScriptApi.startReplicaTargetScript).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('renders Source → Translation → Localization → Final Target Dialogue without engineering vocabulary', async () => {
    const wrapper = await mountWorkspace(replicaProject, currentBible, currentScript)
    expect(wrapper.text()).toContain('原对白')
    expect(wrapper.text()).toContain('你别替我做决定。')
    expect(wrapper.text()).toContain('直译')
    expect(wrapper.text()).toContain("Don't make decisions for me.")
    expect(wrapper.text()).toContain('本土化')
    expect(wrapper.text()).toContain("Don't decide that for me.")
    expect(wrapper.text()).toContain('最终对白')
    expect(wrapper.text()).toContain("Don't decide for me.")

    const text = wrapper.text()
    for (const forbidden of ['P12', 'Artifact', 'fingerprint', 'provenance', 'ProviderJob', 'TTS', 'Timing Plan', 'Generation']) {
      expect(text).not.toContain(forbidden)
    }
    wrapper.unmount()
  })

  it('does not expose the Target Script workspace to REDRAW', async () => {
    const redrawProject: ProjectRead = { ...replicaProject, project_type: 'REDRAW' }
    const wrapper = await mountWorkspace(redrawProject, notBuiltBible, notBuiltScript)
    expect(wrapper.html()).toBe('<!--v-if-->')
    expect(targetBibleApi.getReplicaTargetBible).not.toHaveBeenCalled()
    expect(targetScriptApi.getReplicaTargetScript).not.toHaveBeenCalled()
    expect(targetScriptApi.startReplicaTargetScript).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
