export interface CastingCharacter {
  target_character_id: string
  display_name: string
  localized_identity?: string | null
  personality_constraints?: unknown[]
}

export interface CastingDialogueLine {
  utterance_id: string
  utterance_number: number
  target_character_id: string | null
  final_target_dialogue?: string | null
}

export interface CastingDialogueSample {
  utterance_id: string
  utterance_number: number
  text: string
}

export type CharacterDialogueSample = CastingDialogueSample

export interface CharacterCastingBrief {
  target_character_id: string
  display_name: string
  task_summary: string
  role_identity: string
  target_locale: string
  dialogue_count: number
  personality_constraints: string[]
  dialogue_style_rules: string[]
  dialogue_samples: CastingDialogueSample[]
}

function uniqueStrings(values: unknown[]): string[] {
  const seen = new Set<string>()
  const result: string[] = []
  for (const value of values) {
    const text = String(value ?? '').trim()
    if (!text || seen.has(text)) continue
    seen.add(text)
    result.push(text)
  }
  return result
}

function representativeLines(lines: CastingDialogueLine[]): CastingDialogueLine[] {
  if (lines.length <= 3) return lines
  const indexes = [0, Math.floor((lines.length - 1) / 2), lines.length - 1]
  return [...new Set(indexes)].map((index) => lines[index])
}

export function buildCharacterCastingBrief(
  character: CastingCharacter,
  dialogueLines: CastingDialogueLine[],
  targetLanguage: string,
  targetRegion: string,
  dialogueStyleRules: unknown[] = [],
): CharacterCastingBrief {
  const targetCharacterId = String(character.target_character_id ?? '')
  const displayName = String(character.display_name ?? targetCharacterId).trim() || '未命名角色'
  const lines = dialogueLines.filter((line) => line.target_character_id === targetCharacterId)
  const samples = representativeLines(lines.filter((line) => String(line.final_target_dialogue ?? '').trim()))
    .map((line) => ({
      utterance_id: String(line.utterance_id),
      utterance_number: Number(line.utterance_number ?? 0),
      text: String(line.final_target_dialogue ?? '').trim(),
    }))
  const locale = [String(targetLanguage ?? '').trim(), String(targetRegion ?? '').trim()].filter(Boolean).join(' / ') || '未指定'
  const roleIdentity = String(character.localized_identity ?? '').trim() || displayName
  return {
    target_character_id: targetCharacterId,
    display_name: displayName,
    task_summary: `为 ${displayName} 选择能稳定完成 ${lines.length} 条目标对白的参考声线；只依据当前目标设定与目标剧本判断，不自动推断声线。`,
    role_identity: roleIdentity,
    target_locale: locale,
    dialogue_count: lines.length,
    personality_constraints: uniqueStrings(Array.isArray(character.personality_constraints) ? character.personality_constraints : []),
    dialogue_style_rules: uniqueStrings(Array.isArray(dialogueStyleRules) ? dialogueStyleRules : []),
    dialogue_samples: samples,
  }
}
