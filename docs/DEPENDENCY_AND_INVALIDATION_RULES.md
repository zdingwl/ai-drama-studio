# AI Drama Studio — Dependency / Revision / Invalidation Rules

## 1. 目的

本规则解决一个核心问题：

> 上游 Final 数据已经被下游使用后，如果上游再次被人工修改，旧下游结果是否仍然有效？

没有失效机制时，系统可能出现“数据看起来都存在，但其实是旧数据”的隐蔽错误。

例如：

```text
Shot 边界已修改
但 Character 分析仍然来自旧 Shot
Shot Spec 仍然来自旧 Character / Scene
Generation 仍然来自旧 Shot Spec
QC 却继续显示 PASS
```

这种情况必须被系统识别。

---

## 2. 核心概念

### Revision

可被人工或系统重新确认的重要业务对象，应有 revision / version 概念。

建议至少覆盖：

- Final Shot
- Final Character（涉及结构变化时）
- Final Dialogue
- Final Scene
- Character→Actor Mapping
- Character Bible
- Scene Bible
- Shot Specification
- Reference Asset Set

Revision 只在影响下游语义的内容变化时递增。

### Dependency Snapshot

派生结果创建时必须记录它所依赖的关键上游版本。

示例：

```json
{
  "shot_revision": 4,
  "character_bible_revision": 2,
  "scene_bible_revision": 3,
  "shot_spec_revision": 5
}
```

### Fresh

派生结果的 dependency snapshot 与当前上游版本一致。

### Stale

派生结果仍然存在且历史上可能有价值，但它依赖的上游版本已变化。

`stale` 不等于 `failed`，也不允许自动删除。

### Invalid / Broken

结果本身不可用，例如文件损坏、引用文件缺失、数据库关系断裂。

不要把 `stale` 与 `invalid` 混用。

---

## 3. 基本规则

1. 派生结果必须能回答：“我是基于哪些上游版本产生的？”
2. 上游 revision 变化后，系统必须检查受影响的下游。
3. 下游旧结果默认标记 `stale`，不自动删除。
4. Stale 结果不得被新的正式生产流程默认为 Final 输入。
5. UI 必须显示 stale 原因和需要重新执行的步骤。
6. 人工可以查看旧结果用于对比，但“人工强制继续使用”必须是显式决策。

---

## 4. 修改类型

不是所有修改都应该触发失效。

### Display-only Change

只改变显示，不改变业务语义。

示例：

```text
Character 显示名：人物A → 男主
Project 显示名称修改
UI 排序偏好
```

通常不增加语义 revision，不触发下游 stale。

### Semantic Change

改变下游真实输入。

示例：

```text
Shot final_start/final_end 修改
Dialogue final_text 修改
Dialogue final_character_id 修改
Shot Scene 归属修改
Character→Actor Mapping 修改
Bible 结构字段修改
Shot Spec action / camera / duration 修改
Reference Asset 改变
```

必须增加对应 revision，并执行失效传播。

---

## 5. 推荐失效矩阵

以下是 V1 推荐基线；具体 Feature Contract 可以更精细，但不能放宽到“完全不追踪”。

| 上游变化 | 可能 stale 的下游 |
|---|---|
| Final Shot 边界 | Character Analysis、Scene Candidate、Shot Spec、Generation、QC、Dialogue/Active Speaker 映射（按影响范围） |
| Final Character 合并/拆分 | Speaker Mapping、Casting、Character Bible、Shot Spec、Generation、QC |
| Final Dialogue 文本 | Shot Spec、TTS、Dialogue Fit、Lip Sync、Final Render |
| Dialogue 说话角色 | Shot Spec、Voice binding、TTS、Lip Sync |
| Final Scene 归属/结构 | Scene Bible、Shot Spec、Generation、QC |
| Character→Actor Mapping | Character Bible、Shot Spec、Generation、QC |
| Character Bible | Shot Spec、Generation、Identity QC |
| Scene Bible | Shot Spec、Generation、Scene QC |
| Shot Spec | Generation、QC、TTS/LipSync（若涉及 Dialogue/Duration） |
| Selected Generation | Lip Sync、Final Render、Final QC |
| Final Voice | Dialogue Fit、Lip Sync、Final Render |
| Lip Sync Selected Version | Final Render、Final QC |

---

## 6. 不允许自动删除旧结果

当下游 stale 时：

```text
保留旧记录
保留旧媒体
记录 stale_reason
记录 stale_at
```

禁止：

```text
上游一改
→ 删除所有旧 Generation
```

历史结果对于：

- 对比
- 回退
- 成本追踪
- 算法调试
- 人工误修改恢复

都有价值。

---

## 7. 下游正式读取规则

正式生产步骤默认只能读取：

```text
not stale
+ valid
+ approved/locked/selected（如适用）
```

如果只有 stale 数据存在：

- UI 显示需要重新计算；
- 后端不得静默继续使用；
- 若支持人工强制使用，必须记录 override reason。

---

## 8. Revision 规则

推荐：

```text
revision: integer, 从 1 开始
```

revision 只增不减。

不要把数据库 `updated_at` 当 revision，因为：

- display-only 修改也会改 updated_at；
- 时间精度不能表达明确业务版本；
- 无法稳定建立依赖快照。

### Revision 增长时机

只有真正持久化成功后才增加 revision。

失败事务不能留下 revision 跳跃造成不一致。

---

## 9. Generation 必须保存输入快照

Generation 至少应能追溯：

```text
shot_id
shot_revision
shot_spec_id
shot_spec_revision
character_bible revisions
scene_bible revision
reference asset IDs/hashes
provider
model
provider/model version（能获得时）
prompt compiler version
```

即使上游以后修改，也能知道当时为什么生成了这个结果。

---

## 10. QC 必须绑定具体 Generation

QC 不能只绑定 Shot。

必须明确：

```text
qc_result → generation_id/version
```

Generation stale 后，其 QC 结果历史仍保留，但不能用于证明新 Generation 或新 Shot Spec 已通过。

---

## 11. UI 规则

建议使用：

```text
✓ 当前
⚠ 已过期
✕ 损坏/不可用
```

Stale 提示必须包含：

- 哪个上游发生变化；
- 变化发生时间；
- 哪些结果受影响；
- 推荐重新执行哪个 Feature。

示例：

```text
⚠ SHOT_023 的人物分析已过期
原因：Shot 边界 revision 3 → 4
建议：重新执行 Feature 06 人物识别（仅当前 Shot）
```

---

## 12. Feature Contract 必须回答

如果当前 Feature 产生派生数据，必须写清：

1. 依赖哪些上游对象？
2. 记录哪些上游 revision？
3. 哪些上游变化会使本结果 stale？
4. stale 后 UI 怎么提示？
5. 如何重新计算？
6. 是否支持人工 override？
7. stale 数据是否允许导出/生成？

---

## 13. Stable Gate

涉及派生数据的 Feature Freeze 前必须确认：

- [ ] Dependency Snapshot 已定义
- [ ] Semantic revision 已定义
- [ ] Stale 状态已定义
- [ ] Invalidation 触发条件已定义
- [ ] Stale 不会被静默当作 Final 输入
- [ ] 重新计算路径已测试
- [ ] 历史结果不会自动删除
