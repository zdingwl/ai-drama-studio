import type { BreakdownTimelineEvent } from '../types/breakdown'

export interface DialogueDisplayState {
  events: BreakdownTimelineEvent[]
  continuedGroupCount: number
}

function metadataFlag(event: BreakdownTimelineEvent, key: string): boolean {
  const value = event.metadata?.[key]
  if (value === true || value === 1) return true
  return String(value ?? '').trim().toLowerCase() === 'true'
}

function projectionIndex(event: BreakdownTimelineEvent): number {
  const value = Number(event.metadata?.projection_index)
  return Number.isFinite(value) ? value : 0
}

function groupKey(event: BreakdownTimelineEvent): string {
  const value = event.metadata?.dialogue_group_id ?? event.metadata?.asr_segment_id
  const key = String(value ?? '').trim()
  return key || event.id
}

function isContinuationProjection(event: BreakdownTimelineEvent): boolean {
  return metadataFlag(event, 'continues_from_previous_shot') || projectionIndex(event) > 1
}

/**
 * E1 keeps the complete ASR sentence on every Shot projection so backend truth remains intact.
 * The normal result UI should not print that same sentence again after a cut. We therefore
 * render the sentence only on its first projection and treat later projections as a silent
 * "continues from previous Shot" state. Historical runs without projection metadata keep their
 * previous display behavior.
 */
export function buildDialogueDisplay(events: BreakdownTimelineEvent[]): DialogueDisplayState {
  const seen = new Set<string>()
  const continued = new Set<string>()
  const visible: BreakdownTimelineEvent[] = []

  for (const event of events) {
    if (event.event_type !== 'DIALOGUE') continue
    const key = groupKey(event)
    if (seen.has(key)) continue
    seen.add(key)

    if (isContinuationProjection(event)) {
      continued.add(key)
      continue
    }
    visible.push(event)
  }

  return {
    events: visible,
    continuedGroupCount: continued.size,
  }
}
