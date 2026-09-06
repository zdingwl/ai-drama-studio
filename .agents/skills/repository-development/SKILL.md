---
name: repository-development
description: AI Drama Studio 仓库级开发总控技能。任何新增功能、Bug、前后端、数据库/API、重构、测试、模型链、CI、依赖或交付任务都必须使用；先读当前正式文档和源码，再路由专业技能，验证后安全交付 main。
metadata:
  version: "1.0.0"
  language: zh-CN
---

# AI Drama Studio Repository Development Controller

## 启动时必须做

1. 按 `AGENTS.md` 顺序读取 `docs/00/01/02/03`；相关专项文档按任务补充。
2. 读取根目录 `SKILL.md`。
3. 读取根目录 `AI_SKILLS.md` 的技能路由表，只选择当前任务需要的专业技能。
4. 第一次进入相关模块或影响范围不清时，强制 Codebase Analysis。
5. 确认远端 `main` 最新状态、真实技术栈、测试命令和当前代码/测试。

## 任务分级

- S：局部低风险；
- M：多文件或单模块，必须简短计划；
- L：跨前后端、DB/API、Workflow/数据契约，必须影响分析和完整计划；
- XL：架构/迁移/模型运行方式变化，必须方案、风险、回滚和分阶段验收。

## 永久项目硬边界

开发过程中不得绕过：

- SourceDramaSnapshot 是模块 6–10 唯一源事实入口；
- LocalSubject/Track/Face != Final Character；
- Source != Target；
- SourceDialogueUtterance 1:N ShotDialogueProjection；
- Shot != GenerationSegment；
- GenerationAttempt != GenerationSelection；
- Validity/Readiness/Execution 分离；
- GET 只读，重任务显式 POST；
- Review 处理根问题且不能用“忽略”绕过硬门禁；
- Character V10.1 / H3 QC / 多人 Lip Sync fail-closed；
- raw source audio 不直接混入目标成片。

## 完成门禁

1. 用户目标有实际实现，不是占位。
2. 相关测试/build/typecheck 已真实运行，不能虚构。
3. 本地模型、真实项目、用户看听验收与仓库测试分开报告。
4. 最终 diff 无无关修改、secret、调试垃圾。
5. 数据契约/流程/完成条件变化时同步检查 `docs/00/01/02/03`。
6. 基于最新 main 创建清晰 commit，安全更新 main；禁止 force。
7. 重新读取远端 main 确认提交存在后再报告完成。
