import { describe, expect, it } from 'vitest'
import {
  cinematographyItems,
  personDisplayName,
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
})
