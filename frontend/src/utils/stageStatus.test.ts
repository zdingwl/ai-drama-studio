import { describe, expect, it } from 'vitest'
import { deriveStageStates } from './stageStatus'

describe('deriveStageStates', () => {
  it('does not mark downstream work complete just because episodes exist', () => {
    const states = deriveStageStates({
      episodes: [{ shot_count: 0, preprocess_status: null }],
      tasks: [],
      analysis: null,
    })

    expect(states[1]).toBe('completed')
    expect(states[2]).toBe('not_started')
    expect(states[3]).toBe('not_started')
    expect(states[4]).toBe('planned')
  })

  it('uses the latest relevant breakdown task instead of old failures', () => {
    const states = deriveStageStates({
      episodes: [{ shot_count: 12, preprocess_status: 'READY' }],
      tasks: [
        { task_type: 'EPISODE_BREAKDOWN_P2', status: 'FAILED', created_at: '2026-08-31T10:00:00Z' },
        { task_type: 'EPISODE_BREAKDOWN_P2', status: 'READY', created_at: '2026-09-01T10:00:00Z' },
      ],
      analysis: null,
    })

    expect(states[2]).toBe('completed')
  })

  it('keeps generated shots in review until a successful breakdown task is known', () => {
    const states = deriveStageStates({
      episodes: [{ shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: null,
    })

    expect(states[2]).toBe('review')
  })

  it('surfaces unresolved character evidence as asset review work', () => {
    const states = deriveStageStates({
      episodes: [{ shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: {
        status: 'READY',
        counts: { unresolved_character_candidates: 140 },
      },
    })

    expect(states[3]).toBe('review')
  })
})
