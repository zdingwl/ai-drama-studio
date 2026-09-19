import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import H3PromptWorkspace from './H3PromptWorkspace.vue'
import * as projectApi from '@/features/projects/api'
import * as replicaApi from '@/features/projects/replicaFiveStep'

vi.mock('@/features/projects/api', () => ({
  listProjectTasks: vi.fn(),
}))

vi.mock('@/features/projects/replicaFiveStep', () => ({
  getH3Prompts: vi.fn(),
  startH3Prompts: vi.fn(),
}))

async function mountWorkspace() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: { template: '<main />' } }],
  })
  await router.push('/projects/project-1?episode=episode-1&ep=1')
  await router.isReady()
  const wrapper = mount(H3PromptWorkspace, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('H3PromptWorkspace stale regeneration', () => {
  it('does not let validation issues from a stale H3 artifact block rebuilding', async () => {
    vi.mocked(projectApi.listProjectTasks).mockResolvedValue([])
    vi.mocked(replicaApi.getH3Prompts).mockResolvedValue({
      project_id: 'project-1',
      status: 'STALE',
      artifact_id: 'old-h3',
      revision: 2,
      validation_issues: [
        { code: 'DIALOGUE_TOO_LONG', generation_segment_id: 'old-segment-1', message: '旧对白窗过短' },
        { code: 'REFERENCE_INCOMPLETE', generation_segment_id: 'old-segment-2', message: '旧参考图不完整' },
      ],
      content: {
        target_storyboard_artifact_id: 'old-storyboard',
        target_assets_artifact_id: 'old-assets',
        segments: [],
      },
      provenance: null,
    })
    vi.mocked(replicaApi.startH3Prompts).mockResolvedValue({
      id: 'new-task',
      project_id: 'project-1',
      task_type: 'replica.h3-prompts',
      task_name: '生成 H3 提示词',
      episode_id: 'episode-1',
      progress_percent: 0,
      status: 'queued',
      last_error: null,
      attempt: 0,
      max_attempts: 3,
      can_retry: false,
      can_cancel: true,
      can_resume: false,
      created_at: '2026-09-19T13:30:00Z',
      started_at: null,
      finished_at: null,
    })

    const wrapper = await mountWorkspace()

    expect(wrapper.text()).toContain('上一版 H3 已因上游更新而失效')
    expect(wrapper.text()).toContain('可以直接生成新版 H3 提示词')
    expect(wrapper.text()).not.toContain('个镜头段需要先修订')

    const generate = wrapper.findAll('button').find(button => button.text() === '生成 H3 提示词')
    expect(generate).toBeTruthy()
    expect(generate?.attributes('disabled')).toBeUndefined()

    await generate!.trigger('click')
    await flushPromises()

    expect(replicaApi.startH3Prompts).toHaveBeenCalledWith('project-1', 'episode-1')
    wrapper.unmount()
  })
})
