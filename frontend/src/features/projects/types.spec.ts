import { describe, expect, it } from 'vitest'

import { PROJECT_TYPE_OPTIONS, VIDEO_PROJECT_TYPES, projectTypeLabel } from './types'

describe('project type catalog', () => {
  it('contains exactly six root project skills', () => {
    expect(PROJECT_TYPE_OPTIONS.map((item) => item.value)).toEqual([
      'REPLICA',
      'REDRAW',
      'TRANSLATION',
      'NOVEL_TO_DRAMA',
      'SCRIPT_TO_DRAMA',
      'SCRIPT_LOCALIZATION',
    ])
  })

  it('marks only video-source project types as video projects', () => {
    expect([...VIDEO_PROJECT_TYPES]).toEqual(['REPLICA', 'REDRAW', 'TRANSLATION'])
  })

  it('uses direct Chinese business labels', () => {
    expect(projectTypeLabel('REPLICA')).toBe('复刻短剧')
    expect(projectTypeLabel('SCRIPT_LOCALIZATION')).toBe('剧本本土化')
  })
})
