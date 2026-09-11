import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'

import App from './App.vue'

const technicalPanels = [
  'p6-panel',
  'p7-panel',
  'p8-panel',
  'p9-panel',
  'source-result-approval',
]

async function mountApp(path: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{
      path: '/projects/:id',
      name: 'project-workspace',
      component: { template: '<main data-testid="project-route" />' },
    }],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(App, {
    global: {
      plugins: [router],
      stubs: {
        AppShell: { template: '<div><slot /></div>' },
        SourceScriptStoryboardWorkspace: { template: '<section data-testid="source-workspace" />' },
        TargetBibleWorkspace: { template: '<section data-testid="target-bible-workspace" />' },
        TargetScriptWorkspace: { template: '<section data-testid="target-script-workspace" />' },
        TargetAssetsWorkspace: { template: '<section data-testid="target-assets-workspace" />' },
        P6AcceptancePanel: { template: '<section data-testid="p6-panel" />' },
        P7SourceUnderstandingWorkspace: { template: '<section data-testid="p7-panel" />' },
        P8ShotBreakdownPanel: { template: '<section data-testid="p8-panel" />' },
        P9SourceResolutionPanel: { template: '<section data-testid="p9-panel" />' },
        SourceResultApprovalBar: { template: '<section data-testid="source-result-approval" />' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

describe('App source workspace product mode', () => {
  it('shows the product workspaces without engineering panels on an ordinary project page', async () => {
    const wrapper = await mountApp('/projects/project-1')

    expect(wrapper.get('[data-testid="source-workspace"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="target-bible-workspace"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="target-script-workspace"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="target-assets-workspace"]')).toBeTruthy()
    expect(wrapper.find('.product-mode').exists()).toBe(true)
    for (const panel of technicalPanels) {
      expect(wrapper.find(`[data-testid="${panel}"]`).exists()).toBe(false)
    }
    wrapper.unmount()
  })

  it('keeps the engineering diagnostic panels available behind debug=1', async () => {
    const wrapper = await mountApp('/projects/project-1?debug=1')

    expect(wrapper.get('[data-testid="source-workspace"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="target-bible-workspace"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="target-script-workspace"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="target-assets-workspace"]')).toBeTruthy()
    expect(wrapper.find('.product-mode').exists()).toBe(false)
    for (const panel of technicalPanels) {
      expect(wrapper.get(`[data-testid="${panel}"]`)).toBeTruthy()
    }
    wrapper.unmount()
  })
})
