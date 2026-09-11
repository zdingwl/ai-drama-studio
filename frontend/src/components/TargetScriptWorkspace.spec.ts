import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TargetScriptWorkspace from './TargetScriptWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as targetScriptApi from '@/features/projects/targetScript'
import type { ProjectRead } from '@/features/projects/types'
import type { ReplicaTargetScriptRead } from '@/features/projects/targetScript'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
}))

vi.mock('@/features/projects/targetScript', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/targetScript')>('@/features/projects/targetScript')
  return {
    ...actual,
    getReplicaTargetScript: vi.fn(),
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

const notBuiltResult: ReplicaTargetScriptRead = {
  project_id: 'project-1',
  status: 'NOT_BUILT',
  artifact_id: null,
  revision: null,
  input_fingerprint: null,
  content: null,
}

const currentResult: ReplicaTargetScriptRead = {
  project_id: 'project-1',
  status: 'CURRENT',
  artifact_id: 'script-1',
  revision: 1,
  input_fingerprint: 'a'.repeat(64),
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

async function mountWorkspace(project: ProjectRead, result: ReplicaTargetScriptRead) {
  vi.mocked(projectApi.getProject).mockResolvedValue(project)
  vi.mocked(targetScriptApi.getReplicaTargetScript).mockResolvedValue(result)
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
  it('prepares a read-only UI and exposes no execution action before admission', async () => {
    const wrapper = await mountWorkspace(replicaProject, notBuiltResult)
    expect(wrapper.text()).toContain('目标剧本尚未开放')
    expect(wrapper.text()).toContain('目标剧本将在目标设定通过验收后开放')
    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(targetScriptApi.getReplicaTargetScript).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('renders Source → Translation → Localization → Final Target Dialogue as separate columns', async () => {
    const wrapper = await mountWorkspace(replicaProject, currentResult)
    expect(wrapper.text()).toContain('原对白')
    expect(wrapper.text()).toContain('你别替我做决定。')
    expect(wrapper.text()).toContain('直译')
    expect(wrapper.text()).toContain("Don't make decisions for me.")
    expect(wrapper.text()).toContain('本土化')
    expect(wrapper.text()).toContain("Don't decide that for me.")
    expect(wrapper.text()).toContain('最终对白')
    expect(wrapper.text()).toContain("Don't decide for me.")
    expect(wrapper.findAll('button')).toHaveLength(0)

    const text = wrapper.text()
    for (const forbidden of ['P12', 'Artifact', 'fingerprint', 'provenance', 'ProviderJob', 'TTS', 'Timing Plan', 'Generation']) {
      expect(text).not.toContain(forbidden)
    }
    wrapper.unmount()
  })

  it('does not expose the prepared workspace to REDRAW', async () => {
    const redrawProject: ProjectRead = { ...replicaProject, project_type: 'REDRAW' }
    const wrapper = await mountWorkspace(redrawProject, notBuiltResult)
    expect(wrapper.html()).toBe('<!--v-if-->')
    expect(targetScriptApi.getReplicaTargetScript).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
