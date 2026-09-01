import { describe, expect, it } from 'vitest'
import type { BreakdownReadModelPayload } from '../types/breakdown-read-model'
import { IDENTITY_UI_STALE_WARNING, projectBreakdownReadModelForOrdinaryUi } from './breakdownReadModelUi'

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
        title: '客厅',
        scene_info: {
          location: '客厅',
          interior_exterior: '室内',
          time_of_day: '白天',
          environment: null,
        },
        people: [
          { ref: 'P1', display_name: '人物1', appearance: '黑衣' },
          { ref: 'P2', display_name: '人物2', appearance: '白衣' },
        ],
        story_summary: '两人在客厅。',
        shots: [{
          ordinal: 1,
          start_us: 0,
          end_us: 1_000_000,
          duration_us: 1_000_000,
          thumbnail_url: null,
          reference_url: null,
          visual_description: '两人面对面。',
          people: ['P1', 'P2'],
          performance: [{ text: '转身', people: ['P2'] }],
          dialogue: [{
            start_us: 100_000,
            end_us: 200_000,
            text: '对白原文不能改。',
            speakers: ['P2'],
          }],
          props: [{ label: '花瓶', interaction: 'subject_A：拿起花瓶' }],
          cinematography: { shot_type: '中景', composition: null, camera_motion: null },
          on_screen_text: [{ start_us: 300_000, end_us: 400_000, text: 'OCR 原文' }],
        }],
      }],
    },
    identity: {
      asset_revision_id: 'ASSETREV1',
      resolved_count: 1,
      unresolved_count: 1,
      warnings: ['部分人物尚未完成最终身份确认，当前仍以匿名人物显示。'],
      scenes: [{
        scene_ordinal: 1,
        people: [
          { ref: 'P1', display_name: '人物1', character: null },
          {
            ref: 'P2',
            display_name: '人物001',
            character: {
              id: 'CHAR1',
              name: '人物001',
              cover_url: '/api/content-analysis/characters/CAND1/cover',
            },
          },
        ],
      }],
    },
  }
}

describe('breakdownReadModelUi', () => {
  it('projects only safe Final Character display identity into the ordinary timeline copy', () => {
    const source = payload()
    const result = projectBreakdownReadModelForOrdinaryUi(source)

    expect(result.scenes[0].people[0]).toEqual({
      ref: 'P1',
      display_name: '人物1',
      appearance: '黑衣',
      final_character: null,
    })
    expect(result.scenes[0].people[1]).toEqual({
      ref: 'P2',
      display_name: '人物001',
      appearance: '白衣',
      final_character: {
        id: 'CHAR1',
        name: '人物001',
        cover_url: '/api/content-analysis/characters/CAND1/cover',
      },
    })
    expect(result.warnings).toContain('部分人物尚未完成最终身份确认，当前仍以匿名人物显示。')

    // Existing ordinary renderer resolves refs from scene.people, so action/dialogue labels now use Final name.
    expect(result.scenes[0].shots[0].performance[0].people).toEqual(['P2'])
    expect(result.scenes[0].shots[0].dialogue[0].speakers).toEqual(['P2'])

    // P6 cannot rewrite frozen facts. Existing G2.6 sanitizer may only strip subject_A/B from prop interaction.
    expect(result.scenes[0].shots[0].dialogue[0].text).toBe('对白原文不能改。')
    expect(result.scenes[0].shots[0].on_screen_text[0].text).toBe('OCR 原文')
    expect(result.scenes[0].shots[0].visual_description).toBe('两人面对面。')
    expect(result.scenes[0].shots[0].props[0].interaction).toBe('拿起花瓶')

    // Input read-model itself stays untouched.
    expect(source.timeline.scenes[0].people[1].display_name).toBe('人物2')
    expect(source.timeline.scenes[0].shots[0].props[0].interaction).toBe('subject_A：拿起花瓶')
  })

  it('fails closed when resolved counts or asset revision are invalid', () => {
    const badCount = payload()
    badCount.identity.resolved_count = 2
    const countResult = projectBreakdownReadModelForOrdinaryUi(badCount)
    expect(countResult.scenes[0].people.map((item) => item.display_name)).toEqual(['人物1', '人物2'])
    expect(countResult.warnings).toContain(IDENTITY_UI_STALE_WARNING)

    const noRevision = payload()
    noRevision.identity.asset_revision_id = null
    const revisionResult = projectBreakdownReadModelForOrdinaryUi(noRevision)
    expect(revisionResult.scenes[0].people.map((item) => item.display_name)).toEqual(['人物1', '人物2'])
    expect(revisionResult.scenes[0].people.every((item) => item.final_character === null)).toBe(true)
  })

  it('fails closed on Scene/P* mismatch instead of partially applying names', () => {
    const wrongRef = payload()
    wrongRef.identity.scenes[0].people[1].ref = 'P3'
    const refResult = projectBreakdownReadModelForOrdinaryUi(wrongRef)
    expect(refResult.scenes[0].people.map((item) => item.display_name)).toEqual(['人物1', '人物2'])

    const duplicateRef = payload()
    duplicateRef.identity.scenes[0].people[1].ref = 'P1'
    const duplicateResult = projectBreakdownReadModelForOrdinaryUi(duplicateRef)
    expect(duplicateResult.scenes[0].people.map((item) => item.display_name)).toEqual(['人物1', '人物2'])
  })

  it('rejects a resolved display whose name disagrees with Final Character', () => {
    const source = payload()
    source.identity.scenes[0].people[1].display_name = '对白里猜出的名字'

    const result = projectBreakdownReadModelForOrdinaryUi(source)

    expect(result.scenes[0].people.map((item) => item.display_name)).toEqual(['人物1', '人物2'])
    expect(result.warnings).toContain(IDENTITY_UI_STALE_WARNING)
  })
})
