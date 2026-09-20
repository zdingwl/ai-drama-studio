import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ScriptToDramaScriptLibrary from './ScriptToDramaScriptLibrary.vue'
import { listProjectTasks } from '@/features/projects/api'
import { getDramaState } from '@/features/projects/scriptToDrama'
import {
  extractDramaAssets, getDramaScript, listDramaScripts, pasteDramaScript, updateDramaScript,
} from '@/features/projects/scriptToDramaLibrary'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'script-project' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/features/projects/api', () => ({ listProjectTasks: vi.fn() }))
vi.mock('@/features/projects/scriptToDrama', () => ({ getDramaState: vi.fn() }))
vi.mock('@/features/projects/scriptToDramaLibrary', () => ({
  listDramaScripts: vi.fn(), getDramaScript: vi.fn(), updateDramaScript: vi.fn(),
  pasteDramaScript: vi.fn(), extractDramaAssets: vi.fn(), uploadDramaScripts: vi.fn(),
  selectDramaScript: vi.fn(),
}))

const shelf = {
  project_id: 'script-project', current_document_id: 'document-1',
  scripts: [
    { id: 'script-1', title: '第一集', filename: '第一集.txt', excerpt: '林诗语走进宴会厅', char_count: 100, latest_revision: 1, is_active: true },
    { id: 'script-2', title: '第二集', filename: '第二集.txt', excerpt: '赵教授出场', char_count: 80, latest_revision: 1, is_active: false },
  ],
}
const details = {
  'script-1': { ...shelf.scripts[0], text: '完整剧本正文', sha256: 'hash-1' },
  'script-2': { ...shelf.scripts[1], text: '第二份完整正文', sha256: 'hash-2' },
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
    vi.mocked(getDramaScript).mockImplementation(async (_, id) => details[id as keyof typeof details] as never)
  })

  it('does not display asset tags before extraction, even if names occur in the original text', async () => {
    const wrapper = await workspace()
    expect(wrapper.findAll('.script-card')).toHaveLength(2)
    expect(wrapper.findAll('.asset-tags')).toHaveLength(0)
    expect(wrapper.find('.script-card').text()).toContain('未提取资产')
    expect(wrapper.find('.search-form input').attributes('type')).toBe('search')
    wrapper.unmount()
  })

  it('shows extracted tags only on the currently produced script', async () => {
    const wrapper = await workspace(true)
    expect(wrapper.findAll('.script-card')[0]?.find('.asset-tags').text()).toContain('林诗语')
    expect(wrapper.findAll('.script-card')[1]?.find('.asset-tags').exists()).toBe(false)
    wrapper.unmount()
  })

  it('reads full text for any script, without switching the production source', async () => {
    const wrapper = await workspace()
    await wrapper.findAll('.card-content')[1]!.trigger('click')
    await flushPromises()
    expect(getDramaScript).toHaveBeenCalledWith('script-project', 'script-2')
    expect((wrapper.find('.dialog-body textarea').element as HTMLTextAreaElement).value).toBe('第二份完整正文')
    expect(wrapper.find('.dialog-body textarea').attributes('readonly')).toBeUndefined()
    expect(wrapper.find('.dialog-footer button:last-child').attributes('disabled')).toBeDefined()
    await wrapper.find('.dialog-footer .secondary').trigger('click')
    await wrapper.find('.select-all input').setValue(true)
    expect(wrapper.text()).toContain('已选 2 份')
    const extract = wrapper.findAll('.bulk-line button')[0]
    expect(extract.attributes('disabled')).toBeDefined()
    expect(wrapper.findAll('.bulk-line button')[1]?.attributes('disabled')).toBeDefined()
    expect(extractDramaAssets).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('saves an edit with optimistic revision and leaves other scripts untouched', async () => {
    vi.mocked(updateDramaScript).mockResolvedValue({ ...details['script-2'], text: '编辑后的第二份', latest_revision: 2 } as never)
    const wrapper = await workspace()
    await wrapper.findAll('.card-content')[1]!.trigger('click')
    await flushPromises()
    await wrapper.find('.dialog-body textarea').setValue('编辑后的第二份')
    await wrapper.find('.dialog-footer button:last-child').trigger('click')
    await flushPromises()
    expect(updateDramaScript).toHaveBeenCalledWith('script-project', 'script-2', 1, '第二集', '编辑后的第二份')
    expect(wrapper.text()).toContain('正文已保存为独立的新版本')
    wrapper.unmount()
  })

  it('creates a script only after the dialog has a name and text', async () => {
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
    expect(wrapper.text()).toContain('当前制作剧本没有改变')
    wrapper.unmount()
  })
})
