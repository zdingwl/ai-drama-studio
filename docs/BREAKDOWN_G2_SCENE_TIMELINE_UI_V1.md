# G2.6 Ordinary-user Scene Timeline UI V1

Status: **IMPLEMENTED ON BRANCH / USER-LOCAL ACCEPTANCE PENDING**

Branch: `g2-6-scene-timeline-ui`

## 1. Goal

G2.6 makes the frozen G2.5 `scene-timeline-v1` result the primary ordinary-user reading surface for **02 拉片 → 拉片结果**.

The UI is intentionally not an engineering inspector. Its reading order is:

```text
Episode result
→ Scene navigation
→ readable Scene title
→ story summary
→ location / interior-exterior / time-of-day / environment
→ Scene people
→ Shot cards
   → thumbnail / reference clip
   → visible description
   → people
   → action / performance
   → dialogue
   → props
   → cinematography
   → on-screen text
```

## 2. Frozen data ownership

G2.6 does not create or reinterpret Scene/Shot truth.

```text
G1 + G2.1/G2.2 = frozen Scene/Shot facts
G2.3/G2.4       = frozen readable title/story_summary authority
G2.5             = frozen ordinary-user API
G2.6             = display only
```

The primary result UI reads:

```text
GET /api/episodes/{episode_id}/scene-timeline
```

The existing Breakdown Run list is used only to keep the already-existing task bar status accurate. It is not used to rebuild the visible Scene Timeline.

## 3. Ordinary-user surface

Visible concepts are limited to:

```text
场景
剧情摘要
地点 / 室内外 / 时段 / 环境
本场人物
镜头
时间 / 时长
画面
动作 / 表演
对白
道具
镜头语言
画面文字
用户可读降级提示
```

Sections with no content are hidden instead of showing technical empty states.

Only one Shot reference video is mounted at a time; other Shot cards use lazy thumbnails to avoid loading every clip simultaneously.

## 4. Forbidden primary UI fields

The ordinary result page must not display:

```text
support Fxxxx
source_fingerprint
Evidence IDs
cluster keys
LocalSubject IDs
subject_A / subject_B
confidence
provider/model metadata
raw validator diagnostics
Breakdown Run ID
ShotRevision ID
Final Character / Final Scene / Final Prop IDs
```

Scene-local `P1/P2/...` refs may exist in the API contract but are resolved to `人物1/人物2/...` before visible rendering.

## 5. Files

```text
frontend/src/types/scene-timeline.ts
frontend/src/api/scene-timeline.ts
frontend/src/utils/sceneTimelineUi.ts
frontend/src/utils/sceneTimelineUi.test.ts
frontend/src/components/SceneTimelineResultsV1.vue
frontend/src/components/BreakdownStageV1.vue
frontend/src/scene-timeline-g2-6-overrides.css
frontend/src/main.ts
```

Legacy `BreakdownResultsV1.vue` remains in the repository for rollback/reference but is no longer mounted by the primary `02 拉片 → 拉片结果` path.

## 6. User-local acceptance

Run from `frontend`:

```powershell
npm test -- src/utils/sceneTimelineUi.test.ts
npm run typecheck
npm run build
```

Then start the app and open the accepted real episode:

```text
Episode = EPISODE_0ed6aaca0da4471db0364bd29c3d6a61
Run = BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4
```

Expected visible result:

```text
Scene 1 title = 走廊争花
Scene 2 title = 客厅争执
Scene count = 2
Shot count = 30
```

Visual acceptance:

```text
1. primary page directly shows readable Scene title + story summary
2. Scene people are shown as ordinary display names, not P1/P2 refs
3. Shot cards show visual/action/dialogue/props/cinematography/on-screen text when present
4. no Evidence/support/confidence/provider/model/cluster/LocalSubject diagnostics are visible
5. typography is readable and the page does not resemble an engineering inspector
6. reference clips can be played without mounting every Shot video at once
7. re-run and batch-run task controls still work
8. 镜头管理 remains unchanged
```

Do not mark G2.6 FINAL PASS until user-local typecheck/build and visual review are observed.
