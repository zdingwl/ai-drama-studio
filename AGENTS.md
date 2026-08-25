# AI Drama Studio — Agent Entry Rules (Reference Video V2 / Character V6)

本仓库已经于 2026-08-24 按用户明确决策重建为 **Reference Video 驱动的短剧本地化重制工作台**。
2026-08-25 人物资产链已升级为 **Character V6**；旧 Character V1-V5.1 只能作为历史算法参考，不能覆盖 V6 身份语义。

## 1. 当前唯一产品基线

读取顺序：

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/REFERENCE_VIDEO_V2_ARCHITECTURE.md
5. 当前 Feature / Workflow 文档
6. 当前 V2/V6 代码、测试、Session
```

旧的 35 Feature、F01-F06 Frozen Snapshot、Workflow Versioning Refactor、旧 Source Video / Shot Candidate / Final Shot 设计，以及 Character V1-V5.1 的“检测碎片≈人物资产”做法都属于 **Legacy History**。

## 2. V2 核心原则

```text
Project
→ 多个 Episode（可拖动排序）
→ Preprocess
→ Shot
→ 每个 Shot 保存独立 Reference Clip
→ 人物 / 场景 / 道具 / Dialogue / Track / Mask 绑定 Shot
→ 替换资产 + Voice + 本地化 Dialogue
→ 按 Shot 选择重制策略
→ Reference Video 驱动视频生成
→ 弹性 Production Timeline
→ QC / Export
```

原镜头本身承担动作、构图、机位、人物空间关系、镜头运动和大部分节奏信息，因此 V2 不追求把这些信息全部转换成高成本文字描述。

## 3. 正式用户工作区

```text
01 剧集管理
02 拉片
03 资产
04 内容剧本
05 重制设计
06 生成 / 导出
```

技术子流程是后台能力，不为 FFprobe、Embedding、MOT、ASR 等内部模型单独制造生产页面。

## 4. Character V6 当前事实

人物链路必须严格分成三层：

```text
Observation / Track Evidence
→ Global Identity
→ Final Character
```

**Track 不是 Character，检测碎片也不是 Final Asset。**

当前正式链：

```text
YOLOX Person Observation（约 12fps，长 Shot 有采样上限）
+ YuNet Face Detection
+ SFace Face Embedding Provider
+ YoutuReID Body ReID
↓
BoT-SORT Mature MOT（默认，Camera Motion Compensation）
  └ Runtime / init failure → 整 Shot 从头 ByteTrack fallback
↓
CLEAN Track Gallery / Face hard-conflict split
↓
Project-level Global Identity Graph
↓
RESOLVED / UNRESOLVED
↓
Final Gate: RESOLVED only
```

Tracking 只解决同一 Shot 内的连续轨迹；跨 Shot “是不是同一个人”只能由 Global Identity Graph 决定。

### Face Provider 授权边界

当前 Face provider 继续使用 YuNet + SFace，并与 Global Resolver 解耦。

不要静默下载或打包仅限非商业研究用途的预训练 ArcFace / InsightFace 模型。只有在项目明确选定可商用或已有授权的 ArcFace 权重后才替换 provider；替换 provider 不得改变 Track / Identity / Final Asset 业务结构。

### V6 Resolve 门槛

当前自动发布策略比早期 V6 草案更保守：

```text
同一身份至少有 2 条 Face Track
且 Face Evidence 覆盖至少 2 个不同 Shot
→ RESOLVED

单 Shot 高清脸 / 孤立侧脸 / 一次误检
→ UNRESOLVED

纯 body-only
→ 不允许自行创建 Character

body-only
→ 只允许在相邻 Shot + 极强 CLEAN ReID 时挂回已有 Face cluster
```

这是为了防止单个演员的侧脸、特写、遮挡碎片再次制造“人物020”式虚假人物。

### Global Identity 不变量

- 同 Shot 时间重叠的两条人物 Track 是永久 cannot-link。
- 明确 Face 冲突必须阻断图传递合并。
- Body ReID 只能支持 Face Identity，不能独立创造人物。
- UNRESOLVED 保留真实 bbox / face_visible / sample Evidence，但不增加 Final Character 数量。
- 缺失、损坏或未来未知的 identity_status 必须 fail closed；**只有明确 `RESOLVED` 才能进入 Final Character。**

## 5. Evidence 与 Final Asset

AI Evidence 与 Final Asset 必须分离。

当前人物允许在资产工作流中把 **RESOLVED Identity 自动物化为 AUTO Final Character**，这是 Character V6 的正式 Final Gate，不代表可以修改 Evidence。

```text
CharacterCandidate / CharacterTrack
= immutable AI Evidence

Character / ShotCharacterBinding
= editable Final Asset / Binding
```

UNRESOLVED Candidate 即使内部真实 `face_visible=true`，也只能保留 Evidence，不能通过旧 materializer 的“看见脸就创建人物”逻辑进入 Final Asset。

Final Gate 禁止：
- 临时篡改 Evidence 字段来绕旧逻辑；
- monkeypatch 全局 materializer；
- deny-list 式“只排除 UNRESOLVED”。

必须采用显式 allow-list：`identity_status == RESOLVED`。

## 6. Run / Revision / 事务原则

新 Run 必须完整成功后才能切 Current。

人物 Evidence 持久化顺序：

```text
Track / Global Identity
→ RESOLVED / UNRESOLVED 标记
→ Candidate / Track / Scene Evidence
→ counts
→ Current Run 切换
→ commit
```

任何一步失败，旧 Current 不动。

Final Asset 使用独立 Asset Revision；MANUAL / RESTORE 默认受保护，新 AI Run 不得静默覆盖人工版本。

## 7. 数据原则

- 项目允许多个 Episode。
- `Episode.sort_order` 是所有批量任务的唯一顺序依据。
- 批量预处理、批量拉片和后续 GPU 重任务默认 **顺序执行，concurrency = 1**。
- 所有正式媒体时间使用 integer microseconds。
- Shot 是核心生产单元。
- Reference Clip 是正式资产，不是临时缓存。
- Character / Scene / Prop 是项目级实体，Shot 引用实体 ID。
- Dialogue 必须区分 `dialogue / narration / inner_monologue`；未确认时可保留 `unknown`。
- 新语言时长不要求等于原语言时长；最终使用 Production Timeline。

## 8. V2 / V6 主代码边界

```text
engine/app/main.py
engine/app/studio_v2.py
engine/app/media_v2.py
engine/app/content_models_v2.py
engine/app/content_analysis_v2.py

engine/app/character_observation_v6.py
engine/app/character_tracking_v6.py
engine/app/character_identity_v6.py
engine/app/character_runtime_v6.py
engine/app/asset_final_gate_v6.py
engine/app/asset_workspace_v3.py
engine/app/asset_routes_v3.py

frontend/src/views/ProjectList.vue
frontend/src/views/ProjectStudio.vue
frontend/src/api/client.ts
frontend/src/types/studio.ts
```

`character_visual_v5.py` 等旧人物模块目前仍可能被 V6 复用数据类 / 低层工具函数；这不代表 V5 的身份决策逻辑仍是正式入口。

## 9. 测试基线

默认 pytest 只运行：

```text
engine/tests/v2
```

Character V6 必须至少锁住：

```text
同一演员多个 Shot 碎片 → Global Graph 合回一个身份
三个不同演员 → 保持三个身份
同框两人 → 不能经第三 Track 传递合并
单 Shot 高清脸 → UNRESOLVED
两 Shot Face 确认 → RESOLVED
纯背影 / body-only → 不能创建 Character
UNRESOLVED → Evidence 保留，Final Character 不增加
缺失 identity_status → Final Gate fail closed
MOT 输出按 IoU 映射回 Observation
稀疏采样 → tracker 收到真实 timestamp
BoT-SORT 中途失败 → 当前 Shot 从头 ByteTrack 重跑
```

除此之外必须在用户 Windows 本机用真实短剧素材验收 Tracking、跨 Shot Identity、Final Character 数量和 GPU Runtime。

## 10. Git 工作方式

用户已明确要求：**不要为日常开发新建分支，直接在默认分支 `main` 开发。**

```text
Default Branch: main
Current Development Branch: main
```

规则：
- 后续代码、文档、测试直接提交到 `main`；
- 不主动创建 feature/rebuild 分支；
- 不主动创建 PR；
- 已存在的历史分支只作为历史记录；
- 只有用户以后明确要求时，才改变这一 Git 工作方式。

## 11. 最重要的判断标准

任何新功能都先问：

> 这个数据是否是未来重制 Shot 时 Reference Video 无法可靠提供、但系统必须知道的信息？

如果 Reference Video 已经天然包含，而且结构化后没有明显编辑 / 绑定 / 生成价值，就不要为了“拉片看起来详细”而增加高成本字段。
