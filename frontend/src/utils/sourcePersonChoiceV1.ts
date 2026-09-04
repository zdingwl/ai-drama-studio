export type SourcePersonChoiceInput = {
  explicitCharacterId?: string | null
  suggestedCharacterId?: string | null
  proposalCharacterId?: string | null
  newPersonName?: string | null
}

/**
 * Resolve the mutually exclusive source-person choice used by the confirmation UI.
 * A non-empty new-person name always wins over any AI/default character suggestion.
 */
export function resolveSourcePersonChoiceV1(input: SourcePersonChoiceInput): {
  characterId: string
  createName: string
} {
  const createName = (input.newPersonName || '').trim()
  if (createName) {
    return { characterId: '', createName }
  }

  return {
    characterId: input.explicitCharacterId
      || input.suggestedCharacterId
      || input.proposalCharacterId
      || '',
    createName: '',
  }
}
