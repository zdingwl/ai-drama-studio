export type VoiceGender = 'UNKNOWN' | 'FEMALE' | 'MALE' | 'NEUTRAL'
export type VoiceAgeRange = 'UNKNOWN' | 'CHILD' | 'TEEN' | 'YOUNG_ADULT' | 'ADULT' | 'MATURE' | 'SENIOR'
export type VoiceMetadataStatus = 'ALL' | 'USER' | 'CATALOG' | 'UNLABELED' | 'STALE'

export interface VoiceFilterable {
  voice_key: string
  default_display_name: string
  display_name: string
  locale: string | null
  tags: string[]
  gender: VoiceGender
  age_range: VoiceAgeRange
  style_tags: string[]
  notes: string | null
  metadata_source: 'CATALOG' | 'USER'
  catalog_metadata_available: boolean
  catalog_description: string | null
  source_name: string | null
  license_name: string | null
  usage_notice: string | null
  metadata_stale: boolean
}

export interface VoiceFilterState {
  query: string
  gender: 'ALL' | VoiceGender
  age_range: 'ALL' | VoiceAgeRange
  style_tag: 'ALL' | string
  locale: 'ALL' | string
  metadata_status: VoiceMetadataStatus
}

export interface VoiceFilterOptions {
  style_tags: string[]
  locales: string[]
}

const normalize = (value: string | null | undefined) => (value ?? '').trim().toLocaleLowerCase()

export function collectVoiceFilterOptions<T extends VoiceFilterable>(voices: T[]): VoiceFilterOptions {
  const styleTags = new Set<string>()
  const locales = new Set<string>()
  for (const voice of voices) {
    for (const tag of voice.style_tags) {
      if (tag.trim()) styleTags.add(tag.trim())
    }
    if (voice.locale?.trim()) locales.add(voice.locale.trim())
  }
  return {
    style_tags: [...styleTags].sort((left, right) => left.localeCompare(right, 'zh-CN')),
    locales: [...locales].sort((left, right) => left.localeCompare(right, 'zh-CN')),
  }
}

function matchesMetadataStatus(voice: VoiceFilterable, status: VoiceMetadataStatus): boolean {
  if (status === 'ALL') return true
  if (status === 'STALE') return voice.metadata_stale
  if (status === 'USER') return voice.metadata_source === 'USER' && !voice.metadata_stale
  if (status === 'CATALOG') return voice.metadata_source === 'CATALOG' && voice.catalog_metadata_available && !voice.metadata_stale
  return voice.metadata_source === 'CATALOG' && !voice.catalog_metadata_available && !voice.metadata_stale
}

function matchesQuery(voice: VoiceFilterable, query: string): boolean {
  const needle = normalize(query)
  if (!needle) return true
  const haystack = [
    voice.display_name,
    voice.default_display_name,
    voice.voice_key,
    voice.locale,
    voice.notes,
    voice.catalog_description,
    voice.source_name,
    voice.license_name,
    voice.usage_notice,
    voice.gender,
    voice.age_range,
    ...voice.style_tags,
    ...voice.tags,
  ]
    .map((item) => normalize(item))
    .join('\n')
  return haystack.includes(needle)
}

export function filterVoices<T extends VoiceFilterable>(voices: T[], filters: VoiceFilterState): T[] {
  return voices.filter((voice) => {
    if (!matchesQuery(voice, filters.query)) return false
    if (filters.gender !== 'ALL' && voice.gender !== filters.gender) return false
    if (filters.age_range !== 'ALL' && voice.age_range !== filters.age_range) return false
    if (filters.style_tag !== 'ALL' && !voice.style_tags.includes(filters.style_tag)) return false
    if (filters.locale !== 'ALL' && voice.locale !== filters.locale) return false
    if (!matchesMetadataStatus(voice, filters.metadata_status)) return false
    return true
  })
}
