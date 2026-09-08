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

const replicaProject = {
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

const scriptProject = {
  ...replicaProject,
  id: 'project-script',
  name: '本土化剧本',
  project_type: 'SCRIPT_LOCALIZATION',
  source_language: null,
  root_skill_id: 'project.script_localization',
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
      status: 'READY',
      missing_artifacts: [],
      unavailable_capabilities: [],
    },
  ],
}

function response(data: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
}

function notFound(code = 'PLAN_NOT_COMPILED'): Response {
  return response({ error: { code, message: 'not found', details: null } }, 404)
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

  it('creates a project then explicitly compiles the persisted plan', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input)
        const method = init?.method ?? 'GET'
        if (url.endsWith('/api/v3/skills') && method === 'GET') return response(skillRows)
        if (url.endsWith('/api/v3/projects') && method === 'GET') return response([])
        if (url.endsWith('/api/v3/projects') && method === 'POST') return response(replicaProject, 201)
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

    expect(wrapper.text()).toContain('项目已创建。现在可以导入原始素材。')
    expect(wrapper.text()).toContain('导入原片')
    expect(wrapper.text()).toContain('可执行')
    expect(wrapper.text()).toContain('上传原片')
  })

  it('loads a video project source list and uploads multiple original episodes', async () => {
    const beforeEpisodes = [
      {
        id: 'episode-1',
        source_asset: { id: 'asset-1', original_filename: '01.mp4', mime_type: 'video/mp4', size_bytes: 100 },
        episode_order: 1,
        duration_us: 12_500_000,
        width: 1080,
        height: 1920,
        has_audio: true,
      },
    ]
    const afterEpisodes = [
      ...beforeEpisodes,
      {
        id: 'episode-2',
        source_asset: { id: 'asset-2', original_filename: '02.mp4', mime_type: 'video/mp4', size_bytes: 120 },
        episode_order: 2,
        duration_us: 9_000_000,
        width: 1080,
        height: 1920,
        has_audio: true,
      },
    ]
    let episodeReads = 0

    const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (url.endsWith('/api/v3/skills')) return response(skillRows)
      if (url.endsWith('/api/v3/projects')) return response([replicaProject])
      if (url.endsWith('/api/v3/projects/project-1/plan')) return notFound()
      if (url.endsWith('/api/v3/projects/project-1/sources/episodes') && method === 'GET') {
        episodeReads += 1
        return response(episodeReads === 1 ? beforeEpisodes : afterEpisodes)
      }
      if (url.endsWith('/api/v3/projects/project-1/sources/videos') && method === 'POST') {
        expect(init?.body).toBeInstanceOf(FormData)
        return response(afterEpisodes.slice(1), 201)
      }
      throw new Error(`unexpected request: ${method} ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(HomeView)
    await flushPromises()
    expect(wrapper.text()).toContain('01.mp4')
    expect(wrapper.text()).toContain('12.5 秒')

    const input = wrapper.find('input[type="file"][multiple]').element as HTMLInputElement
    Object.defineProperty(input, 'files', {
      configurable: true,
      value: [new File(['video'], '02.mp4', { type: 'video/mp4' })],
    })
    await wrapper.find('input[type="file"][multiple]').trigger('change')
    await flushPromises()

    expect(wrapper.text()).toContain('02.mp4')
    expect(wrapper.text()).toContain('原始素材已更新，请重新生成执行计划。')
  })

  it('loads text project document and presents replacement rather than media controls', async () => {
    const document = {
      id: 'document-2',
      project_id: 'project-script',
      source_asset: {
        id: 'asset-script',
        project_id: 'project-script',
        asset_kind: 'TEXT',
        original_filename: '剧本.md',
        mime_type: 'text/markdown',
        size_bytes: 800,
        sha256: 'a'.repeat(64),
        immutable: true,
        created_at: '2026-09-08T00:00:00Z',
      },
      revision: 2,
      document_format: 'MARKDOWN',
      encoding: 'utf-8',
      char_count: 3200,
      is_current: true,
      created_at: '2026-09-08T00:00:00Z',
    }

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request) => {
        const url = String(input)
        if (url.endsWith('/api/v3/skills')) return response(skillRows)
        if (url.endsWith('/api/v3/projects')) return response([scriptProject])
        if (url.endsWith('/api/v3/projects/project-script/plan')) return notFound()
        if (url.endsWith('/api/v3/projects/project-script/sources/document')) return response(document)
        throw new Error(`unexpected request: ${url}`)
      }),
    )

    const wrapper = mount(HomeView)
    await flushPromises()
    expect(wrapper.text()).toContain('原始剧本')
    expect(wrapper.text()).toContain('剧本.md')
    expect(wrapper.text()).toContain('当前版本 r2')
    expect(wrapper.text()).toContain('替换文本')
    expect(wrapper.find('input[type="file"][multiple]').exists()).toBe(false)
  })

  it('persists drag reorder through the backend instead of maintaining a frontend stage graph', async () => {
    const episodes = [
      {
        id: 'episode-1',
        source_asset: { id: 'asset-1', original_filename: '01.mp4', mime_type: 'video/mp4', size_bytes: 100 },
        episode_order: 1,
        duration_us: 1_000_000,
        width: 160,
        height: 90,
        has_audio: false,
      },
      {
        id: 'episode-2',
        source_asset: { id: 'asset-2', original_filename: '02.mp4', mime_type: 'video/mp4', size_bytes: 100 },
        episode_order: 2,
        duration_us: 1_000_000,
        width: 160,
        height: 90,
        has_audio: false,
      },
    ]
    const reordered = [
      { ...episodes[1], episode_order: 1 },
      { ...episodes[0], episode_order: 2 },
    ]
    let reorderBody = ''

    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
        const url = String(input)
        const method = init?.method ?? 'GET'
        if (url.endsWith('/api/v3/skills')) return response(skillRows)
        if (url.endsWith('/api/v3/projects')) return response([replicaProject])
        if (url.endsWith('/api/v3/projects/project-1/plan')) return notFound()
        if (url.endsWith('/api/v3/projects/project-1/sources/episodes') && method === 'GET') return response(episodes)
        if (url.endsWith('/api/v3/projects/project-1/sources/episodes/reorder') && method === 'POST') {
          reorderBody = String(init?.body ?? '')
          return response(reordered)
        }
        throw new Error(`unexpected request: ${method} ${url}`)
      }),
    )

    const wrapper = mount(HomeView)
    await flushPromises()
    const rows = wrapper.findAll('.episode-row')
    await rows[1].trigger('dragstart')
    await rows[0].trigger('drop')
    await flushPromises()

    expect(JSON.parse(reorderBody)).toEqual({ episode_ids: ['episode-2', 'episode-1'] })
    expect(wrapper.findAll('.episode-file')[0].text()).toBe('02.mp4')
  })
})
