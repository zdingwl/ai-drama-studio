import { describe, expect, it } from 'vitest'

import { buildCharacterCastingBrief, type CastingDialogueLine } from './p14CastingBrief'

describe('P14 character casting brief', () => {
  it('projects only current Target Bible and Target Script facts', () => {
    const lines: CastingDialogueLine[] = Array.from({ length: 7 }, (_, index) => ({
      utterance_id: `utt-${index + 1}`,
      utterance_number: index + 1,
      target_character_id: index === 2 ? 'target-other' : 'target-lila',
      final_target_dialogue: `Target line ${index + 1}`,
    }))


    const brief = buildCharacterCastingBrief(
      {
        target_character_id: 'target-lila',
        display_name: 'Lila Xu',
        localized_identity: 'Austin apartment resident and story lead.',
        personality_constraints: ['Direct under pressure', 'Keeps dry humor'],
      },
      lines,
      'en-US',
      'US',
      ['Use contemporary American English', 'Keep confrontational exchanges concise'],
    )

    expect(brief.target_character_id).toBe('target-lila')
    expect(brief.display_name).toBe('Lila Xu')
    expect(brief.task_summary).toBe('为 Lila Xu 选择能稳定完成 6 条目标对白的参考声线；只依据当前目标设定与目标剧本判断，不自动推断声线。')
    expect(brief.role_identity).toBe('Austin apartment resident and story lead.')
    expect(brief.target_locale).toBe('en-US / US')
    expect(brief.personality_constraints).toEqual(['Direct under pressure', 'Keeps dry humor'])
    expect(brief.dialogue_style_rules).toEqual(['Use contemporary American English', 'Keep confrontational exchanges concise'])
    expect(brief.dialogue_samples.map((item) => item.utterance_id)).toEqual(['utt-1', 'utt-4', 'utt-7'])
    expect(brief.dialogue_samples.map((item) => item.text)).toEqual(['Target line 1', 'Target line 4', 'Target line 7'])
  })

  it('does not invent samples or role requirements when no dialogue exists', () => {
    const brief = buildCharacterCastingBrief(
      {
        target_character_id: 'silent-character',
        display_name: 'Silent Character',
        localized_identity: 'A silent observer.',
        personality_constraints: [],
      },
      [],
      'en-US',
      'US',
      [],
    )

    expect(brief.dialogue_count).toBe(0)
    expect(brief.dialogue_samples).toEqual([])
    expect(brief.personality_constraints).toEqual([])
    expect(brief.dialogue_style_rules).toEqual([])
  })
})
