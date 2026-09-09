import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import * as projectApi from '@/features/projects/api'
import * as sourceBibleApi from '@/features/projects/sourceBible'
import P7SourceUnderstandingWorkspace from './P7SourceUnderstandingWorkspace.vue'

vi.mock('@/features/projects/api', () => ({
  getProject: vi.fn(),
  updateProject: vi.fn(),
}))

vi.mock('@/features/projects/sourceBible', () => ({
  getP7RuntimeConfig: vi.fn(),
  updateP7RuntimeConfig: vi.fn(),
}))

const project = {
  id: 'project-p7',
  name: 'P7 三模型项目',
  project_type: 'REPLICA' as const,
  source_language: 'zh-CN',
  target_language: 'en-US',
  target_region: 'US',
  scene_strategy: 'MIXED' as const,
  audio_policy: 'REGENERATE_AUDIO' as const,
  visual_style: null,
  source_understanding_provider: 'DOUBAO_SEED_2_1_PRO_API' as const,
  status: 'ACTIVE' as const,
  workflow_revision: 1,
  created_at: '2026-09-09T00:00:00Z',
  updated_at: '2026-09-09T00:00:00Z',
}

const runtimeConfig: sourceBibleApi.P7RuntimeConfig = {
  doubao: {
    api_key: '',
    model: 'doubao-seed-2-1-pro-260628',
    base_url: 'https://ark.cn-beijing.volces.com/api/v3',
    request_timeout_seconds: 1800,
    video_fps: 1,
  },
  qwen38: {
    api_key: '',
    model: 'Qwen/Qwen3.8-27B',
    base_url: 'http://127.0.0.1:8000/v1',
  },
  qwen3_vl_8b: {
    api_key: '',
    model: 'Qwen/Qwen3-VL-8B-Thinking',
    base_url: 'http://127.0.0.1:8001/v1',
  },
  qwen_request_timeout_seconds: 3600,
}

async function mountWorkspace() {
  vi.mocked(sourceBibleApi.getP7RuntimeConfig).mockResolvedValue(runtimeConfig)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/projects/:id', name: 'project-workspace', component: P7SourceUnderstandingWorkspace }],
  })
  await router.push('/projects/project-p7')
  await router.isReady()
  const wrapper = mount(P7SourceUnderstandingWorkspace, {
    global: {
      plugins: [router],
      stubs: { P7SourceBiblePanel: true },
    },
  })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  vi.clearAllMocks()
})

describe('P7SourceUnderstandingWorkspace', () => {
  it('shows exactly the three accepted P7 model choices', async () => {
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    const wrapper = await mountWorkspace()

    const text = wrapper.text()
    expect(text).toContain('Doubao Seed 2.1 Pro')
    expect(text).toContain('Qwen3.8-27B')
    expect(text).toContain('Qwen3-VL-8B-Thinking')
    expect(wrapper.findAll('input[type="radio"]')).toHaveLength(3)
    wrapper.unmount()
  })

  it('persists Qwen3.8 as the project-level P7 model choice', async () => {
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    vi.mocked(projectApi.updateProject).mockResolvedValue({
      ...project,
      source_understanding_provider: 'QWEN3_8_27B_LOCAL',
      workflow_revision: 2,
    })
    const wrapper = await mountWorkspace()

    const qwen38 = wrapper.find('input[value="QWEN3_8_27B_LOCAL"]')
    await qwen38.setValue(true)
    const saveModelButton = wrapper.findAll('button').find((item) => item.text().includes('保存模型选择'))
    expect(saveModelButton).toBeTruthy()
    await saveModelButton!.trigger('click')
    await flushPromises()

    expect(projectApi.updateProject).toHaveBeenCalledWith('project-p7', {
      source_understanding_provider: 'QWEN3_8_27B_LOCAL',
    })
    expect(wrapper.text()).toContain('旧 SOURCE_BIBLE')
    wrapper.unmount()
  })

  it('shows plaintext Ark configuration and saves it through the runtime config API', async () => {
    vi.mocked(projectApi.getProject).mockResolvedValue(project)
    vi.mocked(sourceBibleApi.updateP7RuntimeConfig).mockImplementation(async (payload) => payload)
    const wrapper = await mountWorkspace()

    const apiKey = wrapper.get('[data-testid="doubao-api-key"]')
    expect(apiKey.attributes('type')).toBe('text')
    await apiKey.setValue('ark-local-test-key')
    await wrapper.get('[data-testid="doubao-model"]').setValue('ep-test-seed-2.1-pro')
    await wrapper.get('[data-testid="save-runtime-config"]').trigger('click')
    await flushPromises()

    expect(sourceBibleApi.updateP7RuntimeConfig).toHaveBeenCalledOnce()
    const payload = vi.mocked(sourceBibleApi.updateP7RuntimeConfig).mock.calls[0]?.[0]
    expect(payload?.doubao.api_key).toBe('ark-local-test-key')
    expect(payload?.doubao.model).toBe('ep-test-seed-2.1-pro')
    expect(wrapper.text()).toContain('backend/.env')
    wrapper.unmount()
  })
})
