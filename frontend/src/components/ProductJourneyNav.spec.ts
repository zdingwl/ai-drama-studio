import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ProductJourneyNav from './ProductJourneyNav.vue'
import { getProject } from '@/features/projects/api'

vi.mock('@/features/projects/api', () => ({ getProject: vi.fn() }))

async function mountNavigation(projectType = 'REPLICA', path = '/projects/project-1/source') {
  vi.mocked(getProject).mockResolvedValue({ project_type: projectType } as never)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id/:workspace?', name: 'project-workspace', component: { template: '<div />' } }],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(ProductJourneyNav, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('ProductJourneyNav', () => {
  beforeEach(() => vi.clearAllMocks())

  it('shows exactly the five Replica production stages', async () => {
    const { wrapper } = await mountNavigation()
    expect(wrapper.findAll('button')).toHaveLength(5)
    for (const label of ['分镜分析', '本土化分镜', '资产图', 'H3 提示词', '视频生成']) {
      expect(wrapper.text()).toContain(label)
    }
    for (const legacy of ['目标设定', '配音', '成片']) {
      expect(wrapper.text()).not.toContain(legacy)
    }
  })

  it('navigates through the real five-step workspace routes', async () => {
    const { wrapper, router } = await mountNavigation()
    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/projects/project-1/localize')

    await wrapper.findAll('button')[2].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/projects/project-1/assets')

    await wrapper.findAll('button')[3].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/projects/project-1/prompts')
  })

  it('redirects historical Replica routes to the new five-step equivalents', async () => {
    const { router } = await mountNavigation('REPLICA', '/projects/project-1/storyboard')
    expect(router.currentRoute.value.fullPath).toBe('/projects/project-1/prompts')
  })

  it('keeps the limited legacy navigation for script localization projects', async () => {
    const { wrapper } = await mountNavigation('SCRIPT_LOCALIZATION')
    expect(wrapper.findAll('button')).toHaveLength(2)
    expect(wrapper.text()).toContain('原作')
    expect(wrapper.text()).toContain('剧本')
    expect(wrapper.text()).not.toContain('资产')
  })
})
