import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import HomeView from './HomeView.vue'

const skillRows = [
  ['project.replica', '复刻短剧', 'REPLICA', '保留故事和节奏，本土化人物、场景与对白。'],
  ['project.redraw', '重绘短剧', 'REDRAW', '保留原结构，重点重做视觉。'],
  ['project.translation', '翻译短剧', 'TRANSLATION', '保留原画面，重建目标语言版本。'],
  ['project.novel_to_drama', '小说生成短剧', 'NOVEL_TO_DRAMA', '把小说改造成短剧并生成。'],
  ['project.script_to_drama', '剧本生成短剧', 'SCRIPT_TO_DRAMA', '把剧本变成可生成短剧。'],
  ['project.script_localization', '剧本本土化', 'SCRIPT_LOCALIZATION', '把剧本改成目标地区成立的版本。'],
].map(([id, name, project_type, description]) => ({
  id,
  name,
  version: '1.0.0',
  project_type,
  description,
}))

function response(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
}

describe('HomeView', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders six backend-driven project type cards with fixed selects', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input)
        if (url.endsWith('/api/v3/skills')) return response(skillRows)
        if (url.endsWith('/api/v3/projects')) return response([])
        throw new Error(`unexpected request: ${url}`)
      }),
    )

    const wrapper = mount(HomeView)
    await flushPromises()

    expect(wrapper.text()).toContain('你想创建什么？')
    expect(wrapper.findAll('.type-card')).toHaveLength(6)
    expect(wrapper.text()).toContain('复刻')
    expect(wrapper.text()).toContain('剧本本土化')
    expect(wrapper.find('select').exists()).toBe(true)

    const localizationCard = wrapper.findAll('.type-card').find((item) => item.text().includes('剧本本土化'))
    await localizationCard?.trigger('click')
    expect(wrapper.text()).not.toContain('原始语言')
  })

  it('creates a project then explicitly compiles and renders the persisted plan', async () => {
    const createdProject = {
      id: 'project-1',
      name: '美国版 EP01',
      project_type: 'REPLICA',
      source_language: 'zh-CN',
      target_language: 'en-US',
      target_region: 'US',
      scene_strategy: 'MIXED',
      audio_policy: 'REGENERATE_AUDIO',
      visual_style: 'SOURCE_LIKE',
      root_skill_id: 'project.replica',
      root_skill_version: '1.0.0',
      current_plan_id: null,
      workflow_revision: 1,
    }
    const compiledPlan = {
      id: 'plan-1',
      project_id: 'project-1',
      skill_id: 'project.replica',
      skill_title: '复刻短剧',
      skill_version: '1.0.0',
      revision: 1,
      input_fingerprint: 'a'.repeat(64),
      steps: [
        {
          id: 'source_input',
          phase: '输入',
          title: '导入原片',
          description: '登记原始短剧 Episode。',
          status: 'WAITING_CAPABILITY',
          missing_artifacts: [],
          unavailable_capabilities: ['SOURCE_VIDEO_INGEST'],
        },
      ],
    }

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input)
        const method = init?.method ?? 'GET'
        if (url.endsWith('/api/v3/skills') && method === 'GET') return response(skillRows)
        if (url.endsWith('/api/v3/projects') && method === 'GET') return response([])
        if (url.endsWith('/api/v3/projects') && method === 'POST') return response(createdProject, 201)
        if (url.endsWith('/api/v3/projects/project-1/commands/compile-plan') && method === 'POST') {
          return response(compiledPlan)
        }
        throw new Error(`unexpected request: ${method} ${url}`)
      }),
    )

    const wrapper = mount(HomeView)
    await flushPromises()
    await wrapper.find('input').setValue('美国版 EP01')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('项目已创建，执行计划已生成。')
    expect(wrapper.text()).toContain('导入原片')
    expect(wrapper.text()).toContain('等待后续能力接入')
  })
})
