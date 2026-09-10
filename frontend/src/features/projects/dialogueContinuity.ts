import type { CanonicalDialogueBinding, SourceShotFact } from './shotBreakdown'

export type DialogueContinuity =
  | 'STANDALONE'
  | 'CONTINUES_TO_NEXT'
  | 'CONTINUES_FROM_PREVIOUS'
  | 'PASSES_THROUGH'

export function dialogueContinuity(
  line: CanonicalDialogueBinding,
  shot: SourceShotFact,
): DialogueContinuity {
  const fromPrevious = line.utterance_start_us < shot.start_us
  const toNext = line.utterance_end_us > shot.end_us

  if (fromPrevious && toNext) return 'PASSES_THROUGH'
  if (fromPrevious) return 'CONTINUES_FROM_PREVIOUS'
  if (toNext) return 'CONTINUES_TO_NEXT'
  return 'STANDALONE'
}

export function dialogueContinuityText(
  line: CanonicalDialogueBinding,
  shot: SourceShotFact,
): string | null {
  switch (dialogueContinuity(line, shot)) {
    case 'CONTINUES_TO_NEXT':
      return '→ 延续下一镜 · 同一句'
    case 'CONTINUES_FROM_PREVIOUS':
      return '← 承接上一镜 · 同一句'
    case 'PASSES_THROUGH':
      return '↔ 跨镜延续 · 同一句'
    default:
      return null
  }
}
