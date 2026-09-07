import { describe, expect, it } from 'vitest'
import { nextReviewKey, uniqueReviewItems } from './continuousReviewQueue'

describe('continuous review navigation', () => {
  it('continues after the saved item when related items also disappear', () => {
    expect(nextReviewKey(['a', 'b', 'c', 'd'], 'b', ['a', 'd'])).toBe('d')
  })
  it('returns to deferred items at the end, and stops when empty', () => {
    expect(nextReviewKey(['a', 'b'], 'b', ['a'])).toBe('a')
    expect(nextReviewKey(['a'], 'a', [])).toBe('')
  })
  it('does not repeat an observation referenced by multiple shots', () => {
    expect(uniqueReviewItems([{ key: 'person', shotId: 's1' }, { key: 'person', shotId: 's2' }])).toEqual([{ key: 'person', shotId: 's1' }])
  })
})
