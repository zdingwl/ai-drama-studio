# AI Drama Studio — Agent Entry Rules

Current formal architecture: **Reference Video V2**. Formal Character baseline: **Character V10.1 + explicit Shot Character Assignment**.

Current Breakdown truth:

```text
P1/P2 implementation acceptance      = CONDITIONAL PASS
P2-E1 Episode-context Fusion          = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window Qwen3-VL      = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement      = PLANNED / NEXT
P2-E4 final Episode-context Fusion    = PLANNED
P2.6 Windows / real-model acceptance  = NOT PASSED
P3 02 拉片 UI                         = IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

Never describe P2 as accepted/closed until a real short-drama full-chain run receives the required human acceptance PASS.

Core product principles:

> **先看懂，再识别，再回填。**

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

## 1. New-conversation recovery order

Always read repository truth before relying on old chat/history:

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
6. docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md
7. docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md
8. docs/BREAKDOWN_P2_SIDECAR_CONTRACT.md
9. docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md
10. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md when Character is involved
11. current code/tests
12. latest docs/sessions/*.md handoff
```

Truth priority:

```text
PROJECT_STATE + CURRENT_IMPLEMENTATION_MANIFEST + current code/tests = executable CURRENT
BREAKDOWN_EPISODE_CONTEXT_PLAN = accepted active Breakdown migration target
BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN = wider downstream target
```

Old F01-F06 docs, Frozen snapshots, old Shot-centric assumptions, old Character versions and chat history never override current wiring.

## 2. Current production Breakdown chain

```text
Episode Current ShotRevision
→ create frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR observations
→ P2-E2 overlapping Episode-window Qwen3-VL
→ immutable exact-Shot VLM_OUTPUT sidecar contract
→ P2-E1 Episode-context Fusion
→ anonymous P1 Draft
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal orchestrator:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

Production VLM stable import:

```text
engine/app/breakdown_p2_vlm_runtime_v1.py
→ engine/app/breakdown_p2_vlm_episode_v2.py
profile = breakdown-p2-vlm-episode-window-e2-v1
runner = scripts/run_breakdown_vlm_qwen3_episode_windows.py
```

Production Fusion:

```text
engine/app/breakdown_p2_fusion_episode_v2.py
profile = breakdown-p2-fusion-episode-context-e1-v2
```

Formal APIs remain unchanged. Batch Breakdown must remain sequential by `Episode.sort_order`; heavy jobs remain globally serialized.

## 3. P2-E1 rules

Scene continuity:

```text
missing / UNKNOWN / generic environment → inherit current Scene
compatible specificity (病房 → 医院病房) → same Scene
strong location contradiction or explicit INT ↔ EXT contradiction → new Scene
```

Rule: `看不出来 != 换场`.

Dialogue continuity:

```text
ASR_SEGMENT = Episode-time dialogue text truth
Shot DIALOGUE TimelineEvent = projection, not sentence truth
```

Cross-Shot projections keep the full ASR text and share `dialogue_group_id/asr_segment_id` + source/projection ranges + continuation flags. Raw ASR_WORD stays immutable SUPPORT evidence.

## 4. P2-E2 rules

Default window policy:

```text
target duration = 24s
allowed duration config = 20..40s
overlap = 25%
allowed overlap config = 10..50%
window edges align to Shot boundaries
every Shot is fully covered by at least one window
sequential inference
```

Production media selection:

```text
READY preprocess proxy first
→ Episode source fallback
```

Each Qwen window receives continuous video plus every covered exact `ShotRevisionItem` boundary. The prompt must explicitly preserve these rules:

```text
cut != scene change
closeup/blur/inserts may use adjacent visual context only when evidence supports it
uncertain evidence must remain UNCERTAIN
no ASR/OCR transcription inside VLM
anonymous subject labels only
no Final Character/Scene/Prop/Binding IDs
Simplified Chinese descriptive prose
```

Window output includes `window_summary`, scene-change candidates, anonymous subject continuity hints, prop continuity hints and shot-aware semantics. Per-Shot context includes:

```text
scene_continuity = SAME|NEW_SCENE|UNCERTAIN
scene_basis = DIRECT|CONTEXT|MIXED|UNCERTAIN
context_note
```

When the same Shot is covered by multiple windows, select the candidate with the largest surrounding context margin, then closest window center, then earlier window. Store selected/supporting window provenance in `VLM_OUTPUT.payload.episode_window`.

E2 must keep the frozen P2 sidecar shape:

```text
source_type = VLM_OUTPUT
shot_revision_item_id = exact frozen item
source time = exact Shot range
payload.semantic = existing anonymous semantic schema
```

Historical BreakdownRuns/sidecars are never rewritten. Users must re-run AI 拉片 to get E2 semantics.

## 5. P2-E3 / E4 are not implemented

Do not claim the entire Episode-context migration is finished.

Accepted next order:

```text
P2-E3 Scene + previous/current/next + E2 window + ASR/OCR contextual Shot refinement
→ P2-E4 final Episode-context Fusion using window evidence as primary continuity truth
```

Long-term invariants:

```text
Shot boundary != dialogue sentence boundary
Shot boundary != scene boundary
Shot boundary != maximum semantic context
```

P5 Character safe integration remains paused until the Episode-context semantic baseline is locally stable.

## 6. Anonymous Draft is not identity truth

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
Breakdown Evidence != Final Asset/Binding truth
```

P2 must never write Final Character/Scene/Prop assets or Final Shot bindings. P4 may use Draft as a search hypothesis only after current-shot visual verification.

## 7. Shot / history rules

Reference Video V2 remains authoritative:

```text
FFprobe / FFmpeg
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
```

`Shot.id` is not a permanent historical anchor across reruns/restores. New Current ShotRevision makes incompatible active Breakdown Runs STALE. No ordinal/timestamp guessing is allowed for stale history.

## 8. Character V10.1 is protected

Formal chain:

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project-level identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax:

```text
new identity requires >=3 independent Shots
new identity requires >=3 model-usable images
same-sample cannot-link is hard
high-quality Face conflict is hard negative
ambiguous winner remains unresolved/unassigned
current Final Shot binding comes from explicit shot_presence_assignments
```

Draft/VLM/ASR context cannot override these gates. E1/E2 do not modify Character code.

## 9. P3 / P4 current truth

P3 is implemented on main:

```text
02 拉片
├─ 镜头管理
└─ 拉片结果
   ├─ Scene / Shot
   ├─ anonymous subjects
   ├─ dialogue / action / OCR
   ├─ prop hints
   └─ historical Reference Clip
```

Technical Evidence remains backend truth but is not normal-user primary presentation. UI acceptance remains in progress.

P4 Draft-guided Scene/Prop is implemented with current-revision visual re-verification. Draft cannot directly create Final Scene/Prop. Local/model acceptance remains pending.

## 10. Acceptance gate

Current result:

```text
P1/P2 implementation = CONDITIONAL PASS
P2-E1 local-real = PENDING
P2-E2 local-real Qwen/Windows = PENDING
P2.6 Windows/real-model = NOT PASSED
```

Next real acceptance must verify:

```text
strict runtime/model readiness
real short-drama Episode
ASR → OCR → E2 window VLM → E1 Fusion → P1 validator
same-scene wide shot + closeups/inserts/blur continuity
genuine scene changes still split
anonymous subject/key-prop continuity improves without identity overreach
cross-Shot dialogue remains whole
human required scores >=4/5
no blocking issues
```

Only then may project truth say P2.6 PASS / P2 ACCEPTED / P2 CLOSED.

## 11. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]` for remote development/documentation commits. Historical CI remains historical.

Current Episode-context unit coverage:

```text
engine/tests/v2/test_breakdown_p2_fusion_episode_v2.py
engine/tests/v2/test_breakdown_p2_vlm_episode_v2.py
```

Code/test files existing in the repository are not equivalent to a fresh local pytest/Qwen/CUDA PASS.

## 12. Documentation sync rule

When status changes, keep aligned:

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
docs/BREAKDOWN_P2_LOCAL_ACCEPTANCE.md when runtime/acceptance changes
latest docs/sessions/*.md handoff
```

## 13. Next safe work

```text
A. run a new real Episode Breakdown with E2
B. inspect same-scene continuity, genuine scene changes, subject/prop continuity and E1 dialogue
C. if E2 runtime behavior is sound, implement P2-E3
D. do not advance P5 until Episode-context semantic baseline is stable
```
