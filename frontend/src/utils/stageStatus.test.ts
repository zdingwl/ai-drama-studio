import { describe, expect, it } from 'vitest'
import { deriveStageStates } from './stageStatus'

describe('deriveStageStates', () => {
  it('does not mark downstream work complete just because episodes exist', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 0, preprocess_status: null }],
      tasks: [],
      analysis: null,
      breakdownRuns: [],
    })

    expect(states[1]).toBe('completed')
    expect(states[2]).toBe('not_started')
    expect(states[3]).toBe('not_started')
    expect(states[4]).toBe('planned')
  })

  it('marks stage two complete only when every episode has a current READY run on the current ShotRevision', () => {
    const states = deriveStageStates({
      episodes: [
        { id: 'E1', shot_count: 12, preprocess_status: 'READY' },
        { id: 'E2', shot_count: 8, preprocess_status: 'READY' },
      ],
      tasks: [],
      analysis: null,
      breakdownRuns: [
        { episode_id: 'E1', status: 'READY', is_current: true, source_shot_revision: { is_current: true } },
        { episode_id: 'E2', status: 'READY', is_current: true, source_shot_revision: { is_current: true } },
      ],
    })

    expect(states[2]).toBe('completed')
  })

  it('keeps generated shots in review until a current breakdown result exists', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [{ task_type: 'EPISODE_SHOTS', status: 'READY', created_at: '2026-09-01T10:00:00Z' }],
      analysis: null,
      breakdownRuns: [],
    })

    expect(states[2]).toBe('review')
  })

  it('returns to review when the current Breakdown Run points at a stale ShotRevision', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: null,
      breakdownRuns: [
        { episode_id: 'E1', status: 'READY', is_current: true, source_shot_revision: { is_current: false } },
      ],
    })

    expect(states[2]).toBe('review')
  })

  it('does not call a multi-episode project complete when one episode has no current result', () => {
    const states = deriveStageStates({
      episodes: [
        { id: 'E1', shot_count: 12, preprocess_status: 'READY' },
        { id: 'E2', shot_count: 8, preprocess_status: 'READY' },
      ],
      tasks: [],
      analysis: null,
      breakdownRuns: [
        { episode_id: 'E1', status: 'READY', is_current: true, source_shot_revision: { is_current: true } },
      ],
    })

    expect(states[2]).toBe('review')
  })

  it('shows a newly created breakdown task as processing immediately', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [{ task_type: 'EPISODE_BREAKDOWN_P2', status: 'PROCESSING', created_at: '2026-09-01T10:00:00Z' }],
      analysis: null,
      breakdownRuns: [],
    })

    expect(states[2]).toBe('processing')
  })

  it('surfaces unresolved character evidence as asset review work', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: {
        status: 'READY',
        counts: { unresolved_character_candidates: 140 },
      },
      breakdownRuns: [],
    })

    expect(states[3]).toBe('review')
  })

  it('shows an active asset extraction task as processing', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [{ task_type: 'ASSET_EXTRACTION_V3', status: 'PROCESSING', created_at: '2026-09-01T10:00:00Z' }],
      analysis: { status: 'READY', counts: {} },
      breakdownRuns: [],
    })

    expect(states[3]).toBe('processing')
  })
})
