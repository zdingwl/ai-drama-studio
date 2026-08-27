---
name: ai-drama-studio-reference-video-v2
version: 3.4.0
description: AI Drama Studio Reference Video 驱动的本地短剧本地化重制工作台开发规则；人物资产正式基线 Character V10.1。
---

# AI Drama Studio — Reference Video V2 / Character V10.1

## 0. 新对话恢复规则

项目事实必须来自 GitHub 当前 `main`，不能只依赖旧聊天记录。

读取顺序：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
→ 当前代码/测试
→ 最新 session handoff
```

如果旧 Feature/Frozen 文档和当前 wiring 冲突，以当前正式架构文档 + 当前可执行代码为准，并先修正文档后再继续开发。

## 1. 产品目标

把多集原短剧拆成可控制的 Shot，并把每个原 Shot 保存为 Reference Video。后续通过人物、场景、关键道具、目标语言 Dialogue、Voice 和替换资产控制重制，而不是把原镜头完全翻译成文字后从零猜测动作与摄影。

正式用户工作区：

```text
01 剧集管理
→ 02 拉片
→ 03 资产
→ 04 内容剧本
→ 05 重制设计
→ 06 生成 / 导出
```

技术中间步骤默认后台运行，不为 FFprobe、MOT、Embedding、Person Evidence、ASR 等内部能力单独制造生产页面。

## 2. 核心实体

```text
Project
Episode
Shot
Character
Scene
Prop
Dialogue
Asset
Voice
Generation
```

Shot 是核心生产单元，Reference Clip 是 Shot 一级正式资产。

AI Evidence 与 Final Asset / Binding / Revision 必须分离。

## 3. Character V10.1 正式人物链

```text
Shot / Reference Clip
↓
YOLOX Person Detection (~12fps, long-shot bounded sampling)
↓
每个检测人物拆成一个明确 Person Instance crop
↓
Capture-first Person Evidence
  YoutuReID Person embedding = primary identity model signal
  clothing_upper / clothing_lower = support
  body_hist / body_structure = support
  YuNet + SFace Face = optional support / conflict signal
↓
Mature MOT = temporal organization only
↓
Project-level Person Evidence model classification
↓
RESOLVED / UNRESOLVED
↓
Track-level known-identity recovery
↓
Final Gate
↓
Character + ShotCharacterBinding
```

正式 profile：

```text
runtime:  character-v10.1-capture-first-model-classification
asset:    f05-assets-v10.1-person-evidence-model-classification
resolver: person-evidence-model-classifier-v10.1
```

`content_models_v2.model_status()` 仍可能显示 V10 model-package profile，因为 V10.1 复用同一套固定模型权重；正式 resolver/runtime 仍以 V10.1 为准。

## 4. 三层语义不可混淆

```text
Observation / Person Evidence / Track = 视觉证据
Identity Class = 跨 Shot 人物身份
Final Character = 项目级人物资产
```

Track 数、Face 数、Crop 数永远不能直接当人物数量。

## 5. Capture-first / Identity 规则

所有 model-usable Person Instance 应先被捕获和保存，再决定身份归属。

支持的 evidence condition：

```text
CLEAN
OCCLUDED
CONTAMINATED
PARTIAL
```

CLEAN 不再是唯一 Gallery/分类入口。

### 创建新身份的正式最低门槛

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID consistency
unique identity class
same-sample cannot-link satisfied
no high-quality Face hard conflict
```

风险视角规则：

- 强 `CONTAMINATED` / substantial `PARTIAL` 可以作为新人 seed，但使用更严格跨 Shot ReID 确认；
- 弱、小、低质量 Partial 只能 save/classify/attach，不能创建新人物；
- Face 不是 RESOLVED 的必需条件；
- 高质量 Face 明确冲突仍是 hard negative。

## 6. Shot-level known-identity recovery

Global Identity 单图分类必须保守，因此正式 runtime 在身份确认后执行第二遍 Track 级恢复：

```text
UNRESOLVED Track
→ compare to every RESOLVED identity gallery
→ aggregate repeated observation support
→ >= 3 usable observations
→ >= 2 supporting observations
→ unique winner + margin
→ cannot-link / Face conflict fail closed
→ attach whole Track to existing identity
```

它只能恢复“已经存在的人物在这个 Shot 里出现”，不能创造新 Character。

正式模块：

```text
engine/app/character_shot_binding_v101.py
```

正式 call order：

```text
resolve_global_identities()
→ recover_unresolved_tracks()
→ update_person_evidence_classification()
→ persist CharacterCandidate / CharacterTrack
→ Final Gate
→ ShotCharacterBinding
```

## 7. Final Character Gate

V10/V10.1 采用显式 allow-list / fail-closed：

```text
identity_status == RESOLVED
+ formal resolver
+ confirmed_gallery_shots >= 3
+ confirmed_gallery_images >= 3
+ final_asset_eligible is not false
```

因此：

- `UNRESOLVED` 不物化；
- 缺失/损坏 identity status 不物化；
- unknown resolver 不物化；
- V10/V10.1 不要求 `face_visible=true`。

正式入口：

```text
engine/app/asset_final_gate_v10.py
```

## 8. Evidence / Final Asset / Revision

```text
ContentAnalysisRun
CharacterCandidate
CharacterTrack
Person Evidence manifest/gallery
= immutable AI Evidence

Character / Scene / Prop
ShotCharacterBinding / ShotSceneBinding / ShotPropBinding
= Final Asset / Final Binding
```

旧 Run 不会因为算法代码变化自动重算或自动改绑。验证新人物逻辑必须重新跑资产提取。

MANUAL / RESTORE Revision 默认保护，新 AI Run 不静默覆盖人工版本。

## 9. 模型与授权边界

当前固定模型：

```text
YOLOX Person Detection
YoutuReID Person Re-identification
YuNet Face Detection
SFace Face Embedding
```

YoutuReID 是人物身份主模型信号。Face 只是可选支持与冲突证据。

不要静默下载或打包仅限非商业研究用途的 InsightFace/ArcFace 预训练模型。未来只有明确可商用或已有授权权重才可以替换 Face provider，并且不得改变 Track → Identity → Final Asset Contract。

## 10. Tracking 规则

Tracking 只做时序组织，不决定跨 Shot 身份。

长 Shot 有采样上限，因此 tracker 必须使用真实时间：

```text
timestamp = local_time_us / 1_000_000
```

Mature MOT 运行时缺失不能静默发布人物结果。具体 BoT-SORT / ByteTrack 行为以 `character_tracking_v10.py` runtime status 和代码为准。

## 11. Run / 批量 / 时间原则

新分析 Run 必须完整成功后才能切 Current。

```text
Person Evidence
→ Track
→ Global Identity
→ Shot-level recovery
→ Candidate/Track persistence
→ counts
→ Current Run
→ Final Asset materialization
```

其它原则：

- `Episode.sort_order` 是批量顺序唯一依据；
- GPU/模型重任务默认 `concurrency = 1`；
- 正式媒体时间统一 integer microseconds；
- Reference Clip 是正式资产，不是缓存；
- 新语言时长不要求与原语言时长相等，最终由 Production Timeline 重建时间轴。

## 12. 当前主代码

```text
engine/app/studio_v2.py
engine/app/media_v2.py
engine/app/content_models_v2.py
engine/app/content_analysis_v2.py
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_observation_v10.py
engine/app/character_person_evidence_v10.py
engine/app/character_person_features_v9.py
engine/app/character_tracking_v10.py
engine/app/character_identity_v10.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/character_gallery_v10.py
engine/app/character_evidence_store_v10.py
engine/app/asset_final_gate_v10.py
engine/app/asset_workspace_v3.py
engine/app/asset_routes_v3.py
engine/app/main.py
```

文件名里的 V5/V6/V9 可能是兼容路径；不要据此判断正式算法版本。

## 13. 测试与真实验收

默认测试目录：

```text
engine/tests/v2
```

V10.1 必须重点锁住：

- 多 Person Instance 不因 Track 碎片膨胀人物数；
- same-sample cannot-link 不被绕过；
- strong risky views 可在严格 >=3 Shot 证据下形成身份；
- weak Partial 不创造人物；
- Face optional；
- UNRESOLVED 不进 Final；
- formal resolver / >=3 images / >=3 shots Final Gate fail closed；
- repeated unresolved Track 能唯一恢复到已有身份；
- ambiguous winner 不能恢复；
- cannot-link / Face conflict 阻断 Track recovery。

当前整仓 CI **不是全绿**，不得对用户声称全部测试通过。真实短剧仍必须在用户 Windows 本机验证模型 Runtime、MOT、FFmpeg、跨 Shot Identity、Final Character 数量和 Shot Binding。

## 14. 重制策略

后续按 Shot 可选择：

```text
REUSE_REFERENCE
AUDIO_ONLY
LIPSYNC_ONLY
CHARACTER_REPLACE
SCENE_REPLACE
PROP_REPLACE
PARTIAL_EDIT
FULL_VIDEO_REGEN
```

不是所有 Shot 都调用最昂贵的视频生成模型。

## 15. Git 工作方式

```text
Default Branch: main
Development Branch: main
```

日常开发直接提交 `main`，不主动新建 feature 分支或 PR，除非用户明确改变要求。

## 16. 文档同步硬规则

人物算法/绑定/Final Gate 发生变化时，本次工作结束前必须同步：

```text
AGENTS.md（baseline 变化）
SKILL.md（正式规则变化）
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md 或 successor
最新 docs/sessions/*.md
```

代码改了而这些入口文档仍描述旧版本，视为开发没有完成。

## Legacy

旧 35 Feature、旧 Frozen Snapshot、旧 Workflow Versioning、Character V1-V9 都是历史资料。

任何“检测到一张脸就创建 Character”“Track 数≈人物数”“Face 必须存在才能发布 V10 人物”的旧逻辑都禁止重新接回正式链路。
