# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。  
> 用户流程以 `docs/WORKFLOW_ARCHITECTURE.md` 为最高优先级；内部 Feature Contract / Stable Snapshot 继续作为工程与数据边界。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main

F01 — 创建项目:       STABLE / FROZEN
F02 — 上传原视频:     STABLE / FROZEN
F03 — 视频预处理:     STABLE / FROZEN
F04 — 自动拉片:       STABLE / FROZEN
F05 — 镜头人工修正:   STABLE / FROZEN

Workflow 01 — 导入原片: IMPLEMENTED / READY FOR LOCAL TEST
Workflow 02 — 拉片:     NEXT REFACTOR
Workflow 03 — 人物对白: CONTRACT REWORK REQUIRED

Actor Visual Evidence Prototype: EXISTS / NOT ACCEPTED
```

当前产品已经从“Feature 页面驱动”切换成 **Workflow 驱动**。

---

# 1. 当前最高优先级规则

正式原则：

```text
Feature = 内部工程职责 / 数据 Contract
Workflow = 用户操作步骤
```

用户主流程：

```text
01 导入原片
↓
02 拉片
↓
03 人物对白
↓
04 剧本 / 重制设计
↓
05 生成制作
↓
06 最终合成 / 导出
```

详细见：

```text
docs/WORKFLOW_ARCHITECTURE.md
```

`docs/FEATURE_SEQUENCE.md` 继续保留作为内部能力拆分参考，不再代表前端导航和用户必须逐步点击的页面顺序。

---

# 2. Workflow 01 — 导入原片

## 用户动作

用户只做一次：

```text
选择原片文件
+ 项目名称
+ 原片语言
+ 目标语言 / 地区
+ 保存位置
↓
[创建并导入]
```

## 当前已实现

后端编排：

```text
POST /api/project-imports
↓
import_project_source_workflow()
↓
create_project()
↓
import_source_video()
↓
preprocess_source_video()
↓
Project + Source + Proxy + WAV + Thumbnail + Time Mapping
```

同步 Project / FFmpeg 工作通过 Starlette threadpool 执行，避免长视频初始化堵死 FastAPI event loop。

前端：

```text
首页“新建项目”改为“导入原片”
↓
一个弹窗选择原片 + 填项目资料
↓
一次 multipart 请求
↓
发送原片进度
↓
本地初始化
↓
成功后直接进入项目
```

新增：

```text
engine/app/project_import_workflow.py
engine/tests/unit/test_project_import_workflow.py
frontend/src/api/project-import.ts
frontend/src/types/project-import.ts
```

旧接口仍保留：

```text
POST /api/projects
POST /api/projects/{id}/source-video
POST /api/projects/{id}/preprocess
```

但它们现在只是：

```text
内部 Feature 能力
历史项目恢复
调试入口
```

普通用户主流程不再逐个调用。

F01/F02/F03 底层数据 Contract 和 Stable Snapshot 完全保持冻结。

## 当前 Gate

```text
READY FOR LOCAL TEST
NOT YET WORKFLOW-FROZEN
```

本机必须验证：

```text
新首页点击“导入原片”
→ 只提交一次
→ 自动完成创建 / Source / Proxy / WAV / Thumbnail
→ 成功进入项目总览
→ 项目总览 Workflow 01 显示已完成
```

---

# 3. Workflow 02 — 拉片

下一步重构目标：

```text
用户点击“开始拉片”
↓
F04 Shot Detection
↓
自动 initialize F05 Final Shot Draft
↓
直接进入三栏镜头工作台
↓
人工调整
↓
Confirm Final Shots
```

用户不再需要分别进入：

```text
自动拉片页面
镜头初始化页面
```

`initialize_shot_workbench()` 变成 Workflow 内部编排动作。

当前 F04/F05 冻结业务和数据语义不改。

---

# 4. Workflow 03 — 人物对白

旧的 Candidate-only F06 产品定义已被替代。

正确目标：

```text
先获取演员 / 角色视觉身份
→ 获取全部源对白
→ Speaker 分离
→ Speaker ↔ Actor 匹配
→ 输出“演员 + 该演员对白”
```

自动链路：

```text
Final Shots + Proxy + Audio
↓
Actor Visual Evidence
↓
Whisper ASR
↓
Speaker Diarization / Voice Cluster
↓
Actor/Speaker Matching
↓
Actor Dialogue Draft
```

必须支持：

```text
未归属对白
```

低置信度不得强行绑定演员。

人物合并/拆分/命名和对白修正以后放在同一个“人物对白”人工工作区完成。

---

# 5. 当前演员视觉代码如何处理

仓库已经存在演员视觉识别原型能力：

```text
OpenCV YuNet
SFace Embedding
Shot-local Track
Cross-shot Candidate Clustering
character_detection_runs / candidates / tracks
```

这部分代码不删除，它降级为：

```text
CharacterDialogueWorkflow
└─ Actor Visual Evidence capability
```

真实素材已经证明 Candidate 聚类结果仍需要改进，因此：

```text
NOT READY_FOR_REVIEW
NOT FROZEN
```

禁止把 `AUTO RUN READY` 理解成整个“人物对白”工作流已验收。

---

# 6. 用户导航当前事实

项目侧栏已经切换成：

```text
01 导入原片
02 拉片
03 人物对白
04 剧本 / 重制设计
05 生成制作
06 最终合成 / 导出
```

旧：

```text
视频导入
视频预处理
自动拉片
镜头修正
```

不再作为并列主导航。

旧 route 暂时保留，供旧项目中断恢复和开发调试使用。

---

# 7. Stable Snapshots

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
docs/features/F03-stable-snapshot.md
docs/features/F04-stable-snapshot.md
docs/features/F05-stable-snapshot.md
```

这些仍然有效。

---

# 8. F04 / F05 冻结事实

F04：

```text
F03 proxy.mp4
→ FFprobe 逐帧真实 PTS
→ TransNetV2 1.0.5
→ transition merge
→ 120ms debounce
→ Proxy -> Source integer microseconds
→ Shot Candidate
```

F05：

```text
F04 shot_candidates = Auto Evidence
F05 final_shots      = 后续生产级 Shot
```

共同时间规则：

```text
Source Domain integer microseconds
[start_us, end_us)
禁止 frame_index / fps 作为正式时间
```

Final Shots confirmed 后边界 / 拆分 / 合并锁定。

---

# 9. 当前开发顺序

```text
P0-1 ProjectImportWorkflow
     = IMPLEMENTED / READY FOR LOCAL TEST

通过用户本机验收后：
↓
P0-2 ShotAnalysisWorkflow
↓
P0-3 CharacterDialogueWorkflow 新 Contract
```

在 Workflow 01 本机通过前，不把它标记 STABLE / FROZEN。

---

# 10. 当前恢复顺序

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/WORKFLOW_ARCHITECTURE.md
→ docs/features/F01-stable-snapshot.md
→ docs/features/F02-stable-snapshot.md
→ docs/features/F03-stable-snapshot.md
→ docs/features/F04-stable-snapshot.md
→ docs/features/F05-stable-snapshot.md
→ 当前 Workflow Session
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不创建 PR、不切换正式基线。
