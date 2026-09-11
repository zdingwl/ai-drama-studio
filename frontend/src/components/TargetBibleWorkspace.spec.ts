import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TargetBibleWorkspace from './TargetBibleWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as targetBibleApi from '@/features/projects/targetBible'
import type { ProjectRead, TaskRead } from '@/features/projects/types'
import type { ReplicaTargetBibleRead } from '@/features/projects/targetBible'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/targetBible', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/targetBible')>('@/features/projects/targetBible')
  return {
    ...actual,
    getReplicaTargetBible: vi.fn(),
    startReplicaTargetBible: vi.fn(),
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

const currentResult: ReplicaTargetBibleRead = {
  project_id: 'project-1',
  status: 'CURRENT',
  source_snapshot_artifact_id: 'snapshot-1',
  source_snapshot_revision: 1,
  adaptation_plan: {
    status: 'CURRENT',
    artifact_id: 'plan-1',
    revision: 1,
    input_fingerprint: 'a'.repeat(64),
    content: {
      schema_version: '1.0',
      title: '复刻本土化方案',
      target_language: 'en-US',
      target_region: 'US',
      source_snapshot_artifact_id: 'snapshot-1',
      preservation_locks: [
        {
          lock_id: 'lock-1',
          category: 'HOOK',
          source_summary: '邻居再次把货到付款包裹推给主角。',
          source_refs: ['ep-1@0-2000000'],
          constraint: '保持 Hook 的叙事功能、相对顺序和信息量。',
        },
        {
          lock_id: 'lock-2',
          category: 'SCENE_ORDER',
          source_summary: '0f19ea1a-ba91-4fa8-aa83-92d30f091801#S1:p9-scn-9e06cbdda6c5d89e28d5 → 0f19ea1a-ba91-4fa8-aa83-92d30f091801#S2:p9-scn-bcf417cedf640a31e5f1',
          source_refs: ['0f19ea1a-ba91-4fa8-aa83-92d30f091801'],
          constraint: '保持 Source Scene Assignment 的连续顺序。',
        },
        {
          lock_id: 'lock-3',
          category: 'SHOT_LOGIC',
          source_summary: '保持 59 个 Source Shot 的顺序、镜头功能与反应链。',
          source_refs: ['source-shot-facts'],
          constraint: 'Target Bible 不创建、删除、合并或重排 Source Shot。',
        },
      ],
      localization_decisions: [],
      dialogue_localization_strategy: ['使用自然美式口语'],
      scene_strategy: 'MIXED',
      visual_style: '现实主义竖屏短剧',
    },
  },
  target_bible: {
    status: 'CURRENT',
    artifact_id: 'bible-1',
    revision: 1,
    input_fingerprint: 'b'.repeat(64),
    content: {
      schema_version: '1.0',
      title: '复刻目标设定',
      target_language: 'en-US',
      target_region: 'US',
      source_snapshot_artifact_id: 'snapshot-1',
      target_world: {
        setting_summary: '美国城市公寓社区中的邻里冲突。',
        cultural_context: '用本地邻里边界和快递语境表达原冲突。',
        social_context: '普通城市租住社区。',
        localization_principles: ['不改变故事因果', '不改变反转顺序'],
      },
      characters: [{
        target_character_id: 'tchr-1',
        source_character_id: 'chr-1',
        source_display_name: '徐然',
        display_name: 'Ryan',
        localized_identity: '年轻上班族邻居',
        appearance_direction: '日常都市休闲装',
        personality_constraints: ['保持克制反击的故事功能'],
        continuity_rules: ['发型与服装主色保持一致'],
      }],
      scenes: [{
        target_scene_id: 'tscn-1',
        source_scene_id: 'scn-1',
        source_display_name: '徐然家客厅',
        display_name: "Ryan's Living Room",
        localized_setting: '美国城市公寓客厅',
        visual_direction: '现实主义住宅内景',
        continuity_rules: ['门、沙发和入户动线保持连续'],
      }],
      props: [{
        target_prop_id: 'tprop-1',
        source_prop_id: 'prop-1',
        source_display_name: '货到付款包裹',
        display_name: 'COD Parcel',
        localized_form: '本地快递货到付款包裹',
        continuity_rules: ['包裹外观保持一致'],
      }],
      visual_style: '现实主义竖屏短剧',
      continuity_rules: ['人物核心造型跨场保持一致'],
      dialogue_style_rules: ['使用自然美式口语'],
      adaptation_summary: '故事与节奏完全保留，只替换人物身份、生活环境和文化表达。',
    },
  },
}

const notBuiltResult: ReplicaTargetBibleRead = {
  project_id: 'project-1',
  status: 'NOT_BUILT',
  source_snapshot_artifact_id: null,
  source_snapshot_revision: null,
  adaptation_plan: {
    status: 'NOT_BUILT',
    artifact_id: null,
    revision: null,
    input_fingerprint: null,
    content: null,
  },
  target_bible: {
    status: 'NOT_BUILT',
    artifact_id: null,
    revision: null,
    input_fingerprint: null,
    content: null,
  },
}

async function mountWorkspace(project: ProjectRead, targetResult: ReplicaTargetBibleRead) {
  vi.mocked(projectApi.getProject).mockResolvedValue(project)
  vi.mocked(targetBibleApi.getReplicaTargetBible).mockResolvedValue(targetResult)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', name: 'project-workspace', component: TargetBibleWorkspace }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(TargetBibleWorkspace, {
    attachTo: document.body,
    global: { plugins: [router] },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('TargetBibleWorkspace', () => {
  it('renders a compact product-facing overview without leaking internal scene ids', async () => {
    const wrapper = await mountWorkspace(replicaProject, currentResult)

    expect(wrapper.text()).toContain('目标设定')
    expect(wrapper.text()).toContain('美国')
    expect(wrapper.text()).toContain('English (US)')
    expect(wrapper.text()).toContain('混合本土化')
    expect(wrapper.text()).toContain('故事锁定')
    expect(wrapper.text()).toContain('镜头与场次锁定')
    expect(wrapper.text()).toContain('开场钩子')
    expect(wrapper.text()).toContain('场景连续顺序已锁定')
    expect(wrapper.text()).toContain('59 个镜头的顺序')
    expect(wrapper.text()).toContain('美国城市公寓社区')
    expect(targetBibleApi.startReplicaTargetBible).not.toHaveBeenCalled()

    const text = wrapper.text()
    for (const forbidden of [
      'P11',
      'Artifact',
      'fingerprint',
      'provenance',
      'ProviderJob',
      'Target Script',
      'TARGET_STORYBOARD',
      'TTS',
      'Generation',
      'p9-scn-',
      '0f19ea1a-ba91-4fa8-aa83-92d30f091801',
      'SCENE_ORDER',
      'SHOT_LOGIC',
    ]) {
      expect(text).not.toContain(forbidden)
    }
    wrapper.unmount()
  })

  it('separates people, scenes, props and continuity into product tabs', async () => {
    const wrapper = await mountWorkspace(replicaProject, currentResult)

    expect(wrapper.text()).not.toContain('Ryan')
    await wrapper.findAll('button').find((item) => item.text().startsWith('人物'))!.trigger('click')
    expect(wrapper.get('[data-testid="target-characters"]').text()).toContain('Ryan')
    expect(wrapper.text()).not.toContain("Ryan's Living Room")

    await wrapper.findAll('button').find((item) => item.text().startsWith('场景'))!.trigger('click')
    expect(wrapper.get('[data-testid="target-scenes"]').text()).toContain("Ryan's Living Room")

    await wrapper.findAll('button').find((item) => item.text().startsWith('道具'))!.trigger('click')
    expect(wrapper.get('[data-testid="target-props"]').text()).toContain('COD Parcel')

    await wrapper.findAll('button').find((item) => item.text() === '连续性')!.trigger('click')
    expect(wrapper.get('[data-testid="target-rules"]').text()).toContain('人物核心造型跨场保持一致')
    expect(wrapper.get('[data-testid="target-rules"]').text()).toContain('使用自然美式口语')
    wrapper.unmount()
  })

  it('only starts Target Bible from an explicit user action', async () => {
    vi.mocked(targetBibleApi.startReplicaTargetBible).mockResolvedValue({
      id: 'task-1',
      project_id: 'project-1',
      task_name: '生成复刻目标设定',
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
    vi.mocked(targetBibleApi.getReplicaTargetBible)
      .mockResolvedValueOnce(notBuiltResult)
      .mockResolvedValueOnce(currentResult)

    const wrapper = await mountWorkspace(replicaProject, notBuiltResult)
    expect(targetBibleApi.startReplicaTargetBible).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('尚未生成目标设定')

    const button = wrapper.findAll('button').find((item) => item.text() === '生成目标设定')
    expect(button).toBeTruthy()
    await button!.trigger('click')
    await flushPromises()

    expect(targetBibleApi.startReplicaTargetBible).toHaveBeenCalledTimes(1)
    expect(targetBibleApi.startReplicaTargetBible).toHaveBeenCalledWith('project-1', expect.any(String))
    expect(wrapper.text()).toContain('目标设定已就绪')
    expect(wrapper.text()).toContain('1 位人物')
    wrapper.unmount()
  })

  it('uses refresh wording for stale Target Bible', async () => {
    const stale: ReplicaTargetBibleRead = {
      ...currentResult,
      status: 'STALE',
      adaptation_plan: { ...currentResult.adaptation_plan, status: 'STALE' },
      target_bible: { ...currentResult.target_bible, status: 'STALE' },
    }
    const wrapper = await mountWorkspace(replicaProject, stale)
    expect(wrapper.text()).toContain('原片或目标配置已有更新，需要重新生成目标设定')
    expect(wrapper.findAll('button').some((item) => item.text() === '重新生成目标设定')).toBe(true)
    wrapper.unmount()
  })

  it('does not expose the Replica Target Bible workspace to REDRAW', async () => {
    const redrawProject: ProjectRead = {
      ...replicaProject,
      id: 'project-1',
      project_type: 'REDRAW',
    }
    const wrapper = await mountWorkspace(redrawProject, notBuiltResult)
    expect(wrapper.html()).toBe('<!--v-if-->')
    expect(targetBibleApi.getReplicaTargetBible).not.toHaveBeenCalled()
    expect(targetBibleApi.startReplicaTargetBible).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
