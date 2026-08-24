# AI Drama Studio — Workflow Run / Version / Rerun Contract

Status: CONFIRMED
Official Baseline: `main`

> 本文件定义所有用户 Workflow 的统一重跑、版本、回退和下游失效规则。
> 这是生产系统硬规则，不允许某个 Feature 因为“已确认”就永久禁止重新执行。

---

# 1. 核心原则

```text
确认一个版本 != 锁死整个 Workflow
```

任何会影响生产结果的 Workflow 都必须支持：

```text
首次执行
重新执行
保留历史
新版本成功后切换 current
新版本失败时保留旧 current
查看历史版本
回退/重新选择旧版本
下游 stale
重新计算下游
```

禁止：

```text
第一次成功后永远禁止重跑
确认后只能改数据库才能重新执行
重跑前删除旧结果
新 Run 失败导致旧正式结果丢失
上游变化后下游继续静默使用旧结果
```

---

# 2. 统一 Run 模型

自动计算类能力统一使用 Run：

```text
Run V1
status = ready
is_current = true

用户重新执行
↓
Run V2
status = running
is_current = false

V2 成功
↓
V1 -> historical
V2 -> current

V2 失败
↓
V1 继续 current
V2 -> failed（保留失败记录）
```

推荐状态：

```text
running
ready
failed
historical
stale
```

`historical` 表示曾经有效但不再是当前选择；`stale` 表示其依赖的上游版本已改变。

---

# 3. 统一人工 Revision 模型

人工确认类结果不能原地解锁覆盖。

例如 Final Shots：

```text
Final Shot Set Revision 1
status = confirmed
is_current = true
```

用户需要重新调整：

```text
[重新编辑 / 基于当前版本创建新版]
↓
Revision 2 Draft
↓
人工编辑
↓
Confirm Revision 2
↓
Revision 2 current
Revision 1 historical
```

如果用户取消 Revision 2：

```text
Revision 1 仍然 current
```

人工版本必须支持：

```text
create new draft from current
confirm new revision
compare history
select/rollback previous confirmed revision
```

禁止对已经 confirmed 的历史 Revision 原地修改。

---

# 4. Dependency Snapshot

所有派生 Run / Revision 必须保存它依赖的上游版本。

至少保存：

```text
upstream object id
upstream run/revision id
upstream semantic revision
upstream asset hash（媒体类）
algorithm/model/profile version
```

上游 current 切换后：

```text
旧下游结果保留
↓
标记 stale
↓
不能继续当作 fresh current 使用
```

详细失效规则继续遵守 `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`。

---

# 5. Workflow 01 — 导入原片的重跑

导入原片也必须可重新执行。

场景：

```text
用户选错视频
原片文件版本不对
原片语言设置错
Proxy / Audio 初始化参数未来升级
```

不能覆盖或删除旧 Source。

正确模型：

```text
Source Version 1
+ Preprocess Run 1
↓
用户“重新导入原片”
↓
Source Version 2
+ Preprocess Run 2
↓
用户确认切换
↓
Source V2 current
Source V1 historical
```

Source 改变属于最高级上游语义变化：

```text
Shot
Character
Scene
Dialogue
Design
Generation
Render
```

全部旧下游默认 stale。

当前旧 F02 “一个 Project 只能有一个 Source”规则不足以满足生产需求，需要在 Workflow Versioning 重构时升级为“一个 Project 可以有多个 Source Version，但只有一个 current Source”。不得覆盖原片文件。

---

# 6. Workflow 02 — 拉片的重跑

必须支持两类重做。

## A. 重新自动检测

```text
Current Detection V1
+ Current Final Shot Set R1
↓
[重新自动拉片]
↓
Detection V2
↓
自动创建 Final Shot Draft R2
↓
人工确认
↓
R2 current
R1 historical
```

旧 Detection / Final Shots 都保留。

## B. 不重新跑模型，只重新人工修正

```text
Current Final Shot Set R1 confirmed
↓
[基于当前版本重新编辑]
↓
Final Shot Draft R2（复制 R1）
↓
人工调整
↓
Confirm R2
```

因此 `confirmed` 只能禁止修改 R1 本身，不能禁止创建 R2。

Final Shot current 改变后，人物、场景、对白和所有下游按 Dependency Snapshot 标记 stale。

---

# 7. Workflow 03 — 资产提取的重跑

资产提取第一版包含：

```text
人物资产
场景资产
```

必须支持整体重跑和局部重跑。

## 人物

```text
Actor Detection Run V1
↓
人工资产 Revision 1
↓
发现人物漏识别/误合并
↓
可以：
A. 只重新跑人物自动识别
B. 基于现有人物资产创建人工 Revision 2
```

## 场景

同样支持独立：

```text
Scene Detection Run V1/V2/...
Final Scene Revision 1/2/...
```

人物重跑不得强制场景重跑；场景重跑不得强制人物重跑。

但是如果 Final Shots current 改变，两者都默认 stale。

---

# 8. Workflow 04 — 人物对白的重跑

人物对白内部必须可局部重新执行：

```text
ASR Run
Speaker Diarization Run
Speaker ↔ Character Mapping Run
Final Dialogue Revision
```

允许：

```text
只重跑 ASR
只重跑 Speaker
只重跑 Actor/Speaker Mapping
基于当前对白创建新的人工 Revision
全部重新分析
```

例如只有文字识别错：

```text
不需要重新做人脸/场景
```

只有 Speaker 归属错：

```text
不需要重新跑 Whisper
```

Final Character current 改变时，Speaker/Character Mapping 与 Final Dialogue speaker assignment stale；ASR 文本本身不一定 stale。

---

# 9. Workflow 05+ 的版本规则

剧本/重制设计、生成制作、最终合成天然必须版本化。

例如：

```text
Target Dialogue V1/V2
Character Bible R1/R2
Scene Bible R1/R2
Shot Spec R1/R2
Generation V1/V2/V3
Voice V1/V2
LipSync V1/V2
Audio Mix V1/V2
Master Render V1/V2
```

任何生成结果必须绑定其输入版本，不允许只写“project current”。

---

# 10. UI 统一要求

每个 Workflow 页面必须有统一版本入口：

```text
当前版本：V2 / R3
状态：当前 / 已过期 / 历史

[重新执行]
[基于当前版本重新编辑]
[版本历史]
```

自动重跑弹窗必须说明：

```text
会生成新版本
旧版本不会删除
新版本失败不影响当前版本
成功切换后哪些下游会变成 stale
```

历史版本页面至少显示：

```text
版本号 / Run ID
创建时间
输入版本
算法/Profile
状态
是否 current
结果摘要
```

---

# 11. 禁止“级联自动重跑”

上游重做成功后，下游只能自动标记 stale，不能未经用户确认就把所有昂贵步骤自动重跑。

例如 Final Shots V2 确认后：

```text
人物资产       stale
场景资产       stale
人物对白       stale/部分 stale
Shot Spec      stale
Generation     stale
```

UI 给出：

```text
[重新提取受影响资产]
```

由用户决定何时重新计算。

---

# 12. 回退规则

允许重新选择历史有效版本作为 current，但必须重新计算 freshness。

例如：

```text
Final Shots R1
→ R2
→ 用户回退 R1
```

不能简单把 R1 改 current 后认为所有旧下游都自动 fresh。

必须比较每个下游保存的 Dependency Snapshot；匹配 R1 的结果可以恢复 fresh，不匹配的继续 stale。

---

# 13. 数据删除规则

默认：

```text
不自动删除历史 Run
不自动删除历史 Revision
不自动删除失败 Run Evidence
```

允许未来提供“清理缓存/历史版本”功能，但必须区分：

```text
可重建 Cache
历史业务版本
正式用户资产
```

正式历史版本删除必须显式确认。

---

# 14. Stable Gate 新增硬要求

以后任何 Workflow/Feature 要标记 STABLE，必须额外通过：

```text
[ ] 首次执行可用
[ ] 同输入重新执行可用
[ ] 上游改变后重新执行可用
[ ] 新 Run 失败不会破坏旧 current
[ ] 历史版本可读取
[ ] current 切换可追溯
[ ] stale 正确传播
[ ] stale 不会静默进入正式下游
[ ] confirmed/approved 后仍可创建新 Revision
[ ] 可以基于当前版本重新编辑
```
