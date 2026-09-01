import type {
  SceneTimelineCinematography,
  SceneTimelinePayload,
  SceneTimelinePerson,
  SceneTimelineSceneInfo,
} from '../types/scene-timeline'

const SHOT_LOCAL_SUBJECT_TOKEN = /\bsubject_[a-z0-9]+\b/gi

export function timelineTime(us: number | null | undefined): string {
  if (us === null || us === undefined || !Number.isFinite(us)) return '—'
  const totalSeconds = Math.max(0, us) / 1_000_000
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds - minutes * 60
  return `${String(minutes).padStart(2, '0')}:${seconds.toFixed(2).padStart(5, '0')}`
}

export function timelineDuration(us: number | null | undefined): string {
  if (us === null || us === undefined || !Number.isFinite(us)) return '—'
  const seconds = Math.max(0, us) / 1_000_000
  if (seconds < 10) return `${seconds.toFixed(1)} 秒`
  return `${Math.round(seconds)} 秒`
}

export function sceneInfoTags(info: SceneTimelineSceneInfo): string[] {
  return [info.location, info.interior_exterior, info.time_of_day]
    .map((item) => item?.trim() ?? '')
    .filter(Boolean)
}

export function cinematographyItems(value: SceneTimelineCinematography): string[] {
  return [value.shot_type, value.composition, value.camera_motion]
    .map((item) => item?.trim() ?? '')
    .filter(Boolean)
}

export function personByRef(people: SceneTimelinePerson[], ref: string): SceneTimelinePerson | null {
  return people.find((person) => person.ref === ref) ?? null
}

export function personDisplayName(people: SceneTimelinePerson[], ref: string): string {
  return personByRef(people, ref)?.display_name || '人物'
}

/** Compact fallback used when Final Character has no usable cover image. */
export function personAvatarText(person: SceneTimelinePerson | null | undefined): string {
  const name = person?.display_name?.trim().replace(/\s+/g, '') ?? ''
  return name ? Array.from(name)[0] : '人'
}

/**
 * G2.6 ordinary-user boundary: Shot-local subject_A/B labels are model-local evidence,
 * never identity authority. Remove only those tokens and keep the human-readable action.
 */
export function publicInteractionText(value: string | null | undefined): string {
  if (!value) return ''
  return value
    .replace(SHOT_LOCAL_SUBJECT_TOKEN, '')
    .replace(/^[\s:：,，;；\-—]+|[\s:：,，;；\-—]+$/g, '')
    .replace(/\s{2,}/g, ' ')
    .trim()
}

/**
 * Return a display-only copy. Frozen G2.5 payload truth remains unchanged on the backend.
 */
export function sanitizeOrdinarySceneTimelinePayload(payload: SceneTimelinePayload): SceneTimelinePayload {
  return {
    ...payload,
    scenes: payload.scenes.map((scene) => ({
      ...scene,
      shots: scene.shots.map((shot) => ({
        ...shot,
        props: shot.props.map((prop) => ({
          ...prop,
          interaction: publicInteractionText(prop.interaction) || null,
        })),
      })),
    })),
  }
}
