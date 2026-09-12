import type { AudioClip, TimingItem } from './p14'
import type { ReplicaTargetBibleContent } from './targetBible'
import type { ReplicaTargetScriptContent } from './targetScript'

export interface RetakeClipContext {
  clip: AudioClip
  episode_id: string
  episode_order: number
  character_id: string | null
  character_name: string
  is_overflow: boolean
  selected: boolean
}

export interface RetakeFilterState {
  query: string
  overflow_only: boolean
  selected_only: boolean
}

export function buildRetakeClipContexts(
  clips: AudioClip[],
  script: ReplicaTargetScriptContent | null | undefined,
  bible: ReplicaTargetBibleContent | null | undefined,
  timingItems: TimingItem[],
  selectedIds: Set<string>,
): RetakeClipContext[] {
  const lineContext = new Map<string, { episode_id: string; episode_order: number; character_id: string | null }>()
  for (const episode of script?.episodes ?? []) {
    for (const line of episode.dialogue ?? []) {
      lineContext.set(line.utterance_id, {
        episode_id: episode.episode_id,
        episode_order: episode.episode_order,
        character_id: line.target_character_id,
      })
    }
  }

  const characterNames = new Map(
    (bible?.characters ?? []).map((character) => [character.target_character_id, character.display_name]),
  )
  const overflowIds = new Set(
    timingItems.filter((item) => item.fit_status === 'OVERFLOW').map((item) => item.utterance_id),
  )

  return clips.map((clip) => {
    const line = lineContext.get(clip.utterance_id)
    const characterId = line?.character_id ?? clip.target_character_id ?? null
    return {
      clip,
      episode_id: line?.episode_id ?? 'unknown',
      episode_order: line?.episode_order ?? 999999,
      character_id: characterId,
      character_name: characterId ? (characterNames.get(characterId) ?? '未命名角色') : '未绑定角色',
      is_overflow: overflowIds.has(clip.utterance_id),
      selected: selectedIds.has(clip.utterance_id),
    }
  })
}

export function filterRetakeClipContexts(
  rows: RetakeClipContext[],
  filters: RetakeFilterState,
): RetakeClipContext[] {
  const query = filters.query.trim().toLocaleLowerCase()
  return rows.filter((row) => {
    if (filters.overflow_only && !row.is_overflow) return false
    if (filters.selected_only && !row.selected) return false
    if (!query) return true

    const clip = row.clip
    const haystack = [
      clip.final_target_dialogue,
      clip.voice_label ?? '',
      clip.voice_id,
      row.character_name,
      row.character_id ?? '',
      `#${clip.utterance_number}`,
      `第${row.episode_order}集`,
    ].join('\n').toLocaleLowerCase()
    return haystack.includes(query)
  })
}
