# AI Drama Studio — 拉片先行 / Breakdown-first 资产识别改造地图

> **Status:** ACCEPTED TARGET PLAN / **P1-P2 IMPLEMENTATION CONDITIONAL PASS** / **P2-E1 EPISODE-CONTEXT FUSION IMPLEMENTED** / **P2.6 REAL-MODEL ACCEPTANCE NOT PASSED** / **P3 UI ACCEPTANCE IN PROGRESS** / **P4 IMPLEMENTED, LOCAL ACCEPTANCE PENDING**  
> **Created:** 2026-08-27  
> **Last synchronized:** 2026-08-28 18:12 +08:00  
> **Repository:** `zdingwl/ai-drama-studio`  
> **Current executable baseline:** Reference Video V2 / FastAPI 2.4.1 / Character V10.1 / Breakdown P1 + P2 + Episode-context E1 Fusion + P3 + P4

## 0. 产品定义

“拉片”不等于“切镜头”。镜头切分只是精确时间和编辑边界，真正目标是把整集原视频变成可追溯、可编辑、可用于重制的结构化视听 Draft。

最终用户关心：

```text
场景段
人物A / 人物B
每镜头画面
动作
对白
OCR 文字
关键道具
镜头语言
时间轴
```

核心原则：

> **先看懂，再识别，再回填。**

当前新增的语义原则：

> **Shot 是拉片结果的最小展示单位，不是 AI 理解内容的上下文边界。**

这意味着：

```text
切镜 ≠ 对白断句
切镜 ≠ 场景切换
切镜 ≠ 人物语义上下文终止
```

第一遍 AI 拉片不假装知道全剧真实身份，因此继续使用匿名主体。

## 1. 目标主线

```text
原视频 / Episode
↓
视频预处理
↓
Shot Detection + ShotRevision
只负责精确切镜边界
↓
Episode ASR / OCR
↓
连续/上下文视频理解
↓
Episode-context Scene / Dialogue / Subject continuity
↓
匿名结构化 Breakdown Draft
↓
Draft 指导 Character / Scene / Prop Evidence 搜索
↓
专用视觉/音频 Evidence 验证
↓
跨 Shot / 全项目资产归并
↓
Character / Scene / Prop + Final Shot Bindings
↓
真实资产身份回填 Draft
↓
Final Breakdown
↓
重制设计 / 视频生成
```

Episode-context 详细迁移计划见：

```text
docs/BREAKDOWN_EPISODE_CONTEXT_PLAN.md
```

## 2. 不可破坏的架构原则

### 2.1 Reference Video V2 保留

```text
Project / Episode
FFmpeg / FFprobe
integer microseconds
TransNetV2 Shot boundaries
ShotRevision / ShotRevisionItem
Reference Clip / thumbnail / keyframes
```

Historical Breakdown 必须锚定 exact ShotRevision/ShotRevisionItem，不允许按 Current Shot ordinal/timestamp 猜历史。

### 2.2 Shot boundary 角色重新明确

Shot boundary 是：

```text
编辑边界
Reference Clip 边界
最终展示/检索投影边界
```

Shot boundary 不是：

```text
对白句子边界
Scene 语义边界
AI 最大上下文边界
```

### 2.3 Draft != Final identity/asset truth

```text
人物A / subject_A / LocalSubject != Character
SceneSegmentDraft != Final Scene
DraftPropHint != Final Prop
```

Draft 是 soft semantic prior/search hint。可靠 measurable Evidence + fail-closed resolution 决定 Final assets。

### 2.4 Character V10.1 hard gates 保持权威

P2/P3/P4/P5 不允许：

```text
放松 Character V10.1 identity gates
绕过 same-sample cannot-link
忽略 Face hard conflict
让 VLM/ASR 创建 Character
从 Draft prose 直接写 Final Character binding
```

### 2.5 Raw Evidence and Draft 分层

P2 Provider outputs 继续是 immutable sidecars；Fusion 不删除/改写 raw evidence。历史 sidecar 永不因新 Fusion 策略而重写。

### 2.6 Heavy jobs 顺序执行

Batch 视频/模型任务继续：

```text
Episode.sort_order
concurrency = 1
```

除非后续有独立 scheduler + 明确资源控制，不得擅自并行重模型任务。

## 3. 当前实现地图

| Area | Current | Next |
|---|---|---|
| Project/Episode | IMPLEMENTED | keep |
| FFmpeg/FFprobe preprocess | IMPLEMENTED | keep |
| Shot/Reference Clip | IMPLEMENTED | keep |
| ShotRevision/manual edit/history | IMPLEMENTED | keep |
| P1 anonymous Draft storage/lifecycle | CONDITIONAL PASS | keep |
| P2 raw Evidence sidecar | CONDITIONAL PASS | real-video verify |
| P2 Episode ASR | IMPLEMENTED | real-video verify |
| P2 OCR | IMPLEMENTED | real-video verify |
| P2 current Qwen VLM | IMPLEMENTED, single Reference Clip | P2-E2 continuous windows |
| P2-E1 Episode-context Fusion | IMPLEMENTED | local-real accept |
| P2 full orchestrator | IMPLEMENTED / wired to E1 | real-video verify |
| P2 acceptance reports | IMPLEMENTED | produce real PASS report |
| 02 拉片 UI | IMPLEMENTED | browser/UI acceptance + continuation rendering |
| Draft-guided Scene/Prop Evidence | IMPLEMENTED P4 | local/model acceptance |
| Draft ↔ Character safe mapping | NOT IMPLEMENTED | paused until Episode-context baseline stable |
| Final fill-back/renderers | NOT IMPLEMENTED | later |
| downstream remake integration | PARTIAL/PLANNED | later |

## 4. P1 / P2 implementation acceptance

Current user review:

```text
P1/P2 implementation acceptance = CONDITIONAL PASS
```

Meaning:

- data contracts, lifecycle, persistence and provenance direction are accepted;
- Provider/Fusion/orchestration implementation is accepted conditionally;
- this is **not** real-model quality PASS;
- Episode-context E1 is a new production behavior and still requires local-real acceptance.

## 5. P2 formal implementation

### P2.1 raw Evidence sidecar

```text
PROCESSING BreakdownRun
→ exact frozen ShotRevision / ShotRevisionItems
→ Provider Contract
→ validated raw Evidence
→ fingerprinted immutable sidecar
→ provenance
```

### P2.2 Episode ASR

```text
faster-whisper==1.2.1
large-v3
word timestamps
ASR_SEGMENT + ASR_WORD
Episode source integer microseconds
```

ASR 本身已经是整集时间轴，不需要为了 E1 改成逐 Shot。

### P2.3 OCR

```text
rapidocr==3.9.2
PP-OCRv6 small
ONNX Runtime
multi-frame sampling
OCR_OBSERVATION + geometry + source time
```

### P2.4 current VLM

```text
Qwen/Qwen3-VL-4B-Instruct
current input = exact historical Reference Clip, one Shot at a time
anonymous semantic JSON
Simplified-Chinese Draft prose
```

这是当前明确的临时限制，不再被当作最终目标。

### P2-E1 Episode-context Fusion

正式生产模块：

```text
engine/app/breakdown_p2_fusion_episode_v2.py
profile = breakdown-p2-fusion-episode-context-e1-v2
```

生产 pipeline 已接入该 Fusion。

#### Scene continuity

```text
strong scene anchor
→ current Scene

UNKNOWN / missing / generic scene hint
→ inherit current Scene

compatible specificity
病房 → 医院病房
客厅 → 家中客厅
→ same Scene

strong location contradiction
or explicit INT ↔ EXT contradiction
→ new Scene Segment
```

E1 核心规则：

```text
看不出来 != 换场
```

#### Cross-Shot dialogue

```text
ASR_SEGMENT = Episode-time dialogue text truth
Shot TimelineEvent(DIALOGUE) = projection
```

跨镜对白不再按 word timing 改写成半句话。多个 Shot projection 共享：

```text
dialogue_group_id = asr_segment_id
dialogue_source_start_us / dialogue_source_end_us
projection_start_us / projection_end_us
continues_from_previous_shot / continues_to_next_shot
```

ASR_WORD 仍是 immutable raw/support Evidence。

### P2.6 production + acceptance tooling

Formal top-level profile remains:

```text
breakdown-p2-full-v1
ASR → OCR → VLM → Episode-context E1 Fusion → P1 validator
```

Background APIs unchanged：

```text
POST /api/episodes/{episode_id}/tasks/breakdown
POST /api/projects/{project_id}/tasks/breakdown-batch
GET /api/breakdown/p2/runtime-preflight
POST /api/breakdown-runs/{run_id}/p2-acceptance
```

## 6. Episode-context migration phases

### P2-E1 — Fusion continuity

```text
IMPLEMENTED ON MAIN
LOCAL-REAL ACCEPTANCE PENDING
```

解决：

```text
同场景特写/虚化导致 Scene 碎裂
跨切镜对白被切成残句
```

### P2-E2 — overlapping continuous-window VLM

```text
PLANNED / NOT IMPLEMENTED
```

目标：逻辑整集、执行分窗。

建议默认：

```text
20–40 秒窗口
20–35% overlap
窗口携带 exact Shot boundaries
按 Episode 顺序串行
```

输出 window-level：

```text
Scene continuity/change candidates
anonymous subject continuity hints
key actions
prop continuity hints
shot-aware observations
```

### P2-E3 — contextual Shot refinement

```text
PLANNED
```

每镜精细结果使用：

```text
Scene Context
+ Previous Shot
+ Current Shot
+ Next Shot
+ overlapping ASR
+ overlapping OCR
+ window context
```

### P2-E4 — final Episode-context Fusion

```text
PLANNED
```

最终语义关系：

```text
Scene = spans multiple Shots
Dialogue = spans one or more Shots
LocalSubject = Scene/window-scoped anonymous continuity
Shot = display/search projection of Episode semantic ranges
```

E1 的确定性规则届时作为保守 fallback，而不是唯一 Scene continuity 来源。

## 7. P2.6 real-model acceptance status

Current authoritative result：

```text
P2.6 Windows / real-model acceptance = NOT PASSED
P2-E1 real-short-drama behavior acceptance = PENDING
```

Required retest：

```text
strict preflight
+ real short-drama Episode
+ ASR → OCR → VLM → E1 Fusion → P1 validator
+ cross-Shot dialogue check
+ same-scene closeup/blur continuity check
+ genuine scene-change check
+ acceptance report
+ human review required scores >=4/5
+ no blocking issues
= P2.6 PASS
```

Until that evidence exists, forbidden wording includes `P2 ACCEPTED / P2 CLOSED / P2.6 PASS`.

## 8. P3 — UI acceptance in progress

Current normal user flow：

```text
02 拉片
├─ 镜头管理
└─ 拉片结果
   ├─ Scene / Shot
   ├─ 人物/匿名主体
   ├─ 对白
   ├─ 动作
   ├─ 关键道具
   └─ Reference Clip
```

Technical provenance remains backend truth but is not primary presentation.

E1 后 UI 应利用：

```text
dialogue_group_id
continues_from_previous_shot
continues_to_next_shot
```

把跨镜对白显示成“对白继续”，而不是两个互不相关的重复句子。

P3 status：

```text
implementation = IMPLEMENTED
browser/UI acceptance = IN PROGRESS
accepted/closed = NO
```

## 9. P4 — Draft-guided Scene / Prop Evidence

P4 已实现：

```text
engine/app/breakdown_asset_guidance_v1.py
profile = breakdown-asset-guidance-p4-v1
engine/app/asset_semantics_p4_v1.py
```

只允许 current revision-safe Draft 作为 soft guidance：

```text
BreakdownRun.is_current = true
status READY / READY_WITH_WARNINGS
source_shot_revision_id == current ShotRevision.id
exact ShotRevisionItem anchor
current original_shot_id still exists
```

禁止：

```text
STALE/history → current Shot by ordinal
history → current Shot by nearest timestamp
FAILED/PROCESSING Draft as guidance
Draft Scene/Prop bypassing visual verification
```

Scene flow：

```text
SceneSegmentDraft soft hint
→ current visual verification
→ MATCH / CONFLICT / UNKNOWN
→ existing SceneCandidate / ShotSceneEvidence
```

Prop flow：

```text
DraftPropOccurrence
→ current visual verification
→ observed=false: reject
→ observed=true + confidence >=0.45: Evidence
new unprompted prop confidence >=0.68
```

P4 status：

```text
implementation = IMPLEMENTED
local/model acceptance = PENDING
quality PASS = NO
```

## 10. Formal Character V10.1 — protected

```text
YOLOX Person Detection
→ capture-first Person Evidence
→ mature MOT
→ YoutuReID project-level identity
→ RESOLVED / UNRESOLVED
→ explicit Shot × known-Character Assignment
→ Final Character Gate
```

Never relax：

```text
new identity >=3 independent Shots
new identity >=3 model-usable images
same-sample cannot-link
high-quality Face hard conflict
ambiguous winner unresolved
explicit shot_presence_assignments = current Final binding truth
```

Episode-context semantics may guide later search, but cannot override these gates.

## 11. Formal phase order from here

```text
P0 Planning / Contract                         COMPLETE
P1 implementation                              CONDITIONAL PASS
P2 implementation                              CONDITIONAL PASS
P2-E1 Episode-context Fusion                   IMPLEMENTED / LOCAL-REAL ACCEPTANCE PENDING
P2-E2 continuous-window VLM                    PLANNED
P2-E3 contextual Shot refinement               PLANNED
P2-E4 final Episode-context Fusion             PLANNED
P2.6 Windows / real-model acceptance           NOT PASSED
P3 02 拉片 UI                                  IMPLEMENTED / UI ACCEPTANCE IN PROGRESS
P4 Draft-guided Scene / Prop evidence          IMPLEMENTED / LOCAL ACCEPTANCE PENDING
P5 Draft ↔ Character safe integration          PLANNED / PAUSED
P6 Final identity/asset fill-back + renderers   PLANNED
P7 downstream remake integration               PLANNED
```

P5 暂停，直到 Episode-context Breakdown baseline 通过本地真实素材验证，避免在已知 Shot-centric 语义错误上继续叠加人物上下文集成。

## 12. 禁止捷径

```text
Shot Detection == complete Breakdown                    forbidden
Shot boundary == dialogue sentence boundary             forbidden
Shot boundary == Scene boundary                         forbidden
single closeup UNKNOWN == new Scene                     forbidden
VLM prose == Final identity                              forbidden
VLM subject_A → Character                                forbidden
ASR speaker → Character                                  forbidden
SceneSegmentDraft == Final Scene                         forbidden
DraftPropHint == Final Prop                              forbidden
P4 observed=false DraftPropHint -> PropCandidate         forbidden
STALE Breakdown -> current asset guidance                forbidden
Fusion deletes/rewrites raw Evidence                     forbidden
semantic context overrides Face/cannot-link              forbidden
missing real acceptance but docs claim PASS              forbidden
```

## 13. 用户可理解的流程

```text
① 视频处理
② 镜头切分（只负责时间/编辑边界）
③ 整集上下文 AI 拉片
④ 人物 / 场景 / 道具专用识别验证
⑤ 资产确认与回填
⑥ 最终拉片
⑦ 重制
```

当前已走到：

```text
③ 的 E1 Fusion 已落地
③ 的连续窗口视觉理解 E2 尚未实现
④ 的 Scene/Prop guidance P4 已实现但仍待本地验收
```
