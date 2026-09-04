import { describe, expect, it } from 'vitest'
import { personConfirmationMark } from './personConfirmationMark'

describe('人物身份快捷确认', () => {
  const shot = { id: 'shot-1', thumbnail_url: '/frame-1' }
  it('明确单人确认直接产生当前原图参考，不要求先框选', () => {
    expect(personConfirmationMark(shot, undefined, true)).toEqual({ shot_id: 'shot-1', image_url: '/frame-1', box: [0, 0, 1, 1], source: 'MANUAL_SINGLE_PERSON' })
  })
  it('不把普通提交或没有图片的镜头自动当作单人', () => {
    expect(personConfirmationMark(shot, undefined, false)).toBeNull()
    expect(personConfirmationMark({ id: 'shot-1' }, undefined, true)).toBeNull()
  })
  it('已有人工框优先，不扩大到全图', () => {
    const mark = { shot_id: shot.id, image_url: shot.thumbnail_url, box: [.1, .2, .3, .4], source: 'MANUAL_BOX' }
    expect(personConfirmationMark(shot, mark, true)).toEqual(mark)
  })
  it('不使用其他镜头或过期图片的框', () => {
    expect(personConfirmationMark(shot, { shot_id: 'old', image_url: '/old', box: [0, 0, 1, 1] }, false)).toBeNull()
  })
})
