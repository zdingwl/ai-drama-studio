import { expect, it } from 'vitest'
import { personImageViewport } from './personImageViewport'
it('preserves the source pixel aspect ratio for portrait crops', () => {
  expect(personImageViewport([1080,1920],[.1,.2,.5,.5])).toBe('108 384 540 960')
})
it('handles landscape frames without normalizing to a square', () => {
  expect(personImageViewport([1920,1080],[0,0,.5,1])).toBe('0 0 960 1080')
})
it('rejects invalid and unloaded geometry', () => {
  expect(personImageViewport(null,[0,0,1,1])).toBeNull()
  expect(personImageViewport([100,100],[0,0,NaN,1])).toBeNull()
  expect(personImageViewport([100,100],[0,0,2,1])).toBeNull()
})
