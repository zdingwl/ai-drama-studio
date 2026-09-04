import type { PersonMark } from './personReviewGroups'

// 单人快捷提交是用户对当前画面的明确判断，不是自动人数检测结果。
export function personConfirmationMark(
  shot: { id: string; thumbnail_url?: string | null } | null,
  mark: PersonMark | undefined,
  confirmSinglePerson: boolean,
): PersonMark | null {
  if (!shot?.thumbnail_url) return null
  if (mark?.shot_id === shot.id && mark.image_url === shot.thumbnail_url) return mark
  return confirmSinglePerson
    ? { shot_id: shot.id, image_url: shot.thumbnail_url, box: [0, 0, 1, 1], source: 'MANUAL_SINGLE_PERSON' }
    : null
}
