# AI Drama Studio — Agent Entry Rules (Reference Video V2 / Character V10.1)

本仓库当前正式产品架构为 **Reference Video V2**。人物资产正式运行基线已经升级到 **Character V10.1**。

> **重要：不要从文件名猜当前算法版本。** 例如 `character_runtime_v6.py` 仍是兼容文件名，但文件内容和正式 wiring 已经是 Character V10.1。

## 1. 新对话必须按这个顺序恢复上下文

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
6. 当前相关代码与测试
7. 最新 docs/sessions/*.md handoff
```

不要先读取旧 F01-F06 Frozen Snapshot 或旧 Character V1-V9 文档，再拿历史 Contract 覆盖当前代码。

如果任何文档和当前可执行 wiring 不一致，**先停止功能开发并同步文档**。

## 2. 当前唯一产品基线

```text
Architecture: Reference Video V2
Default branch: main
FastAPI app version: 2.4.1
Formal Character runtime: V10.1
Runtime profile: character-v10.1-capture-first-model-classification
Asset profile: f05-assets-v10.1-person-evidence-model-classification
Resolver: person-evidence-model-classifier-v10.1
```

旧 35 Feature、旧 Frozen Snapshot、旧 Workflow Versioning、Character V1-V9 只作为历史实现参考，不是当前正式业务 Contract。

## 3. V2 核心产品原则

```text
Project
→ 多个 Episode（可拖动排序）
→ Preprocess
→ Shot
→ 每个 Shot 保存独立 Reference Clip
→ 人物 / 场景 / 道具 / Dialogue / Track / Mask 绑定 Shot
→ 替换资产 + Voice + 本地化 Dialogue
→ 按 Shot 选择重制策略
→ Reference Video 驱动生成
→ Production Timeline
→ QC / Export
```

Reference Clip 已天然包含动作、构图、机位、空间关系、镜头运动和大量节奏信息，因此不要为了“拉片更详细”无意义地把所有视觉信息重新文字化。

## 4. 正式用户工作区

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

FFprobe、Embedding、MOT、Person Evidence、ASR、模型内部日志等技术子步骤默认在后台执行。

## 5. Character V10.1 正式人物链

正式链路：

```text
Shot / Reference Clip
↓
YOLOX Person Detection（约 12fps；长 Shot 有采样上限）
↓
每个检测人物拆成独立 Person Instance crop
↓
Person Evidence capture-first
  + YoutuReID Person embedding（主身份模型信号）
  + clothing_upper / clothing_lower
  + body_hist / body_structure
  + YuNet / SFace Face（可选支持）
↓
Mature MOT 做 Shot 内时序组织
↓
Project-level Person Evidence model classification
↓
RESOLVED / UNRESOLVED
↓
V10.1 Track-level known-identity recovery
↓
Final Gate
↓
Character + ShotCharacterBinding
```

### 三层语义不可混淆

```text
Observation / Person Evidence / Track = 视觉证据
Identity Class = 跨 Shot 身份
Final Character = 项目级可编辑人物资产
```

**Track 数、Face 数、Crop 数都不能直接当人物数量。**

## 6. V10.1 Identity Contract

当前正式创建新人物的最低结构门槛：

```text
>= 3 independent Shots
>= 3 model-usable Person Images
stable cross-Shot Person-ReID class
unique winner
no cannot-link violation
no high-quality Face hard conflict
```

重要规则：

- Face 是可选支持，不再是创建人物的必需条件。
- CLEAN 不是唯一可用人物图。
- CLEAN / OCCLUDED 可按正常门槛参与身份形成。
- 强 `CONTAMINATED` / 大面积 `PARTIAL` 可以提出新人，但需要更严格跨 Shot ReID 确认。
- 弱、小、低质量 Partial 只能保存/分类/挂回，不能创建新人。
- 同一采样时刻的不同 Person Instance 是硬 cannot-link。
- 高质量 Face 明确冲突必须阻断合并。

## 7. Shot-level Binding Recovery 是正式链的一部分

V10.1 在 Global Identity 确认后增加：

```text
recover_unresolved_tracks(candidates)
```

用途：解决“人物资产识别正确，但某个 Shot 仍显示待解析人物/未绑定”的问题。

规则：

```text
UNRESOLVED Track
→ 对已有 RESOLVED identity gallery 做整段多帧比对
→ >= 3 usable observations
→ >= 2 supporting observations
→ unique winner + margin
→ cannot-link / Face conflict fail closed
→ 整个 Track 并入已有身份
```

它：

- **不能创建新 Character**；
- 只能挂到已经确认的 `RESOLVED` identity；
- winner 不唯一时保持 `UNRESOLVED`；
- recovery 后 `CharacterTrack` / `ShotCharacterBinding` 使用新的 Track 归属。

正式模块：

```text
engine/app/character_shot_binding_v101.py
```

## 8. Final Character Gate

V10/V10.1 正式 Final Gate 是显式 allow-list / fail-closed：

```text
identity_status == RESOLVED
+ formal resolver
+ confirmed_gallery_shots >= 3
+ confirmed_gallery_images >= 3
+ final_asset_eligible is not false
```

对于 V10/V10.1：

- Face visible **不是** Final Gate 必需条件；
- `UNRESOLVED` 永远不物化；
- 缺失/损坏 status 或 resolver 永远 fail closed。

正式入口：

```text
engine/app/asset_final_gate_v10.py
```

## 9. Evidence 与 Final Asset 分离

```text
ContentAnalysisRun / CharacterCandidate / CharacterTrack / Person Evidence
= immutable AI Evidence

Character / ShotCharacterBinding
= editable Final Asset / Binding
```

旧 Run 不会因为代码更新自动重新绑定。人物算法变化后要验证效果，必须重新执行资产提取产生新 Run。

MANUAL / RESTORE Asset Revision 默认受保护，新 AI Run 不得静默覆盖人工版本。

## 10. 当前正式代码边界

```text
engine/app/main.py
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
```

兼容文件名中的 V5/V6/V9 不等于正式算法版本。判断当前版本必须看 `character_visual_v2.py` facade、`character_runtime_v6.py` runtime profile 和 `PROJECT_STATE`。

## 11. Model / License boundary

固定人物模型集：

```text
YOLOX
YoutuReID
YuNet
SFace
```

YoutuReID 是主身份模型。Face 只作为可选支持与冲突证据。

不要静默下载或打包仅限非商业研究用途的 InsightFace/ArcFace 预训练权重。未来替换 Face provider 时，必须先确定可商用/已有授权权重，并保持 Track → Identity → Final Asset Contract 不变。

## 12. Run / Revision / 时间原则

- 新 Run 完整成功后才能切 Current。
- `Episode.sort_order` 是批量顺序唯一依据。
- GPU/重任务默认顺序执行，`concurrency = 1`。
- 正式媒体时间使用 integer microseconds。
- Reference Clip 是正式 Shot 资产，不是临时缓存。
- Character / Scene / Prop 是项目级实体，Shot 绑定实体 ID。

## 13. 当前测试现实

不要声称“整个 CI 已通过”。当前全量 GitHub Actions 仍有 legacy/environment 失败，包括：

```text
CI 缺 cv2/full media runtime
CI 缺 trackers runtime
旧 V6 断言与 V10.1 语义不一致
FFmpeg 相关轻量 CI 环境差异
旧 workspace 测试预期
frontend vue-tsc / TypeScript compatibility
```

新的 V10.1 Shot binding recovery 已加入专门回归：

```text
稳定多帧 → 已确认身份
ambiguous winner → 不绑定
cannot-link conflict → 不绑定
```

最终 Release Gate 仍是用户 Windows 本机真实短剧素材。

## 14. Git 工作方式

用户要求日常开发直接提交默认分支：

```text
Default Branch: main
Development Branch: main
```

不要主动新建 feature 分支或 PR，除非用户以后明确要求。

## 15. 文档与代码同步硬规则

任何人物代码修改结束前，至少检查并同步：

```text
AGENTS.md（正式基线变化时）
SKILL.md（正式规则/基线变化时）
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md 或其 successor
最新 docs/sessions/*.md
```

若代码和文档不一致，本次开发视为没有收口。
