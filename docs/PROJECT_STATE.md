# AI Drama Studio — Project State

> 新对话恢复当前项目状态的第一入口。
> 用户流程以 `docs/WORKFLOW_ARCHITECTURE.md` 为最高优先级；所有 Workflow 重跑/版本/回退必须遵守 `docs/WORKFLOW_RUN_VERSIONING.md`。

## 当前状态

```text
Project: AI Drama Studio
Official Baseline: main
Current Working Branch: main

F01-F05 Existing Capability: STABLE BASELINE
Actor Visual Evidence Prototype: EXISTS / NOT ACCEPTED

Current Product Work:
WORKFLOW VERSIONING REFACTOR
```

当前不继续向后堆新 Feature。

用户已经确认两个架构修正：

```text
1. Feature != 用户页面；产品改成 Workflow 驱动
2. 每个 Workflow 必须可重复执行并保留版本
```

---

# 1. 当前用户主流程

```text
01 导入原片
↓
02 拉片
↓
03 资产提取
   ├ 人物
   └ 场景
↓
04 人物对白
↓
05 剧本 / 重制设计
↓
06 生成制作
↓
07 最终合成 / 导出
```

详细见：

```text
docs/WORKFLOW_ARCHITECTURE.md
docs/WORKFLOW_RUN_VERSIONING.md
```

`docs/FEATURE_SEQUENCE.md` 只保留为内部能力拆分参考，不再代表前端一级导航。

---

# 2. 全局版本化硬规则

任何 Workflow 都必须支持：

```text
首次执行
重新执行
新 Run / Revision
旧版本保留
新版本成功后切 current
新版本失败时旧 current 不受影响
历史版本读取
回退 / 重新选择
下游 stale
重新计算下游
```

确认规则改为：

```text
confirmed/approved = 当前 Revision 被锁定
!= 整个 Workflow 永远禁止重做
```

需要修改时创建新的 Draft / Revision，不原地解锁旧 confirmed 版本。

---

# 3. Workflow 01 — 导入原片

当前已有一次性编排实现：

```text
POST /api/project-imports
→ create_project()
→ import_source_video()
→ preprocess_source_video()
```

前端已经是一张“导入原片”表单。

但当前旧底层仍存在：

```text
一个 Project 只能有一个 Source Video
```

这个限制现在被认定为不满足生产需求。

下一版必须升级为：

```text
Source V1 / V2 / ...
只有一个 current Source
旧 Source 永不覆盖
```

重新导入 Source 后，旧 Shot / Asset / Dialogue / Design / Generation / Render 默认 stale。

---

# 4. Workflow 02 — 拉片

用户体验目标已经确定：

```text
开始拉片
→ Auto Shot Detection
→ 自动创建 Final Shot Draft
→ 直接进入镜头工作台
→ 人工确认
```

旧 F04 技术结果页不再作为必须停留的用户步骤。

但当前旧 F05 规则：

```text
confirmed 后永久禁止边界/拆分/合并
```

只能用于保护“该 Revision 不被修改”，不能再用于禁止整个拉片 Workflow 重做。

必须升级为：

```text
Final Shots R1 confirmed
↓
重新自动拉片 / 基于 R1 重新编辑
↓
Final Shots Draft R2
↓
Confirm R2
↓
R1 historical
R2 current
```

---

# 5. Workflow 03 — 资产提取

拉片完成后先提取资产：

```text
人物资产
场景资产
```

人物和场景必须分别支持：

```text
自动 Run V1/V2/...
人工 Final Revision R1/R2/...
重新执行
基于当前结果重新编辑
版本历史
```

人物重跑不强制场景重跑；场景重跑不强制人物重跑。

当前 YuNet + SFace 代码保留为：

```text
AssetExtractionWorkflow
└ Actor Visual Evidence capability
```

Candidate-only 页面不是最终产品。

---

# 6. Workflow 04 — 人物对白

前置：

```text
Current Final Characters
+ Current Final Shots
+ Current Audio
```

内部允许局部重跑：

```text
ASR Run
Speaker Run
Speaker ↔ Character Mapping Run
Final Dialogue Revision
```

可以只重跑其中一个，不强制全部从头执行。

必须支持未归属对白，低置信度不得强行绑定人物。

---

# 7. 下游失效规则

继续遵守：

```text
docs/DEPENDENCY_AND_INVALIDATION_RULES.md
```

上游 current 变化：

```text
旧下游保留
→ stale
→ 禁止静默作为 fresh current 使用
```

禁止自动级联重跑所有昂贵任务。

---

# 8. 现有 Stable Snapshot 如何理解

F01-F05 Stable Snapshot 仍然是重要底层基线：

```text
ID
时间轴
文件安全
Auto Evidence
Final Shot 数据语义
```

但是其中与“整个 Workflow 永久不可重做”冲突的限制，需要通过新 Migration / 新 Version Model 向前升级。

冻结不能成为拒绝生产需求的理由。

必须保留旧数据兼容，不原地破坏现有项目。

---

# 9. 当前开发优先级

立即暂停继续扩展资产/对白算法，先补版本化底座：

```text
P0-0  Run / Revision / Current / Stale 通用规则
↓
P0-1  Source Versioning + 导入原片重跑
↓
P0-2  Final Shot Revision + 拉片重跑/重新编辑
↓
P0-3  资产提取 Workflow（人物 + 场景）
↓
P0-4  人物对白 Workflow
```

以后任何 Workflow 要验收，必须同时验证：

```text
第一次执行
第二次重新执行
失败不破坏旧版本
历史可读取
current 可切换
下游 stale 正确
```

---

# 10. 当前恢复顺序

```text
AGENTS.md
→ SKILL.md
→ docs/PROJECT_STATE.md
→ docs/WORKFLOW_ARCHITECTURE.md
→ docs/WORKFLOW_RUN_VERSIONING.md
→ docs/DEPENDENCY_AND_INVALIDATION_RULES.md
→ F01-F05 Stable Snapshots
→ 当前 Workflow Session
```

`main` 是唯一正式 Source of Truth。未经用户明确要求，不创建 PR、不切换正式基线。
