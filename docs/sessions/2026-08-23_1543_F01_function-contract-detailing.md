# Session Handoff — F01 Function Contract Detailing

## Session

```text
Date: 2026-08-23 15:43 +08:00
Feature: F01 — 创建项目
Branch: main
Business Code: NOT_STARTED
Status: PLANNED
```

## 用户反馈

用户指出此前 F01 规划虽然列出了 Controller / Service / Repository 等函数，但大量内容只有函数名和一句“单一职责”，无法直接理解这些函数的真正作用，尤其 Controller 不知道是干什么的。

该反馈成立。

## 本次修正

新增：

```text
docs/features/F01-function-contracts.md
templates/FUNCTION_CONTRACT_TEMPLATE.md
```

并更新：

```text
docs/PROJECT_STATE.md
```

## 新规则

单函数规划以后不能只写：

```text
create_project_endpoint() — request validate → service → DTO
```

必须进一步说明：

1. 真实业务作用；
2. 为什么独立；
3. 谁调用；
4. 调用谁；
5. 输入；
6. 输出；
7. DB/文件/网络/前端状态副作用；
8. 明确禁止行为；
9. 异常；
10. 测试。

## Controller 定义

Controller / Endpoint 是 HTTP 边界，不是业务层。

正确职责：

```text
HTTP request
→ Schema validation
→ Service call
→ Response DTO
→ Domain Error → HTTP Error
```

Controller 禁止：

```text
SQL
mkdir
读写 project.json
生成 Project ID
拼 Workspace Path
事务编排
Recovery
```

## 已详细解释的 F01 函数组

```text
Backend Foundation B01-B11
Project Validation / Paths P01-P09
Manifest M01-M06
Repository R01-R07
Recovery / Service S01-S09
API Controller A01-A06
Frontend API F01-F06
Pinia Store F07-F11
Vue UI Handler U01-U09
```

## 当前状态

- F01 主 Contract 已存在；
- F01 Function Contracts 已存在；
- 未开始代码；
- 未创建新分支；
- 未创建 PR；
- F01 仍等待用户确认。

## 下一步

用户继续审查 F01 Function Contracts。

如果用户确认后：

```text
F01 PLANNED
→ IN_PROGRESS
→ 从 B01 resolve_app_data_dir() 开始
→ Function Contract
→ 实现
→ 测试
→ PASS
→ B02
```

不得跳到整个 Controller/Service 批量开发，也不得开始 F02。
