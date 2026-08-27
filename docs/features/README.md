# Feature Documents

本目录保存项目历史 Feature 规格、实现、测试、验收和 Freeze 文档。

## Current architecture warning

AI Drama Studio 已经重构为 **Reference Video V2**。因此这里的旧 `F01-F06`、Frozen Snapshot、旧 35-Feature 顺序不再自动代表当前可执行架构。

新对话不要从本目录开始恢复项目状态。

当前强制读取顺序：

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/CURRENT_IMPLEMENTATION_MANIFEST.md
→ PROJECT_STATE 指定的 current implementation doc
→ current code
```

当前人物实现文档：

```text
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

## Historical value

本目录中的 Feature 文档仍然有价值，用于：

- 追溯为什么曾经这样设计；
- 查找旧 API/DB/UX 决策；
- 复用低层实现思路；
- 理解迁移路径。

但旧文档不能在没有新的用户明确决策时覆盖当前正式 wiring。

旧 Feature 文件如果被后续架构取代，应在文件顶部明确标记：

```text
LEGACY / SUPERSEDED
```

而不是让新对话误以为它仍是 `PLANNED` 的下一步。

## Documentation synchronization rule

当前代码发生正式架构/profile/resolver/Final Gate/Binding 变化时，优先同步：

```text
AGENTS.md
SKILL.md
docs/PROJECT_STATE.md
docs/CURRENT_IMPLEMENTATION_MANIFEST.md
current implementation doc
latest docs/sessions handoff
```

代码与这些入口文档不一致时，先修文档再继续开发。

历史模板仍保留：

```text
templates/FEATURE_SPEC_TEMPLATE.md
templates/FEATURE_IMPLEMENTATION_LOG_TEMPLATE.md
```
