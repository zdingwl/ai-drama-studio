import type {
  SceneTimelineCinematography,
  SceneTimelinePerson,
  SceneTimelineSceneInfo,
} from '../types/scene-timeline'

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

export function personDisplayName(people: SceneTimelinePerson[], ref: string): string {
  return people.find((person) => person.ref === ref)?.display_name || '人物'
}
