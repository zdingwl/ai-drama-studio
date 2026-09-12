import { describe, expect, it } from 'vitest'

import type { TimingItem } from './p14'
import {
  buildTimingTriageRows,
  requiredDurationFactor,
  summarizeTimingTriage,
  summarizeTimingTriageByEpisode,
  triageTimingItem,
} from './p14TimingTriage'

const item = (overrides: Partial<TimingItem>): TimingItem => ({
  utterance_id: 'utt-1',
  utterance_number: 1,
  source_slot_duration_us: 4_000_000,
  actual_speech_duration_us: 5_000_000,
  residual_hold_us: 0,
  overflow_us: 1_000_000,
  fit_status: 'OVERFLOW',
  ...overrides,
})

describe('P14 timing overflow triage', () => {
  it('treats the 0.8 product boundary as a retake candidate without auto-applying it', () => {
    const row = item({ source_slot_duration_us: 4_000_000, actual_speech_duration_us: 5_000_000 })
    expect(requiredDurationFactor(row)).toBeCloseTo(0.8)
    expect(triageTimingItem(row)).toBe('RETAKE_TRY')
  })

  it('routes overflow below the minimum product factor back to Target Script', () => {
    const row = item({ source_slot_duration_us: 3_000_000, actual_speech_duration_us: 5_000_000, overflow_us: 2_000_000 })
    expect(requiredDurationFactor(row)).toBeCloseTo(0.6)
    expect(triageTimingItem(row)).toBe('SCRIPT_REWRITE')
  })

  it('keeps already fitting dialogue out of retake/script rewrite buckets', () => {
    const row = item({ fit_status: 'FIT', source_slot_duration_us: 5_000_000, actual_speech_duration_us: 4_000_000, overflow_us: 0, residual_hold_us: 1_000_000 })
    expect(triageTimingItem(row)).toBe('FIT')
  })

  it('maps episode/text facts from CURRENT Target Script and summarizes without changing timing facts', () => {
    const items = [
      item({ utterance_id: 'utt-1' }),
      item({ utterance_id: 'utt-2', utterance_number: 2, source_slot_duration_us: 3_000_000, actual_speech_duration_us: 5_000_000, overflow_us: 2_000_000 }),
    ]
    const script = {
      schema_version: '1.0',
      title: 'Target',
      target_language: 'en-US',
      target_region: 'US',
      source_snapshot_artifact_id: 'source',
      adaptation_plan_artifact_id: 'plan',
      target_bible_artifact_id: 'bible',
      episodes: [
        {
          episode_id: 'ep-1',
          episode_order: 1,
          dialogue: [
            { utterance_id: 'utt-1', utterance_number: 1, source_start_us: 0, source_end_us: 4_000_000, source_text: '', source_language: 'zh', target_character_id: 'c1', translation_text: '', localization_text: '', final_target_dialogue: 'First target line', localization_notes: [] },
            { utterance_id: 'utt-2', utterance_number: 2, source_start_us: 5_000_000, source_end_us: 8_000_000, source_text: '', source_language: 'zh', target_character_id: 'c1', translation_text: '', localization_text: '', final_target_dialogue: 'Second target line', localization_notes: [] },
          ],
        },
      ],
    }

    const rows = buildTimingTriageRows(items, script)
    expect(rows.map((row) => row.final_target_dialogue)).toEqual(['First target line', 'Second target line'])
    expect(summarizeTimingTriage(rows)).toEqual({ total: 2, fit: 0, overflow: 2, retake_try: 1, script_rewrite: 1 })
    expect(summarizeTimingTriageByEpisode(rows)).toEqual([
      { episode_id: 'ep-1', episode_order: 1, total: 2, fit: 0, overflow: 2, retake_try: 1, script_rewrite: 1 },
    ])
  })
})
