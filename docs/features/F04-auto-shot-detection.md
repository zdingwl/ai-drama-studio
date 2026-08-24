# F04 — 自动拉片 Contract

Feature ID: F04  
Feature Name: 自动拉片  
Status: IN DEVELOPMENT  
Contract Status: CONFIRMED  
Official Baseline: main  
Stable Dependencies: F01、F02、F03 — STABLE / FROZEN  
Business Code: IN DEVELOPMENT

> 2026-08-24 用户明确确认 F04 改为**全本地 TransNetV2 镜头检测**。此前尚未确认、尚未落业务代码的 FFmpeg SCDet 草案作废。F04 仍只负责 Shot Boundary Detection / Shot Candidate，不提前实现 F06 人物、F08 ASR、F11 Scene 或其它下游能力。

---

# 1. 用户流程

```text
进入“04 自动拉片”
→ 检查 F03 PREPROCESS READY
→ 校验 proxy.mp4 SHA-256
→ 用户点击“开始自动拉片”
→ 本地 TransNetV2 对 Proxy 做逐帧 transition prediction
→ FFprobe 读取同一 Proxy 的逐帧真实 PTS
→ 模型 frame prediction 与真实 PTS 按解码顺序一一对齐
→ 连续 transition 帧归并为一个自动切换事件
→ 近邻事件确定性去抖
→ 生成连续 Shot Candidate
→ Proxy 时间映射为 Source Timeline integer microseconds
→ 保存 Detection Run + Shot Candidate
→ 页面展示镜头数量、时间段、时长、边界分数
→ 重启后仍能读取同一份结果
```

最小成功定义：

```text
F03 ready
→ F04 本地检测成功
→ shot_count >= 1
→ 所有 Shot 连续覆盖整个 Proxy 分析区间
→ 无 overlap / gap / 负时长
→ 所有权威边界来自真实 PTS，不来自 frame_index / fps
→ Source 时间可追溯到 F03 proxy_to_source_offset_us
→ 自动证据不会被 F05 人工结果覆盖
```

---

# 2. Scope

F04 V1 必须实现：

1. F03 ready 前置检查；
2. 检测前、ready commit 前各校验一次 `proxy.mp4` SHA-256；
3. 使用本地 **TransNetV2 PyTorch** 做镜头 transition prediction；
4. 使用 FFprobe 读取 Proxy 主视频流真实 frame PTS；
5. 模型预测帧数必须与 FFprobe 可用时间戳帧数一致，否则失败，不按 FPS 猜时间；
6. 连续超过阈值的 transition frames 只归并为一个 transition interval；
7. transition interval 的正式 cut 时间取“该 transition 后第一帧”的真实 Proxy PTS；
8. 极近重复 cut 做确定性去抖；
9. 使用 F03 `proxy_to_source_offset_us` 映射 Source Timeline；
10. 自动生成连续 Shot Candidate；
11. 保存 detector/model/runtime/upstream 快照；
12. 数据库存储 Detection Run + Shot Candidate；
13. `processing / ready` 状态持久化；
14. 应用启动清理无法恢复执行的旧 `processing` run；
15. GET / POST API；
16. Vue 自动拉片页面；
17. ready 后 F04 不允许静默覆盖重跑；
18. F01/F02/F03 回归。

---

# 3. Not In Scope

F04 不做：

```text
拖动/手改镜头边界
拆分 / 合并 / 新增 / 删除 Shot
人工确认 Final Shot
逐帧编辑器
人物识别（F06）
ASR / Whisper（F08）
Speaker（F09）
Scene 识别（F11）
Qwen3-VL 镜头语义理解
云端 Provider / 计费 API
```

人工边界修正属于 F05。F04 产生的是 Auto Evidence，不是 Final Shot。

---

# 4. Detector Profile V1

固定：

```text
detector_name: transnetv2_pytorch
detector_profile_version: 1
implementation_package: transnetv2-pytorch==1.0.5
transition_threshold: 0.5
min_boundary_gap_us: 120000
preferred_device: auto  # CUDA > reliable fallback
```

规则：

- UI 不允许用户自由输入阈值；
- `transition_score` / `end_boundary_score` 是模型 sigmoid 输出，用于排序和诊断，不展示成“准确率”；
- 设备自动选择允许 CUDA / CPU，但必须记录本次实际 device；
- 模型实现版本与 PyTorch runtime 版本必须记录；
- 首版只允许该 Profile，未来算法/阈值变化必须新增 Profile Version，不得静默改变既有结果含义。

为什么不再使用旧 SCDet 草案：用户在 F04 开发前明确要求采用本地效果优先方案，并确认 TransNetV2 为自动切镜核心。旧 SCDet Contract 从未 Frozen，也没有历史 F04 数据需要兼容，因此 V1 直接以 TransNetV2 为正式基线。

---

# 5. 时间域 Contract

F04 正式输出属于：

```text
Source Domain
```

检测发生在：

```text
F03 proxy.mp4
```

权威单位固定：

```text
integer microseconds
```

## 5.1 模型帧号不是权威时间

TransNetV2 的 prediction index 只用于回答：

```text
“第几个解码帧属于 transition”
```

禁止：

```text
cut_seconds = frame_index / fps
cut_us = round(frame_index * 1_000_000 / fps)
```

F04 必须另外执行 FFprobe：

```text
-show_frames
best_effort_timestamp_time / pts_time
```

并按解码顺序建立：

```text
prediction_index -> actual_proxy_pts_us
```

只有实际 PTS 可以进入正式 Shot 时间字段。

## 5.2 VFR

F03 已冻结：Proxy 不强制 CFR。

因此：

- FPS 只用于展示/诊断；
- prediction 数量与 PTS 数量不一致时直接 `SHOT_DETECTION_FRAME_ALIGNMENT_FAILED`；
- 缺少可用 PTS 时直接失败；
- 不允许退回 FPS 猜时间。

## 5.3 Transition interval → Cut

模型 `score > 0.5` 的连续帧视为一个 transition interval：

```text
[i ... j]
```

正式 cut 使用：

```text
frame j + 1 的实际 Proxy PTS
```

原因：连续 transition 帧（尤其淡入淡出）本身属于转场过程；下一稳定帧是连续 Shot Coverage 更稳定的边界锚点。若 transition 已延伸到视频末尾、没有 `j+1`，不额外生成尾部 cut，最后 Shot 由 `video_end` 收口。

该策略与 TransNetV2 官方 `predictions_to_scenes()` 对连续 transition 段进行归并的语义保持一致，但本项目不直接采用其 FPS 秒数。

## 5.4 Proxy → Source

```text
cut_source_us = cut_proxy_us + proxy_to_source_offset_us
```

必须复用公共 `derived_to_source_microseconds()`。

Shot 使用半开区间：

```text
[start_us, end_us)
```

## 5.5 Detection start/end

FFprobe Proxy 主视频流读取：

```text
proxy_start_us
proxy_duration_us
proxy_end_us = proxy_start_us + proxy_duration_us
```

F03 `proxy_duration_us` 与 F04 重新读取的 stream duration 误差必须：

```text
<= 1000 us
```

超出直接失败。

---

# 6. 自动事件归一化

处理顺序固定：

```text
TransNetV2 raw scores
→ threshold > 0.5
→ 合并连续 transition frames
→ 用 transition 后第一帧真实 PTS 形成 CutEvent
→ 删除 <= detection_start / >= detection_end 的事件
→ exact timestamp 去重
→ 按时间排序
→ 120ms 近邻窗口内保留 score 最大事件
→ 再次保证严格递增
```

禁止随机补边界、按最小时长随意删远距离真实事件，或为了得到“更多镜头”降低阈值。

没有任何 cut 时：整个视频生成 1 个 Shot Candidate，这是合法结果。

---

# 7. Shot Candidate 连续性

归一化 cut 为 `C1..Cn`：

```text
Shot 1 = [video_start, C1)
Shot 2 = [C1, C2)
...
Shot N = [Cn, video_end)
```

必须满足：

```text
shot_count >= 1
ordinal = 1..N
start < end
prev.end == next.start
first.start == detection_start
last.end == detection_end
无 gap
无 overlap
Proxy duration == mapped Source duration
shot_count == detected_cut_count + 1
```

Proxy 与 Source 两套时间字段都保存。

---

# 8. AI / Human 分离

F04 字段固定表达自动证据：

```text
detected_proxy_start_us
detected_proxy_end_us
detected_start_us
detected_end_us
end_boundary_score
```

F05 禁止覆盖这些字段。人工修正必须形成独立 Final 数据。

---

# 9. ID Contract

Detection Run：

```text
SHOT_DETECTION_<32位 UUID4 小写 hex>
```

Candidate：

```text
SHOT_CANDIDATE_<32位 UUID4 小写 hex>
```

Candidate ID 不是最终生产 Shot ID。

---

# 10. Database / Migration

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

升级仍由 `init_database()` 在 pending migration 前执行 SQLite `Connection.backup()`。

## 10.1 `shot_detection_runs`

| 字段 | 说明 |
|---|---|
| id | Detection ID |
| project_id | F01 Project |
| source_video_id | F02 Source |
| status | `processing / ready` |
| detector_name | `transnetv2_pytorch` |
| detector_profile_version | V1 = 1 |
| detector_threshold | 0.5 |
| min_boundary_gap_us | 120000 |
| detector_package_version | `1.0.5` |
| torch_version | 实际 PyTorch runtime |
| detector_device | `cuda... / cpu` |
| ffprobe_version | 时间戳读取工具版本 |
| preprocess_profile_version | F03 snapshot |
| proxy_sha256_snapshot | F03 proxy SHA snapshot |
| proxy_to_source_offset_us | F03 mapping snapshot |
| proxy_start_us / proxy_end_us | Proxy detection range |
| source_start_us / source_end_us | mapped Source range |
| analyzed_frame_count | 成功对齐的 frame 数 |
| detected_cut_count | 归一化 cut 数 |
| shot_count | Candidate 数 |
| created_at / completed_at | UTC |

约束：

```text
PRIMARY KEY(id)
FOREIGN KEY(project_id) → projects.id
FOREIGN KEY(source_video_id) → source_videos.id
UNIQUE(project_id)
status IN ('processing', 'ready')
threshold > 0 AND threshold < 1
min_boundary_gap_us >= 0
ready → timeline/runtime/count 字段完整
shot_count >= 1
shot_count = detected_cut_count + 1
```

## 10.2 `shot_candidates`

| 字段 | 说明 |
|---|---|
| id | Candidate ID |
| detection_id | 所属 Detection Run |
| project_id | Project ID |
| ordinal | 1-based |
| detected_proxy_start_us | Proxy start |
| detected_proxy_end_us | Proxy end |
| detected_start_us | Source start |
| detected_end_us | Source end |
| duration_us | Source duration |
| end_boundary_kind | `cut / video_end` |
| end_boundary_score | TransNetV2 transition score；video_end 为 NULL |

跨行连续性由业务层在 commit 前验证。

---

# 11. Dependency / Stale Contract

Run 保存：

```text
source_video_id
preprocess_profile_version
proxy_sha256_snapshot
proxy_to_source_offset_us
detector profile/model/runtime
```

若读取 ready 结果时发现 F03 身份、profile、proxy SHA 或 mapping 快照不一致：

```text
SHOT_DETECTION_UPSTREAM_CHANGED
```

F04 不静默重新计算、不覆盖历史自动证据。

---

# 12. Recovery Contract

F04 不写新的正式媒体文件，只写 DB。

正常完成事务：

```text
INSERT all candidates
+ UPDATE run ready
```

同一事务提交。

崩溃后遗留 `processing`：应用启动时删除该 processing run 及其候选（若有），用户可重新运行。`ready` 不自动删除。

---

# 13. API

```text
GET  /api/projects/{project_id}/shot-detection
POST /api/projects/{project_id}/shot-detection
```

GET：无结果返回 `200 null`。  
POST：同步执行 F04，成功 `201` 返回完整 Detection + Candidates。

主要错误：

```text
SHOT_DETECTION_PREPROCESS_REQUIRED       409
SHOT_DETECTION_ALREADY_EXISTS           409
SHOT_DETECTION_IN_PROGRESS              409
SHOT_DETECTION_PROXY_INTEGRITY_MISMATCH 409
SHOT_DETECTION_MODEL_UNAVAILABLE        503
SHOT_DETECTION_MODEL_INVALID            503
SHOT_DETECTION_FFPROBE_UNAVAILABLE      503
SHOT_DETECTION_FRAME_ALIGNMENT_FAILED   500
SHOT_DETECTION_INVALID_RESULT           500
SHOT_DETECTION_FAILED                   500
SHOT_DETECTION_UPSTREAM_CHANGED         409
```

---

# 14. Frontend

Route：

```text
/projects/:projectId/shot-detection
```

页面必须：

- F03 未 ready 时阻止运行并引导回 F03；
- 未运行时解释本地 TransNetV2 Profile V1；
- 运行时显示真实 loading，不伪造百分比；
- ready 后展示 Shot Count、模型/设备、Detection Range 和 Candidate 列表；
- `end_boundary_score` 只显示“边界分数”，不显示“准确率”；
- 不提供 F05 才允许的边界编辑功能。

---

# 15. P0 Feature Checklist

## P0-01 Dependency / Revision / Invalidation

- 适用：Yes
- 原因：F04 派生于 F03 Proxy。
- 上游 revision：F02 Source identity + F03 profile/proxy SHA/mapping snapshot。
- 派生结果：Detection Run + Shot Candidate。
- stale：F03 identity/profile/proxy SHA/mapping 任一变化。
- stale 处理：后端返回 `SHOT_DETECTION_UPSTREAM_CHANGED`，UI 不静默覆盖。
- 重新计算：未来由显式 revision/reset Contract 处理；V1 ready 不覆盖重跑。
- 人工 override：F04 不允许；F05 独立 Final 数据。

开发完成：`PASS`

## P0-02 Media Timebase

- 适用：Yes
- 输入 timeline：F03 Proxy Timeline。
- 输出 timeline：Proxy Evidence + Source Domain。
- 权威单位：integer microseconds。
- Source↔Proxy：Yes，使用 F03 offset。
- VFR：Yes；真实 PTS 权威，FPS 非权威。
- 音频 sample rate：N/A，F04 不读音频。
- rounding：`seconds_to_microseconds()` / `derived_to_source_microseconds()`。
- 时间误差测试：duration <= 1ms；VFR PTS；非零 start/offset；frame alignment。

开发完成：`PASS`

## P0-03 Environment Baseline

- 适用：Yes
- 新依赖：TransNetV2 PyTorch runtime。
- 新本地模型：Yes，TransNetV2。
- 版本：`transnetv2-pytorch==1.0.5`；PyTorch 版本显式锁定并记录 runtime。
- 模型来源/hash：模型/分发信息写入 `config/models.yaml`；运行时校验 bundled weight 存在。
- RTX 4060 Ti 16GB：支持 CUDA，GPU concurrency 仍为 1；CPU fallback 可用。
- 新电脑：安装 pinned requirements，确认 FFmpeg/FFprobe 与模型权重可读取。

开发完成：`PASS`

## P0-04 DB + File Recovery

- 适用：Yes
- transaction：Candidates + ready 同事务。
- 媒体/缓存：不生成正式媒体；模型仅只读 Proxy。
- staging/tmp：N/A。
- 文件校验：Proxy SHA 开始前/commit 前双检。
- 崩溃：可能留下 processing run。
- restart recovery：清理旧 processing，不动 ready。
- migration：0005。
- migration backup：复用 init_database SQLite backup gate。
- orphan/missing file：Proxy 缺失/Hash mismatch 阻止读取/运行。

开发完成：`PASS`

## P0-05 Provider Job Safety

- 适用：No
- 原因：F04 全本地推理，不提交任何云端 Provider Job。

开发完成：`N/A`

## Stable Gate

```text
P0 DEPENDENCY REVIEW: PASS
P0 TIMEBASE REVIEW: PASS
P0 ENVIRONMENT REVIEW: PASS
P0 RECOVERY REVIEW: PASS
P0 PROVIDER JOB REVIEW: N/A
```

---

# 16. Acceptance Gate

进入 READY_FOR_REVIEW 前必须通过：

```text
Migration 0005
ID / normalization / candidate continuity unit tests
VFR real-PTS alignment tests
no-cut / one-cut / gradual-transition tests
proxy integrity / upstream stale / recovery tests
GET / POST API tests
F01/F02/F03 regression
Frontend typecheck/build
真实视频 smoke test（若当前执行环境具备模型、FFmpeg 与 GPU/CPU runtime）
```

用户验收前不得把 F04 标记为 STABLE / FROZEN。
