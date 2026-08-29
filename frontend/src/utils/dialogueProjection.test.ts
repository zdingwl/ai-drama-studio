import { describe, expect, it } from 'vitest'
import type { BreakdownTimelineEvent } from '../types/breakdown'
import { buildDialogueDisplay } from './dialogueProjection'

function dialogue(
  id: string,
  text: string,
  metadata: Record<string, unknown> = {},
): BreakdownTimelineEvent {
  return {
    id,
    run_id: 'RUN',
    shot_draft_id: 'SHOT',
    ordinal: 1,
    event_type: 'DIALOGUE',
    source_start_us: 0,
    source_end_us: 1_000_000,
    shot_relative_start_us: 0,
    shot_relative_end_us: 1_000_000,
    content_text: text,
    language: 'zh-CN',
    emotion_hint: null,
    speaking_style_hint: null,
    confidence: null,
    origin: 'ASR',
    metadata,
    participants: [],
  }
}

describe('buildDialogueDisplay', () => {
  it('keeps the first projection of a cross-shot dialogue', () => {
    const state = buildDialogueDisplay([
      dialogue('E1', '王阿姨', {
        dialogue_group_id: 'ASR_1',
        projection_index: 1,
        continues_from_previous_shot: false,
        continues_to_next_shot: true,
      }),
    ])

    expect(state.events.map((item) => item.content_text)).toEqual(['王阿姨'])
    expect(state.continuedGroupCount).toBe(0)
  })

  it('suppresses the repeated full sentence on later Shot projections', () => {
    const state = buildDialogueDisplay([
      dialogue('E2', '王阿姨', {
        dialogue_group_id: 'ASR_1',
        projection_index: 2,
        continues_from_previous_shot: true,
      }),
      dialogue('E3', '我刚到的花', {
        dialogue_group_id: 'ASR_2',
        projection_index: 1,
      }),
    ])

    expect(state.events.map((item) => item.content_text)).toEqual(['我刚到的花'])
    expect(state.continuedGroupCount).toBe(1)
  })

  it('deduplicates repeated rows from the same dialogue group inside one Shot', () => {
    const state = buildDialogueDisplay([
      dialogue('E1', '同一句', { dialogue_group_id: 'ASR_1' }),
      dialogue('E2', '同一句', { dialogue_group_id: 'ASR_1' }),
    ])

    expect(state.events).toHaveLength(1)
  })

  it('keeps historical dialogue rows that have no projection metadata', () => {
    const state = buildDialogueDisplay([dialogue('OLD', '旧结果对白')])

    expect(state.events.map((item) => item.content_text)).toEqual(['旧结果对白'])
    expect(state.continuedGroupCount).toBe(0)
  })
})
