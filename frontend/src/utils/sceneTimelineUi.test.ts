import { describe, expect, it } from 'vitest'
import {
  cinematographyItems,
  personDisplayName,
  publicInteractionText,
  sanitizeOrdinarySceneTimelinePayload,
  sceneInfoTags,
  timelineDuration,
  timelineTime,
} from './sceneTimelineUi'

describe('sceneTimelineUi', () => {
  it('formats microsecond timeline values for ordinary-user display', () => {
    expect(timelineTime(0)).toBe('00:00.00')
    expect(timelineTime(65_250_000)).toBe('01:05.25')
    expect(timelineDuration(4_250_000)).toBe('4.3 秒')
    expect(timelineDuration(12_600_000)).toBe('13 秒')
  })

  it('keeps only readable scene and cinematography values', () => {
    expect(sceneInfoTags({
      location: '公寓走廊',
      interior_exterior: '室内',
      time_of_day: '白天',
      environment: '走廊内有花瓶',
    })).toEqual(['公寓走廊', '室内', '白天'])

    expect(cinematographyItems({
      shot_type: '近景',
      composition: null,
      camera_motion: '固定',
    })).toEqual(['近景', '固定'])
  })

  it('maps Scene-local refs to ordinary display names without exposing refs', () => {
    const people = [
      { ref: 'P1', display_name: '人物1', appearance: '年轻女性' },
      { ref: 'P2', display_name: '人物2', appearance: '老年女性' },
    ]
    expect(personDisplayName(people, 'P2')).toBe('人物2')
    expect(personDisplayName(people, 'P9')).toBe('人物')
  })

  it('removes shot-local subject tokens without inventing identity', () => {
    expect(publicInteractionText('subject_A 拿起花瓶')).toBe('拿起花瓶')
    expect(publicInteractionText('subject_B：握住手提包')).toBe('握住手提包')
    expect(publicInteractionText('subject_A')).toBe('')
    expect(publicInteractionText('人物靠近桌面')).toBe('人物靠近桌面')
  })

  it('sanitizes prop interactions in the ordinary-user payload copy', () => {
    const payload = sanitizeOrdinarySceneTimelinePayload({
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
        scene_info: { location: '客厅', interior_exterior: '室内', time_of_day: '白天', environment: null },
        people: [],
        story_summary: null,
        shots: [{
          ordinal: 1,
          start_us: 0,
          end_us: 1_000_000,
          duration_us: 1_000_000,
          thumbnail_url: null,
          reference_url: null,
          visual_description: null,
          people: [],
          performance: [],
          dialogue: [],
          props: [{ label: '花瓶', interaction: 'subject_A：拿起' }],
          cinematography: { shot_type: null, composition: null, camera_motion: null },
          on_screen_text: [],
        }],
      }],
    })

    expect(payload.scenes[0].shots[0].props[0].interaction).toBe('拿起')
    expect(JSON.stringify(payload)).not.toMatch(/subject_[a-z0-9]+/i)
  })
})
