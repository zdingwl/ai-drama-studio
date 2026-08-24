# F06 — Function Contracts

> 目标：只看这份文档，就能知道 F06 每个公开函数为什么存在。Controller 不允许复制算法职责；内部算法函数也必须保持单一职责。

## 1. 后端公开业务函数

V1 对外只保留 3 个核心业务入口。

### `get_character_detection(project_id)`

**干嘛：** 读取当前项目正在使用的 F06 Current Run，以及它的全部 Character Candidate / Track。  
**输入：** `project_id`。  
**输出：** `CharacterDetectionRecord | None`。  
**读取：** confirmed F05 Edit Set、current character_detection_run、candidate、track。  
**为什么存在：** 页面刷新、应用重启后必须恢复同一份自动人物 Evidence。  
**必须校验：** Run 记录的 `source_edit_set_id + source_edit_set_revision` 与当前冻结 F05 来源一致。  
**不能做：** 不自动重跑、不修数据、不修改 F05、不创建 Final Character。

### `run_character_detection(project_id)`

**干嘛：** 第一次运行 F06 自动人物识别。  
**输入：** `project_id`。  
**前置：** F05 必须存在且 `status=confirmed`；当前项目不得已有 current Ready F06 Run。  
**过程：** 采样计划 → 人脸检测 → embedding → Track → clustering → validate → DB 持久化。  
**输出：** 新的 Ready `CharacterDetectionRecord`。  
**为什么存在：** F06 是独立、可恢复、可追溯的一次算法运行，而不是页面临时推理。  
**不能做：** 不覆盖已有 Ready Run；已有结果时必须使用显式 rerun。

### `rerun_character_detection(project_id)`

**干嘛：** 用户明确要求时重新执行 F06，但保留旧结果直到新结果完全成功。  
**输入：** `project_id`。  
**前置：** F05 confirmed；如果 F07 已建立 Final Character 来源，则按 F07/F06 dependency contract 禁止无条件替换。  
**过程：** 新 Run 独立 processing → 完整计算 → validate → 事务切换 current。  
**失败行为：** 新 Run 标记 failed，旧 current Ready Run 不变。  
**为什么存在：** 模型/Profile 调整或自动结果不理想时需要安全重算，但不能先删旧 Evidence。  
**不能做：** 不原地 UPDATE 旧 Candidate/Track，不静默替换 F07 来源。

---

## 2. 内部算法函数

内部函数不是 API，不单独创建 Controller。

### `_require_confirmed_final_shots(project_id)`

**干嘛：** 获取并校验 F05 confirmed Final Timeline。  
**输入：** Project ID。  
**输出：** `ShotWorkbenchRecord`。  
**为什么存在：** 所有人物 Track 必须绑定稳定 Final Shot ID，不能读取 F04 Candidate 当生产 Shot。  
**不能做：** 不初始化 F05、不修改 F05。

### `_build_sample_plan(final_shots, profile)`

**干嘛：** 为每个 Final Shot 生成稳定 Source-time 分析时间点。  
**输入：** Final Shots + sampling profile。  
**输出：** 按 Shot 分组的 `SamplePoint[]`。  
**规则：** 约 4 FPS、每 Shot 3–12 帧、round-half-up、避开精确边界、全部 integer microseconds。  
**为什么存在：** 人物识别采样不能依赖 UI 是否曾打开，也不能只靠 F05 五张关键帧。  
**不能做：** 不读取视频、不运行模型。

### `_load_analysis_frame(project_id, source_time_us)`

**干嘛：** 返回指定 Source time 的 BGR 分析帧。  
**优先级：** 可复用已有稳定 JPEG → 否则从 F03 Proxy 抽帧并写 F06 cache。  
**输出：** 图像矩阵 + cache metadata。  
**为什么存在：** 把 Source→relative time 映射和 FFmpeg/缓存逻辑集中，算法层不自己拼命令。  
**不能做：** 不决定采样点、不做人脸检测。

### `_create_face_models(model_registry, profile)`

**干嘛：** 加载固定 YuNet / SFace ONNX 模型并验证模型文件身份。  
**输入：** model registry + F06 profile。  
**输出：** Detector / Recognizer runtime。  
**为什么存在：** 禁止业务流程隐式下载 latest 模型或随机换权重。  
**不能做：** 不开始整集分析；缺模型/hash 不符必须显式失败。

### `_detect_and_embed_faces(frame, source_time_us, models, profile)`

**干嘛：** 对一张分析帧做人脸检测、5 点对齐、SFace embedding。  
**输入：** 图像 + Source time + models + profile。  
**输出：** `FaceObservation[]`。  
**每个 Observation 至少：** bbox、landmarks、detection score、quality、normalized embedding。  
**为什么存在：** Detection / embedding 是一个单帧原子步骤，便于测试和调参。  
**不能做：** 不跨帧跟踪、不直接创建 Candidate。

### `_build_shot_tracks(final_shot, observations, profile)`

**干嘛：** 在一个 Final Shot 内，把多帧 Face Observation 连接成 Face Track。  
**输入：** 一个 Final Shot + 该 Shot 全部 observations。  
**输出：** `TrackDraft[]`。  
**依据：** 时间顺序、bbox 空间连续性、embedding similarity。  
**为什么存在：** 后续聚类单位应该是 Track，而不是几百张单帧脸。  
**不能做：** 不跨 Shot 连接、不命名人物。

### `_summarize_track(track_observations)`

**干嘛：** 把一个 Track 归纳成持久化特征。  
**输出至少：** normalized mean embedding、representative sample、mean/max quality、start/end、samples_json。  
**为什么存在：** 聚类和 UI 不需要永久保存每张脸的完整 embedding。  
**不能做：** 不决定 Candidate assignment。

### `_cluster_tracks(track_drafts, profile)`

**干嘛：** 跨 Final Shot 把 Track 保守聚类为 Character Candidate。  
**输入：** 全部 Track + clustering profile。  
**输出：** `CandidateDraft[]` + track assignment。  
**必须遵守：** 高 Precision 优先、cannot-link、确定性排序、固定阈值。  
**为什么存在：** 自动人物识别的核心结果就是“哪些 Track 很可能同一人”。  
**不能做：** 不把 Candidate 变成 Final Character，不猜名字。

### `_tracks_are_cannot_link(left, right)`

**干嘛：** 判断两个 Track 是否存在明确的“不可能同一人”证据。  
**V1 规则：** 同一 Source 时段/同一 Shot 内同时存在的两个独立人脸 Track不能自动归为同一 Candidate。  
**输出：** bool + reason。  
**为什么存在：** 防止仅凭脸相似度把同框的两个相似人物误合并。  
**不能做：** 不负责正向相似度计算。

### `_select_candidate_cover(candidate_tracks)`

**干嘛：** 为自动 Candidate 选择一张最适合 UI 展示的 Evidence Face。  
**依据：** face quality、尺寸、正面程度、detection score。  
**输出：** cover track + source time + bbox。  
**为什么存在：** F06 页面需要稳定头像，但这不是 F07 正式 Reference。  
**不能做：** 不允许用户在 F06 修改正式 Cover。

### `_validate_character_result(run, candidates, tracks, final_shots)`

**干嘛：** 在结果写成 current 前进行完整一致性校验。  
**至少校验：**

```text
所有 Track 属于本 Run
所有 Track 绑定存在的 Final Shot
所有 Candidate 属于本 Run
每个 Track 必须属于且只属于一个 Candidate
candidate.track_count / shot_count 正确
first_seen <= last_seen
cover 指向本 Candidate Evidence
embedding dimension 一致且有限值
同 Candidate 不违反 cannot-link
run count 与实际数量一致
```

**为什么存在：** rerun 必须“先完整验证、后切 current”。  
**不能做：** 不静默修正错误结果。

### `_persist_character_run(...)`

**干嘛：** 用一个明确事务保存 Run + Candidate + Track，并在 rerun 成功时原子切 current。  
**为什么存在：** SQL 和 current 切换不能散落在算法函数/Controller。  
**不能做：** 不运行模型、不改变 F05。

---

## 3. ID Functions

### `generate_character_detection_run_id()`

输出：

```text
CHAR_DETECTION_<UUID4>
```

只生成 ID，不写数据库。

### `generate_character_candidate_id()`

输出：

```text
CHAR_CANDIDATE_<UUID4>
```

这是 F06 AI Evidence ID，不得被 F07 当成 Final Character ID。

### `generate_character_track_id()`

输出：

```text
TRACK_<UUID4>
```

Track ID 在所属 Run 内稳定。

---

## 4. Controller `engine/app/main.py`

Controller 仅负责：

```text
Path / Query / Body 校验
→ 调业务函数
→ Response Schema
→ 统一错误映射
```

| Endpoint | Controller | Business |
|---|---|---|
| `GET /character-detection` | 读取 current | `get_character_detection()` |
| `POST /character-detection` | 首次识别 | `run_character_detection()` |
| `POST /character-detection/rerun` | 显式重跑 | `rerun_character_detection()` |
| `GET /candidates/{id}/cover` | 返回缓存/重建 Evidence JPEG | cover media helper |

Controller 禁止：

```text
自己跑 OpenCV
自己聚类
自己写 SQL
自己生成 Shot
修改 F05 Final Shot
创建 Final Character
```

---

## 5. Frontend Store

计划只需要：

```text
loadCharacterDetection()
runCharacterDetection()
rerunCharacterDetection()
```

统一内部 `_execute()` 管理 loading/running/error/currentRun。

页面不直接修改 Candidate/Track 数据。

---

## 6. 页面职责

页面只负责：

```text
显示 Candidate 列表
选择 Candidate
显示 Track / Evidence Faces
控制播放器 seek
按 Source time 高亮当前 Evidence
触发首次 Run / Rerun
显示 Profile / Model / Runtime 信息
```

页面禁止：

```text
命名人物
人工合并/拆分人物
删除人物 Candidate Evidence
直接改 candidate_id
在浏览器里做 embedding/clustering
伪造对白/Speaker 数据
```
