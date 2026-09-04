export type SpeakerOption = {
  person_key: string
  character_id?: string | null
  visible_in_shot?: boolean
}

/** 按正式身份去重；镜头绑定决定默认范围，不用同名或场景出现代替绑定。 */
export function shotSpeakerCandidates<T extends SpeakerOption>(
  candidates: T[], boundCharacterIds: string[], offscreen = false,
): T[] {
  const bound = new Set(boundCharacterIds)
  const grouped = new Map<string, T>()
  for (const person of candidates) {
    const id = person.character_id
    if (!id || !person.person_key || (offscreen ? bound.has(id) : !bound.has(id))) continue
    const previous = grouped.get(id)
    if (!previous || (!previous.visible_in_shot && person.visible_in_shot)) grouped.set(id, person)
  }
  return [...grouped.values()]
}
