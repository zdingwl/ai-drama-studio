import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'
import { getProject } from '@/features/projects/api'

vi.mock('@/features/projects/api', () => ({ getProject: vi.fn() }))

const technicalPanels = ['p6-panel', 'p7-panel', 'p8-panel', 'p9-panel', 'source-result-approval']
const fiveStepIds = ['source-storyboard-workspace', 'localized-storyboard-workspace', 'asset-images-workspace', 'h3-prompt-workspace', 'h3-generation-workspace']

async function mountApp(path: string, projectType = 'REPLICA') {
  vi.mocked(getProject).mockResolvedValue({ project_type: projectType } as never)
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
        EpisodeWorkspaceNav: { template: '<section data-testid="episode-workspace-nav" />' },
        SourceStoryboardWorkspace: { template: '<section data-testid="source-storyboard-workspace" />' },
        LocalizedStoryboardWorkspace: { template: '<section data-testid="localized-storyboard-workspace" />' },
        AssetImagesWorkspace: { template: '<section data-testid="asset-images-workspace" />' },
        EpisodeManagementWorkspace: { template: '<section data-testid="episode-management-workspace" />' },
        H3PromptWorkspace: { template: '<section data-testid="h3-prompt-workspace" />' },
        H3GenerationWorkspace: { template: '<section data-testid="h3-generation-workspace" />' },
        SourceScriptStoryboardWorkspace: { template: '<section data-testid="source-workspace" />' },
        TargetBibleWorkspace: { template: '<section data-testid="target-bible-workspace" />' },
        TargetScriptWorkspace: { template: '<section data-testid="target-script-workspace" />' },
        ReplicaProductionWorkspace: { template: '<section data-testid="replica-production-workspace" />' },
        ScriptLocalizationWorkspace: { template: '<section data-testid="script-localization-workspace" />' },
        P6AcceptancePanel: { template: '<section data-testid="p6-panel" />' },
        P7SourceUnderstandingWorkspace: { template: '<section data-testid="p7-panel" />' },
        P8ShotBreakdownPanel: { template: '<section data-testid="p8-panel" />' },
        P9SourceResolutionPanel: { template: '<section data-testid="p9-panel" />' },
        ProjectOverviewWorkspace: { template: '<section data-testid="project-overview-workspace" />' },
        SourceResultApprovalBar: { template: '<section data-testid="source-result-approval" />' },
      },
    },
  })
  await flushPromises()
  return wrapper
}

function expectOnlyFiveStep(wrapper: ReturnType<typeof mount>, expected: string) {
  for (const id of fiveStepIds) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(id === expected)
}

describe('App production workspace isolation', () => {
  beforeEach(() => vi.clearAllMocks())

  it.each([['overview', 'project-overview-workspace'], ['episodes', 'episode-management-workspace']])(
    'keeps Replica %s page without the episode switch rail', async (workspace, testId) => {
      const wrapper = await mountApp(`/projects/project-1/${workspace}`)
      expect(wrapper.get(`[data-testid="${testId}"]`)).toBeTruthy()
      expect(wrapper.find('[data-testid="episode-workspace-nav"]').exists()).toBe(false)
      expect(wrapper.get('[data-testid="journey-nav"]')).toBeTruthy()
      wrapper.unmount()
    },
  )

  it('routes Replica source to the existing source storyboard and episode rail', async () => {
    const wrapper = await mountApp('/projects/project-1/source')
    expect(wrapper.find('[data-testid="project-route"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="episode-workspace-nav"]')).toBeTruthy()
    expectOnlyFiveStep(wrapper, 'source-storyboard-workspace')
    expect(wrapper.find('[data-testid="script-localization-workspace"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it.each([
    ['localize', 'localized-storyboard-workspace'],
    ['assets', 'asset-images-workspace'],
    ['prompts', 'h3-prompt-workspace'],
    ['generation', 'h3-generation-workspace'],
  ])('keeps Replica %s in exactly one five-step workspace', async (workspace, testId) => {
    const wrapper = await mountApp(`/projects/project-1/${workspace}`)
    expectOnlyFiveStep(wrapper, testId)
    expect(wrapper.find('[data-testid="target-bible-workspace"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="target-script-workspace"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="replica-production-workspace"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps the Replica legacy script route intact', async () => {
    const wrapper = await mountApp('/projects/project-1/script')
    for (const id of ['source-workspace', 'target-bible-workspace', 'target-script-workspace']) {
      expect(wrapper.get(`[data-testid="${id}"]`)).toBeTruthy()
    }
    for (const id of fiveStepIds) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
    wrapper.unmount()
  })

  it.each(['source', 'script', 'overview'])(
    'routes script localization %s without mounting a Replica/video component', async workspace => {
      const wrapper = await mountApp(`/projects/project-1/${workspace}`, 'SCRIPT_LOCALIZATION')
      expect(wrapper.get('[data-testid="script-localization-workspace"]')).toBeTruthy()
      expect(wrapper.find('[data-testid="episode-workspace-nav"]').exists()).toBe(false)
      expect(wrapper.find('[data-testid="source-workspace"]').exists()).toBe(false)
      for (const id of fiveStepIds) expect(wrapper.find(`[data-testid="${id}"]`).exists()).toBe(false)
      wrapper.unmount()
    },
  )

  it('keeps engineering diagnostics behind debug=1', async () => {
    const wrapper = await mountApp('/projects/project-1/source?debug=1')
    expect(wrapper.find('[data-testid="journey-nav"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="project-route"]')).toBeTruthy()
    for (const panel of technicalPanels) expect(wrapper.get(`[data-testid="${panel}"]`)).toBeTruthy()
    wrapper.unmount()
  })
})
