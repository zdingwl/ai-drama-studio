# Session Handoff — 2026-08-27 20:15 +09:00 — PROJECT — Breakdown P1 Closure

## 1. 本次开发目标

- 正式完成 Breakdown-first Phase P1.7。
- 把 P1.1–P1.6 已落地事实同步回 CURRENT / Manifest / Target Plan / P1 Contract。
- 在真实 `windows-latest` 上完成 P1 空数据库、历史项目与 focused regression 兼容验收。
- 固化 Windows P1 CI 门槛，防止 P2+ 后续破坏旧项目/历史 Reference Clip。

## 2. 开始前项目状态

- 当前 Feature：Breakdown-first P1.7
- Feature 状态：P1.1–P1.6 已完成，P1.7 未开始
- 前置 Stable Feature：Reference Video V2 / Character V10.1 / Breakdown P1.1–P1.6
- 当前 branch：`main`
- 当前 PR：无
- 开始前最新 commit：`c960ef36dea4ce044921c1ccba07b63e21622b5b`
- 开始前已知问题：CURRENT 文档仍把 P1 写成 NOT IMPLEMENTED；全仓 Ubuntu CI 有 28 个既有 legacy/runtime/environment failures；frontend 有既有 vue-tsc/TypeScript build failure。

## 3. 本次实际完成

- 新增 P1.7 Windows/历史项目兼容验收测试。
- 新增 `breakdown-p1-windows` CI job，使用 `windows-latest`。
- 验证 fresh empty DB 两次 `init_database()` 幂等、ADD-only，不创建业务行。
- 验证 pre-P1 historical V2 DB 在补 ShotRevision/P1 tables 后旧 Project/Episode/Shot/Reference Clip 不变且可读。
- 验证 Windows 含空格/中文路径可正常通过 P1 focused suite。
- 验证 read-only Breakdown API/serializer 不会给历史项目偷偷创建 BASELINE ShotRevision 或 BreakdownRun。
- Windows P1 focused suite 实际 32/32 PASS。
- Ubuntu full pytest 变为 `28 failed, 219 passed, 1 skipped`；新增 2 个 compatibility tests 均通过，原 28 个失败类别未增加。
- 同步 `PROJECT_STATE.md`：P1 COMPLETE / P2 NEXT。
- 同步 `CURRENT_IMPLEMENTATION_MANIFEST.md`：列出 P1 modules/tables/lifecycle/validator/API/STALE/Windows acceptance。
- 同步 `BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`：P0/P1 COMPLETE，P2 NEXT，P3-P7 PLANNED。
- 同步 `BREAKDOWN_DRAFT_DATA_CONTRACT.md`：从设计稿状态改为 IMPLEMENTED/CLOSED Contract，并记录真实 P1 物理表与 P2 I/O 边界。
- Character V10.1、Final Asset/Binding、ASR/OCR/VLM runtime 均未修改。

## 4. 修改文件清单

### 新增

- `engine/tests/v2/test_breakdown_p1_compat_acceptance_v1.py` — P1.7 fresh DB / historical pre-P1 DB ADD-only compatibility acceptance。
- `docs/sessions/2026-08-27_2015_PROJECT_breakdown-p1-closure.md` — 本 handoff。

### 修改

- `.github/workflows/v2-ci.yml` — 新增 Windows Breakdown P1 focused CI job。
- `docs/PROJECT_STATE.md` — CURRENT 状态同步为 P1 COMPLETE / P2 NEXT。
- `docs/CURRENT_IMPLEMENTATION_MANIFEST.md` — 补齐 P1 executable manifest 和最新 CI reality。
- `docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md` — 同步 Phase 状态与 P2 唯一下一阶段。
- `docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md` — 同步为已实现 P1 Contract。

### 删除

- 无。

## 5. 关键代码位置

| 位置 | 作用 | 后续修改注意事项 |
|---|---|---|
| `engine/app/breakdown_models_v1.py` | P1 anonymous Draft ORM / 10 tables | P2 必须复用；不要另建平行 Draft schema |
| `engine/app/breakdown_service_v1.py` | Run lifecycle / publish / FAIL / STALE | READY 必须继续走真实 validator |
| `engine/app/breakdown_validator_v1.py` | P1 fail-closed validator | 不要为了模型方便绕过 hard errors |
| `engine/app/breakdown_serializer_v1.py` | read-only current/history serializer | historical read 不能偷偷创建 BASELINE |
| `engine/app/breakdown_routes_v1.py` | read-only Breakdown API | P2 write API 需单独设计，不改写历史 AI Draft |
| `engine/app/shot_revision_v2.py` | ShotRevision history + P1.6 STALE integration | 新 Current Revision 与 STALE 必须同事务 |
| `engine/tests/v2/test_breakdown_p1_compat_acceptance_v1.py` | P1.7 empty/historical acceptance | 保持 Windows/Unicode/ADD-only cases |
| `.github/workflows/v2-ci.yml` | durable Windows P1 gate | P2+ 不得删除该 job |

## 6. API 变化

### 新增

- P1.7 无新增 API。

### 修改

- 无。

### 删除

- 无。

### 当前 Contract

P1.4 既有 read-only Contract 继续有效：

```text
Episode Breakdown Run history
Episode current Breakdown
Breakdown by Run ID
historical ShotRevisionItem provenance
historical Reference Clip URL
```

## 7. Database 变化

### Migration

- P1.7 无新 migration / schema change。

### 表/字段变化

- 无。

### 当前 P1 表

```text
v2_breakdown_runs
v2_scene_segment_drafts
v2_shot_semantic_drafts
v2_local_subjects
v2_shot_local_subjects
v2_timeline_events
v2_timeline_event_subjects
v2_draft_prop_hints
v2_draft_prop_occurrences
v2_breakdown_evidence_links
```

### 数据兼容性

- fresh empty DB：通过。
- pre-P1 historical V2 DB：ADD-only upgrade 通过。
- old Project/Episode/Shot rows：保持可读。
- old ShotRevision/ShotRevisionItem/Breakdown history：保持可读。
- old Reference Clip：保持可读。
- 不 DROP 旧表/字段。

## 8. 文件系统变化

- 新增目录：无。
- 新增生成文件：无业务生成文件。
- 路径/命名规则：P1.7 acceptance 明确测试 Windows 含空格/中文路径。
- 是否改变已有文件 Contract：No。

## 9. 依赖 / 环境变化

- Python package：无新增生产依赖。
- Node package：无。
- FFmpeg/CUDA要求：无变化。
- 环境变量：无。
- 配置文件：`.github/workflows/v2-ci.yml` 增加 `windows-latest` P1 focused job。

## 10. 技术决策与原因

### Decision 001 — P1.7 必须先验收再写“完成”

- 决策：先增加 Windows/fresh/historical acceptance，再同步文档。
- 原因：P1 Contract 明确定义 P1.7 = 文档同步 + Windows 空数据/历史项目兼容验收。
- 替代方案：只改文档。
- 为什么没有采用：会出现“文档完成但旧项目/Windows 未验证”的假完成。
- 对后续的影响：P2+ 每个 PR 都持续受到 Windows P1 gate 保护。

### Decision 002 — Historical read 继续纯读取

- 决策：P1.4 read-only serializer 对 pre-P1 Episode 没有 Breakdown 时返回空历史/None，不创建 BASELINE。
- 原因：GET/read 不应产生隐藏业务写入。
- 替代方案：读取时调用 `ensure_current_revision()`。
- 为什么没有采用：会改变旧项目状态，破坏可预期性和 P1.7 compatibility contract。
- 对后续的影响：P2 write/run creation 才能显式建立需要的 Current ShotRevision。

### Decision 003 — P1 closure 不等于 P2 inference 完成

- 决策：CURRENT docs 将 `P1 data/runtime infrastructure` 与 `P2 ASR/OCR/VLM producer` 明确分开。
- 原因：防止恢复上下文后把空结构化表误报成自动内容拉片。
- 对后续的影响：下一阶段唯一是 P2。

## 11. 本次没有做的内容

- 没有实现 ASR。
- 没有实现 OCR。
- 没有实现 VLM semantic Breakdown producer。
- 没有实现 Speaker diarization / active speaker。
- 没有实现 P3 structured Breakdown UI。
- 没有让 Draft 指导 Scene/Prop/Character Final resolution。
- 没有创建 DraftResolution 物理表。
- 没有修改 Character V10.1。
- 没有写 Character/Scene/Prop/Shot Binding/AssetRevision。
- 没有解决全仓既有 28 个 backend failures。
- 没有解决既有 frontend vue-tsc/TypeScript build failure。

## 12. 测试执行情况

### 自动测试 — Windows P1 acceptance

```text
Runner: windows-latest / Microsoft Windows Server 2025
Command:
python -m pytest -q \
  engine/tests/v2/test_breakdown_p1_compat_acceptance_v1.py \
  engine/tests/v2/test_breakdown_contract_compat_v1.py \
  engine/tests/v2/test_breakdown_lifecycle_v1.py \
  engine/tests/v2/test_breakdown_validator_v1.py \
  engine/tests/v2/test_breakdown_stale_integration_v1.py

Result: 32/32 PASS
```

### 自动测试 — Ubuntu full suite

```text
Compile engine/app: PASS
FastAPI import/version: PASS — AI Drama Studio 2.4.1
pytest: 28 failed, 219 passed, 1 skipped
```

28 failures 与 P1.6 baseline 相同类别：旧 Final Gate/workspace expectations、轻量 CI 缺 `cv2` / `trackers` / ffmpeg、旧 V6 assertions 等。

### Frontend

```text
npm run build: existing failure
```

P1.7 无 frontend feature change。

### 手工测试

- 无单独人工 UI 操作；P1.7 是 backend/data compatibility closure。

### 真实素材测试

- 本阶段无新真实视频推理；P1 没有 ASR/OCR/VLM producer。
- Character V10.1 real-video SHOT 0001–0009 acceptance 是独立事项，不要和 P1 Windows DB/test acceptance 混淆。

## 13. 当前 Bug / 风险

### Bug

- 全仓仍有 28 个既有 backend test failures。
- frontend build 仍有既有 vue-tsc/TypeScript compatibility failure。

### 风险

- P2 如果重新发明一套 Draft schema，会破坏已冻结 P1 contract。
- P2 如果直接写 Final Asset/Bindings，会越过 P1/P4/P5 边界。
- P2 如果把 VLM prose 当 identity truth，会破坏 Character V10.1 fail-closed contract。

### 临时 workaround

- 无。P1 focused Windows gate 已作为正式长期门槛。

## 14. Contract 变化检查

- Input Contract：P1.7 未改变 P1 producer input；文档同步为真实已实现状态。
- Output Contract：未改变。
- API Contract：未改变。
- DB Contract：未改变；新增兼容验收锁住 ADD-only 行为。
- File Contract：未改变。
- ID/状态枚举：未改变。

## 15. 当前 Feature 状态

- 状态：STABLE / CLOSED（以 PR #8 squash merge 到 `main` 为最终仓库落点）
- 已完成：P1.1–P1.7 全部内容、Windows compatibility acceptance、文档同步。
- 未完成：P2+。
- 是否可进入下一个 Feature：Yes。
- 下一 Feature：P2 ASR/OCR/VLM anonymous Draft sidecar。

## 16. Git 状态

- Repository：`zdingwl/ai-drama-studio`
- Branch：`feat/breakdown-p1-7-closure`
- 开始前 main：`c960ef36dea4ce044921c1ccba07b63e21622b5b`
- Acceptance commit：`19976f185b64c45610ca380301490c80b9b825d8`
- Docs commits：本 PR 后续 commits（最终 squash 后请重新读取 `main` SHA）
- PR：#8 `chore: close Breakdown P1 with compatibility acceptance`
- 是否存在未提交修改：No；所有修改均在 PR branch。

## 17. 下一步唯一推荐动作

> 在用户明确要求进入 P2 后，先从最新 `main` 重新读取 P1 Contract 与 Breakdown modules，然后只规划/实现 P2 的 ASR/OCR/VLM anonymous Draft producer/provider boundary；P2 必须输出到现有 P1 entities，并继续禁止 Final Asset/Binding writes。

## 18. 新对话读取清单

1. `AGENTS.md`
2. `SKILL.md`
3. `docs/PROJECT_STATE.md`
4. `docs/CURRENT_IMPLEMENTATION_MANIFEST.md`
5. `docs/BREAKDOWN_FIRST_ASSET_PIPELINE_PLAN.md`
6. `docs/BREAKDOWN_DRAFT_DATA_CONTRACT.md`
7. `docs/ASSET_CHARACTER_RECOGNITION_V10_1.md`（涉及 Character 时）
8. 本 Session Handoff
9. 必要代码：
   - `engine/app/breakdown_models_v1.py`
   - `engine/app/breakdown_service_v1.py`
   - `engine/app/breakdown_validator_v1.py`
   - `engine/app/breakdown_serializer_v1.py`
   - `engine/app/breakdown_routes_v1.py`
   - `engine/app/shot_revision_v2.py`
   - `.github/workflows/v2-ci.yml`

## 19. 给下一位 Agent 的一句话

> Breakdown P1 已完成并通过真实 Windows 32/32 focused compatibility acceptance；下一步只能在明确进入 P2 后，让 ASR/OCR/VLM producer 复用现有 P1 Draft Contract，绝不能越级写 Final Asset/Binding。
