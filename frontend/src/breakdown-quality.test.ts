import { describe, expect, it } from 'vitest'

import { evaluateBreakdownShotQuality, hasUnconfirmedSourcePeople } from './breakdown-quality'
import type { SceneTimelineShot } from './types/scene-timeline'

function makeShot(overrides: Partial<SceneTimelineShot> = {}): SceneTimelineShot {
  return {
    ordinal: 1,
    start_us: 0,
    end_us: 2_000_000,
    duration_us: 2_000_000,
    thumbnail_url: null,
    reference_url: '/media/shot-1.mp4',
    summary: '人物在室内说话。',
    narrative_function: '交代信息',
    visual_description: '一名人物坐在桌边看向镜头。',
    people: ['P1'],
    performance: [{ text: '人物坐在桌边并抬头看向对方', people: ['P1'] }],
    dialogue: [{ start_us: 200_000, end_us: 1_200_000, text: '你好', speakers: ['P1'] }],
    props: [],
    cinematography: {
      shot_type: '中景',
      composition: '人物位于画面中央',
      camera_motion: '固定',
    },
    on_screen_text: [],
    ...overrides,
  }
}

describe('evaluateBreakdownShotQuality', () => {
  it('uses visible expression even when action only says speaking', () => {
    expect(evaluateBreakdownShotQuality(makeShot({ performance: [{ text: '说话', people: ['P1'] }], performance_details: { expression: '惊讶', posture: '直立', gaze: '前方', interaction: null } })).ready).toBe(true)
  })
  it('does not accept unknown placeholders as performance evidence', () => {
    expect(evaluateBreakdownShotQuality(makeShot({ performance: [{ text: '说话', people: ['P1'] }], performance_details: { expression: '无法判断', posture: '未知', gaze: null, interaction: '暂无独立人物交互描述' } })).reason).toBe('动作/表情信息不足')
  })
  it('allows an observed lack of movement without inventing action', () => {
    expect(evaluateBreakdownShotQuality(makeShot({ performance: [{ text: '保持站姿，未见明显动作变化', people: ['P1'] }] })).ready).toBe(true)
  })
  it('does not waive speaker confirmation when expression is useful', () => {
    expect(evaluateBreakdownShotQuality(makeShot({ performance: [], performance_details: { expression: '皱眉', posture: null, gaze: null, interaction: null }, dialogue: [{ text: '你好', start_us: 0, end_us: 1000, speakers: [] }] })).reason).toBe('对白说话人待确认')
  })
  it('blocks completed status when dialogue speaker is unresolved', () => {
    const result = evaluateBreakdownShotQuality(makeShot({
      dialogue: [{ start_us: 200_000, end_us: 1_200_000, text: '你好', speakers: [] }],
    }))

    expect(result).toEqual({ ready: false, reason: '对白说话人待确认' })
  })

  it('allows a fully grounded shot with bound dialogue speaker', () => {
    expect(evaluateBreakdownShotQuality(makeShot())).toEqual({ ready: true, reason: '' })
  })
})

describe('formal source identity checks', () => {
  it('blocks missing and historical identity overlays', () => {
    expect(hasUnconfirmedSourcePeople(makeShot(), [])).toBe(true)
    expect(hasUnconfirmedSourcePeople(makeShot(), [{ ref: 'P1', display_name: '人物1', appearance: null }])).toBe(true)
  })
  it('checks off-screen speaker references too', () => {
    expect(hasUnconfirmedSourcePeople(makeShot({ people: [] }), [])).toBe(true)
  })
  it('accepts formal identity references and silent empty shots', () => {
    expect(hasUnconfirmedSourcePeople(makeShot(), [{ ref: 'P1', display_name: '人物1', appearance: null, final_character: { id: 'C1', name: '角色', cover_url: null } }])).toBe(false)
    expect(hasUnconfirmedSourcePeople(makeShot({ people: [], dialogue: [] }), [])).toBe(false)
  })
})
