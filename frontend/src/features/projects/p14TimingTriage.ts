import type { TimingItem } from './p14'
import type { ReplicaTargetScriptContent } from './targetScript'

export const MIN_RETAKE_DURATION_FACTOR = 0.8

export type TimingTriageRoute = 'FIT' | 'RETAKE_TRY' | 'SCRIPT_REWRITE'

export interface TimingTriageRow {
  item: TimingItem
  episode_id: string
  episode_order: number
  final_target_dialogue: string
  required_duration_factor: number | null
  route: TimingTriageRoute
}

export interface TimingTriageSummary {
  total: number
  fit: number
  overflow: number
  retake_try: number
  script_rewrite: number
}

export interface TimingEpisodeTriage {
  episode_id: string
  episode_order: number
  total: number
  fit: number
  overflow: number
  retake_try: number
  script_rewrite: number
}

export function requiredDurationFactor(item: TimingItem): number | null {
  if (item.actual_speech_duration_us <= 0) return null
  return item.source_slot_duration_us / item.actual_speech_duration_us
}

export function triageTimingItem(item: TimingItem): TimingTriageRoute {
  if (item.fit_status === 'FIT') return 'FIT'
  const required = requiredDurationFactor(item)
  if (required !== null && required >= MIN_RETAKE_DURATION_FACTOR) return 'RETAKE_TRY'
  return 'SCRIPT_REWRITE'
}

export function buildTimingTriageRows(
  items: TimingItem[],
  script: ReplicaTargetScriptContent | null | undefined,
): TimingTriageRow[] {
  const dialogue = new Map<string, { episode_id: string; episode_order: number; final_target_dialogue: string }>()
  for (const episode of script?.episodes ?? []) {
    for (const line of episode.dialogue ?? []) {
      dialogue.set(line.utterance_id, {
        episode_id: episode.episode_id,
        episode_order: episode.episode_order,
        final_target_dialogue: line.final_target_dialogue,
      })
    }
  }

  return items.map((item) => {
    const line = dialogue.get(item.utterance_id)
    return {
      item,
      episode_id: line?.episode_id ?? 'unknown',
      episode_order: line?.episode_order ?? 999999,
      final_target_dialogue: line?.final_target_dialogue ?? '',
      required_duration_factor: requiredDurationFactor(item),
      route: triageTimingItem(item),
    }
  })
}

export function summarizeTimingTriage(rows: TimingTriageRow[]): TimingTriageSummary {
  return rows.reduce<TimingTriageSummary>((summary, row) => {
    summary.total += 1
    if (row.route === 'FIT') summary.fit += 1
    else {
      summary.overflow += 1
      if (row.route === 'RETAKE_TRY') summary.retake_try += 1
      else summary.script_rewrite += 1
    }
    return summary
  }, { total: 0, fit: 0, overflow: 0, retake_try: 0, script_rewrite: 0 })
}

export function summarizeTimingTriageByEpisode(rows: TimingTriageRow[]): TimingEpisodeTriage[] {
  const episodes = new Map<string, TimingEpisodeTriage>()
  for (const row of rows) {
    const key = `${row.episode_order}:${row.episode_id}`
    let summary = episodes.get(key)
    if (!summary) {
      summary = {
        episode_id: row.episode_id,
        episode_order: row.episode_order,
        total: 0,
        fit: 0,
        overflow: 0,
        retake_try: 0,
        script_rewrite: 0,
      }
      episodes.set(key, summary)
    }
    summary.total += 1
    if (row.route === 'FIT') summary.fit += 1
    else {
      summary.overflow += 1
      if (row.route === 'RETAKE_TRY') summary.retake_try += 1
      else summary.script_rewrite += 1
    }
  }
  return [...episodes.values()].sort((left, right) => left.episode_order - right.episode_order)
}
