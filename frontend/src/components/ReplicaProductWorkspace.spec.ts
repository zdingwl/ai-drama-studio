import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as projectApi from '@/features/projects/api'
import * as p14Api from '@/features/projects/p14'
import * as productionApi from '@/features/projects/production'
import * as replicaProductApi from '@/features/projects/replicaProduct'
import * as targetAssetsApi from '@/features/projects/targetAssets'
import * as targetBibleApi from '@/features/projects/targetBible'
import * as targetScriptApi from '@/features/projects/targetScript'
import * as baseApi from '@/lib/api'

import ReplicaProductWorkspace from './ReplicaProductWorkspace.vue'

vi.mock('@/features/projects/api', () => ({ getProject: vi.fn() }))
vi.mock('@/features/projects/p14', () => ({
  getTargetAudio: vi.fn(),
  getTimingPlan: vi.fn(),
  listAudioCandidates: vi.fn(),
  listTimingCandidates: vi.fn(),
  retakeTargetAudio: vi.fn(),
  reviewAudioCandidate: vi.fn(),
  reviewTimingCandidate: vi.fn(),
  startTargetAudio: vi.fn(),
  startTimingPlan: vi.fn(),
}))
vi.mock('@/features/projects/production', () => ({
  getFinalOutput: vi.fn(),
  listGenerationCandidates: vi.fn(),
  listPostCandidates: vi.fn(),
  reviewGeneration: vi.fn(),
  reviewPost: vi.fn(),
}))
vi.mock('@/features/projects/replicaProduct', () => ({
  getReplicaWorkflow: vi.fn(),
  startReplicaAdaptation: vi.fn(),
  startReplicaFinalOutput: vi.fn(),
  startReplicaGeneration: vi.fn(),
}))
vi.mock('@/features/projects/targetAssets', () => ({
  acceptReplicaTargetAssets: vi.fn(),
  listReplicaTargetAssetCandidates: vi.fn(),
  rejectReplicaTargetAssets: vi.fn(),
}))
vi.mock('@/features/projects/targetBible', () => ({ getReplicaTargetBible: vi.fn() }))
vi.mock('@/features/projects/targetScript', () => ({
  getReplicaTargetScript: vi.fn(),
  startReplicaTargetScriptTimingRewrite: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ apiRequest: vi.fn() }))

const project = {
  id: 'project-1',
  name: 'Replica product',
  project_type: 'REPLICA' as const,
  source_language: 'zh-CN',
  target_language: 'en-US',
  target_region: 'US',
  scene_strategy: 'KEEP' as const,
  audio_policy: 'REGENERATE_AUDIO' as const,
  visual_style: null,
  source_understanding_provider: 'DOUBAO_SEED_2_1_PRO_API' as const,
  status: 'ACTIVE' as const,
  workflow_revision: 1,
  created_at: '2026-09-13T00:00:00Z',
  updated_at: '2026-09-13T00:00:00Z',
}

const workflow = {
  project_id: 'project-1',
  next_action: 'GENERATE_ADAPTATION' as const,
  headline: '生成改编方案',
  description: '系统会自动完成目标设定、对白改写和视觉方案。',
  progress_percent: 30,
  active_task: null,
  last_error: null,
  steps: [
    { key: 'source', title: '原片', status: 'COMPLETE' as const, summary: '上传、解析并查看原片剧本与分镜' },
    { key: 'adaptation', title: '改编设定', status: 'READY' as const, summary: '目标人物、对白、视觉与配音' },
    { key: 'production', title: '生成成片', status: 'WAITING' as const, summary: '生成视频、检查画面并完成后期' },
  ],
  pending: {
    target_assets_candidate_id: null,
    target_audio_candidate_id: null,
    timing_candidate_id: null,
    video_candidate_id: null,
    final_candidate_id: null,
    timing_overflow_count: 0,
  },
}

async function mountWorkspace() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: { template: '<div />' } }],
  })
  await router.push('/projects/project-1')
  await router.isReady()
  const wrapper = mount(ReplicaProductWorkspace, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(projectApi.getProject).mockResolvedValue(project)
  vi.mocked(replicaProductApi.getReplicaWorkflow).mockResolvedValue(workflow)
  vi.mocked(targetBibleApi.getReplicaTargetBible).mockResolvedValue({
    project_id: 'project-1',
    status: 'NOT_BUILT',
    source_snapshot_artifact_id: null,
    source_snapshot_revision: null,
    adaptation_plan: { status: 'NOT_BUILT', artifact_id: null, revision: null, input_fingerprint: null, content: null },
    target_bible: { status: 'NOT_BUILT', artifact_id: null, revision: null, input_fingerprint: null, content: null },
  })
  vi.mocked(targetScriptApi.getReplicaTargetScript).mockResolvedValue({
    project_id: 'project-1',
    status: 'NOT_BUILT',
    artifact_id: null,
    revision: null,
    input_fingerprint: null,
    content: null,
  })
  vi.mocked(targetAssetsApi.listReplicaTargetAssetCandidates).mockResolvedValue([])
  vi.mocked(p14Api.getTargetAudio).mockResolvedValue({ status: 'NOT_BUILT', artifact_id: null, content: null })
  vi.mocked(p14Api.listAudioCandidates).mockResolvedValue([])
  vi.mocked(p14Api.getTimingPlan).mockResolvedValue({ status: 'NOT_BUILT', artifact_id: null, content: null })
  vi.mocked(p14Api.listTimingCandidates).mockResolvedValue([])
  vi.mocked(productionApi.listGenerationCandidates).mockResolvedValue([])
  vi.mocked(productionApi.listPostCandidates).mockResolvedValue([])
  vi.mocked(productionApi.getFinalOutput).mockResolvedValue({ status: 'NOT_BUILT', artifact_id: null, content: null })
  vi.mocked(replicaProductApi.startReplicaAdaptation).mockResolvedValue({
    id: 'task-1', project_id: 'project-1', task_name: '生成改编方案', progress_percent: 0, status: 'queued', last_error: null,
    attempt: 0, max_attempts: 3, can_retry: false, can_cancel: true, can_resume: false, created_at: '', started_at: null, finished_at: null,
  })
})

describe('ReplicaProductWorkspace', () => {
  it('loads read-only state and exposes only the single next product action', async () => {
    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('从原片到成片，只做三步')
    expect(wrapper.text()).toContain('现在只需要做这一件事')
    expect(wrapper.text()).toContain('生成改编方案')
    expect(wrapper.findAll('button').some((button) => button.text() === '生成改编方案')).toBe(true)
    expect(replicaProductApi.startReplicaAdaptation).not.toHaveBeenCalled()
    expect(replicaProductApi.startReplicaGeneration).not.toHaveBeenCalled()
    expect(replicaProductApi.startReplicaFinalOutput).not.toHaveBeenCalled()
    expect(baseApi.apiRequest).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('starts the product pipeline only after the user clicks the visible action', async () => {
    const wrapper = await mountWorkspace()
    const action = wrapper.findAll('button').find((button) => button.text() === '生成改编方案')
    expect(action).toBeTruthy()

    await action!.trigger('click')
    await flushPromises()

    expect(replicaProductApi.startReplicaAdaptation).toHaveBeenCalledTimes(1)
    expect(replicaProductApi.startReplicaAdaptation).toHaveBeenCalledWith('project-1')
    wrapper.unmount()
  })
})
