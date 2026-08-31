# G2.5 Scene Timeline API V1

Status: **IMPLEMENTED ON BRANCH / USER-LOCAL ACCEPTANCE PENDING**

Branch: `g2-5-scene-timeline-api`

## 1. Goal

G2.5 exposes the already-frozen G2 Scene Timeline as the ordinary-user read surface.

It does **not** redefine Scene / Shot truth and it does **not** add a second inference path.

Frozen ownership remains:

```text
G1 / G2.1 / G2.2
→ Scene / Shot / people / action / ASR dialogue / props / cinematography / OCR

G2.3 / G2.4
→ readable_title / story_summary only

G2.5
→ read/result materialization + API only
```

Character V10.1 and all Final Asset / Binding paths remain untouched.

## 2. Ordinary-user endpoints

```text
GET /api/episodes/{episode_id}/scene-timeline
GET /api/breakdown-runs/{run_id}/scene-timeline
```

Episode behavior:

```text
missing Episode                  -> 404
existing Episode, no current READY Run -> null
current READY/READY_WITH_WARNINGS Run  -> scene-timeline-v1
```

Explicit Run behavior:

```text
missing Run                      -> 404
PROCESSING/FAILED/STALE Run      -> 409 safe user message
READY/READY_WITH_WARNINGS Run    -> scene-timeline-v1
```

Both endpoints are read-only. They never start ASR/OCR/VLM/Qwen and never mutate Breakdown/Final data.

## 3. Primary response contract

The response model is the frozen:

```text
SceneTimelinePayloadV1
schema_version = scene-timeline-v1
```

Primary result contains only:

```text
Scene info
people
Shot cards
visual/action
ASR dialogue
props
cinematography
OCR
readable Scene title/story_summary when a validated Narrative artifact exists
user-readable fallback warnings
```

Primary result must not expose:

```text
support Fxxxx
source_fingerprint
Evidence IDs
cluster keys
LocalSubject DB IDs
confidence
provider/model metadata
raw Narrative/validator diagnostics
Final Character / Final Scene / Final Prop IDs
```

The strict frozen Pydantic contract remains the final leak guard.

## 4. Narrative materialization boundary

The accepted G2.3 Narrative runtime is intentionally **not** called from GET.

Narrative generation is explicit:

```powershell
python scripts/materialize_breakdown_g2_scene_timeline_v1.py <READY_RUN_ID> --device cuda
```

Canonical workspace artifact:

```text
<episode workspace>/breakdown/<run_id>/scene-timeline/narrative-overlay-v1.json
```

The raw artifact may retain internal `support Fxxxx` because it is a developer-side provenance artifact. The ordinary-user API never returns this file directly.

Before an overlay can be written or consumed, G2.5 rechecks:

```text
Run / Episode / ShotRevision anchors
all Scene ordinals are covered
Scene source_fingerprint
frozen G2.4 support validation for every persisted claim
exact equality between persisted claim and the claim G2.4 accepts again
frozen apply_scene_narrative_overlay_v1 gate
```

Therefore a hand-written JSON file with a correct fingerprint cannot bypass the frozen G2.4 authority rules.

## 5. Fallback behavior

No Narrative artifact:

```text
Deterministic G2.2 Timeline is returned.
User warning:
场景标题与剧情摘要暂未完成可读整理，当前展示基础拉片结果。
```

Corrupt/stale/untrusted Narrative artifact:

```text
Deterministic G2.2 Timeline is returned.
User warning:
场景可读整理与当前拉片结果不一致，当前展示基础拉片结果。
```

Validated overlay with partial G2.3/G2.4 warnings:

```text
Accepted title/summary fields are applied.
Rejected/missing fields keep deterministic values.
Raw model/validator warnings are hidden.
User warning:
部分场景的标题或剧情摘要使用基础拉片结果。
```

## 6. User-local acceptance

New G2.5 unit boundary:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_result_v1.py engine/tests/v2/test_breakdown_scene_timeline_routes_v1.py -q
```

Frozen G2 regression boundary:

```powershell
python -m pytest engine/tests/v2/test_breakdown_scene_timeline_v1.py engine/tests/v2/test_breakdown_scene_narrative_v1.py engine/tests/v2/test_breakdown_scene_narrative_qwen3_v1.py engine/tests/v2/test_breakdown_scene_narrative_real_regression_v1.py -q
```

For the previously accepted real Run:

```powershell
python scripts/materialize_breakdown_g2_scene_timeline_v1.py BREAKDOWNRUN_6953039fc8a940b6b239f6475cd537e4 --device cuda
```

Expected API semantics after materialization:

```text
Scene 1 title = 走廊争花
Scene 2 title = 客厅争执
primary response contains no support Fxxxx / source_fingerprint / provider diagnostics
Shot objects remain frozen and unchanged
```

Do not mark G2.5 FINAL PASS until the user-local tests and real Run API review are observed.
