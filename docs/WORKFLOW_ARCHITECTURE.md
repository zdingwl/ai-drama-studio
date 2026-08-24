# AI Drama Studio — User Workflow Architecture

Status: CONFIRMED  
Official Baseline: `main`

> 本文件定义用户真正看到和操作的生产流程。
> 内部 Feature 继续作为工程能力、数据 Contract 和回归边界，但不再要求 `一个 Feature = 一个页面 = 用户点一次`。
> 所有 Workflow 的重跑/历史/回退规则必须同时遵守 `docs/WORKFLOW_RUN_VERSIONING.md`。

---

# 1. 核心原则

```text
Feature  = 内部工程职责 / 数据边界
Workflow = 用户生产步骤
```

正确结构：

```text
多个内部能力
→ Workflow Orchestrator
→ 一个连续用户工作区
```

第二条同等重要的硬规则：

```text
任何 Workflow 都不能只执行一次。
```

必须支持：

```text
首次执行
重新执行
生成新 Run / Revision
保留历史
新版本成功后切换 current
失败保留旧 current
下游 stale
版本历史 / 回退
```

“确认”只锁定当前 Revision，不允许锁死整个 Workflow。

---

# 2. 用户主流程

V1 用户主流程固定为：

```text
01 导入原片
↓
02 拉片
↓
03 资产提取
↓
04 人物对白
↓
05 剧本 / 重制设计
↓
06 生成制作
↓
07 最终合成 / 导出
```

左侧导航、项目总览和“下一步”按钮全部按 Workflow 组织。

---

# 3. Workflow 01 — 导入原片

用户一次提交：

```text
项目名称
原片文件
原片语言
目标语言
目标地区
保存位置
↓
[创建并导入]
```

内部：

```text
Project
→ Source Video
→ FFprobe
→ Proxy
→ Audio WAV
→ Thumbnail
→ Source/Proxy/Audio Time Mapping
```

普通首次使用不再要求分别进入“创建项目 / 视频导入 / 视频预处理”。

## 重跑

必须支持：

```text
[重新导入原片]
```

重新导入不能覆盖旧 Source，而是创建新的 Source Version + Preprocess Run。
新 Source 成功切换为 current 后，所有依赖旧 Source 的下游默认 stale。

旧 F02 “一个 Project 永远只有一份 Source”规则将在版本化重构时升级为：

```text
一个 Project 可以有多个 Source Version
但只有一个 current Source
```

原片文件永远不原地覆盖。

---

# 4. Workflow 02 — 拉片

用户入口：

```text
[开始拉片]
```

内部：

```text
Current Proxy
↓
自动 Shot Detection Run
↓
自动创建 Final Shot Draft Revision
↓
直接进入三栏镜头工作台
↓
人工调整
↓
确认当前 Final Shot Revision
```

用户不需要理解 `initialize_shot_workbench()`。

## 重跑

必须同时支持：

```text
A. 重新自动拉片
B. 不重跑模型，只基于当前 Final Shots 重新人工编辑
```

例：

```text
Final Shots R1 confirmed
↓
[重新拉片]
↓
Detection V2
↓
Final Shots Draft R2
↓
Confirm R2
```

或者：

```text
Final Shots R1 confirmed
↓
[重新编辑]
↓
复制为 Draft R2
↓
只人工修正
↓
Confirm R2
```

R1 不删除。

---

# 5. Workflow 03 — 资产提取

拉片完成后先提取稳定生产资产，而不是直接进入对白。

第一版资产范围：

```text
人物资产
场景资产
```

## 人物资产

输入：

```text
Current Final Shots
+ Proxy
```

内部能力：

```text
Face Detection
→ Face Track
→ Face Embedding
→ Cross-shot Actor Clustering
→ Actor Candidate
→ 人工合并/拆分/删除/命名/选 Reference
→ Final Character Revision
```

当前已有 YuNet + SFace Candidate 原型降级为这里的 Actor Visual Evidence 能力，不再是独立用户 Workflow。

## 场景资产

输入：

```text
Current Final Shots
+ Shot Keyframes / Proxy
```

输出：

```text
Scene Candidate
→ 人工合并/拆分/命名/Reference
→ Final Scene Revision
```

第一版先不强制抽取道具/服装/车辆等二级资产；以后需要再加入资产中心。

## 重跑

必须允许局部重跑：

```text
[重新识别人物]
[重新识别场景]
[重新提取全部资产]
```

人物错误不能强迫场景重跑；场景错误也不能强迫人物重跑。

人工资产确认后仍允许创建新的 Revision。

---

# 6. Workflow 04 — 人物对白

前置条件：

```text
Current Final Characters
+ Current Final Shots
+ Current Audio
```

最终产品：

```text
演员 / 角色
+
该角色说了哪些源对白
+
每句对白 Source 时间
```

自动链路：

```text
Audio
↓
Whisper ASR
↓
Dialogue Segments
↓
Speaker Diarization / Voice Cluster
↓
Speaker ↔ Final Character Matching
↓
Actor Dialogue Draft
```

低置信度必须进入：

```text
未归属对白
```

不得强行绑定人物。

人工工作区允许：

```text
对白文字修改
时间修改
拆分 / 合并
改说话人
处理未归属对白
最终确认
```

人物资产的合并/拆分/命名主要属于 Workflow 03，不应再把 Character Candidate 当成人物对白页面的最终产品。

## 重跑

必须允许局部：

```text
[重新 ASR]
[重新 Speaker 分离]
[重新人物/说话人匹配]
[全部重新分析]
[基于当前对白重新编辑]
```

只有 ASR 错误时不必重新做人脸/场景。
只有说话人绑定错误时不必重新跑 Whisper。

---

# 7. Workflow 05 — 剧本 / 重制设计

输入至少包括：

```text
Final Shots
Final Characters
Final Scenes
Final Source Dialogues
```

内部可以继续拆分：

```text
本土演员库 / 选角
Character Bible
Scene Bible
目标对白本土化
对白时长约束
Shot Specification
```

但用户页面按重制设计工作流组织，不按算法模块逐个做一级导航。

所有人工产物使用 Revision，新版本不得覆盖历史版本。

---

# 8. Workflow 06 — 生成制作

内部：

```text
单 Shot 生成
Generation Versions
Auto QC
人工选择版本
批量生成
TTS
Dialogue Fit
Lip Sync
```

生成天然使用版本：

```text
Generation V1 / V2 / V3...
Voice V1 / V2...
LipSync V1 / V2...
```

任何一次重新生成都不能覆盖用户之前选择过的版本。

---

# 9. Workflow 07 — 最终合成 / 导出

内部：

```text
音频组装 / 混音
字幕
最终合成
整集 QC
导出
```

必须支持：

```text
Audio Mix V1/V2
Subtitle V1/V2
Master Render V1/V2
```

旧 Master 保留，最终只选择一个 current approved Master 用于导出。

---

# 10. Orchestrator 规则

建议用户级编排层：

```text
ProjectImportWorkflow
ShotAnalysisWorkflow
AssetExtractionWorkflow
CharacterDialogueWorkflow
RemakeDesignWorkflow
GenerationWorkflow
FinalizationWorkflow
```

Orchestrator 只负责：

```text
阶段编排
Run / Revision 创建
current 选择
依赖快照
stale 传播
失败恢复
```

禁止：

```text
复制底层 SQL
复制 FFmpeg 算法
复制模型推理
覆盖历史业务结果
```

典型结构：

```text
Controller
→ Workflow Orchestrator
→ Capability / Feature Services
→ DB / Media / Model
```

---

# 11. UI 统一版本入口

每个 Workflow 页面必须能看到：

```text
当前版本：V2 / R3
状态：当前 / 已过期 / 历史
```

并按该 Workflow 能力提供：

```text
[重新执行]
[基于当前版本重新编辑]
[版本历史]
```

不是所有按钮每页都必须同时出现，但每个 Workflow 必须有明确的重做路径。

上游改变导致下游 stale 时，UI 必须明确提示，不得静默使用。

---

# 12. 不允许自动级联重跑

上游新版本切换成功：

```text
只标记下游 stale
```

不能未经用户确认自动把所有 AI / 生成任务重新跑一遍。

例如 Final Shots R2 confirmed：

```text
人物资产 stale
场景资产 stale
人物对白 stale / 部分 stale
重制设计 stale
生成结果 stale
最终合成 stale
```

用户再决定：

```text
[重新提取受影响资产]
```

---

# 13. 冻结能力如何处理

已有 Stable Snapshot 继续保留其底层数据/时间轴/ID/安全规则。

但如果旧规则与“生产流程必须支持重跑/版本化”发生冲突，必须通过新 Migration / 新 Revision 模型向前升级，不能以“以前冻结过”为理由拒绝用户重做。

尤其需要升级：

```text
Source Video 单版本限制
confirmed Final Shot 永久不可重开限制
```

升级方式必须保留旧数据，不原地破坏已存在项目。

---

# 14. 当前重构优先级

```text
P0-0  全局 Run / Revision / Current / Stale 基础规则
P0-1  导入原片 Workflow + Source Versioning
P0-2  拉片 Workflow + Final Shot Revision 重开/重跑
P0-3  资产提取 Workflow（人物 + 场景）
P0-4  人物对白 Workflow
```

在版本化底座未补齐前，不继续扩展后续生产功能。
