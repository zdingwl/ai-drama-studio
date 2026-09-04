export type PersonMark = { shot_id: string; image_url: string; box: number[]; source?: string | null }
export type PersonObservation = {
  key: string; anchor: string; name: string; appearance: string | null
  episode_id: string; episode_title: string; character_id: string | null
  suggested_character_id?: string | null; identity_issue?: string | null
  localization?: PersonMark | null
  shots: { id: string; ordinal: number; thumbnail_url: string | null }[]
}
export type PersonGroup = { id: string; name: string; characterId: string; rows: PersonObservation[] }
export function groupPersonObservations(
  rows: PersonObservation[], characters: { id: string; name: string }[],
  moves: Record<string, string>, proposals: Record<string, { character_id?: string | null }>,
): PersonGroup[] {
  const groups = new Map<string, PersonGroup>()
  for (const row of rows) {
    const suggested = row.identity_issue ? null : row.suggested_character_id || proposals[row.key]?.character_id
    const id = moves[row.key] || (row.identity_issue ? 'unassigned' : row.character_id ? `formal:${row.character_id}` : suggested ? `candidate:${suggested}` : 'unassigned')
    const characterId = id.startsWith('formal:') || id.startsWith('candidate:') ? id.slice(id.indexOf(':') + 1) : ''
    const name = characters.find((item) => item.id === characterId)?.name || (id === 'unassigned' ? '未归组' : '拆分候选组')
    if (!groups.has(id)) groups.set(id, { id, name, characterId, rows: [] })
    groups.get(id)!.rows.push(row)
  }
  return [...groups.values()]
}
export function validPersonMark(row: PersonObservation, mark?: PersonMark | null): mark is PersonMark {
  if (!mark || mark.box.length !== 4 || !mark.box.every(Number.isFinite)) return false
  const [x, y, w, h] = mark.box as [number, number, number, number]
  return x >= 0 && y >= 0 && w >= .02 && h >= .02 && x + w <= 1.000001 && y + h <= 1.000001
    && row.shots.some((shot) => shot.id === mark.shot_id && shot.thumbnail_url === mark.image_url)
}
