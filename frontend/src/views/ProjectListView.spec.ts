import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import ProjectListView from './ProjectListView.vue'

const projects = [
  {
    id: 'project-1', name: '纽约复刻计划', project_type: 'REPLICA', source_language: 'zh-CN',
    target_language: 'en-US', target_region: 'US', scene_strategy: 'MIXED', audio_policy: 'REGENERATE_AUDIO',
    visual_style: null, source_understanding_provider: 'DOUBAO_SEED_2_1_PRO_API', status: 'ACTIVE', workflow_revision: 2,
    created_at: '2026-09-12T00:00:00Z', updated_at: '2026-09-13T00:00:00Z',
  },
  {
    id: 'project-2', name: '旧版翻译', project_type: 'TRANSLATION', source_language: 'zh-CN',
    target_language: 'ja-JP', target_region: 'JP', scene_strategy: 'KEEP', audio_policy: 'REGENERATE_AUDIO',
    visual_style: null, source_understanding_provider: 'DOUBAO_SEED_2_1_PRO_API', status: 'ARCHIVED', workflow_revision: 1,
    created_at: '2026-09-10T00:00:00Z', updated_at: '2026-09-10T00:00:00Z',
  },
]

function response(data: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => data } as Response
}

async function mountView() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: ProjectListView }, { path: '/projects/:id', component: { template: '<div />' } }],
  })
  await router.push('/')
  await router.isReady()
  const wrapper = mount(ProjectListView, { global: { plugins: [router] }, attachTo: document.body })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('ProjectListView', () => {
  it('renders design-led cards and supports status, search, and view controls', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(projects)))
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('我的项目')
    expect(wrapper.findAll('.project-card')).toHaveLength(2)
    expect(wrapper.text()).toContain('进行中 1')
    expect(wrapper.text()).toContain('已归档 1')

    await wrapper.find('input[type="search"]').setValue('纽约')
    expect(wrapper.findAll('.project-card')).toHaveLength(1)
    expect(wrapper.text()).not.toContain('旧版翻译')

    await wrapper.get('button[aria-label="列表视图"]').trigger('click')
    expect(wrapper.get('.project-collection').classes()).toContain('is-list')
    wrapper.unmount()
  })

  it('creates projects from the modal instead of expanding the form in the list', async () => {
    const created = { ...projects[0], id: 'project-3', name: '新项目' }
    vi.stubGlobal('fetch', vi.fn(async (_input: string | URL | Request, init?: RequestInit) =>
      init?.method === 'POST' ? response(created, 201) : response([]),
    ))
    const wrapper = await mountView()

    expect(document.body.querySelector('.create-dialog')).toBeNull()
    await wrapper.get('.primary-action').trigger('click')
    const dialog = document.body.querySelector('.create-dialog') as HTMLElement
    expect(dialog).not.toBeNull()

    const nameInput = dialog.querySelector('input') as HTMLInputElement
    nameInput.value = '新项目'
    nameInput.dispatchEvent(new Event('input'))
    ;(dialog.querySelector('form') as HTMLFormElement).dispatchEvent(new Event('submit'))
    await flushPromises()

    expect(wrapper.text()).toContain('新项目')
    expect(document.body.querySelector('.create-dialog')).toBeNull()
    wrapper.unmount()
  })
})
