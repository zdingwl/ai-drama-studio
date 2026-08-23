# AI Drama Studio — Dependency / Revision / Invalidation Rules

## 1. 目的

解决核心问题：

> 上游 Final/Approved/Locked 数据已经被下游使用后，如果上游再次发生语义修改，旧下游结果还能不能继续当作当前结果？

原则：不能静默继续使用。

---

## 2. 核心状态

### Revision

重要业务对象在“影响下游语义”的内容变化时递增 revision。

### Dependency Snapshot

派生结果创建时保存它依赖的上游 revision/version/hash。

### Fresh

依赖快照与当前上游一致。

### Stale

结果本身仍然存在，但上游语义已经变化，因此不能默认作为当前正式输入。

### Invalid / Broken

结果本身损坏、缺文件、关系断裂等。

`stale` 不等于 `failed`，也不等于 `invalid`。

---

## 3. 建议需要 Revision 的对象

至少考虑：

- Final Shot；
- Final Character 结构；
- Final Source Dialogue；
- Final Scene；
- Character→Actor Mapping；
- Character Bible；
- Scene Bible；
- Target Dialogue；
- Target Dialogue Timing Constraint；
- Shot Specification；
- Reference Asset Set；
- Selected Generation / Final Voice / Selected LipSync；
- Final Audio Mix；
- Subtitle Track。

Revision 只在语义变化时递增，display-only 修改不应该制造无意义 stale。

---

## 4. Display-only vs Semantic Change

### Display-only

通常不触发下游 stale：

```text
Project 显示名称
Character 显示名（业务身份不变）
UI 排序/展开状态
纯备注
```

### Semantic Change

必须评估/触发下游 stale：

```text
Shot final_start/end
Character 合并/拆分
Source Dialogue 文本/说话人/时间
Scene 归属
Actor Mapping
Bible 结构字段
Target Dialogue 文本/说话人
Timing Constraint
Shot Spec 动作/镜头/时长/参考
Selected Generation
Final Voice
Selected LipSync
Audio Mix 输入
Subtitle Cue 时间/文本
```

---

## 5. V1 失效矩阵

| 上游变化 | 默认需要评估/标记 stale 的下游 |
|---|---|
| Final Shot 边界 | Character Analysis、Speaker/Active-Speaker Mapping、Scene Candidate、Target Timing、Shot Spec、Generation、QC、TTS Fit、LipSync、Subtitle、Render |
| Final Character 合并/拆分 | Speaker Mapping、Casting、Character Bible、Localization Context、Shot Spec、Generation、QC |
| Final Source Dialogue 文本 | Localization Draft、Approved Target Dialogue（如来源变化）、Timing、Shot Spec、TTS、Subtitle |
| Final Source Dialogue 说话角色 | Localization、Voice Binding、Target Dialogue、Shot Spec、TTS、LipSync |
| Final Scene 归属/结构 | Scene Bible、Localization Context（如场景影响表达）、Shot Spec、Generation、Scene QC |
| Character→Actor Mapping | Character Bible、Shot Spec、Generation、Identity QC |
| Character Bible | Localization Context、Shot Spec、Generation、Identity QC、TTS style（如使用） |
| Scene Bible | Localization Context（如使用）、Shot Spec、Generation、Scene QC |
| Approved Target Dialogue | Target Timing、Shot Spec、TTS、Dialogue Fit、LipSync、Subtitle、Final Audio、Render |
| Target Dialogue Timing Constraint | Shot Spec、Generation（如 duration/action pacing 受影响）、Dialogue Fit |
| Approved Shot Spec | Generation、QC、TTS/LipSync（若对白/时长相关）、Subtitle timing、Render |
| Selected Generation | LipSync、Final Audio（若用视频原生音频）、Subtitle/Render timing、Final QC |
| Final Voice | Dialogue Fit、LipSync、Final Audio、Subtitle timing（如按真实语音调整）、Render |
| Selected LipSync | Render、Final QC |
| Final Audio Mix | Render、Final QC |
| Subtitle Track | Render（烧录时）、Export、Final QC |

具体 Feature 可以缩小影响范围，但必须说明原因；不能默认“不追踪”。

---

## 6. 派生结果必须记录 Dependency Snapshot

例如 Generation 至少应追溯：

```text
shot_id + shot_revision
shot_spec_id + shot_spec_revision
character_bible revisions
scene_bible revision
target_dialogue_revision
timing_constraint_revision
reference asset ids/hashes
provider/model/version
prompt compiler version
```

TTS 至少应追溯：

```text
target_dialogue_revision
character/voice binding revision
provider/model/version
```

Subtitle Track 至少应追溯：

```text
target_dialogue_revision
final shot/timeline revisions
final voice timing revision（如使用）
```

Final Render 至少应追溯：

```text
selected shot media versions
final audio mix revision
subtitle track revision
render settings revision
```

---

## 7. Stale 结果不能自动删除

上游变化后：

```text
保留旧记录/媒体
记录 stale_at
记录 stale_reason
记录 upstream old/new revision
```

原因：

- 对比；
- 回退；
- 成本追踪；
- 调试；
- 人工误操作恢复。

---

## 8. 正式生产读取规则

默认只允许读取：

```text
fresh
+ valid
+ approved/locked/selected（按对象要求）
```

如果只有 stale 数据：

- UI 明确提示；
- 后端禁止静默继续；
- 给出推荐重新执行 Feature；
- 若允许人工强制继续，必须记录 override reason。

---

## 9. Revision 规则

推荐：

```text
revision: integer，1 开始，只增不减
```

不能用 `updated_at` 代替 semantic revision。

revision 只有在事务持久化成功后增加。

重要人工资产（Bible、Target Dialogue、Shot Spec 等）在对应 Feature 实现时应保存 Revision Snapshot/历史内容，而不只是覆盖当前值。

---

## 10. QC 必须绑定具体生成版本

QC 必须明确：

```text
qc_result → generation_id/version
```

Generation stale 后，旧 QC 作为历史保留，但不能证明新 Generation 已通过。

Episode QC 同样绑定具体 Master Candidate/Render Version。

---

## 11. UI 提示

建议：

```text
✓ 当前
⚠ 已过期
✕ 损坏/不可用
```

Stale 提示至少说明：

- 哪个上游改变；
- revision old → new；
- 哪些结果受影响；
- 推荐重跑哪个 Feature；
- 是否允许人工 override。

---

## 12. Feature Contract 必须回答

如果产生派生数据：

1. 依赖哪些上游对象/revision？
2. 保存什么 Dependency Snapshot？
3. 哪些变化会 stale？
4. stale 后 UI/后端怎么处理？
5. 如何重新计算？
6. 是否允许 override？
7. stale 是否禁止 Export/Generate/Render？

---

## 13. Stable Gate

```text
[ ] Semantic revision 已定义
[ ] Dependency Snapshot 已定义
[ ] Stale 状态/原因已定义
[ ] Invalidation 触发条件已定义
[ ] Stale 不会静默进入正式生产
[ ] Recompute/Recovery 已测试
[ ] 历史结果不会自动删除
[ ] 对新 Target Dialogue / Audio / Subtitle 链路的影响已覆盖（如适用）
```
