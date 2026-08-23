# Session Handoff — P0 Engineering Hardening

## 1. 本次目标

在正式进入 Feature 01 之前，对现有 Skill 做一次工程规则加固，补齐 5 个 P0 缺口：

1. 上下游 revision / stale / invalidation；
2. 媒体统一 Timebase；
3. 环境与依赖可复现；
4. SQLite + 本地文件写入、migration 与崩溃恢复；
5. Provider 异步/计费任务的幂等、超时与恢复。

## 2. 开始前状态

- 业务代码尚未开始。
- 当前 Feature：F01 创建项目，PLANNED / NOT_STARTED。
- 已存在主 `SKILL.md`、30 Feature 顺序、冻结规则、跨对话协议、代码/数据库注释规范。
- Skill 审计发现长期维护和数据有效性方面仍有 P0 缺口。

## 3. 实际完成

### 新增 Skill Addendum

- `SKILL_P0.md`

定义 `SKILL.md + SKILL_P0.md` 共同构成完整 Skill。

### 新增 P0 索引

- `docs/P0_RULES_INDEX.md`

### 新增 5 个 P0 Contract

- `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`
- `docs/MEDIA_TIMEBASE_CONTRACT.md`
- `docs/ENVIRONMENT_BASELINE.md`
- `docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`
- `docs/PROVIDER_JOB_RULES.md`

### 新增 Feature P0 Checklist

- `templates/P0_FEATURE_CHECKLIST.md`

每个 Feature 编码前必须逐项填写 PASS/N/A。

### 更新 Agent 入口

- `AGENTS.md`

新增 P0 Skill、P0 Index 和详细 P0 规则的强制读取/执行规则。

### 更新项目状态

- `docs/PROJECT_STATE.md`

记录 P0 规则已建立，并将 P0 Review 纳入 Stable Gate。

## 4. 关键技术决策

### Decision 01 — 不直接修改超长主 SKILL，增加强制 Addendum

决策：增加根目录 `SKILL_P0.md`，并在 `AGENTS.md` 中明确它与 `SKILL.md` 共同构成完整 Skill。

原因：主 Skill 已很长；P0 规则属于全局工程 Contract，独立文档更容易维护、审计和在新对话按需读取。

### Decision 02 — 业务时间使用 integer microseconds

决策：业务权威时间使用整数微秒，Source Timeline 为母时间轴。

原因：避免 float 秒、29.97/23.976、VFR、Proxy offset、音频时间轴造成累积误差。

### Decision 03 — 上游修改不删除下游，只标 stale

原因：保留历史结果用于对比、回退、成本和调试；正式生产默认禁止读取 stale 结果。

### Decision 04 — Provider timeout 不等于 failed

原因：远端可能已创建并计费。必须优先 reconciliation/resume，避免重复生成。

### Decision 05 — SQLite 与媒体采用状态机补偿而非假装原子事务

原因：DB transaction 不能包含文件系统。采用 pending/staging/validate/atomic rename/finalize + startup recovery。

## 5. 本次没有做

- 没有开始 Feature 01 业务代码。
- 没有最终决定 F01 的数据库布局。
- 没有实现 runtime/environment 诊断代码。
- 没有实现 revision/stale DB schema。
- 没有实现 Provider Job DB schema。
- 没有实现 media time utility。

这些都应在具体 Feature 首次需要时通过 Contract 落地，不在全局规则阶段提前写死实现细节。

## 6. Contract 变化

项目级 Contract 发生变化：Yes。

新增全局约束：

- 派生结果必须支持 dependency revision / stale 语义（适用时）；
- 时间业务数据不得只依赖 float 秒；
- 新依赖必须锁定/记录；
- DB+文件写入必须有恢复策略；
- 外部计费任务必须支持安全重试/恢复语义；
- Feature Freeze 增加 5 个 P0 Review。

## 7. 测试

本次仅修改文档规则，没有业务代码可运行测试。

已完成文档一致性检查：

- P0 Addendum 能索引 5 个详细规范；
- AGENTS 读取顺序包含 P0；
- PROJECT_STATE 已记录 P0 Gate；
- Feature P0 Checklist 可用于 F01–F30。

## 8. 当前风险

- 主 `SKILL.md` 本体没有直接插入 P0 正文，而是通过强制 `SKILL_P0.md` Addendum 组成完整 Skill；Agent 必须遵守 `AGENTS.md` 的读取顺序。
- 未来实际实现 revision/stale/timebase/job state 时，具体字段名仍需要在对应 Feature Contract 中冻结。

## 9. Git

- Repository：`zdingwl/ai-drama-studio`
- Branch：`docs/p0-hardening`
- Base：`docs/project-skill`
- 上游 Draft PR：#1（`docs/project-skill` → `main`）
- 本次 P0 规则将单独创建 Draft PR 到 `docs/project-skill`。

## 10. 下一步唯一动作

> 审阅/合并 P0 hardening PR 到 `docs/project-skill`；随后创建 `docs/features/F01-create-project.md`，把 `templates/P0_FEATURE_CHECKLIST.md` 一并嵌入 Feature 01 Contract，再决定项目 DB 布局、Project ID、Workspace 规则并开始 F01 编码。

## 11. 新对话建议读取

1. `AGENTS.md`
2. `SKILL.md`
3. `SKILL_P0.md`
4. `docs/PROJECT_STATE.md`
5. `docs/P0_RULES_INDEX.md`
6. 当前 Feature 文档（创建后）
7. 本 Session Handoff
