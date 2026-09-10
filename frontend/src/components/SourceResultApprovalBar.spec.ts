import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import SourceResultApprovalBar from './SourceResultApprovalBar.vue'
import * as projectApi from '@/features/projects/api'
import * as snapshotApi from '@/features/projects/sourceSnapshot'
import type { SourceVideoSnapshotRead } from '@/features/projects/sourceSnapshot'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
}))

vi.mock('@/features/projects/sourceSnapshot', async () => {
  const actual = await vi.importActual<typeof import('@/features/projects/sourceSnapshot')>('@/features/projects/sourceSnapshot')
  return {
    ...actual,
    getSourceVideoSnapshot: vi.fn(),
    finalizeSourceVideoSnapshot: vi.fn(),
  }
})

const notBuilt: SourceVideoSnapshotRead = {
  project_id: 'project-result',
  status: 'NOT_BUILT',
  artifact_id: null,
  revision: null,
  input_fingerprint: null,
  content: null,
  provenance: null,
}

const current: SourceVideoSnapshotRead = {
  project_id: 'project-result',
  status: 'CURRENT',
  artifact_id: 'snapshot-1',
  revision: 1,
  input_fingerprint: 'a'.repeat(64),
  content: null,
  provenance: null,
}

async function mountBar(value: SourceVideoSnapshotRead = notBuilt) {
  vi.mocked(projectApi.getProject).mockResolvedValue({ id: 'project-result', project_type: 'REPLICA' } as Awaited<ReturnType<typeof projectApi.getProject>>)
  vi.mocked(snapshotApi.getSourceVideoSnapshot).mockResolvedValue(value)

  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', component: SourceResultApprovalBar }],
  })
  await router.push('/projects/project-result')
  await router.isReady()
  const wrapper = mount(SourceResultApprovalBar, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

afterEach(() => vi.clearAllMocks())

describe('SourceResultApprovalBar', () => {
  it('loads read-only, stays passive when confirmed, and hides internal P10 vocabulary', async () => {
    const wrapper = await mountBar(current)

    expect(snapshotApi.finalizeSourceVideoSnapshot).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('当前原片分析结果已确认')
    expect(wrapper.text()).toContain('后续步骤会直接使用上面这套原片理解结果')
    expect(wrapper.find('[data-testid="source-result-confirm"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('P10')
    expect(wrapper.text()).not.toContain('SourceVideoSnapshot')
    expect(wrapper.text()).not.toContain('Frozen Inputs')
    expect(wrapper.text()).not.toContain('fingerprint')
    expect(wrapper.text()).not.toContain('provenance')
    wrapper.unmount()
  })

  it('confirms only after an explicit click when no result boundary exists yet', async () => {
    const wrapper = await mountBar()

    expect(wrapper.text()).toContain('当前原片分析结果尚未确认')
    expect(wrapper.get('[data-testid="source-result-confirm"]').text()).toBe('确认当前原片分析结果')
    expect(snapshotApi.finalizeSourceVideoSnapshot).not.toHaveBeenCalled()

    vi.mocked(snapshotApi.finalizeSourceVideoSnapshot).mockResolvedValue(current)
    await wrapper.get('[data-testid="source-result-confirm"]').trigger('click')
    await flushPromises()

    expect(snapshotApi.finalizeSourceVideoSnapshot).toHaveBeenCalledTimes(1)
    expect(snapshotApi.finalizeSourceVideoSnapshot).toHaveBeenCalledWith('project-result')
    expect(wrapper.text()).toContain('当前原片分析结果已确认')
    expect(wrapper.find('[data-testid="source-result-confirm"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('translates stale snapshot state into a user-facing re-confirm action', async () => {
    const wrapper = await mountBar({ ...current, status: 'STALE' })

    expect(wrapper.text()).toContain('原片分析结果已有更新，请重新确认')
    expect(wrapper.text()).toContain('上面的原片理解结果发生过修改')
    expect(wrapper.get('[data-testid="source-result-confirm"]').text()).toBe('重新确认当前结果')
    expect(snapshotApi.finalizeSourceVideoSnapshot).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
