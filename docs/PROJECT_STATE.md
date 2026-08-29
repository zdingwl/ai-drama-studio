# AI Drama Studio — Project State

> **Last synchronized:** 2026-08-29 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Branch:** `main`  
> **Architecture:** Reference Video V2  
> **FastAPI app version:** `2.4.1`  
> **Formal Character runtime:** Character V10.1

## 1. Current truth

```text
P1/P2 implementation acceptance      = CONDITIONAL PASS
P2-E1 Episode-context Scene/Dialogue  = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window Qwen3-VL      = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E3 contextual Shot refinement      = IMPLEMENTED / LOCAL-REAL QUALITY NOT ACCEPTED
P2-E4 final Episode-context Fusion    = IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2.6 Windows / real-model acceptance  = NOT PASSED
P3 02 拉片 UI                         = IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene/Prop            = IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character                  = PLANNED / PAUSED
```

Latest real short-drama run before E4 was **REJECTED**:

```text
30 Shots
21 LocalSubjects total
Scene 04 / 客厅 / 19 Shots -> 14 LocalSubjects
actual visible continuity -> same one woman + one man
E3 -> 30/30 TimeoutExpired -> explicit FALLBACK_E2
```

This run is acceptance evidence for the E4 blocker. It is not a PASS.

## 2. Product principle

> **先看懂，再识别，再回填。**

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

Hard semantic boundaries remain:

```text
LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
ASR speaker != Character
raw Evidence / Draft != Final binding truth
```

## 3. Current production Breakdown chain

```text
Episode Current ShotRevision
→ frozen PROCESSING BreakdownRun
→ Episode ASR
→ OCR observations
→ P2-E2 overlapping Episode-window Qwen3-VL
→ preserve E2 window subject/prop continuity hints
→ P2-E3 contextual Shot refinement
   └─ E3-only failure -> FALLBACK_E2, keep validated E2
→ one immutable exact-Shot VLM_OUTPUT sidecar
   payload.e2_semantic = original E2 visual semantic
   payload.semantic = E3 grounded semantic or E2 fallback
→ P2-E4 Episode-context Fusion
   ├─ E1 conservative Scene continuity
   ├─ ASR_SEGMENT cross-Shot dialogue truth/projection
   └─ anonymous Subject Continuity Graph
→ P1 validator
→ READY / READY_WITH_WARNINGS
```

Formal pipeline remains:

```text
engine/app/breakdown_p2_pipeline_v1.py
profile = breakdown-p2-full-v1
provider order = ASR → OCR → VLM
```

Production VLM class used by the pipeline:

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
→ engine/app/breakdown_p2_vlm_runtime_v1.py (E2 → E3 + grounding/fallback)
→ preserves window subject_continuity_hints / prop_continuity_hints
```

Production Fusion:

```text
engine/app/breakdown_p2_fusion_episode_v4.py
profile = breakdown-p2-fusion-episode-context-e4-v1
base = breakdown-p2-fusion-episode-context-e1-v2
```

Formal APIs stay unchanged. Batch remains sequential by `Episode.sort_order`; heavy work remains globally serialized.

## 4. Reference Video / history invariants

```text
FFprobe / FFmpeg preprocess
TransNetV2 Shot boundaries
integer microseconds
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
manual boundary edit / split / merge / rerun / restore
```

Shot boundaries are timing/edit coordinates, not semantic-context limits. Historical Breakdown remains anchored to exact frozen ShotRevision/ShotRevisionItem and is never silently rebound.

## 5. P2-E1 Scene + Dialogue rules retained inside E4

Scene:

```text
UNKNOWN / missing / generic / background-poor closeup -> inherit current Scene
compatible specificity -> same Scene
strong location contradiction or explicit INT ↔ EXT contradiction -> new Scene
```

Rule: `看不出来 != 换场`.

Dialogue:

```text
ASR_SEGMENT = Episode-time text truth
Shot DIALOGUE TimelineEvent = projection, not sentence truth
```

Cross-Shot projections keep the full ASR segment text and share `dialogue_group_id/asr_segment_id`, source/projection ranges and continuation flags. Raw ASR_WORD remains immutable SUPPORT evidence. The result UI suppresses repeated continuation projections and shows “承接上一镜对白”.

## 6. P2-E2 continuity preservation

E2 still uses shot-aligned overlapping Episode windows:

```text
default target = 24s
allowed = 20..40s
overlap = 25%
allowed = 10..50%
sequential inference
READY proxy first -> Episode source fallback
```

Qwen window output already contains:

```text
window_summary
scene_change_candidates
subject_continuity_hints
prop_continuity_hints
shots[]
```

The previous E2 normalizer discarded subject/prop continuity hints. Production now preserves normalized hints in `ProviderResult.metadata.window_summaries` so E4 can consume them without changing the frozen sidecar schema.

## 7. P2-E3 current truth

E3 is still a text-only contextual quality layer:

```text
Scene context
+ Previous/Current/Next E2 Shot semantics
+ E2 window context
+ overlapping ASR/OCR
```

E3 cannot create new visual presence or Final IDs. Current production behavior is fail-soft: malformed Shot output, missing runtime, model-load failure, subprocess timeout or other E3-only failure returns validated E2 semantics with explicit `FALLBACK_E2` provenance. E2 visual failure still fails closed.

The latest 30-Shot real run had `TimeoutExpired` for every E3 Shot/pass and therefore **does not count as E3 quality acceptance**.

## 8. P2-E4 anonymous subject continuity

E4 is now implemented in production. It fixes the exact-string `appearance_summary` fragmentation that created false temporary people.

Semantic model:

```text
Shot-local subject_A / subject_B = observation labels only
anonymous Subject Continuity Graph = cross-Shot Draft continuity
LocalSubject = Scene-scoped anonymous cluster
LocalSubject != Character
```

Primary edges:

```text
E2 window subject_continuity_hints
```

Conservative fallback edges use stable appearance cues only. Dynamic state is excluded from the identity key:

```text
exclude: expression / emotion / action / pose / speaking / screen position / camera framing
prefer: gender presentation / age band / hair / clothing / persistent accessories
```

Hard negative:

```text
any two observations in the same Shot = cannot-link
cannot-link is enforced transitively during graph union
```

If a hint is ambiguous or stable evidence is insufficient, E4 leaves observations separate instead of forcing a merge.

E4 stores graph provenance in `LocalSubject.appearance_json` and Run/Fusion metadata, including observation/cluster counts, explicit/fallback union counts and rejected cannot-link attempts.

## 9. P1 / Character protection

Formal P1 Draft tables are unchanged. E4 does not perform a destructive schema migration.

Character V10.1 remains protected:

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

E4 anonymous continuity is only a better search/understanding prior. It cannot override same-sample cannot-link, face conflict, >=3 independent Shot/image gates, explicit assignment or Final Character truth.

## 10. Validation reality / next acceptance

Code added for E4:

```text
engine/app/breakdown_p2_vlm_continuity_v1.py
engine/app/breakdown_p2_fusion_episode_v4.py
engine/tests/v2/test_breakdown_p2_e4_subject_continuity.py
```

Remote code presence is not a fresh local pytest/Qwen/CUDA PASS. Hosted GitHub Actions remain intentionally unused.

Next real run must re-run the same rejected Episode and verify at minimum:

```text
1. Scene 04 / 19 Shots / actual one woman + one man -> roughly two stable LocalSubjects, not A-N
2. Shot-local subject label swaps do not create new people
3. expression/action/pose changes do not create new people
4. two people visible in the same Shot are never merged
5. genuine new people remain separate
6. Scene continuity and genuine scene changes do not regress
7. cross-Shot dialogue remains whole and UI does not duplicate continuation text
8. E3 FALLBACK_E2 remains explicit if timeout repeats
9. Character V10.1 / Final Asset tables remain untouched
```

Only after this real run + human review may P2.6 move toward PASS. Current truth remains **NOT PASSED**.

## 11. Testing / CI discipline

Do not consume hosted GitHub Actions quota. Use `[skip ci]` for remote development/documentation commits. Code/test files in the repository are not equivalent to local execution.

## 12. Next safe work

```text
A. git pull
B. re-run the exact rejected Episode so new E2 continuity metadata + E4 Fusion are generated
C. inspect LocalSubject count and the 19-Shot living-room sequence first
D. if anonymous continuity is correct, inspect E3 timeout separately
E. do not advance P5 until Episode-context Breakdown passes real acceptance
```
