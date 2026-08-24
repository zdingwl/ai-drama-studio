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

Stable Features: F01, F02, F03
Frozen Features: F01, F02, F03

Current Feature: F04 — 自动拉片
Feature Status: PLANNED
F04 Contract: DRAFTED / WAITING_USER_CONFIRMATION
F04 Function Contracts: DRAFTED / WAITING_USER_CONFIRMATION
F04 Business Code: NOT STARTED
F04 Frontend: NOT STARTED
F04 User Acceptance: NOT STARTED

Next After F04: F05 — Shot 人工修正（NOT STARTED）
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

F03 向 F04 提供的正式输入：

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

因此 F04 不得使用 `frame_index / fps` 作为权威 Shot 时间。

---

# F04 权威规划文档

```text
docs/features/F04-auto-shot-detection.md
docs/features/F04-function-contracts.md
```

用户尚未确认，因此当前只是 PLANNED，禁止开始业务编码。

---

# F04 当前规划

目标：

```text
F03 ready Proxy
→ 本地自动镜头切换检测
→ 保存不可覆盖的 Auto Shot Candidate
→ 同时保存 Proxy Timeline + Source Timeline
→ 页面展示自动 Shot 结果
→ F05 再做人工作业
```

F04 V1 Detector：

```text
FFmpeg scdet
detector_profile_version = 1
threshold = 10.0
min_boundary_gap_us = 120000
```

原因：

- 复用现有 FFmpeg，不新增 OpenCV / PySceneDetect / 云 Provider；
- 使用真实 PTS，适配 F03 VFR Proxy；
- 自动结果只是 Candidate，不直接成为 Final Shot；
- F05 负责人工修正。

SCDet score 只能解释为：

```text
切换强度 / boundary_score
```

不得冒充概率置信度。

---

# F04 Time Contract

F04 属于 Source Domain。

权威时间：

```text
integer microseconds
```

检测发生在 Proxy：

```text
cut_proxy_us
```

正式映射：

```text
cut_source_us = cut_proxy_us + proxy_to_source_offset_us
```

Shot Candidate 使用：

```text
[start_us, end_us)
```

必须满足：

```text
无 gap
无 overlap
first.start == detection_start
last.end == detection_end
prev.end == next.start
```

无 Cut 也是合法结果：

```text
整个视频 = 1 个 Shot Candidate
```

---

# F04 AI Evidence / Human Final

F04 只保存自动原始证据：

```text
detected_proxy_start_us
detected_proxy_end_us
detected_start_us
detected_end_us
boundary_score
```

F05 禁止覆盖这些字段。

F05 必须新增独立 Human Final Shot Contract，支持：

```text
边界调整
拆分
合并
新增
删除
人工确认
```

但 F05 目前 NOT STARTED。

---

# F04 Database Plan

计划新增：

```text
0005_create_shot_detection

shot_detection_runs
shot_candidates
```

Detection Run：

```text
SHOT_DETECTION_<UUID4>
status = processing / ready
1 Project → 1 F04 V1 ready run
```

Candidate：

```text
SHOT_CANDIDATE_<UUID4>
```

Candidate 不是最终 `SHOT_<UUID>`；最终 Shot 身份由 F05 Contract 决定。

0001–0004 已属于冻结 Migration 历史，不得改写。

---

# F04 Recovery Plan

F04 不产生新的正式媒体文件。

流程：

```text
DB processing run
→ FFmpeg scan
→ 内存构造 Candidate
→ 单 DB transaction 保存所有 Candidate + run ready
```

如果应用异常退出：

```text
旧 processing run
→ 下次启动 recover_shot_detections()
→ 清理 processing run / candidate
→ 用户重新检测
```

ready 结果不会被 Recovery 删除。

同一进程重复 POST：

```text
SHOT_DETECTION_IN_PROGRESS
```

ready 后重复 POST：

```text
SHOT_DETECTION_ALREADY_EXISTS
```

---

# F04 Core Functions Plan

6 个核心后端函数：

```text
generate_shot_detection_id()
detect_proxy_cut_events()
build_shot_candidates()
run_shot_detection()
get_shot_detection()
recover_shot_detections()
```

2 个 Controller：

```text
get_shot_detection_api()
run_shot_detection_api()
```

详细职责：

```text
docs/features/F04-function-contracts.md
```

---

# F04 API Plan

```text
GET  /api/projects/{project_id}/shot-detection
POST /api/projects/{project_id}/shot-detection
```

GET 支持：

```text
null
processing
ready + candidates
```

POST 成功：

```text
201 ready DetectionDTO
```

---

# F04 Frontend Plan

计划路由：

```text
/projects/:projectId/shot-detection
```

F03 未 ready：

```text
阻止并引导视频预处理
```

未检测：

```text
展示 Proxy + 固定 Detector Profile V1
→ 开始自动拉片
```

processing：

```text
正在分析镜头切换…
不伪造百分比
```

ready：

```text
Shot 数量
Cut 数量
检测区间
Detector Profile
只读 Shot Strip
Candidate 时间表
```

F04 不提供拖边界或拆分/合并编辑器。

---

# P0 Planning

```text
P0-01 Dependency / Revision: APPLICABLE / PENDING
P0-02 Media Timebase:         APPLICABLE / PENDING
P0-03 Environment:            APPLICABLE / PENDING
P0-04 DB + Recovery:          APPLICABLE / PENDING
P0-05 Provider Job:           N/A（本地 FFmpeg）
```

详细填写在 `docs/features/F04-auto-shot-detection.md`。

---

# 当前 Gate

现在：

```text
F04 = PLANNED
```

只有用户确认 F04 Contract 后才能：

```text
F04 → IN_PROGRESS
```

然后按计划开发：

```text
0005 Migration
→ ID / SCDet parser
→ PTS / Source Mapping
→ Candidate builder + continuity validation
→ Detection business flow
→ Recovery
→ GET / POST API
→ Vue 自动拉片页
→ F01/F02/F03/F04 tests
→ 真实短剧测试
→ READY_FOR_REVIEW
```

F04 未冻结前不得正式开发 F05。

## 最近更新时间

- 日期：2026-08-24 12:37 +08:00
- 状态：用户明确开始 F04；F04 主 Contract 和详细函数职责已规划并提交 main，等待用户确认后进入编码。
