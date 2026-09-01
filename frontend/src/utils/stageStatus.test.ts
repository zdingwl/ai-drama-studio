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
    expect(states[4]).toBe('not_started')
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

  it('does not treat a stale failed Breakdown Run as a current blocker', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: null,
      breakdownRuns: [
        { episode_id: 'E1', status: 'FAILED', is_current: true, source_shot_revision: { is_current: false } },
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

  it('keeps assets in review until a final non-stale workspace revision exists', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: { status: 'READY', counts: { unresolved_character_candidates: 0 } },
      breakdownRuns: [],
      assetWorkspace: { status: 'READY', stale: false, revision: null },
    })

    expect(states[3]).toBe('review')
  })

  it('keeps assets in review when AI evidence conflicts with the current final binding', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: { status: 'READY', counts: { unresolved_character_candidates: 0 } },
      breakdownRuns: [],
      assetWorkspace: {
        status: 'READY',
        stale: false,
        revision: { id: 'REV1' },
        bindings_by_shot: {
          S1: { character_ids: ['CHAR_A'], scene_id: 'SCENE_A', prop_ids: [] },
        },
        evidence_by_shot: {
          S1: {
            characters: [{ confidence: 0.95, final_asset_id: 'CHAR_B' }],
            scene: { confidence: 0.95, final_asset_id: 'SCENE_A' },
            props: [],
          },
        },
      },
    })

    expect(states[3]).toBe('review')
  })

  it('keeps assets in review when high-confidence evidence has not been bound', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: { status: 'READY', counts: { unresolved_character_candidates: 0 } },
      breakdownRuns: [],
      assetWorkspace: {
        status: 'READY',
        stale: false,
        revision: { id: 'REV1' },
        bindings_by_shot: {
          S1: { character_ids: [], scene_id: null, prop_ids: [] },
        },
        evidence_by_shot: {
          S1: {
            characters: [],
            scene: { confidence: 0.92, final_asset_id: 'SCENE_A' },
            props: [],
          },
        },
      },
    })

    expect(states[3]).toBe('review')
  })

  it('keeps actionable low-confidence evidence in review until the suggested final asset is confirmed', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: { status: 'READY', counts: { unresolved_character_candidates: 0 } },
      breakdownRuns: [],
      assetWorkspace: {
        status: 'READY',
        stale: false,
        revision: { id: 'REV1' },
        bindings_by_shot: {
          S1: { character_ids: [], scene_id: null, prop_ids: [] },
        },
        evidence_by_shot: {
          S1: {
            characters: [{ confidence: 0.62, final_asset_id: 'CHAR_A' }],
            scene: null,
            props: [],
          },
        },
      },
    })

    expect(states[3]).toBe('review')
  })

  it('clears low-confidence review after a human confirms the same final asset', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: { status: 'READY', counts: { unresolved_character_candidates: 0 } },
      breakdownRuns: [],
      assetWorkspace: {
        status: 'READY',
        stale: false,
        revision: { id: 'REV1' },
        bindings_by_shot: {
          S1: { character_ids: ['CHAR_A'], scene_id: null, prop_ids: [] },
        },
        evidence_by_shot: {
          S1: {
            characters: [{ confidence: 0.62, final_asset_id: 'CHAR_A' }],
            scene: null,
            props: [],
          },
        },
      },
    })

    expect(states[3]).toBe('completed')
  })

  it('marks assets complete only with a READY non-stale final revision, no unresolved evidence, and no inbox review work', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 12, preprocess_status: 'READY' }],
      tasks: [],
      analysis: { status: 'READY', counts: { unresolved_character_candidates: 0 } },
      breakdownRuns: [],
      assetWorkspace: {
        status: 'READY',
        stale: false,
        revision: { id: 'REV1' },
        bindings_by_shot: {
          S1: { character_ids: ['CHAR_A'], scene_id: 'SCENE_A', prop_ids: ['PROP_A'] },
        },
        evidence_by_shot: {
          S1: {
            characters: [{ confidence: 0.95, final_asset_id: 'CHAR_A' }],
            scene: { confidence: 0.95, final_asset_id: 'SCENE_A' },
            props: [{ confidence: 0.9, final_asset_id: 'PROP_A' }],
          },
        },
      },
    })

    expect(states[3]).toBe('completed')
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

  it('marks Stage 04 editing when at least one current draft is in progress', () => {
    const states = deriveStageStates({
      episodes: [
        { id: 'E1', shot_count: 10, preprocess_status: 'READY' },
        { id: 'E2', shot_count: 10, preprocess_status: 'READY' },
      ],
      tasks: [],
      analysis: null,
      localizationDrafts: [
        { episode_id: 'E1', status: 'DRAFT', stale: false, progress: { total: 8, pending: 3 } },
      ],
    })

    expect(states[4]).toBe('editing')
  })

  it('marks Stage 04 review when a draft is in review', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 10, preprocess_status: 'READY' }],
      tasks: [],
      analysis: null,
      localizationDrafts: [
        { episode_id: 'E1', status: 'IN_REVIEW', stale: false, progress: { total: 8, pending: 0 } },
      ],
    })

    expect(states[4]).toBe('review')
  })

  it('blocks Stage 04 when its immutable source anchor is stale', () => {
    const states = deriveStageStates({
      episodes: [{ id: 'E1', shot_count: 10, preprocess_status: 'READY' }],
      tasks: [],
      analysis: null,
      localizationDrafts: [
        { episode_id: 'E1', status: 'DRAFT', stale: true, progress: { total: 8, pending: 0 } },
      ],
    })

    expect(states[4]).toBe('blocked')
  })

  it('marks Stage 04 complete only when every episode is FINAL', () => {
    const states = deriveStageStates({
      episodes: [
        { id: 'E1', shot_count: 10, preprocess_status: 'READY' },
        { id: 'E2', shot_count: 9, preprocess_status: 'READY' },
      ],
      tasks: [],
      analysis: null,
      localizationDrafts: [
        { episode_id: 'E1', status: 'FINAL', stale: false, progress: { total: 8, pending: 0 } },
        { episode_id: 'E2', status: 'FINAL', stale: false, progress: { total: 6, pending: 0 } },
      ],
    })

    expect(states[4]).toBe('completed')
  })
})