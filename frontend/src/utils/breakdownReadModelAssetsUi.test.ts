import { describe, expect, it } from 'vitest'
import type { BreakdownReadModelPayload } from '../types/breakdown-read-model'
import {
  FINAL_ASSET_UI_STALE_WARNING,
  projectBreakdownReadModelForOrdinaryUi,
} from './breakdownReadModelUi'

function payload(): BreakdownReadModelPayload {
  return {
    schema_version: 'breakdown-read-model-v1',
    timeline: {
      schema_version: 'scene-timeline-v1',
      source_breakdown_run_id: 'RUN1',
      source_shot_revision_id: 'REV1',
      episode_id: 'EP1',
      status: 'READY',
      is_current: true,
      scene_count: 1,
      shot_count: 1,
      warnings: [],
      scenes: [{
        ordinal: 1,
        start_us: 0,
        end_us: 1_000_000,
        duration_us: 1_000_000,
        title: '客厅争执',
        scene_info: {
          location: '客厅',
          interior_exterior: '室内',
          time_of_day: '白天',
          environment: '窗边有自然光',
        },
        people: [{ ref: 'P1', display_name: '人物1', appearance: '黑衣' }],
        story_summary: '人物站在窗边。',
        shots: [{
          ordinal: 1,
          start_us: 0,
          end_us: 1_000_000,
          duration_us: 1_000_000,
          thumbnail_url: null,
          reference_url: null,
          visual_description: '桌上有花瓶。',
          people: ['P1'],
          performance: [],
          dialogue: [{ start_us: 100_000, end_us: 200_000, text: '对白原文', speakers: [] }],
          props: [{ label: '花瓶', interaction: 'subject_A：拿起' }],
          cinematography: { shot_type: null, composition: null, camera_motion: null },
          on_screen_text: [{ start_us: 300_000, end_us: 400_000, text: 'OCR 原文' }],
        }],
      }],
    },
    identity: {
      asset_revision_id: 'ASSETREV1',
      resolved_count: 1,
      unresolved_count: 0,
      warnings: [],
      scenes: [{
        scene_ordinal: 1,
        people: [{
          ref: 'P1',
          display_name: '人物001',
          character: {
            id: 'CHAR1',
            name: '人物001',
            cover_url: '/character.jpg',
          },
        }],
      }],
    },
    assets: {
      asset_revision_id: 'ASSETREV1',
      warnings: [],
      scenes: [{
        scene_ordinal: 1,
        scene: { id: 'SCENE1', name: '公寓客厅', cover_url: '/scene.jpg' },
      }],
      shots: [{
        scene_ordinal: 1,
        shot_ordinal: 1,
        props: [
          { id: 'PROP1', name: '蓝色花瓶', cover_url: null },
          { id: 'PROP2', name: '黑色手提包', cover_url: '/bag.jpg' },
        ],
      }],
    },
  }
}

describe('breakdownReadModel Final Scene/Prop projection', () => {
  it('adds display-only Final Scene/Prop assets without rewriting frozen G2 facts', () => {
    const source = payload()
    const result = projectBreakdownReadModelForOrdinaryUi(source)

    expect(result.scenes[0].title).toBe('客厅争执')
    expect(result.scenes[0].scene_info.location).toBe('客厅')
    expect(result.scenes[0].final_scene).toEqual({
      id: 'SCENE1',
      name: '公寓客厅',
      cover_url: '/scene.jpg',
    })
    expect(result.scenes[0].shots[0].final_props).toEqual([
      { id: 'PROP1', name: '蓝色花瓶', cover_url: null },
      { id: 'PROP2', name: '黑色手提包', cover_url: '/bag.jpg' },
    ])

    // Final Prop is a separate binding projection. G2 observed prop text remains its own truth.
    expect(result.scenes[0].shots[0].props).toEqual([{ label: '花瓶', interaction: '拿起' }])
    expect(result.scenes[0].shots[0].dialogue[0].text).toBe('对白原文')
    expect(result.scenes[0].shots[0].on_screen_text[0].text).toBe('OCR 原文')

    // Character projection remains independent and safe.
    expect(result.scenes[0].people[0].display_name).toBe('人物001')
    expect(result.scenes[0].people[0].final_character?.id).toBe('CHAR1')

    // Source read model is immutable from the UI projection point of view.
    expect(source.timeline.scenes[0].final_scene).toBeUndefined()
    expect(source.timeline.scenes[0].shots[0].final_props).toBeUndefined()
    expect(source.timeline.scenes[0].shots[0].props[0].interaction).toBe('subject_A：拿起')
  })

  it('invalid asset overlay clears only Final Scene/Prop while keeping safe Character identity', () => {
    const source = payload()
    source.assets!.shots[0].shot_ordinal = 9

    const result = projectBreakdownReadModelForOrdinaryUi(source)

    expect(result.scenes[0].final_scene).toBeNull()
    expect(result.scenes[0].shots[0].final_props).toEqual([])
    expect(result.warnings).toContain(FINAL_ASSET_UI_STALE_WARNING)
    expect(result.scenes[0].people[0].display_name).toBe('人物001')
    expect(result.scenes[0].people[0].final_character?.id).toBe('CHAR1')
  })

  it('duplicate or malformed Final Props fail closed instead of falling back to G2 prop labels', () => {
    const duplicate = payload()
    duplicate.assets!.shots[0].props = [
      { id: 'PROP1', name: '蓝色花瓶', cover_url: null },
      { id: 'PROP1', name: '另一个名字', cover_url: null },
    ]
    const duplicateResult = projectBreakdownReadModelForOrdinaryUi(duplicate)
    expect(duplicateResult.scenes[0].shots[0].final_props).toEqual([])
    expect(duplicateResult.scenes[0].shots[0].props[0].label).toBe('花瓶')

    const noRevision = payload()
    noRevision.assets!.asset_revision_id = null
    const noRevisionResult = projectBreakdownReadModelForOrdinaryUi(noRevision)
    expect(noRevisionResult.scenes[0].final_scene).toBeNull()
    expect(noRevisionResult.scenes[0].shots[0].final_props).toEqual([])
  })

  it('backend asset warnings are surfaced without suppressing a structurally safe overlay', () => {
    const source = payload()
    source.assets!.warnings = ['部分场景没有统一 Final Scene，保留拉片场景。']
    source.assets!.scenes[0].scene = null

    const result = projectBreakdownReadModelForOrdinaryUi(source)

    expect(result.scenes[0].final_scene).toBeNull()
    expect(result.scenes[0].shots[0].final_props?.length).toBe(2)
    expect(result.warnings).toContain('部分场景没有统一 Final Scene，保留拉片场景。')
  })
})
