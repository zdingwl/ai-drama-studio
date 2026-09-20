import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ScriptToDramaScriptLibrary from './ScriptToDramaScriptLibrary.vue'
import { listProjectTasks } from '@/features/projects/api'
import { getDramaSource, getDramaState } from '@/features/projects/scriptToDrama'
import { extractDramaAssets, listDramaScripts, pasteDramaScript } from '@/features/projects/scriptToDramaLibrary'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'script-project' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/features/projects/api', () => ({ listProjectTasks: vi.fn() }))
vi.mock('@/features/projects/scriptToDrama', () => ({ getDramaSource: vi.fn(), getDramaState: vi.fn() }))
vi.mock('@/features/projects/scriptToDramaLibrary', () => ({
  listDramaScripts: vi.fn(), pasteDramaScript: vi.fn(), extractDramaAssets: vi.fn(),
  uploadDramaScripts: vi.fn(), selectDramaScript: vi.fn(),
}))

const shelf = {
  project_id: 'script-project', current_document_id: 'document-1',
  scripts: [
    { id: 'script-1', title: '第一集', filename: '第一集.txt', excerpt: '林诗语走进宴会厅', char_count: 100, latest_revision: 1, is_active: true },
    { id: 'script-2', title: '第二集', filename: '第二集.txt', excerpt: '赵教授出场', char_count: 80, latest_revision: 2, is_active: false },
  ],
}

async function workspace(extracted = false) {
  vi.mocked(getDramaState).mockResolvedValue({
    world: { status: extracted ? 'CURRENT' : 'NOT_BUILT', content: extracted ? { characters: [{ name: '林诗语' }], locations: [], props: [], review_status: 'NEEDS_REVIEW' } : null },
    assets: { status: extracted ? 'CURRENT' : 'NOT_BUILT', content: extracted ? { review_status: 'NEEDS_REVIEW' } : null },
  } as never)
  const wrapper = mount(ScriptToDramaScriptLibrary)
  await flushPromises()
  return wrapper
}

describe('ScriptToDramaScriptLibrary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(listDramaScripts).mockResolvedValue(shelf)
    vi.mocked(listProjectTasks).mockResolvedValue([])
    vi.mocked(getDramaSource).mockResolvedValue({ text: '完整剧本正文', document_id: 'document-1' } as never)
  })

  it('does not display asset tags before extraction, even if names appear in raw text', async () => {
    const wrapper = await workspace()
    expect(wrapper.findAll('.script-card')).toHaveLength(2)
    expect(wrapper.findAll('.asset-tags')).toHaveLength(0)
    expect(wrapper.find('.script-card').text()).toContain('未提取资产')
    expect(wrapper.find('.search-form input').attributes('type')).toBe('search')
    wrapper.unmount()
  })

  it('shows extracted tags only for the current script, never attaches them to another script', async () => {
    const wrapper = await workspace(true)
    expect(wrapper.findAll('.script-card')[0]?.find('.asset-tags').text()).toContain('林诗语')
    expect(wrapper.findAll('.script-card')[1]?.find('.asset-tags').exists()).toBe(false)
    wrapper.unmount()
  })

  it('separates card detail from checkboxes and never sends unsupported batch extraction', async () => {
    const wrapper = await workspace()
    await wrapper.find('.card-content').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    expect(wrapper.find('textarea[readonly]').element.value).toBe('完整剧本正文')
    await wrapper.find('.dialog-footer .secondary').trigger('click')
    await wrapper.find('.select-all input').setValue(true)
    expect(wrapper.text()).toContain('已选 2 份')
    const extract = wrapper.findAll('.bulk-line button')[0]
    expect(extract.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('.bulk-line button')[1]?.attributes('disabled')).toBeDefined()
    expect(extractDramaAssets).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('creates a script only after the new-script dialog has a name and body', async () => {
    vi.mocked(pasteDramaScript).mockResolvedValue(shelf)
    const wrapper = await workspace()
    await wrapper.find('.toolbar-actions button').trigger('click')
    expect(wrapper.find('[role="dialog"]').exists()).toBe(true)
    const save = wrapper.find('.dialog-footer button:last-child')
    expect(save.attributes('disabled')).toBeDefined()
    await wrapper.find('.dialog-body input').setValue('第三集')
    await wrapper.find('.dialog-body textarea').setValue('场次 01：开始')
    await wrapper.find('.dialog-footer button:last-child').trigger('click')
    await flushPromises()
    expect(pasteDramaScript).toHaveBeenCalledWith('script-project', '第三集', '场次 01：开始')
    wrapper.unmount()
  })
})
