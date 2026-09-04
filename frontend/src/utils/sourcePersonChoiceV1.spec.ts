import { describe, expect, it } from 'vitest'

import { resolveSourcePersonChoiceV1 } from './sourcePersonChoiceV1'

describe('resolveSourcePersonChoiceV1', () => {
  it('prefers an explicit new-person name over AI and existing-character suggestions', () => {
    expect(resolveSourcePersonChoiceV1({
      explicitCharacterId: '',
      suggestedCharacterId: 'CHAR_002',
      proposalCharacterId: 'CHAR_003',
      newPersonName: ' 同学母亲 ',
    })).toEqual({ characterId: '', createName: '同学母亲' })
  })

  it('uses an explicit existing-character choice when no new-person name is present', () => {
    expect(resolveSourcePersonChoiceV1({
      explicitCharacterId: 'CHAR_004',
      suggestedCharacterId: 'CHAR_002',
      proposalCharacterId: 'CHAR_003',
      newPersonName: '',
    })).toEqual({ characterId: 'CHAR_004', createName: '' })
  })

  it('falls back to the AI suggestion when there is no explicit choice', () => {
    expect(resolveSourcePersonChoiceV1({
      explicitCharacterId: '',
      suggestedCharacterId: 'CHAR_002',
      proposalCharacterId: 'CHAR_003',
    })).toEqual({ characterId: 'CHAR_002', createName: '' })
  })
})
