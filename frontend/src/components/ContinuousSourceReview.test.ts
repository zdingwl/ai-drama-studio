// @vitest-environment happy-dom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import SourceShotReviewWorkspaceV2 from './SourceShotReviewWorkspaceV2.vue'
import SourceDialogueReviewQueue from './SourceDialogueReviewQueue.vue'
import { api } from '../api/client'
import { remakeApi } from '../api/remake'
import type { Episode, Shot } from '../types/studio'
import type { ReviewIssue } from '../types/remake'

vi.mock('../api/client', () => ({ api: { getAssetWorkspace: vi.fn(), listShots: vi.fn() } }))
vi.mock('../api/remake', () => ({ remakeApi: { listReviewIssues: vi.fn(), resolveSpeakerReviewIssue: vi.fn() } }))
const episode = { id: 'ep', title: '第一集', sort_order: 1 } as Episode
const shots = [1, 2].map(ordinal => ({ id: `s${ordinal}`, ordinal, start_us: (ordinal - 1) * 10, end_us: ordinal * 10, thumbnail_url: `/frame${ordinal}`, reference_url: `/video${ordinal}` })) as Shot[]
const people = ['a', 'b', 'c'].map((key, index) => ({ key, name: `观察${key}`, appearance: `外观${key}`, episode_id: 'ep', character_id: null as string | null, shots: index === 2 ? [shots[1]!] : [shots[0]!, shots[1]!] }))
let observations: typeof people
let speakerIssues: ReviewIssue[]
let wrapper: VueWrapper | undefined
let fetchMock: ReturnType<typeof vi.fn>
const response = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
const workspace = () => ({ revision: 'r1', observations, characters: [{ id: 'char', name: '正式人物', shot_ids: ['s1', 's2'] }] })
function button(text: string) { return wrapper!.findAll('button').find(button => button.text().includes(text))! }

beforeEach(() => {
  observations = structuredClone(people)
  speakerIssues = []
  vi.mocked(api.listShots).mockResolvedValue(shots)
  vi.mocked(api.getAssetWorkspace).mockResolvedValue({ bindings_by_shot: { s1: { character_ids: ['char'], scene_id: null, prop_ids: [] }, s2: { character_ids: ['char'], scene_id: null, prop_ids: [] } }, evidence_by_shot: {}, characters: [], scenes: [], props: [] } as never)
  vi.mocked(remakeApi.listReviewIssues).mockImplementation(async () => structuredClone(speakerIssues))
  fetchMock = vi.fn(async (_url: string, options?: RequestInit) => {
    if (options?.method === 'POST') {
      const body = JSON.parse(options.body as string)
      observations = observations.map(row => body.keys.includes(row.key) ? { ...row, character_id: 'char' } : row)
    }
    return response(workspace())
  })
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.clearAllMocks(); vi.unstubAllGlobals() })

async function mountPeople(extra = {}) {
  wrapper = mount(SourceShotReviewWorkspaceV2, { props: { projectId: 'p', episodes: [episode], reviewKind: 'people', focusEpisodeId: 'ep', ...extra } })
  await flushPromises()
}
describe('人物连续确认', () => {
  it('opens read-only at the clicked observation and current shot, then advances within and across shots', async () => {
    await mountPeople({ focusPersonKey: 'a', focusShotOrdinal: 2 })
    expect(wrapper!.findAll('.person-row')).toHaveLength(1)
    expect(wrapper!.find('.editor-head').text()).toContain('镜头 02')
    expect(wrapper!.text()).toContain('还剩 3 项')
    expect(fetchMock.mock.calls.every(([, options]) => !options?.method)).toBe(true)
    await wrapper!.find('.new-person input').setValue('新人物')
    await button('单人画面，确认并继续').trigger('click')
    await flushPromises()
    expect(wrapper!.find('.person-info').text()).toContain('观察b')
    expect(wrapper!.text()).toContain('还剩 2 项')
    expect(wrapper!.find('.editor-head').text()).toContain('镜头 01')
    await wrapper!.find('.new-person input').setValue('第二人')
    await button('单人画面，确认并继续').trigger('click')
    await flushPromises()
    expect(wrapper!.find('.person-info').text()).toContain('观察c')
    expect(wrapper!.find('.editor-head').text()).toContain('镜头 02')
  })
  it('keeps the selected person and name on save failure', async () => {
    await mountPeople()
    fetchMock.mockImplementation(async (_url: string, options?: RequestInit) => options?.method ? response({ detail: '版本已变化' }, 409) : response(workspace()))
    await wrapper!.find('.new-person input').setValue('保留姓名')
    await button('单人画面，确认并继续').trigger('click')
    await flushPromises()
    expect(wrapper!.find('.person-info').text()).toContain('观察a')
    expect((wrapper!.find('input[type="text"]').element as HTMLInputElement).value).toBe('保留姓名')
    expect(wrapper!.get('[role="alert"]').text()).toContain('版本已变化')
    expect(wrapper!.text()).toContain('还剩 3 项')
  })
  it('defers without writing or reducing the pending count', async () => {
    await mountPeople()
    await button('暂看下一项').trigger('click')
    expect(wrapper!.find('.person-info').text()).toContain('观察b')
    expect(wrapper!.text()).toContain('还剩 3 项')
    expect(fetchMock.mock.calls.every(([, options]) => !options?.method)).toBe(true)
  })
})

describe('说话人连续确认', () => {
  it('saves one decision then shows the next sentence in the same shot', async () => {
    observations = []
    speakerIssues = ['一句', '二句'].map((text, index) => ({ id: `i${index}`, issue_type: 'SPEAKER', shot_id: 's1', ai_suggestion: { dialogue_key: `d${index}`, source_text: text, candidate_people: [{ person_key: 'person', character_id: 'char', character_name: '正式人物', visible_in_shot: true }] } })) as ReviewIssue[]
    vi.mocked(remakeApi.resolveSpeakerReviewIssue).mockImplementation(async (id) => {
      const issue = speakerIssues.find(issue => issue.id === id)!
      speakerIssues = speakerIssues.filter(issue => issue.id !== id)
      return issue
    })
    await mountPeople({ reviewKind: 'speakers' })
    expect(wrapper!.findAll('.speaker-row')).toHaveLength(1)
    await button('正式人物').trigger('click')
    await button('确认说话人并继续').trigger('click')
    await flushPromises()
    expect(wrapper!.find('.dialogue-copy').text()).toContain('二句')
    expect(remakeApi.resolveSpeakerReviewIssue).toHaveBeenCalledWith('i0', 'person')
    expect(wrapper!.text()).toContain('还剩 1 项')
  })
})

describe('对白冲突与说话人入口', () => {
  const evidence = () => [1, 2].map(n => ({ id: `e${n}`, revision: 'r', status: 'OPEN', start_us: n, end_us: n + 1, asr_text: `语音${n}`, subtitle_text: `字幕${n}`, utterance_id: `u${n}` }))
  async function mountDialogue() {
    wrapper = mount(SourceDialogueReviewQueue, { props: { projectId: 'p', episode, sourceReady: false, blockingReason: '尚未就绪' } })
    await flushPromises()
  }
  it('shows the blocking dialogue immediately without a prepare POST, then advances after saving', async () => {
    let rows = evidence()
    fetchMock.mockImplementation(async (url: string, options?: RequestInit) => {
      if (options?.method) rows = rows.filter(row => !url.includes(`/${row.id}/`))
      return response(rows)
    })
    await mountDialogue()
    expect(wrapper!.text()).toContain('语音1')
    expect(fetchMock.mock.calls.every(([, options]) => !options?.method)).toBe(true)
    await button('确认台词并继续').trigger('click')
    await flushPromises()
    expect(wrapper!.text()).toContain('语音2')
    expect(wrapper!.text()).toContain('台词还剩 1 项')
    await button('确认台词并继续').trigger('click')
    await flushPromises()
    expect(wrapper!.text()).toContain('开始连续确认说话人')
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('prepare'))).toBe(false)
  })
  it('preserves edited dialogue after a rejected save', async () => {
    fetchMock.mockImplementation(async (_url: string, options?: RequestInit) => options?.method ? response({ detail: '版本冲突' }, 409) : response(evidence()))
    await mountDialogue()
    await wrapper!.find('textarea').setValue('人工改写整句')
    await button('确认台词并继续').trigger('click')
    await flushPromises()
    expect((wrapper!.find('textarea').element as HTMLTextAreaElement).value).toBe('人工改写整句')
    expect(wrapper!.text()).toContain('台词还剩 2 项')
    expect(wrapper!.get('[role="alert"]').text()).toContain('版本冲突')
  })
  it('keeps prepare failures in the dialog with an explicit retry', async () => {
    fetchMock.mockImplementation(async (_url: string, options?: RequestInit) => options?.method ? response({ detail: '当前剧集没有有效拉片结果' }, 409) : response([]))
    await mountDialogue()
    await button('开始连续确认说话人').trigger('click')
    await flushPromises()
    expect(wrapper!.get('[role="alert"]').text()).toContain('当前剧集没有有效拉片结果')
    expect(button('重新读取').exists()).toBe(true)
  })
})
