# F04 — 自动拉片 Contract

Feature ID: F04  
Feature Name: 自动拉片  
Status: PLANNED  
Contract Status: DRAFTED / WAITING_USER_CONFIRMATION  
Official Baseline: main  
Stable Dependencies: F01、F02、F03 — STABLE / FROZEN  
Business Code: NOT STARTED

> F04 只负责从 F03 已冻结 Proxy 自动产生 **Shot Candidate**。自动检测原始边界必须保留，F05 人工修正不得覆盖这些原始证据。

---

# 1. 目标

F04 要完成的真实用户流程：

```text
进入项目“04 自动拉片”
→ 检查 F03 PREPROCESS READY
→ 读取 proxy.mp4 + Proxy→Source Timeline Mapping
→ 用户点击“开始自动拉片”
→ 本地 FFmpeg SCDet 扫描 Proxy 的真实 PTS
→ 得到自动切换事件
→ 去重/归一化边界
→ 组装连续 Shot Candidate
→ 把 Proxy 时间映射为 Source Timeline integer microseconds
→ 保存 Detection Run + Shot Candidate
→ 页面展示 Shot 数量、时间段、时长和切换强度
→ 重启后仍能读取同一份检测结果
```

最小成功定义：

```text
F03 ready
→ 自动拉片
→ 至少得到 1 个 Shot Candidate
→ 所有 Shot 连续覆盖整个 Proxy/Source 分析区间
→ 无重叠、无空洞、无负时长
→ Source 时间可追溯回 F03 Mapping
→ 原始自动边界不被人工结果覆盖
```

---

# 2. Scope

F04 V1 必须实现：

1. F03 ready 前置检查；
2. 再次校验磁盘 `proxy.mp4` SHA-256 与 F03 `proxy_sha256` 一致；
3. 使用本机 FFmpeg `scdet` 自动检测镜头切换；
4. 检测必须使用媒体真实 PTS / timestamp，不使用 `frame_index / fps` 作为权威时间；
5. 自动切换事件使用 F03 `proxy_to_source_offset_us` 映射到 Source Timeline；
6. 对相邻极近重复切换事件做确定性去抖；
7. 自动生成连续 Shot Candidate；
8. 记录 Detector Profile、FFmpeg Version、阈值和上游 Proxy SHA 快照；
9. 数据库存储 Detection Run + Shot Candidate；
10. 处理状态持久化；
11. 应用重启时安全清理已经不可能继续执行的旧 `processing` Detection Run；
12. GET / POST API；
13. Vue 自动拉片页面；
14. ready 结果重启后仍可读取；
15. ready 后禁止在 F04 静默覆盖重跑；
16. F01/F02/F03 回归。

---

# 3. Not In Scope

F04 明确不做：

```text
拖动 Shot 边界
手工修改开始/结束时间
拆分 Shot
合并 Shot
新增 Shot
删除 Shot
人工确认 Final Shot
Shot 播放/逐帧编辑器
Shot 缩略图批量生成
人物识别
ASR
Speaker
Scene
本土化
任何云端 Provider / 计费 AI API
```

这些不能为了“页面更完整”提前塞入 F04。

其中：

```text
边界调整 / 拆分 / 合并 / 新增 / 删除 / 最终确认
→ F05 Shot 人工修正
```

---

# 4. 为什么 F04 V1 使用 FFmpeg SCDet

当前项目已经把 FFmpeg / FFprobe 作为本地媒体基础设施，F03 已经验证 VFR 与真实 timestamp。

F04 V1 采用：

```text
FFmpeg scdet
```

而不是新增 OpenCV / PySceneDetect / 新的深度学习模型依赖。

原因：

1. 不新增 Python/native 依赖；
2. Windows 当前环境已经需要 FFmpeg；
3. `scdet` 直接在解码后的真实视频帧上工作；
4. 可以读取真实 PTS，适合 F03 不强制 CFR 的 Proxy；
5. F04 是自动 Candidate，不要求算法结果直接成为 Final Shot；
6. 错检/漏检由 F05 人工修正；
7. 第一版优先“真实生产流程完整可用”，不是先搭复杂模型体系。

注意：

```text
SCDet score ≠ 概率置信度
```

因此 UI / DB 一律叫：

```text
boundary_score
切换强度
```

禁止显示为“95% 准确率”之类未经校准的概率。

---

# 5. Detector Profile V1

固定：

```text
detector_name: ffmpeg_scdet
detector_profile_version: 1
threshold: 10.0
min_boundary_gap_us: 120000   # 120 ms
```

用途：

- `threshold=10.0`：F04 V1 固定 SCDet 阈值；
- `min_boundary_gap_us=120ms`：连续转场/闪帧可能在极短时间内产生多个事件，V1 在 120ms 窗口内只保留切换强度最高的一个边界；
- 该规则只是自动 Candidate 归一化，不声称替代 F05 人工判断。

F04 UI 不让用户自由输入阈值。

原因：固定 Profile 才能让当前检测结果具有可复现含义；如果未来确实需要多灵敏度检测，应新增 Detector Profile V2 / Detection Revision，而不是静默改变 V1。

---

# 6. 时间域 Contract

F04 属于：

```text
Source Domain
```

检测实际发生在：

```text
F03 proxy.mp4
```

但正式 Shot Candidate 必须同时保存：

```text
Proxy Timeline
Source Timeline
```

权威单位：

```text
integer microseconds
```

## 6.1 Cut Event

FFmpeg 输出切换事件真实 Proxy timestamp：

```text
cut_proxy_us
```

映射：

```text
cut_source_us = cut_proxy_us + proxy_to_source_offset_us
```

必须调用 F03 已建立的公共媒体时间换算能力，不允许：

```text
frame_index / fps
float 秒作为 DB 权威值
```

## 6.2 Shot 区间

Shot Candidate 固定使用半开区间：

```text
[start_us, end_us)
```

例如：

```text
Shot 1: [0, 2_400_000)
Shot 2: [2_400_000, 5_100_000)
```

边界 `2_400_000` 只属于 Shot 2 的开始，不产生重叠。

## 6.3 第一 / 最后 Shot

F04 会 FFprobe Proxy 主视频流得到：

```text
proxy_stream_start_us
proxy_stream_duration_us
proxy_stream_end_us = start + duration
```

然后：

```text
source_detection_start_us = proxy_stream_start_us + proxy_to_source_offset_us
source_detection_end_us   = proxy_stream_end_us   + proxy_to_source_offset_us
```

F03 `proxy_duration_us` 与 F04 实际 FFprobe Proxy stream duration 必须在允许误差内一致。

目标误差：

```text
<= 1 ms
```

超出则停止检测，不允许静默继续。

## 6.4 VFR

F03 已冻结：Proxy 不强制 CFR。

因此 F04：

```text
必须使用 PTS / pts_time
不得把 avg_frame_rate 当成时间轴
```

FPS 只能用于展示或诊断。

---

# 7. 自动边界归一化

FFmpeg SCDet 的原始事件经过以下确定性处理：

```text
按 proxy timestamp 升序
→ 删除不在检测区间内部的事件
→ 相同 timestamp 去重
→ 120ms 去抖窗口内保留 boundary_score 最大事件
→ 映射 Source Timeline
```

禁止：

- 为了凑 Shot 数量随机补边界；
- 因为 Shot 很短就无依据删除远距离真实事件；
- 根据 FPS 猜边界；
- 人工结果回写覆盖原始 Detection Candidate。

如果没有检测到任何 cut：

```text
整个视频仍然生成 1 个 Shot Candidate
```

这是合法结果，不是错误。

---

# 8. Shot Candidate 连续性规则

假设归一化 cut：

```text
C1, C2, ..., Cn
```

则生成：

```text
Shot 1 = [video_start, C1)
Shot 2 = [C1, C2)
...
Shot N = [Cn, video_end)
```

所有 Candidate 必须满足：

```text
shot_count >= 1
ordinal = 1..N
start < end
duration_us = end_us - start_us
prev.end_us == next.start_us
无 gap
无 overlap
first.start == detection_start
last.end == detection_end
```

同样规则必须同时满足 Proxy Timeline 与 Source Timeline。

---

# 9. AI / Human 分离

F04 输出是：

```text
Auto / AI Evidence
```

字段命名固定使用：

```text
detected_proxy_start_us
detected_proxy_end_us
detected_start_us
detected_end_us
```

F05 不允许执行：

```text
UPDATE shot_candidates SET detected_start_us = 人工值
```

F05 必须新增独立的 Final Shot 数据/字段 Contract，例如：

```text
final_start_us
final_end_us
```

或者独立 `shots` 表。

具体由 F05 Contract 决定。

原则只有一个：

```text
AI 自动证据永远保留
人工 Final 与 AI Evidence 分开
```

---

# 10. ID Contract

Detection Run：

```text
SHOT_DETECTION_<32位 UUID4 小写 hex>
```

Candidate：

```text
SHOT_CANDIDATE_<32位 UUID4 小写 hex>
```

说明：

- F04 Candidate ID 不是最终生产 Shot ID；
- F05 合并/拆分后最终 Shot 身份可能改变；
- 正式 `SHOT_<UUID>` 是否在 F05 生成，由 F05 Contract 决定。

---

# 11. Database / Migration

新增 Migration：

```text
0005_create_shot_detection
```

Migration chain：

```text
0001 projects
→ 0002 source_videos
→ 0003 source_preprocess
→ 0004 repair source_preprocess audio constraint
→ 0005 shot detection
```

已有数据库升级仍走共享：

```text
SQLite Connection.backup()
→ Alembic upgrade
```

不得改写已经冻结的 0001–0004 历史。

## 11.1 `shot_detection_runs`

| 字段 | 说明 |
|---|---|
| id | `SHOT_DETECTION_<UUID>` |
| project_id | F01 Project |
| source_video_id | F02 Source ID |
| status | `processing / ready` |
| detector_name | `ffmpeg_scdet` |
| detector_profile_version | V1 = 1 |
| detector_threshold | V1 = 10.0 |
| min_boundary_gap_us | V1 = 120000 |
| ffmpeg_version | 实际运行的 FFmpeg 版本字符串 |
| preprocess_profile_version | F03 profile snapshot |
| proxy_sha256_snapshot | F03 Proxy SHA snapshot |
| proxy_to_source_offset_us | F03 Mapping snapshot |
| proxy_start_us | ready 时实际 Proxy stream start |
| proxy_end_us | ready 时实际 Proxy stream end |
| source_start_us | ready 时 mapped Source start |
| source_end_us | ready 时 mapped Source end |
| detected_cut_count | 归一化后的 cut 数量 |
| shot_count | Candidate 数量 |
| created_at | UTC |
| completed_at | ready UTC |

约束：

```text
PRIMARY KEY(id)
FOREIGN KEY(project_id) → projects.id
FOREIGN KEY(source_video_id) → source_videos.id
UNIQUE(project_id)
CHECK(status IN ('processing', 'ready'))
ready 时 timeline / count / ffmpeg_version 必须完整
shot_count >= 1
detected_cut_count >= 0
shot_count = detected_cut_count + 1
```

F04 V1 一个 Project 只保存一份正式 Detection Run。

ready 后 F04 不直接覆盖重跑；错误由 F05 人工修正。未来如果需要 Detection Revision，再做 V2。

## 11.2 `shot_candidates`

| 字段 | 说明 |
|---|---|
| id | Candidate ID |
| detection_id | 所属 Detection Run |
| project_id | Project ID |
| ordinal | 1-based 顺序 |
| detected_proxy_start_us | Proxy start |
| detected_proxy_end_us | Proxy end |
| detected_start_us | Source start |
| detected_end_us | Source end |
| duration_us | Source duration |
| end_boundary_kind | `cut / video_end` |
| end_boundary_score | SCDet score；video_end 时 NULL |

约束：

```text
PRIMARY KEY(id)
FOREIGN KEY(detection_id) → shot_detection_runs.id
FOREIGN KEY(project_id) → projects.id
UNIQUE(detection_id, ordinal)
CHECK(ordinal >= 1)
CHECK(proxy_end > proxy_start)
CHECK(detected_end > detected_start)
CHECK(duration_us = detected_end_us - detected_start_us)
CHECK(end_boundary_kind IN ('cut', 'video_end'))
cut → end_boundary_score NOT NULL
video_end → end_boundary_score NULL
```

跨行连续性由业务层在 DB commit 前统一验证，SQLite 单行 CHECK 不承担跨行验证。

---

# 12. Dependency / Stale Contract

F04 Detection Run 必须保存 F03 上游快照：

```text
source_video_id
preprocess_profile_version
proxy_sha256_snapshot
proxy_to_source_offset_us
```

读取 F04 时必须重新确认：

```text
当前 F03 ready
当前 F03 source_video_id == run.source_video_id
当前 F03 profile_version == snapshot
当前 F03 proxy_sha256 == snapshot
当前 F03 offset == snapshot
磁盘 proxy SHA == F03 proxy SHA
```

不一致：

```text
SHOT_DETECTION_STALE
```

不得把旧 Candidate 静默作为正式输入。

目前 F03 已冻结且不提供替换路径，所以正常用户不会产生 stale；该检查是为了后续 Migration / Contract V2 安全。

---

# 13. Processing / Recovery

F04 不生成新的长期媒体文件，因此恢复比 F03 简单。

正常流程：

```text
DB detection_run = processing（先提交）
→ 本地 FFmpeg SCDet
→ 内存中构造 + 校验 Candidate
→ 单个 DB transaction:
   INSERT all shot_candidates
   UPDATE detection_run = ready
```

如果 FFmpeg / 解析 / 校验失败：

```text
删除本次 processing run
→ 不留下 Candidate
→ 用户可重新运行
```

如果进程崩溃：

```text
数据库可能只剩 processing run
```

应用重启时：

```text
recover_shot_detections()
→ 删除 processing 对应的 Candidate（理论上事务不会留下）
→ 删除 processing run
→ 用户重新运行
```

为什么可以直接清理：

- F04 没有付费 Provider；
- 没有需要保留的生成媒体；
- FFmpeg 子进程不会跨应用进程重启继续存在于业务控制链；
- ready 结果在同一 DB transaction 中一次提交。

同一进程内重复点击：

```text
已有 processing
→ 409 SHOT_DETECTION_IN_PROGRESS
```

不得删除正在运行的 Detection Run。

---

# 14. Proxy Integrity

开始检测前：

```text
磁盘 proxy size/hash
== F03 ready metadata
```

检测结束、DB ready commit 前再次校验：

```text
磁盘 proxy SHA
== F03 proxy_sha256
== run.proxy_sha256_snapshot
```

处理中 Proxy 被系统外替换：

```text
SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH
→ 不保存 ready Candidate
→ 删除本次 processing run
```

F04 不自动修复/覆盖 Proxy。

---

# 15. API Contract

新增：

```text
GET  /api/projects/{project_id}/shot-detection
POST /api/projects/{project_id}/shot-detection
```

GET：

```text
没有 run
→ 200 null

processing
→ 200 DetectionDTO(status=processing, candidates=[])

ready
→ 200 DetectionDTO(status=ready, candidates=[...])
```

POST：

```text
无 F03 ready
→ 409

已有 processing
→ 409 SHOT_DETECTION_IN_PROGRESS

已有 ready
→ 409 SHOT_DETECTION_ALREADY_EXISTS

成功
→ 201 DetectionDTO(status=ready)
```

Controller 继续遵守：

```text
HTTP → Business → Response
```

Controller 不允许自己：

```text
SQL
FFmpeg
FFprobe
Hash
时间映射
Candidate 组装
Recovery
```

---

# 16. 稳定错误码

至少：

```text
SHOT_DETECTION_PREPROCESS_REQUIRED
SHOT_DETECTION_ALREADY_EXISTS
SHOT_DETECTION_IN_PROGRESS
SHOT_DETECTION_PROXY_MISSING
SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH
SHOT_DETECTION_FFMPEG_UNAVAILABLE
SHOT_DETECTION_FFPROBE_UNAVAILABLE
SHOT_DETECTION_FAILED
SHOT_DETECTION_INVALID_RESULT
SHOT_DETECTION_STALE
```

HTTP 建议：

```text
PREPROCESS_REQUIRED                  409
ALREADY_EXISTS                      409
IN_PROGRESS                         409
PROXY_MISSING                       409
PROXY_INTEGRITY_MISMATCH            409
FFMPEG_UNAVAILABLE                  503
FFPROBE_UNAVAILABLE                 503
FAILED                              500
INVALID_RESULT                      500
STALE                               409
```

错误文案必须说明用户下一步能做什么，不能只返回内部 exception。

---

# 17. Frontend Contract

正式路由：

```text
/projects/:projectId/shot-detection
```

左侧：

```text
01 项目总览       enabled
02 视频导入       enabled
03 视频预处理     enabled
04 自动拉片       enabled
05 人物对白       disabled（现有聚合占位暂不拆 F05 之外功能）
...
```

> 如果侧边栏未来要严格显示 35 Feature，不在 F04 顺便重做导航信息架构；F04 只开放当前“自动拉片”入口。

## 17.1 F03 未完成

```text
显示“请先完成视频预处理”
→ 按钮进入 F03
```

## 17.2 未检测

展示：

- Proxy 文件；
- Proxy 时长；
- Proxy SHA 摘要；
- Detector `FFmpeg SCDet`；
- Profile V1；
- threshold 10.0；
- 120ms 去抖；
- “开始自动拉片”。

固定参数只读，不使用自由文本输入框。

## 17.3 Processing

显示：

```text
正在分析镜头切换…
系统正在按真实视频时间戳扫描 Proxy。
```

不伪造百分比。

## 17.4 Ready

顶部摘要：

```text
AUTO SHOT DETECTION READY
Shot 数量
Cut 数量
分析区间总时长
Detector Profile
```

展示一个简洁 Shot Strip：

- 每个块宽度按 Shot Duration 比例展示；
- 块上显示 `01 / 02 / 03...`；
- 只用于查看，不可拖动。

下面展示 Candidate 表格：

```text
序号
Source Start
Source End
Duration
Boundary Type
Boundary Score
```

第一版不做播放和人工编辑。

右侧 / 底部明确：

```text
下一阶段：F05 Shot 人工修正
```

F05 未开发前不显示可点击的正式编辑入口。

---

# 18. Core Backend Functions

F04 核心函数保持 6 个：

```text
generate_shot_detection_id()
detect_proxy_cut_events()
build_shot_candidates()
run_shot_detection()
get_shot_detection()
recover_shot_detections()
```

Controller 2 个：

```text
get_shot_detection_api()
run_shot_detection_api()
```

详细职责：

```text
docs/features/F04-function-contracts.md
```

Candidate ID、FFprobe parsing、SCDet stdout parsing、Hash、DB row mapping 等可以是私有 helper，不升级成十几个“核心函数”。

---

# 19. Workspace Impact

F04 V1：

```text
不新增正式媒体文件目录
不修改 preprocess/
不修改 source/
```

Detection / Candidate 结果全部保存在应用级 SQLite。

如开发测试需要临时日志，只能放 OS temp / 测试临时目录，正式业务完成后不得依赖这些文件恢复结果。

---

# 20. Project Format Impact

F04 不修改：

```text
project.json
project_format_version
```

Shot Detection 数据属于应用数据库业务状态，不在 F04 扩展 Project Manifest。

---

# 21. Environment

新增 Python 依赖：

```text
无
```

新增 Node 依赖：

```text
无
```

本地依赖：

```text
FFmpeg + FFprobe
```

F04 需要在用户当前 FFmpeg 上验证：

```text
ffmpeg -filters
```

存在：

```text
scdet
metadata
```

若缺失：

```text
SHOT_DETECTION_FFMPEG_UNAVAILABLE / FAILED
```

不得静默切换到另一套算法导致同一 Profile V1 含义变化。

---

# 22. Tests

## Unit / Integration

至少：

```text
Detection ID 格式 + UUID4 + 大量唯一
SCDet metadata 解析
Decimal 秒 → integer microseconds
VFR PTS 保留
120ms 去抖
窗口内保留最高 boundary_score
无 cut → 1 Shot
多 cut → N+1 Shot
半开区间
无 gap / overlap
first/last 覆盖整个检测区间
Proxy→Source offset 映射
非零 offset
Proxy Hash mismatch
Proxy 处理中被替换
已有 processing
已有 ready
processing Recovery
GET null / processing / ready
POST ready
HTTP error envelope
0004→0005 Migration
Migration 前 backup
F01/F02/F03 数据保留
```

## Real Sample

必须至少测试：

1. 单镜头 5–10 秒视频 → 1 Candidate；
2. 3–5 个明显硬切视频 → Shot 数量和时间基本正确；
3. 快速闪帧 / 连续转场视频 → 去抖不产生明显 1 帧碎 Shot；
4. VFR 视频 → timestamp-based 边界正确；
5. 非零 Source offset 样本 → Source 时间映射正确；
6. 用户真实短剧片段 → 页面结果可用于下一步人工修正。

F04 不要求自动结果 100% 正确；要求：

```text
Candidate 有用
原始证据可追溯
时间正确
F05 可以人工修正
```

---

# 23. P0 Feature Checklist

## P0-01 Dependency / Revision / Invalidation

- 适用：Yes
- 原因：F04 是 F03 Proxy 的派生结果。
- 上游 revision/snapshot：`source_video_id`、`preprocess_profile_version`、`proxy_sha256_snapshot`、`proxy_to_source_offset_us`。
- 派生结果：Detection Run + Shot Candidate。
- stale 条件：F03 identity/profile/hash/offset 与 snapshot 不一致。
- stale 后：后端返回 `SHOT_DETECTION_STALE`，UI 不把旧 Candidate 当正式输入。
- 重新计算：未来 Contract 允许后重新检测；F04 V1 Frozen 后不静默覆盖 ready。
- 人工 override：N/A；F05 产生 Human Final，不覆盖 AI Evidence。

开发完成：PENDING

---

## P0-02 Media Timebase

- 适用：Yes
- 原因：F04 输出 Shot Source Timeline。
- 输入 timeline：Proxy Timeline + F03 Mapping。
- 输出 timeline：Proxy + Source Timeline。
- 权威单位：integer microseconds。
- Source↔Proxy：Yes。
- VFR：Yes，必须 PTS-based。
- 音频 sample rate：N/A。
- rounding：复用 `engine/app/core/media_time.py`。
- 时间误差测试：目标 <= 1ms。

开发完成：PENDING

---

## P0-03 Environment Baseline

- 适用：Yes
- 新 Python/Node dependency：No。
- 新本地模型：No。
- 依赖：现有 FFmpeg / FFprobe，必须支持 scdet/metadata。
- RTX 4060 Ti：不要求 GPU；V1 可 CPU 解码检测。
- 新电脑：FFmpeg 环境验证加入 F04 测试说明。

开发完成：PENDING

---

## P0-04 DB + File Recovery

- 适用：Yes
- DB transaction：processing 先提交；ready 时 candidates + run ready 同事务。
- 媒体文件：只读 F03 Proxy，不产生正式新媒体。
- staging：N/A，F04 无持久化媒体输出。
- 崩溃：留下 processing run。
- restart recovery：删除 processing candidate/run，允许重新检测。
- Migration：0005。
- Migration backup：共享 SQLite Backup Gate。
- orphan：processing candidate 统一清理；ready candidate 必须有 run。

开发完成：PENDING

---

## P0-05 Provider Job Safety

- 适用：No
- 原因：F04 V1 完全本地 FFmpeg，不调用付费/异步 Provider。

开发完成：N/A

---

# 24. Stable Gate

F04 最多由 Agent 推进到：

```text
READY_FOR_REVIEW
```

只有用户实际验证并明确确认后才能：

```text
F04 → STABLE / FROZEN
```

Stable 前至少：

```text
P0 DEPENDENCY REVIEW: PASS
P0 TIMEBASE REVIEW: PASS
P0 ENVIRONMENT REVIEW: PASS
P0 RECOVERY REVIEW: PASS
P0 PROVIDER JOB REVIEW: N/A

F04 tests PASS
F01 regression PASS
F02 regression PASS
F03 regression PASS
真实短剧自动拉片完成
页面重启后仍可读取
用户明确验收通过
```

F04 未冻结前不得正式开发 F05。
