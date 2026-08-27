# AI Drama Studio — 跨对话持续开发协议

## 1. 目的

聊天窗口可能超限、新对话可能没有历史上下文，也可能由不同 Agent/开发者连续接手。

因此：

> 项目真实上下文必须保存在 GitHub，而不是只存在聊天记录中。

新对话应该能够依赖 `main` 中的当前入口文档和代码直接继续，不重新从旧计划推断“现在运行的到底是哪一版”。

---

## 2. `main` 是恢复基线

默认：

```text
main = 当前正式开发基线
```

用户已要求日常开发直接在 `main` 进行。除非用户明确指定其它 branch/PR，否则新会话不得自行切换工作基线。

---

## 3. 新对话强制最短读取顺序

当前 Reference Video V2 项目不再把旧 35 Feature 文档当第一恢复入口。

必须先读：

```text
1. AGENTS.md
2. SKILL.md
3. docs/PROJECT_STATE.md
4. docs/CURRENT_IMPLEMENTATION_MANIFEST.md
5. PROJECT_STATE 指定的当前实现文档
6. 当前正式 wiring 代码
7. 最新相关 docs/sessions/*.md
8. 只有确实需要历史原因时，才读旧 Feature/Frozen/版本文档
```

当前人物链的实现文档是：

```text
docs/ASSET_CHARACTER_RECOGNITION_V10_1.md
```

不要因为看到 `docs/features/F06-auto-character-detection.md`、旧 V6 文档或 Frozen Snapshot 就假设它仍是当前实现。

---

## 4. 新增：文档与代码一致性检查

读取入口文档后，任何涉及人物/Shot/资产的工作开始前必须做一次最小 wiring check。

人物当前至少检查：

```text
engine/app/character_visual_v2.py
engine/app/character_runtime_v6.py
engine/app/character_identity_v101.py
engine/app/character_shot_binding_v101.py
engine/app/asset_final_gate_v10.py
```

检查内容：

```text
formal runtime profile
formal resolver
实际 import/call order
Final Gate allow-list
```

如果代码和 `PROJECT_STATE` / `CURRENT_IMPLEMENTATION_MANIFEST` 不一致：

> 先同步文档，再继续写新功能。

禁止选择“看起来更新”的旧文档直接覆盖当前可执行 wiring。

---

## 5. `PROJECT_STATE.md` 的职责

它只保存“现在是什么状态”，至少包括：

- 当前架构与 app version；
- 当前正式算法/Resolver/Profile；
- 当前代码 wiring；
- 当前实现状态；
- 当前阻塞项；
- 已知 Bug/CI 状态；
- 已确认关键技术决策；
- 下一步唯一动作；
- 当前应读取的实现文档。

历史流水账放 Session，不放 PROJECT_STATE。

---

## 6. `CURRENT_IMPLEMENTATION_MANIFEST.md` 的职责

它是比历史 Feature 文档更短的“可执行实现清单”，用于防止文件名、兼容模块名和旧版本文档误导新对话。

至少维护：

```text
Repository / branch / app version
formal runtime profile
formal asset profile
formal resolver
actual call order
active module map
Final Gate
validation status
current implementation docs
```

算法正式入口变化时必须同步它。

---

## 7. Feature / Version 文档的职责

长期 Feature 文档仍保留产品演进历史，但必须区分：

```text
CURRENT IMPLEMENTATION
LEGACY / SUPERSEDED
STABLE SNAPSHOT OF AN OLD ARCHITECTURE
```

旧 Contract 即使曾经“CONFIRMED BY USER”，在后续用户明确批准架构重构后也可能成为 Legacy。旧确认不能覆盖用户后来确认的新架构。

对当前实现有直接约束的版本文档必须由 `PROJECT_STATE` 明确点名。

---

## 8. Session Handoff

每一次实际开发或重要文档同步结束创建：

```text
docs/sessions/YYYY-MM-DD_HHMM_<scope>_<topic>.md
```

至少回答：

1. 本次目标；
2. 开始前状态；
3. 实际完成；
4. 修改文件；
5. API/DB/File 是否变化；
6. 技术决策；
7. 没完成什么；
8. 测试/CI/真实素材状态；
9. 当前 Bug/风险；
10. Contract 是否变化；
11. branch/commit；
12. 下一步具体动作；
13. 新对话应该先读哪些文件。

禁止只写“今天完成某功能”。

---

## 9. 文档权威冲突

当前项目按以下顺序理解：

```text
用户最新明确决策
→ 当前正式可执行 wiring + 明确 Stable Contract
→ AGENTS.md / SKILL.md
→ PROJECT_STATE.md
→ CURRENT_IMPLEMENTATION_MANIFEST.md
→ PROJECT_STATE 明确点名的 current implementation doc
→ 最新 Session
→ Legacy Feature / Frozen / 历史版本文档
→ 历史聊天讨论
```

原因：本仓库已经经历过大版本架构重构，旧 Frozen/Feature 文件不能因为文件名正式就永久高于后来已落地的新架构。

发现冲突必须显式记录和修复。

---

## 10. Stable/Frozen 权限

Agent 可以将新工作推进到：

```text
IMPLEMENTED / READY_FOR_REVIEW
```

只有用户明确完成真实素材/产品验收后才可以写：

```text
STABLE / FROZEN
```

代码存在和单元测试存在都不等于真实媒体验收完成。

---

## 11. 代码与文档是一个交付物

任何实际代码修改结束前至少：

```text
更新 current implementation doc
+ 更新 PROJECT_STATE
+ 更新 CURRENT_IMPLEMENTATION_MANIFEST（正式 wiring/profile 变化时）
+ 新建 Session Handoff
```

如果涉及全局 baseline，再同步：

```text
AGENTS.md
SKILL.md
README.md（用户入口状态变化时）
```

代码完成但当前入口文档仍描述旧算法：

> 本次开发未完成。

---

## 12. 开发过程中必须立刻记录的变化

以下变化不能等会话最后凭记忆补：

- DB Schema/Migration；
- API Contract；
- 正式 runtime/resolver/profile；
- Identity / Final Gate 规则；
- Shot Binding 语义；
- 新依赖/模型/Provider；
- 环境版本变化；
- 时间轴/文件路径规则；
- Provider workaround；
- 真实素材异常；
- 临时兼容模块/文件名；
- P0 实现方式变化。

---

## 13. 下一步必须可执行

禁止：

```text
下一步：继续优化人物识别
```

应写：

```text
下一步：在 Windows 本机拉取 main，重新执行资产提取，核对指定 Shots 的 ShotCharacterBinding；如仍未绑定，读取该 Run 的 person_evidence 与 track_recovery_* 元数据定位失败环节。
```

---

## 14. 目标

即使完全没有旧聊天记录，一个新 Agent 也应该能够：

```text
读取少量 current 入口文档
→ 知道实际运行版本
→ 知道当前 wiring
→ 分辨 Legacy 文档
→ 知道当前验证状态
→ 直接执行 Next Action
```

而不是重新从旧 F06 规划、旧 Character V6 或聊天历史推断项目现状。
