import type {
  BreakdownReadAssetOverlay,
  BreakdownReadModelPayload,
  BreakdownReadSceneIdentity,
} from '../types/breakdown-read-model'
import type {
  FinalPropDisplay,
  FinalSceneDisplay,
  SceneTimelinePayload,
  SceneTimelineScene,
} from '../types/scene-timeline'
import { sanitizeOrdinarySceneTimelinePayload } from './sceneTimelineUi'

export const IDENTITY_UI_STALE_WARNING = '人物身份信息暂不可用，当前继续使用匿名人物显示。'
export const FINAL_ASSET_UI_STALE_WARNING = '场景/道具最终资产暂不可用，当前保留拉片原结果。'

function mergeWarnings(...groups: string[][]): string[] {
  return Array.from(new Set(groups.flat().map((item) => item.trim()).filter(Boolean)))
}

function anonymousIdentityTimeline(timeline: SceneTimelinePayload): SceneTimelinePayload {
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

function clearFinalAssets(timeline: SceneTimelinePayload, warning: string): SceneTimelinePayload {
  return {
    ...timeline,
    warnings: mergeWarnings(timeline.warnings, [warning]),
    scenes: timeline.scenes.map((scene) => ({
      ...scene,
      final_scene: null,
      shots: scene.shots.map((shot) => ({
        ...shot,
        final_props: [],
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

function projectIdentity(
  timeline: SceneTimelinePayload,
  payload: BreakdownReadModelPayload,
): SceneTimelinePayload {
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
    return anonymousIdentityTimeline(timeline)
  }

  for (const scene of timeline.scenes) {
    const sceneIdentity = identityScenes.get(scene.ordinal)
    if (!sceneIdentity || !sceneIdentityIsSafe(scene, sceneIdentity)) {
      return anonymousIdentityTimeline(timeline)
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

function finalSceneIsSafe(value: FinalSceneDisplay | null): boolean {
  return value === null || Boolean(value.id.trim() && value.name.trim())
}

function finalPropsAreSafe(values: FinalPropDisplay[]): boolean {
  const ids = new Set<string>()
  for (const item of values) {
    if (!item.id.trim() || !item.name.trim() || ids.has(item.id)) return false
    ids.add(item.id)
  }
  return true
}

function assetOverlayIsSafe(timeline: SceneTimelinePayload, assets: BreakdownReadAssetOverlay): boolean {
  const sceneMap = new Map(assets.scenes.map((item) => [item.scene_ordinal, item]))
  const shotMap = new Map(assets.shots.map((item) => [`${item.scene_ordinal}:${item.shot_ordinal}`, item]))
  const expectedSceneOrdinals = new Set(timeline.scenes.map((scene) => scene.ordinal))
  const expectedShotKeys = new Set(
    timeline.scenes.flatMap((scene) => scene.shots.map((shot) => `${scene.ordinal}:${shot.ordinal}`)),
  )

  if (
    sceneMap.size !== assets.scenes.length
    || shotMap.size !== assets.shots.length
    || sceneMap.size !== expectedSceneOrdinals.size
    || shotMap.size !== expectedShotKeys.size
  ) return false

  for (const ordinal of expectedSceneOrdinals) {
    const item = sceneMap.get(ordinal)
    if (!item || !finalSceneIsSafe(item.scene)) return false
  }
  for (const key of expectedShotKeys) {
    const item = shotMap.get(key)
    if (!item || !finalPropsAreSafe(item.props)) return false
  }

  const hasFinalAssets = assets.scenes.some((item) => item.scene !== null)
    || assets.shots.some((item) => item.props.length > 0)
  if (hasFinalAssets && !assets.asset_revision_id) return false
  return true
}

function projectFinalAssets(
  timeline: SceneTimelinePayload,
  assets: BreakdownReadAssetOverlay | null | undefined,
): SceneTimelinePayload {
  if (!assets) return timeline
  if (!assetOverlayIsSafe(timeline, assets)) {
    return clearFinalAssets(timeline, FINAL_ASSET_UI_STALE_WARNING)
  }

  const sceneMap = new Map(assets.scenes.map((item) => [item.scene_ordinal, item.scene]))
  const shotMap = new Map(assets.shots.map((item) => [`${item.scene_ordinal}:${item.shot_ordinal}`, item.props]))
  return {
    ...timeline,
    warnings: mergeWarnings(timeline.warnings, assets.warnings),
    scenes: timeline.scenes.map((scene) => ({
      ...scene,
      final_scene: sceneMap.get(scene.ordinal) ? { ...sceneMap.get(scene.ordinal)! } : null,
      shots: scene.shots.map((shot) => ({
        ...shot,
        final_props: (shotMap.get(`${scene.ordinal}:${shot.ordinal}`) ?? []).map((item) => ({ ...item })),
      })),
    })),
  }
}

/**
 * P6 ordinary-user projection.
 *
 * Frozen G2 stays under `timeline`. Character identity and Final Scene/Prop bindings are projected
 * only into display-only fields after independent fail-closed validation. Shot facts, dialogue,
 * OCR, G2 props, timings, P* membership and backend business state are never rewritten.
 */
export function projectBreakdownReadModelForOrdinaryUi(
  payload: BreakdownReadModelPayload,
): SceneTimelinePayload {
  const base = sanitizeOrdinarySceneTimelinePayload(payload.timeline)
  const timeline = { ...base, scenes: base.scenes.map(scene => ({ ...scene, shots: scene.shots.map(shot => ({ ...shot, people: [...new Set([...shot.people, ...(payload.manual_presence?.[String(shot.ordinal)] || []).filter(ref => scene.people.some(person => person.ref === ref))])] })) })) }
  const withIdentity = projectIdentity(timeline, payload)
  const result = projectFinalAssets(withIdentity, payload.assets)
  return { ...result, scenes: result.scenes.map(scene => ({ ...scene, shots: scene.shots.map(shot => ({ ...shot, presence_review_id: payload.presence_review?.[String(shot.ordinal)], dialogue: shot.dialogue.map((dialogue, index) => {
    const key = `${result.episode_id}:${result.source_shot_revision_id}:H${shot.ordinal}:D${index + 1}`
    const ref = payload.speaker_overrides?.[key]
    return ref && scene.people.some(person => person.ref === ref && person.final_character) ? { ...dialogue, speakers: [ref] } : dialogue
  }) })) })) }
}
