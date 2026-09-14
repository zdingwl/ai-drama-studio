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
      path: '/projects/:id/:workspace?',
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
        ProductJourneyNav: { template: '<nav data-testid="journey-nav" />' },
        SourceStoryboardWorkspace: { template: '<section data-testid="source-storyboard-workspace" />' },
        LocalizedStoryboardWorkspace: { template: '<section data-testid="localized-storyboard-workspace" />' },
        AssetImagesWorkspace: { template: '<section data-testid="asset-images-workspace" />' },
        H3PromptWorkspace: { template: '<section data-testid="h3-prompt-workspace" />' },
        H3GenerationWorkspace: { template: '<section data-testid="h3-generation-workspace" />' },
        SourceScriptStoryboardWorkspace: { template: '<section data-testid="source-workspace" />' },
        TargetBibleWorkspace: { template: '<section data-testid="target-bible-workspace" />' },
        TargetScriptWorkspace: { template: '<section data-testid="target-script-workspace" />' },
        ReplicaProductionWorkspace: { template: '<section data-testid="replica-production-workspace" />' },
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

const fiveStepIds = [
  'source-storyboard-workspace',
  'localized-storyboard-workspace',
  'asset-images-workspace',
  'h3-prompt-workspace',
  'h3-generation-workspace',
]

function expectOnlyFiveStep(wrapper: ReturnType<typeof mount>, expected: string) {
  for (const id of fiveStepIds) {
    expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(id === expected)
  }
}

describe('App Replica five-step product workspaces', () => {
  it('routes source to the final source storyboard surface', async () => {
    const wrapper = await mountApp('/projects/project-1/source')
    expect(wrapper.get('[data-testid="project-route"]')).toBeTruthy()
    expectOnlyFiveStep(wrapper, 'source-storyboard-workspace')
    wrapper.unmount()
  })

  it.each([
    ['localize', 'localized-storyboard-workspace'],
    ['assets', 'asset-images-workspace'],
    ['prompts', 'h3-prompt-workspace'],
    ['generation', 'h3-generation-workspace'],
  ])('routes %s to exactly one five-step workspace', async (workspace, testId) => {
    const wrapper = await mountApp(`/projects/project-1/${workspace}`)
    expectOnlyFiveStep(wrapper, testId)
    expect(wrapper.find('[data-testid="target-bible-workspace"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="target-script-workspace"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="replica-production-workspace"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps historical script route readable without putting it in the Replica five-step path', async () => {
    const wrapper = await mountApp('/projects/project-1/script')
    expect(wrapper.get('[data-testid="source-workspace"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="target-bible-workspace"]')).toBeTruthy()
    expect(wrapper.get('[data-testid="target-script-workspace"]')).toBeTruthy()
    for (const id of fiveStepIds) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps engineering acceptance panels behind debug=1', async () => {
    const wrapper = await mountApp('/projects/project-1/source?debug=1')
    expect(wrapper.find('[data-testid="journey-nav"]').exists()).toBe(false)
    for (const panel of technicalPanels) expect(wrapper.get(`[data-testid="${panel}"]`)).toBeTruthy()
    for (const id of fiveStepIds) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
    wrapper.unmount()
  })
})
