import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'

import HomeView from './HomeView.vue'

describe('HomeView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('shows the V3 workspace baseline', async () => {
    const wrapper = mount(HomeView)
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('AI 短剧生产工作台')
    expect(wrapper.text()).toContain('前端骨架已就绪')
  })
})
