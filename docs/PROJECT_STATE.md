# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。详细 Contract、实现和历史过程放在 `docs/features/` 与 `docs/sessions/`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main（用户未要求切换/新建其它分支）

F01 — 创建项目:     STABLE / FROZEN
F02 — 上传原视频:   STABLE / FROZEN
F03 — 视频预处理:   STABLE / FROZEN
F04 — 自动拉片:     READY_FOR_REVIEW

Stable Features: F01, F02, F03
Frozen Features: F01, F02, F03

Current Feature: F04 — 自动拉片
F04 Contract: CONFIRMED
F04 Function Contracts: CONFIRMED
F04 Business Code: IMPLEMENTED
F04 Database Migration: IMPLEMENTED (0005)
F04 Frontend: IMPLEMENTED
F04 Automated Test Files: IMPLEMENTED
F04 User Acceptance: PENDING LOCAL WINDOWS / RTX 4060 Ti SMOKE TEST

Next After F04 Acceptance: F05 — Shot 人工修正（NOT STARTED）
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不新建、切换、删除、重命名分支，也不创建或操作 PR。

---

# 恢复顺序

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/features/F01-stable-snapshot.md
→ docs/features/F02-stable-snapshot.md
→ docs/features/F03-stable-snapshot.md
→ docs/features/F04-auto-shot-detection.md
→ docs/features/F04-function-contracts.md
→ docs/features/F04-database-dictionary.md
→ 最新相关 docs/sessions/*.md
```

冻结 Feature 的 Stable Snapshot 高于开发阶段 Contract / Implementation Log。

---

# 冻结上游

F01、F02、F03 已由用户实际测试并冻结。

权威快照：

```text
docs/features/F01-stable-snapshot.md
docs/features/F02-stable-snapshot.md
docs/features/F03-stable-snapshot.md
```

F04 不允许修改这些冻结规则。

F03 向 F04 提供：

```text
preprocess/SOURCE_xxx/proxy.mp4
source_preprocess.profile_version
source_preprocess.proxy_sha256
source_preprocess.proxy_duration_us
source_preprocess.proxy_to_source_offset_us
Source Domain integer microseconds
```

F03 已冻结：

```text
Proxy 不强制 VFR→CFR
source_us = proxy_us + proxy_to_source_offset_us
```

因此 F04 任何正式 Shot 时间都不得使用 `frame_index / fps`。

---

# F04 正式技术方案

用户在 2026-08-24 明确确认使用全本地自动拉片方案，F04 开发前的 FFmpeg SCDet 草案已经废弃。

F04 V1：

```text
F03 proxy.mp4
→ FFprobe 逐帧真实 PTS
→ TransNetV2 raw transition prediction
→ prediction index 与真实 PTS 一一对齐
→ 连续 transition frames 归并
→ transition 后第一帧真实 PTS 作为 Cut
→ 120ms 近邻确定性去抖
→ Proxy → Source integer microseconds
→ 连续 Shot Candidate
→ SQLite ready
```

Detector Profile V1：

```text
detector_name = transnetv2_pytorch
transnetv2-pytorch = 1.0.5
torch = 2.5.1
threshold = 0.5
min_boundary_gap_us = 120000
preferred_device = auto
```

模型与依赖身份：

```text
engine/requirements.txt
config/models.yaml
docs/ENVIRONMENT_BASELINE.md
```

---

# F04 Scope Boundary

F04 只负责：

```text
Shot Boundary Detection
Auto Evidence
Shot Candidate
```

F04 不做：

```text
F05 人工边界修正
F06 人物识别
F08 Whisper ASR
F11 Scene 理解
Qwen3-VL 镜头语义分析
云端 Provider
```

这里必须和“完整本地技术栈”区分：Whisper / Qwen3-VL 可以在后续 Feature 使用，但不能为了方便提前塞进 F04。

---

# F04 Time Contract

权威单位：

```text
integer microseconds
```

模型 frame index 只表示“第几个解码帧像 transition”，不是时间。

正式 Cut：

```text
continuous transition [i..j]
→ cut_proxy_us = actual PTS of frame j+1
```

严格禁止：

```text
frame_index / fps
```

Prediction 数与 FFprobe PTS 数不一致：

```text
SHOT_DETECTION_FRAME_ALIGNMENT_FAILED
```

不截短、不补齐、不按 FPS 猜。

Source Mapping：

```text
cut_source_us = cut_proxy_us + proxy_to_source_offset_us
```

Candidate 为半开区间：

```text
[start_us, end_us)
```

必须无 gap、无 overlap、首尾覆盖完整检测区间。无任何 Cut 时整个视频生成 1 个 Candidate，属于合法结果。

---

# F04 Database

Migration：

```text
0005_create_shot_detection
```

新增：

```text
shot_detection_runs
shot_candidates
```

不改写 0001–0004 冻结历史。

详细字段语义：

```text
docs/features/F04-database-dictionary.md
```

Auto Evidence：

```text
detected_proxy_start_us
detected_proxy_end_us
detected_start_us
detected_end_us
end_boundary_score
```

F05 禁止覆盖这些字段。

---

# F04 Backend / API

核心业务：

```text
engine/app/shot_detection.py
```

主要函数：

```text
generate_shot_detection_id()
inspect_proxy_timeline()
detect_proxy_cut_events()
build_shot_candidates()
run_shot_detection()
get_shot_detection()
recover_shot_detections()
```

API：

```text
GET  /api/projects/{project_id}/shot-detection
POST /api/projects/{project_id}/shot-detection
```

应用启动 Recovery 顺序：

```text
F01
→ F02
→ F03
→ F04
```

旧 `processing` F04 Run 会清理；`ready` 不自动删除、不静默覆盖重跑。

---

# F04 Frontend

页面：

```text
/projects/:projectId/shot-detection
frontend/src/views/ShotDetection.vue
```

已实现：

```text
F03 未 ready → 阻止运行并引导 F03
F03 ready → 显示固定本地 Profile
开始自动拉片 → 真实 loading，不伪造百分比
ready → 显示 Shot Count / Cut Count / frame count / runtime
Candidate 表 → Source 起止 / 时长 / 边界类型 / 边界分数
项目总览 → F04 状态与入口
左侧导航 → 04 自动拉片已开放
F05 编辑按钮 → 不存在
```

边界分数只称：

```text
boundary score / transition score
```

禁止称“准确率”。

---

# F04 Test Assets

当前已增加：

```text
engine/tests/unit/test_shot_detection_f04.py
engine/tests/unit/test_shot_detection_model_mapping_f04.py
engine/tests/unit/test_database_migration_f04.py
```

覆盖：

```text
UUID4 business ID
no-cut = one shot
multiple cuts continuity
exact duplicate cut
120ms debounce
edge cut filtering
Source offset mapping
VFR irregular PTS mapping
continuous transition merge
transition reaching video tail
prediction/PTS count mismatch
invalid score fail-closed
0005 schema/head/score constraint
```

---

# 当前验证边界

当前 ChatGPT 工具容器：

```text
Python 3.13.5
PyTorch 2.10.0 CPU
FFmpeg / FFprobe 7.1.5
transnetv2-pytorch 未安装
```

它不是用户 Windows + RTX 4060 Ti 项目环境。因此当前不能声称完成真实 TransNetV2 GPU smoke test，也不能因为工具容器与项目版本不同而改动固定依赖。

用户本机最终验收必须执行：

```text
python -m pip install -r engine/requirements.txt
python -m pytest engine/tests -q
npm ci                       # frontend 目录
npm run typecheck            # frontend 目录
npm run build                # frontend 目录
```

然后启动后端/前端，用真实 F03 ready 项目进入：

```text
04 自动拉片
→ 开始自动拉片
→ 检查 Shot 数与明显切镜点
→ 关闭/重启应用
→ 再次进入 F04
→ ready 结果仍存在
```

同时记录：

```text
Python patch version
PyTorch 2.5.1
CUDA available
GPU 名称
TransNetV2 1.0.5
FFmpeg / FFprobe 版本
真实视频 Shot Count
```

---

# Freeze Gate

当前：

```text
F04 READY_FOR_REVIEW
F04 NOT FROZEN
```

只有用户明确反馈本机自动测试 + 真实视频运行通过后，才允许：

```text
创建 F04 Stable Snapshot
标记 F04 STABLE / FROZEN
开始 F05
```
