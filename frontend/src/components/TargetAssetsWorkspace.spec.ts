import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import TargetAssetsWorkspace from './TargetAssetsWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as targetAssetsApi from '@/features/projects/targetAssets'
import * as targetBibleApi from '@/features/projects/targetBible'
import type { ReplicaTargetAssetsContent, ReplicaTargetAssetsRead, TargetAssetsCandidateRead } from '@/features/projects/targetAssets'
import type { ReplicaTargetBibleRead } from '@/features/projects/targetBible'
import type { ProjectRead, TaskRead } from '@/features/projects/types'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/targetBible', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/targetBible')>('@/features/projects/targetBible')
  return { ...actual, getReplicaTargetBible: vi.fn() }
})

vi.mock('@/features/projects/targetAssets', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/targetAssets')>('@/features/projects/targetAssets')
  return {
    ...actual,
    getReplicaTargetAssets: vi.fn(),
    listReplicaTargetAssetCandidates: vi.fn(),
    startReplicaTargetAssets: vi.fn(),
    regenerateReplicaTargetAssets: vi.fn(),
    acceptReplicaTargetAssets: vi.fn(),
    rejectReplicaTargetAssets: vi.fn(),
  }
})

const project = {
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
  target_bible: { status: 'NOT_BUILT', artifact_id: null, revision: null, input_fingerprint: null, content: null },
} as ReplicaTargetBibleRead

const content: ReplicaTargetAssetsContent = {
  schema_version: '1.0',
  title: '目标资产',
  target_bible_artifact_id: 'bible-1',
  target_language: 'en-US',
  target_region: 'US',
  visual_style: 'Naturalistic drama',
  characters: [{
    target_asset_id: 'tasset_chr_1',
    target_asset_revision: 1,
    asset_type: 'CHARACTER',
    target_entity_id: 'tchr-1',
    target_character_id: 'tchr-1',
    display_name: 'Alice',
    asset_fingerprint: 'c'.repeat(64),
    identity_direction: 'Young urban professional',
    demographic_direction: 'Late-20s contemporary American presentation',
    face_direction: 'Oval face with straight brows',
    hair_direction: 'Shoulder-length dark hair with stable side part',
    body_direction: 'Lean average-height build',
    wardrobe_baseline: 'Neutral work-casual baseline',
    signature_visual_features: ['straight brows', 'silver stud earrings'],
    continuity_constraints: ['Keep the same face identity'],
    generation_guidance: ['Stable facial geometry'],
    negative_constraints: ['No age drift'],
    reference_media: [],
  }],
  scenes: [{
    target_asset_id: 'tasset_scn_1',
    target_asset_revision: 1,
    asset_type: 'SCENE',
    target_entity_id: 'tscn-1',
    target_scene_id: 'tscn-1',
    display_name: 'Apartment Hallway',
    asset_fingerprint: 'd'.repeat(64),
    spatial_identity: 'US apartment corridor',
    layout: 'Long straight corridor with unit doors on both sides',
    architecture_style: 'Contemporary mid-rise apartment',
    interior_exterior_style: 'Interior common corridor',
    materials_palette: ['off-white drywall', 'dark wood doors'],
    fixed_landmarks: ['elevator lobby', 'fire alarm'],
    lighting_baseline: 'Warm-neutral practical ceiling lights',
    time_of_day_baseline: 'Interior baseline',
    continuity_constraints: ['Keep landmark positions fixed'],
    generation_guidance: ['Preserve corridor vanishing point'],
    negative_constraints: ['No topology changes'],
    reference_media: [],
  }],
  props: [{
    target_asset_id: 'tasset_prop_1',
    target_asset_revision: 1,
    asset_type: 'PROP',
    target_entity_id: 'tprop-1',
    target_prop_id: 'tprop-1',
    display_name: 'Blue Rose Bouquet',
    asset_fingerprint: 'e'.repeat(64),
    functional_identity: 'Blue bouquet with the same story function',
    visual_form: 'Compact blue rose bouquet in matte wrap',
    materials: ['rose petals', 'matte paper'],
    color_palette: ['royal blue', 'charcoal'],
    scale_reference: 'Forearm length',
    signature_visual_features: ['blue roses', 'charcoal wrap'],
    continuity_constraints: ['Keep wrapping geometry stable'],
    generation_guidance: ['Stable bouquet silhouette'],
    negative_constraints: ['No red roses'],
    reference_media: [],
  }],
}

const notBuilt: ReplicaTargetAssetsRead = {
  project_id: 'project-1',
  status: 'NOT_BUILT',
  artifact_id: null,
  revision: null,
  input_fingerprint: null,
  content: null,
}

const currentAssets: ReplicaTargetAssetsRead = {
  project_id: 'project-1',
  status: 'CURRENT',
  artifact_id: 'assets-1',
  revision: 1,
  input_fingerprint: 'f'.repeat(64),
  content,
}

const pending: TargetAssetsCandidateRead = {
  id: 'candidate-1',
  project_id: 'project-1',
  target_bible_artifact_id: 'bible-1',
  base_target_assets_artifact_id: null,
  generated_by_task_id: 'task-1',
  generation_sequence: 1,
  input_fingerprint: '1'.repeat(64),
  schema_version: '1.0',
  review_status: 'NEEDS_REVIEW',
  review_reason: null,
  reviewed_at: null,
  created_at: '2026-09-11T00:00:00Z',
  content,
}

async function mountWorkspace(
  bible: ReplicaTargetBibleRead = currentBible,
  assets: ReplicaTargetAssetsRead = notBuilt,
  candidates: TargetAssetsCandidateRead[] = [],
  selectedProject: ProjectRead = project,
) {
  vi.mocked(projectApi.getProject).mockResolvedValue(selectedProject)
  vi.mocked(targetBibleApi.getReplicaTargetBible).mockResolvedValue(bible)
  vi.mocked(targetAssetsApi.getReplicaTargetAssets).mockResolvedValue(assets)
  vi.mocked(targetAssetsApi.listReplicaTargetAssetCandidates).mockResolvedValue(candidates)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', name: 'project-workspace', component: TargetAssetsWorkspace }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(TargetAssetsWorkspace, { attachTo: document.body, global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('TargetAssetsWorkspace', () => {
  it('loads via GET only and exposes an explicit generate action only after Target Bible is current', async () => {
    const wrapper = await mountWorkspace()
    expect(targetAssetsApi.startReplicaTargetAssets).not.toHaveBeenCalled()
    expect(targetAssetsApi.regenerateReplicaTargetAssets).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('可以生成目标资产候选')
    expect(wrapper.findAll('button').some((item) => item.text() === '生成目标资产')).toBe(true)
    expect(wrapper.text()).toContain('页面刷新不会自动调用')
    wrapper.unmount()
  })

  it('does not expose generation while Target Bible is not current', async () => {
    const wrapper = await mountWorkspace(notBuiltBible)
    expect(wrapper.text()).toContain('等待当前有效的目标设定')
    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(targetAssetsApi.startReplicaTargetAssets).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows a generated candidate for review without treating it as formal current assets', async () => {
    const wrapper = await mountWorkspace(currentBible, notBuilt, [pending])
    expect(wrapper.text()).toContain('候选版本 1 · 待人工确认')
    expect(wrapper.text()).toContain('Alice')
    expect(wrapper.text()).toContain('Apartment Hallway')
    expect(wrapper.text()).toContain('Blue Rose Bouquet')
    expect(wrapper.text()).toContain('确认并作为正式资产')
    expect(wrapper.text()).not.toContain('正式目标资产已确认')
    wrapper.unmount()
  })

  it('accepts a candidate only after an explicit reason and uses optimistic review fields', async () => {
    vi.mocked(targetAssetsApi.acceptReplicaTargetAssets).mockResolvedValue(currentAssets)
    vi.mocked(targetAssetsApi.getReplicaTargetAssets)
      .mockResolvedValueOnce(notBuilt)
      .mockResolvedValueOnce(currentAssets)
    vi.mocked(targetAssetsApi.listReplicaTargetAssetCandidates)
      .mockResolvedValueOnce([pending])
      .mockResolvedValueOnce([{ ...pending, review_status: 'ACCEPTED', review_reason: 'Looks consistent' }])

    const wrapper = await mountWorkspace(currentBible, notBuilt, [pending])
    const textarea = wrapper.find('textarea')
    await textarea.setValue('Looks consistent across character, scene and prop identity')
    const button = wrapper.findAll('button').find((item) => item.text() === '确认并作为正式资产')
    expect(button).toBeTruthy()
    await button!.trigger('click')
    await flushPromises()

    expect(targetAssetsApi.acceptReplicaTargetAssets).toHaveBeenCalledWith('project-1', 'candidate-1', {
      expected_target_bible_artifact_id: 'bible-1',
      expected_generation_sequence: 1,
      reason: 'Looks consistent across character, scene and prop identity',
    })
    expect(wrapper.text()).toContain('正式目标资产已确认')
    wrapper.unmount()
  })

  it('offers explicit regeneration for formal assets rather than mutating them on load', async () => {
    const wrapper = await mountWorkspace(currentBible, currentAssets, [])
    expect(targetAssetsApi.regenerateReplicaTargetAssets).not.toHaveBeenCalled()
    expect(wrapper.findAll('button').some((item) => item.text() === '重新生成候选')).toBe(true)
    expect(wrapper.text()).toContain('rev 1')
    wrapper.unmount()
  })

  it('does not render the P13 workspace for REDRAW', async () => {
    const redraw: ProjectRead = { ...project, project_type: 'REDRAW' }
    const wrapper = await mountWorkspace(currentBible, notBuilt, [], redraw)
    expect(wrapper.html()).toBe('<!--v-if-->')
    expect(targetBibleApi.getReplicaTargetBible).not.toHaveBeenCalled()
    expect(targetAssetsApi.getReplicaTargetAssets).not.toHaveBeenCalled()
    expect(targetAssetsApi.startReplicaTargetAssets).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
