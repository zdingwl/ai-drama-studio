import type { BreakdownReadModelPayload, BreakdownReadSceneIdentity } from '../types/breakdown-read-model'
import type { SceneTimelinePayload, SceneTimelineScene } from '../types/scene-timeline'
import { sanitizeOrdinarySceneTimelinePayload } from './sceneTimelineUi'

export const IDENTITY_UI_STALE_WARNING = '人物身份信息暂不可用，当前继续使用匿名人物显示。'

function mergeWarnings(...groups: string[][]): string[] {
  return Array.from(new Set(groups.flat().map((item) => item.trim()).filter(Boolean)))
}

function anonymousTimeline(timeline: SceneTimelinePayload): SceneTimelinePayload {
  return {
    ...timeline,
    warnings: mergeWarnings(timeline.warnings, [IDENTITY_UI_STALE_WARNING]),
    scenes: timeline.scenes.map((scene) => ({
      ...scene,
      people: scene.people.map((person) => ({
        ref: person.ref,
        display_name: person.display_name,
        appearance: person.appearance,
        final_character: null,
      })),
    })),
  }
}

function sceneIdentityIsSafe(scene: SceneTimelineScene, identity: BreakdownReadSceneIdentity): boolean {
  if (identity.scene_ordinal !== scene.ordinal) return false
  if (identity.people.length !== scene.people.length) return false

  const timelineRefs = new Set(scene.people.map((person) => person.ref))
  const identityRefs = new Set(identity.people.map((person) => person.ref))
  if (timelineRefs.size !== scene.people.length || identityRefs.size !== identity.people.length) return false
  if (timelineRefs.size !== identityRefs.size) return false
  for (const ref of timelineRefs) {
    if (!identityRefs.has(ref)) return false
  }

  const timelinePeople = new Map(scene.people.map((person) => [person.ref, person]))
  for (const person of identity.people) {
    const source = timelinePeople.get(person.ref)
    if (!source) return false
    if (person.character) {
      if (!person.character.id.trim() || !person.character.name.trim()) return false
      if (person.display_name !== person.character.name) return false
    } else if (person.display_name !== source.display_name) {
      return false
    }
  }
  return true
}

/**
 * P6 ordinary-user projection.
 *
 * The backend read-model keeps frozen G2 under `timeline` and Final Character under a separate
 * identity overlay. This function makes a display-only copy for the existing renderer. It never
 * changes Shot facts, dialogue, OCR, props, timings, P* membership, or backend business state.
 */
export function projectBreakdownReadModelForOrdinaryUi(
  payload: BreakdownReadModelPayload,
): SceneTimelinePayload {
  const timeline = sanitizeOrdinarySceneTimelinePayload(payload.timeline)
  const identity = payload.identity
  const identityScenes = new Map(identity.scenes.map((scene) => [scene.scene_ordinal, scene]))
  const peopleCount = identity.scenes.reduce((sum, scene) => sum + scene.people.length, 0)
  const resolvedCount = identity.scenes.reduce(
    (sum, scene) => sum + scene.people.filter((person) => person.character !== null).length,
    0,
  )

  if (
    identityScenes.size !== identity.scenes.length
    || identityScenes.size !== timeline.scenes.length
    || identity.resolved_count !== resolvedCount
    || identity.unresolved_count !== peopleCount - resolvedCount
    || (resolvedCount > 0 && !identity.asset_revision_id)
  ) {
    return anonymousTimeline(timeline)
  }

  for (const scene of timeline.scenes) {
    const sceneIdentity = identityScenes.get(scene.ordinal)
    if (!sceneIdentity || !sceneIdentityIsSafe(scene, sceneIdentity)) {
      return anonymousTimeline(timeline)
    }
  }

  return {
    ...timeline,
    warnings: mergeWarnings(timeline.warnings, identity.warnings),
    scenes: timeline.scenes.map((scene) => {
      const sceneIdentity = identityScenes.get(scene.ordinal)!
      const identityByRef = new Map(sceneIdentity.people.map((person) => [person.ref, person]))
      return {
        ...scene,
        people: scene.people.map((person) => {
          const display = identityByRef.get(person.ref)!
          return {
            ...person,
            display_name: display.character?.name ?? person.display_name,
            final_character: display.character ? { ...display.character } : null,
          }
        }),
      }
    }),
  }
}
