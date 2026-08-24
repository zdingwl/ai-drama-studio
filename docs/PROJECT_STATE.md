# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。详细 Contract / Function Contract / Database Dictionary / Stable Snapshot / Session 记录放在 `docs/features/` 与 `docs/sessions/`。

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
F06 — 自动人物识别:   PLANNED / CONTRACT CONFIRMED

Current Feature: F06 — 自动人物识别
Coding Status: NOT STARTED
```

注意：左侧导航可以继续显示“人物对白”作为大工作区名称，但正式 35 Feature 顺序保持：

```text
F06 自动人物识别
→ F07 人物人工修正
→ F08 ASR 源对白识别
→ F09 Speaker / Character 匹配
→ F10 源对白人工修正
```

不得把 Whisper / Speaker / 人工对白提前塞回 F06。

---

## Stable Snapshots

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
docs/features/F03-stable-snapshot.md
docs/features/F04-stable-snapshot.md
docs/features/F05-stable-snapshot.md
```

---

## 当前恢复顺序

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-stable-snapshot.md
→ docs/features/F02-stable-snapshot.md
→ docs/features/F03-stable-snapshot.md
→ docs/features/F04-stable-snapshot.md
→ docs/features/F05-stable-snapshot.md
→ docs/features/F06-auto-character-detection.md
→ docs/features/F06-function-contracts.md
→ docs/features/F06-database-dictionary.md
→ docs/features/F06-p0-checklist.md
→ 最新 F06 Session
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建/切换/删除分支，不创建 PR。

---

# F04 冻结事实

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

真实 Windows 本机验收：

```text
31 Shot Candidates
30 Cuts
1659 PTS Aligned Frames
66.360s Source Range
Device: cuda
PyTorch: 2.5.1+cu124
GPU: NVIDIA GeForce RTX 3060 Ti
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

# F05 冻结事实

F05 是三栏 Final Shot 工作台：

```text
左：Final Shot 列表 / 缩略图 / 时间 / 当前 Shot 高亮
中：F03 Proxy 播放器 / Shot Timeline / 5 关键帧
右：Final Start/End / 拆分 / 合并 / 确认 / 语义占位
```

核心关系：

```text
F04 shot_candidates = Auto Evidence（只读）
F05 final_shots      = 后续生产级 Shot
```

Final Shot ID：

```text
SHOT_<UUID4>
```

真实测试项目：

```text
31 Final Shots
shot_edit_sets.status = confirmed
```

confirmed 后边界 / 拆分 / 合并全部锁定。

Time Contract：

```text
Source Domain integer microseconds
[start_us, end_us)
first.start == edit_set.source_start_us
last.end == edit_set.source_end_us
prev.end == next.start
ordinal = 1..N
无 gap
无 overlap
```

F05 已冻结播放器/关键帧规则：

```text
当前 Shot 5 张关键帧 = 高优先级，播放中允许串行加载/生成
整集缩略图 = 低优先级，播放期间暂停
缓存存在且非空 -> 禁止重新 FFmpeg
Alembic init_database -> 进程级锁 + 每 DB path 只 migration 一次
```

---

# F06 已确认规划

## 唯一目标

F06 只回答：

> 原片画面里有哪些“很可能是同一个人”的自动人物候选？

输入：

```text
confirmed F05 Final Shots
+ F03 Proxy
```

输出：

```text
Character Detection Run
Character Track
Character Candidate
```

F06 自动 Evidence != F07 Final Character。

## 正式 V1 技术路线

```text
Final Shots
→ Shot 自适应采样（约 4 FPS，每 Shot 3–12 帧）
→ OpenCV YuNet 人脸检测
→ OpenCV SFace 对齐 + Embedding
→ Shot-local Face Track
→ 保守跨 Shot Clustering
→ Character Candidate
```

计划 Python 新依赖：

```text
opencv-python==4.11.0.86
```

复用：

```text
numpy==2.1.3
FFmpeg / FFprobe
```

V1 OpenCV DNN 固定 CPU；不修改当前 PyTorch/CUDA 基线。

模型：

```text
face_detection_yunet_2023mar.onnx
face_recognition_sface_2021dec.onnx
```

编码前必须完成：

```text
模型固定下载
→ 实际 SHA-256
→ config/models.yaml
→ Windows FaceDetectorYN / FaceRecognizerSF smoke test
```

## F06 聚类原则

```text
Precision 优先
宁可同一人物被拆成多个 Candidate
也不要把两个不同人物自动合并
```

明确 cannot-link：同一时段同框出现的两个独立 Face Track 不得自动归为同一 Candidate。

## F06 Database Plan

Migration：

```text
0007_create_character_detection
```

只新增：

```text
character_detection_runs
character_candidates
character_tracks
```

## F06 API Plan

```text
GET  /api/projects/{project_id}/character-detection
POST /api/projects/{project_id}/character-detection
POST /api/projects/{project_id}/character-detection/rerun
GET  /api/projects/{project_id}/character-detection/candidates/{candidate_id}/cover
```

公开业务函数只保留：

```text
get_character_detection()
run_character_detection()
rerun_character_detection()
```

算法内部函数不各自创建 Controller。

## F06 页面 Plan

```text
左：Character Candidate 列表
中：Proxy 播放器 + 人物出现时间轴
右：自动 Candidate 详情 + Evidence Faces
```

F06 页面只读，不允许命名、合并、拆分、删除人物；这些属于 F07。

---

# F06 明确不做

```text
人物正式姓名
人物人工合并/拆分
角色类型
人物关系
Whisper ASR
对白文本
Speaker Diarization
Speaker -> Character
Scene
Qwen3-VL 镜头语义
Character Bible
演员库 / 选角
```

---

# 当前 Coding Gate

F06 Contract 已经由用户确认，但业务代码尚未开始。

正式编码前先完成 P0 环境门槛：

```text
1. opencv-python==4.11.0.86 写入 requirements
2. YuNet / SFace 固定模型文件与 SHA-256
3. 写入 config/models.yaml
4. Windows 本机验证 FaceDetectorYN / FaceRecognizerSF 可用
```

之后才能进入：

```text
F06 IN_PROGRESS
```

当前结论：

```text
F01-F05 = STABLE / FROZEN
F06      = PLANNED / CONTRACT CONFIRMED / NOT CODED
```
