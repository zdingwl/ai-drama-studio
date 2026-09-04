import type { SceneTimelineShot, SceneTimelinePerson } from './types/scene-timeline'

export interface BreakdownQualityResult {
  ready: boolean
  reason: string
}

const WEAK_PERFORMANCE_RE = /^(?:正在)?(?:说话|讲话|对话|发言|talking|speaking|speaks?|talks?)$/i
const UNKNOWN_PERFORMANCE_RE = /^(?:未知|不明|不确定|无法判断|无法确认|看不清|未识别|待补充|待确认|暂无.*|无|unknown|unclear|n\/?a|[-—]+)$/i

function normalizedPerformanceText(value: string): string {
  return value.trim().replace(/[，。！？、；：,.!?;:\s]+/g, '')
}

function isWeakPerformanceText(value: string): boolean {
  const normalized = normalizedPerformanceText(value)
  const withoutAnonymousSubject = normalized.replace(/^(?:人物\d+|P\d+)/i, '')
  return !withoutAnonymousSubject || WEAK_PERFORMANCE_RE.test(withoutAnonymousSubject) || UNKNOWN_PERFORMANCE_RE.test(withoutAnonymousSubject)
}

function hasUsefulPerformance(shot: SceneTimelineShot): boolean {
  if (!shot.people.length) return true
  const rows = [...shot.performance.map((item) => item.text), ...Object.values(shot.performance_details || {})]
    .filter((value): value is string => typeof value === 'string' && Boolean(value.trim()))
  if (!rows.length) return false
  return rows.some((row) => !isWeakPerformanceText(row))
}

function hasDialogueTimingIssue(shot: SceneTimelineShot): boolean {
  return shot.dialogue.some((item) => (
    item.start_us < shot.start_us
    || item.end_us > shot.end_us
    || item.end_us <= item.start_us
  ))
}

function hasUnresolvedDialogueSpeaker(shot: SceneTimelineShot): boolean {
  return shot.dialogue.some((item) => item.text.trim().length > 0 && item.speakers.length === 0)
}

export function evaluateBreakdownShotQuality(shot: SceneTimelineShot): BreakdownQualityResult {
  if (!shot.visual_description?.trim()) {
    return { ready: false, reason: '缺少镜头画面描述' }
  }
  if (!hasUsefulPerformance(shot)) {
    return { ready: false, reason: '动作/表情信息不足' }
  }
  if (hasDialogueTimingIssue(shot)) {
    return { ready: false, reason: '对白时间超出镜头范围' }
  }
  if (hasUnresolvedDialogueSpeaker(shot)) {
    return { ready: false, reason: '对白说话人待确认' }
  }
  if (!shot.cinematography.shot_type?.trim()) {
    return { ready: false, reason: '缺少景别信息' }
  }
  if (!shot.cinematography.composition?.trim()) {
    return { ready: false, reason: '缺少构图信息' }
  }
  return { ready: true, reason: '' }
}

/** Anonymous observations and missing speaker references are never formal identities. */
export function hasUnconfirmedSourcePeople(shot: SceneTimelineShot, people: SceneTimelinePerson[]): boolean {
  if (shot.presence_review_id) return true
  const refs = new Set([...shot.people, ...shot.dialogue.flatMap((item) => item.speakers)])
  return [...refs].some((ref) => !people.find((person) => person.ref === ref)?.final_character)
}
