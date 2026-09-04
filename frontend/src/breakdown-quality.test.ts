import { describe, expect, it } from 'vitest'

import { evaluateBreakdownShotQuality } from './breakdown-quality'
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
