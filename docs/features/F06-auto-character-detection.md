# F06 — 自动人物识别 Contract

Feature ID: F06  
Feature Name: 自动人物识别  
Status: PLANNED  
Contract Status: CONFIRMED BY USER  
Official Baseline: main  
Upstream: F05 Final Shots（STABLE / FROZEN）  
Downstream: F07 人物人工修正

> 左侧导航当前可继续使用“人物对白”作为大工作区名称，但正式 35 Feature 生产顺序不变：F06 只做自动人物识别；F08 才做 ASR，F09 做 Speaker/Character，F10 做源对白人工修正。

## 1. 唯一目标

F06 只回答：

> 原片画面中有哪些“很可能是同一个人”的人物候选？

输入：

```text
F05 confirmed Final Shots
+ F03 proxy.mp4
```

输出：

```text
Character Detection Run
+ Character Tracks
+ Character Candidates
```

F06 的输出全部是 AI / Algorithm Evidence，不是最终人物。

F06 禁止直接生成正式人物姓名、角色类型、主角/配角结论或 Final Character ID。

这些人工语义全部属于 F07。

---

## 2. 正式技术路线

V1 锁定为本地 CPU 路线：

```text
F05 Final Shots
↓
按 Shot 自适应采样
↓
OpenCV YuNet
人脸检测 + 5 landmarks
↓
OpenCV SFace
对齐裁脸 + Face Embedding
↓
Shot-local Face Track
↓
保守式跨 Shot Clustering
↓
Character Candidates
```

计划依赖：

```text
opencv-python==4.11.0.86
numpy==2.1.3（复用当前锁定版本）
```

模型：

```text
YuNet: face_detection_yunet_2023mar.onnx
SFace: face_recognition_sface_2021dec.onnx
```

模型来源固定为 OpenCV Zoo；模型文件不提交 Git，正式编码前必须把实际下载文件 SHA-256 写入 `config/models.yaml`。

V1 不使用：

```text
PyTorch
CUDA
InsightFace
YOLO
ByteTrack
scikit-learn
Qwen3-VL
Whisper
云端 API
```

原因：F06 只解决稳定的人物候选聚类，第一版优先依赖少、可复现、可人工修正。F04 已冻结的 PyTorch/CUDA 环境不得因 F06 被无关升级。

---

## 3. Sampling Profile V1

F06 不只使用 F05 的 5 张 UI 关键帧。

F05 关键帧是人工查看资产；F06 为人物识别建立独立分析采样计划。

每个 Final Shot：

```text
target_fps = 4
min_samples = 3
max_samples = 12
```

目标采样数：

```text
round_half_up(shot_duration_seconds * 4)
→ clamp(3, 12)
```

样例：

```text
0.8s  -> 3 frames
2.8s  -> 11 frames
5.0s  -> 12 frames
```

采样点必须位于 Final Shot 内部并避开精确切镜边界。

所有采样时间使用：

```text
Source Domain integer microseconds
```

禁止使用：

```text
frame_index / fps
```

推导正式人物 Evidence 时间。

如果 F05 `.cache/f05/frames/<source_time_us>.jpg` 已存在同时间点图片，可以直接复用；不存在时才从 F03 Proxy 抽取分析帧。

---

## 4. Detection / Embedding

### YuNet

对每张分析帧输出：

```text
bbox
5 facial landmarks
detection score
```

V1 Profile 初始参数：

```text
detection_confidence = 0.90
nms_threshold = 0.30
```

参数必须持久化到 Run Profile，不允许只写死在代码里却无法追溯。

### SFace

每个合格 Face：

```text
alignCrop
→ feature embedding
→ L2 normalize
```

SFace 官方 demo 的同人 cosine 基准阈值为 0.363；F06 聚类采用更保守的应用阈值，初始 Profile 计划：

```text
cluster_cosine_threshold = 0.45
```

该值属于 F06 Profile V1，需要在真实短剧样本验收时检查误合并情况；如需调整，必须形成新的 Profile 版本，不静默改变已有 Run 的语义。

---

## 5. Shot-local Track

F06 的 `Character Track` 定义为：

> 同一个 Final Shot 中，一组连续采样帧里很可能属于同一个人物的人脸 Evidence。

Track 只在一个 Final Shot 内存在，不跨 Shot。

关联依据：

```text
bbox spatial continuity
+ face embedding similarity
+ sample time order
```

允许人物转头/遮挡导致一个真实人物在同一 Shot 被拆成多个 Track；F06 宁可多拆，不允许为了“Track 看起来连续”强行错误连接。

Track 必须绑定：

```text
final_shot_id
```

F06 禁止自行创建第二套 Shot。

---

## 6. Conservative Cross-shot Clustering

跨 Shot 聚类原则：

> 高 Precision 优先，Recall 第二。

即：

```text
宁可把同一个人物拆成 Candidate #003 + #007
也不要把两个不同人物错误合并成一个 Candidate
```

因为 F07 合并两个候选很简单，而拆解错误混合人物成本更高。

必须有 Cannot-link 规则：

```text
同一 Source 时间同时出现在画面中的两个不同 Face Track
不得自动归入同一 Character Candidate
```

候选聚类基于：

```text
Track normalized embedding
+ pair/candidate similarity
+ temporal coexistence constraints
```

V1 不引入 scikit-learn；使用 NumPy 实现确定性、保守式聚类。

---

## 7. AI Evidence 与 Human Final 分离

F06：

```text
CHAR_CANDIDATE_<UUID4>
TRACK_<UUID4>
```

F07：

```text
CHARACTER_<UUID4>
```

F06 Candidate 永远是只读自动证据。

F07 可以：

```text
命名
合并多个 Candidate
拆分错误 Candidate
删除路人/误检
设置角色类型
选择正式 Cover / Reference
```

但不能覆盖 F06 原始 Track/Candidate Evidence。

---

## 8. Rerun / Versioning

每次自动人物识别生成新的：

```text
CHAR_DETECTION_<UUID4>
```

Run 保存：

```text
source_edit_set_id
source_edit_set_revision
sampling_profile
model identities
opencv_version
runtime device
```

重跑规则：

```text
旧 Current Run 保留
→ 新 Run processing
→ 完整 Detection / Tracking / Clustering
→ 全量 validate
→ 一个 DB transaction 切换 current Run
```

失败：

```text
新 Run = failed
旧 Current Run 继续有效
```

一旦 F07 已基于某个 F06 Run 创建 Final Character 数据，禁止静默替换其来源；后续如需要重跑必须走明确的 dependency/stale 方案。

---

## 9. 数据库

Migration 计划：

```text
0007_create_character_detection
```

只新增 3 张业务表：

```text
character_detection_runs
character_candidates
character_tracks
```

不为每个采样帧单独建表；采样 Evidence 使用 Track 的 `samples_json` 保存轻量时间/bbox/score 信息。

详细字段见：

```text
docs/features/F06-database-dictionary.md
```

---

## 10. Workspace / Cache

F06 缓存：

```text
<Project Workspace>/.cache/f06/
├─ frames/
├─ faces/
└─ candidates/
```

缓存只用于 UI / Debug：

```text
可删除
可重建
不是业务 Source of Truth
```

正式证据保存在数据库：

```text
source_time_us
bbox
track embedding
track samples
candidate assignment
model/profile identity
```

---

## 11. API V1

只保留 4 个入口：

```text
GET  /api/projects/{project_id}/character-detection
POST /api/projects/{project_id}/character-detection
POST /api/projects/{project_id}/character-detection/rerun
GET  /api/projects/{project_id}/character-detection/candidates/{candidate_id}/cover
```

不为每个算法内部步骤创建 Controller。

---

## 12. 页面 V1

F06 继续使用工作台布局：

```text
左：Character Candidate 列表
中：F03 Proxy 播放器 + Candidate 出现时间轴
右：Candidate 自动识别详情 + Evidence Faces
```

Candidate 列表显示：

```text
自动头像
Candidate 编号
Track 数
出现 Shot 数
首次 / 最后出现时间
```

交互：

```text
点击 Candidate -> 查看全部 Track
点击 Track -> 播放器 seek 到代表 Source time
播放时 -> 当前出现 Candidate/Track 可高亮
```

F06 页面只读，不提供命名/合并/拆分/删除人物操作。

---

## 13. Scope — F06 必须做

- 读取 confirmed F05 Final Shot；
- 创建稳定分析采样计划；
- 本地人脸检测；
- 人脸对齐与 embedding；
- Shot-local Track；
- 保守跨 Shot 聚类；
- Character Candidate / Track 持久化；
- 自动 Evidence UI；
- 显式安全 rerun；
- 模型/Profile/运行环境可追溯；
- 自动结果永远与 F07 Final Character 分离。

---

## 14. Not In Scope

F06 明确不做：

```text
人物正式姓名
人物人工合并/拆分
角色类型
人物关系
Character Bible
Whisper ASR
对白文本
Speaker Diarization
Active Speaker
Speaker -> Character
Scene
景别 / 运镜 / 动作
Qwen3-VL
演员库 / 选角
云端 API
```

---

## 15. Freeze Gate

F06 最终验收至少必须证明：

```text
1. confirmed F05 才能进入 F06
2. 真实视频能完成采样 -> Detection -> Track -> Candidate
3. 同人物跨多个 Shot 能大部分聚到一起
4. 同镜同时出现的不同人物不被错误合并
5. 低质量/小脸不会导致大量错误 Candidate 污染
6. 点击 Candidate / Track 能正确跳到 Source 时间
7. rerun 失败不破坏旧 Ready Run
8. 模型/Profile/源 F05 revision 可追溯
9. 重启应用后结果可恢复
10. F01-F05 Stable Regression 全部通过
```

AI / Agent 最多把 F06 推进到 READY_FOR_REVIEW；只有用户真实素材确认后才能 STABLE / FROZEN。
