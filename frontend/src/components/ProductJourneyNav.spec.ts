import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProductJourneyNav from './ProductJourneyNav.vue'
import { getProject } from '@/features/projects/api'

vi.mock('@/features/projects/api', () => ({ getProject: vi.fn() }))

async function mountNavigation(projectType = 'REPLICA') {
  vi.mocked(getProject).mockResolvedValue({ project_type: projectType } as never)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id/:workspace?', name: 'project-workspace', component: { template: '<div />' } }],
  })
  await router.push('/projects/project-1/source')
  await router.isReady()
  const wrapper = mount(ProductJourneyNav, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('ProductJourneyNav', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows the six unified production workspaces', async () => {
    const { wrapper } = await mountNavigation()
    expect(wrapper.findAll('button')).toHaveLength(6)
    for (const label of ['原作', '剧本', '资产', '分镜', '生成', '成片']) expect(wrapper.text()).toContain(label)
  })

  it('navigates between real workspace routes', async () => {
    const { wrapper, router } = await mountNavigation()
    await wrapper.findAll('button')[2].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/projects/project-1/assets')
  })

  it('hides video-production workspaces for script localization', async () => {
    const { wrapper } = await mountNavigation('SCRIPT_LOCALIZATION')
    expect(wrapper.findAll('button')).toHaveLength(2)
    expect(wrapper.text()).toContain('原作')
    expect(wrapper.text()).toContain('剧本')
    expect(wrapper.text()).not.toContain('资产')
  })
})
