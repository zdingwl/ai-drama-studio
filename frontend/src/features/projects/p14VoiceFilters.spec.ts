import { describe, expect, it } from 'vitest'

import { collectVoiceFilterOptions, filterVoices, type VoiceFilterState, type VoiceFilterable } from './p14VoiceFilters'

const voices: VoiceFilterable[] = [
  {
    voice_key: 'voice-female-warm',
    default_display_name: 'Voice 01',
    display_name: '温柔青年女声',
    locale: 'zh-CN',
    tags: ['demo'],
    gender: 'FEMALE',
    age_range: 'YOUNG_ADULT',
    style_tags: ['温柔', '自然'],
    notes: '适合年轻女主角',
    metadata_source: 'USER',
    metadata_stale: false,
  },
  {
    voice_key: 'voice-male-deep',
    default_display_name: 'Voice 02',
    display_name: '低沉成熟男声',
    locale: 'en-US',
    tags: ['demo'],
    gender: 'MALE',
    age_range: 'MATURE',
    style_tags: ['低沉', '沉稳'],
    notes: '适合成熟男性角色',
    metadata_source: 'USER',
    metadata_stale: false,
  },
  {
    voice_key: 'voice-unlabeled',
    default_display_name: 'Voice 03',
    display_name: 'Voice 03',
    locale: null,
    tags: ['demo'],
    gender: 'UNKNOWN',
    age_range: 'UNKNOWN',
    style_tags: [],
    notes: null,
    metadata_source: 'CATALOG',
    metadata_stale: false,
  },
  {
    voice_key: 'voice-stale',
    default_display_name: 'Voice 04',
    display_name: 'Voice 04',
    locale: 'zh-CN',
    tags: ['demo'],
    gender: 'UNKNOWN',
    age_range: 'UNKNOWN',
    style_tags: [],
    notes: null,
    metadata_source: 'CATALOG',
    metadata_stale: true,
  },
]

const filters = (overrides: Partial<VoiceFilterState> = {}): VoiceFilterState => ({
  query: '',
  gender: 'ALL',
  age_range: 'ALL',
  style_tag: 'ALL',
  locale: 'ALL',
  metadata_status: 'ALL',
  ...overrides,
})

describe('P14 voice catalog classification filters', () => {
  it('combines gender, age and style filters', () => {
    expect(filterVoices(voices, filters({ gender: 'FEMALE', age_range: 'YOUNG_ADULT', style_tag: '温柔' })))
      .toEqual([voices[0]])
  })

  it('searches readable names, technical ids, notes and tags', () => {
    expect(filterVoices(voices, filters({ query: '女主角' }))).toEqual([voices[0]])
    expect(filterVoices(voices, filters({ query: 'voice-male-deep' }))).toEqual([voices[1]])
  })

  it('separates human-labeled, unlabeled and stale voices', () => {
    expect(filterVoices(voices, filters({ metadata_status: 'USER' }))).toEqual([voices[0], voices[1]])
    expect(filterVoices(voices, filters({ metadata_status: 'UNLABELED' }))).toEqual([voices[2]])
    expect(filterVoices(voices, filters({ metadata_status: 'STALE' }))).toEqual([voices[3]])
  })

  it('collects reusable style and locale categories from the catalog', () => {
    expect(collectVoiceFilterOptions(voices)).toEqual({
      style_tags: ['低沉', '沉稳', '温柔', '自然'],
      locales: ['en-US', 'zh-CN'],
    })
  })
})
