import { describe, expect, it } from 'vitest'

import { buildRetakeClipContexts, filterRetakeClipContexts } from './p14RetakeFilters'

const clips: any[] = [
  { utterance_id: 'ep1-u1', utterance_number: 1, target_character_id: 'lila', final_target_dialogue: 'Mrs. Henderson.', voice_id: 'v1', voice_label: 'Lila voice' },
  { utterance_id: 'ep1-u2', utterance_number: 2, target_character_id: 'jake', final_target_dialogue: 'Left, go left!', voice_id: 'v2', voice_label: 'Jake voice' },
  { utterance_id: 'ep2-u1', utterance_number: 1, target_character_id: 'marnie', final_target_dialogue: 'What is wrong with your wife?', voice_id: 'v3', voice_label: 'Marnie voice' },
]

const script: any = {
  episodes: [
    { episode_id: 'ep-1', episode_order: 1, dialogue: [{ utterance_id: 'ep1-u1', target_character_id: 'lila' }, { utterance_id: 'ep1-u2', target_character_id: 'jake' }] },
    { episode_id: 'ep-2', episode_order: 2, dialogue: [{ utterance_id: 'ep2-u1', target_character_id: 'marnie' }] },
  ],
}
const bible: any = {
  characters: [
    { target_character_id: 'lila', display_name: 'Lila Xu' },
    { target_character_id: 'jake', display_name: 'Jake Miller' },
    { target_character_id: 'marnie', display_name: 'Marnie Miller' },
  ],
}

describe('P14 retake filters', () => {
  it('projects episode and readable character context from CURRENT Target Script/Bible', () => {
    const rows = buildRetakeClipContexts(clips as any, script, bible, [{ utterance_id: 'ep1-u2', fit_status: 'OVERFLOW' }] as any, new Set(['ep2-u1']))
    expect(rows.map((row) => [row.episode_order, row.character_name, row.is_overflow, row.selected])).toEqual([
      [1, 'Lila Xu', false, false],
      [1, 'Jake Miller', true, false],
      [2, 'Marnie Miller', false, true],
    ])
  })

  it('combines overflow, selected and keyword filters without changing selection state', () => {
    const rows = buildRetakeClipContexts(clips as any, script, bible, [{ utterance_id: 'ep1-u2', fit_status: 'OVERFLOW' }] as any, new Set(['ep1-u2', 'ep2-u1']))
    expect(filterRetakeClipContexts(rows, { query: '', overflow_only: true, selected_only: true }).map((row) => row.clip.utterance_id)).toEqual(['ep1-u2'])
    expect(filterRetakeClipContexts(rows, { query: 'marnie', overflow_only: false, selected_only: false }).map((row) => row.clip.utterance_id)).toEqual(['ep2-u1'])
    expect(filterRetakeClipContexts(rows, { query: '第1集', overflow_only: false, selected_only: false })).toHaveLength(2)
  })
})
