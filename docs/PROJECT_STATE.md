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

F06 Actor Visual Evidence Prototype: EXISTS / NOT ACCEPTED
Current Product Work: WORKFLOW REFACTOR
```

当前不是继续推进旧的 `F06 Candidate-only` 产品流程。

用户已经确认：原先 `一个 Feature = 一个页面 = 一次用户操作` 的产品流程不合理，正式改成 Workflow 驱动。

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

`docs/FEATURE_SEQUENCE.md` 暂时保留作为内部能力拆分参考，不再代表前端导航和用户必须逐步点击的页面顺序。

---

# 2. Workflow 01 — 导入原片

用户只做一次：

```text
项目名称
+ 原片文件
+ 原片语言
+ 目标语言 / 地区
+ 保存位置
↓
创建并导入
```

系统内部一次编排：

```text
F01 create_project
→ F02 import_source_video
→ FFprobe
→ F03 preprocess_source_video
→ proxy.mp4 + audio.wav + thumbnail.jpg + time mapping
→ 初始化完成
```

F01/F02/F03 底层数据 Contract 保持冻结，不因为 UI 合并而改语义。

---

# 3. Workflow 02 — 拉片

用户只需要：

```text
开始拉片
```

系统内部：

```text
F04 Shot Detection
→ 自动 initialize F05 Final Shot Draft
→ 直接进入三栏镜头工作台
→ 人工调整
→ Confirm Final Shots
```

`initialize_shot_workbench()` 不再作为用户必须理解或点击的步骤。

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

# 5. F06 当前代码如何处理

仓库已经存在 F06 人脸识别原型能力：

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

当前真实素材已经证明 Candidate 聚类结果仍需要改进，因此：

```text
NOT READY_FOR_REVIEW
NOT FROZEN
```

禁止把 `AUTO RUN READY` 理解成 Feature 已验收。

---

# 6. Stable Snapshots

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
docs/features/F03-stable-snapshot.md
docs/features/F04-stable-snapshot.md
docs/features/F05-stable-snapshot.md
```

这些仍然有效。

---

# 7. F04 冻结事实

正式算法：

```text
F03 proxy.mp4
→ FFprobe 逐帧真实 PTS
→ TransNetV2 1.0.5
→ transition merge
→ 120ms debounce
→ Proxy -> Source integer microseconds
→ Shot Candidate
```

冻结规则：

```text
Source Domain integer microseconds
[start_us, end_us)
禁止 frame_index / fps 作为正式时间
shot_candidates.detected_* 永远只读
F05 已存在 shot_edit_sets 后禁止 F04 rerun
```

---

# 8. F05 冻结事实

核心关系：

```text
F04 shot_candidates = Auto Evidence
F05 final_shots      = 后续生产级 Shot
```

Final Shot：

```text
SHOT_<UUID4>
Source Domain integer microseconds
[start_us, end_us)
无 gap
无 overlap
```

confirmed 后边界 / 拆分 / 合并锁定。

播放器/关键帧规则：

```text
当前 Shot 关键帧高优先级
整集缩略图低优先级
缓存命中禁止重新 FFmpeg
Alembic Migration 进程级串行
```

---

# 9. 当前开发顺序

现在暂停继续扩展旧 F06 Candidate 页面。

正式顺序：

```text
P0-1 ProjectImportWorkflow
P0-2 ShotAnalysisWorkflow
P0-3 CharacterDialogueWorkflow 重新 Contract
```

第一步先把“创建项目 + 导入 + 预处理”合成一个真正的用户入口。

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
