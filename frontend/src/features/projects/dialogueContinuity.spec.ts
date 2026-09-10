import { describe, expect, it } from 'vitest'

import type { CanonicalDialogueBinding, SourceShotFact } from './shotBreakdown'
import { dialogueContinuity, dialogueContinuityText } from './dialogueContinuity'

function shot(startUs: number, endUs: number): SourceShotFact {
  return {
    shot_anchor_id: 'shot-1',
    shot_number: 1,
    start_us: startUs,
    end_us: endUs,
    duration_us: endUs - startUs,
    visual_description: 'test',
    camera_language: {
      shot_size: 'test',
      composition: 'test',
      angle_or_type: 'test',
      movement: 'test',
      focal_length_dof: 'test',
    },
    bindings: {
      characters: [],
      scenes: [],
      props: [],
      unresolved_subject_notes: [],
    },
    dialogue: [],
    sound_effects: [],
    ambience: [],
    visual_text_evidence_ids: [],
  }
}

function line(startUs: number, endUs: number): CanonicalDialogueBinding {
  return {
    utterance_id: 'utterance-1',
    utterance_number: 1,
    utterance_start_us: startUs,
    utterance_end_us: endUs,
    overlap_start_us: Math.max(startUs, 1_000_000),
    overlap_end_us: Math.min(endUs, 2_000_000),
    text: '黄阿姨',
    language: 'zh',
    delivery: 'DIALOGUE',
    speaker: null,
  }
}

describe('dialogue continuity', () => {
  const currentShot = shot(1_000_000, 2_000_000)

  it('keeps a dialogue fully contained in one shot standalone', () => {
    const item = line(1_100_000, 1_500_000)
    expect(dialogueContinuity(item, currentShot)).toBe('STANDALONE')
    expect(dialogueContinuityText(item, currentShot)).toBeNull()
  })

  it('marks a line that starts here and continues across the next cut as one utterance', () => {
    const item = line(1_200_000, 2_300_000)
    expect(dialogueContinuity(item, currentShot)).toBe('CONTINUES_TO_NEXT')
    expect(dialogueContinuityText(item, currentShot)).toBe('→ 延续下一镜 · 同一句')
  })

  it('marks the next-shot overlap as continuation of the same utterance', () => {
    const item = line(700_000, 1_300_000)
    expect(dialogueContinuity(item, currentShot)).toBe('CONTINUES_FROM_PREVIOUS')
    expect(dialogueContinuityText(item, currentShot)).toBe('← 承接上一镜 · 同一句')
  })

  it('marks an utterance that passes through the whole current shot', () => {
    const item = line(700_000, 2_300_000)
    expect(dialogueContinuity(item, currentShot)).toBe('PASSES_THROUGH')
    expect(dialogueContinuityText(item, currentShot)).toBe('↔ 跨镜延续 · 同一句')
  })
})
