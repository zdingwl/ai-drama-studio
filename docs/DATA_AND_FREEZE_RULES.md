# AI Drama Studio — Data & Freeze Rules

本文件定义项目中的数据边界、版本、冻结、兼容和下游读取原则。

## 1. 总原则

项目采用：

```text
逐 Feature 开发
+ Contract 冻结
+ Revision / Dependency 追踪
+ 用户最终验收
```

每个 Feature 必须明确：

- Input / Output；
- Reads / Writes / Must NOT Modify；
- API；
- DB；
- File；
- Revision / Stale；
- Status / Error Codes；
- Test / Regression；
- Freeze Snapshot。

下游只依赖已冻结 Contract，不依赖上游内部实现。

---

## 2. AI 原始结果与人工最终结果分离

只要 AI 结果允许人工修正，就不能覆盖原始证据。

示例：

```text
Shot:
detected_start_us / detected_end_us
final_start_us / final_end_us

Dialogue:
asr_text
final_source_text
localized_draft
approved_target_text

QC:
ai_qc_status / ai_qc_scores
human_decision / human_reason
```

目的：可追溯、可回退、可比较、可重新计算。

---

## 3. 源对白与目标对白是不同 Contract

正式生产链：

```text
ASR Source Dialogue
→ Final Source Dialogue
→ Localization Draft
→ Approved Target Dialogue
→ Target Dialogue Timing Constraint
→ Shot Spec / TTS / Subtitle
```

禁止让下游直接把源对白当目标语言成品。

TTS、字幕和正式 Shot Spec 必须使用 `Approved Target Dialogue`。

---

## 4. Stable / Frozen 权限

Agent 只能推进到：

```text
READY_FOR_REVIEW
```

只有用户明确确认验收通过后，Feature 才能：

```text
STABLE / FROZEN
```

---

## 5. Stable 后默认冻结

至少：

```text
Input Contract
Output Contract
API Contract
核心 DB fields
ID rules
File/Workspace rules
Status enum
Error codes
Project Format impact（如适用）
```

下游禁止：

- 修改同名字段语义；
- 绕过 Final/Approved/Locked 数据；
- 复制一套上游算法；
- 破坏已有 API；
- 静默删除历史版本。

---

## 6. 必须修改 Frozen Contract 时

优先顺序：

```text
Additive Change
→ Adapter
→ V2 Contract
→ Migration
```

破坏兼容性前必须：

- 影响分析；
- 数据/API/文件迁移方案；
- 回归范围；
- 用户明确确认。

禁止偷偷改变 V1。

---

## 7. Revision / Dependency / Stale

重要对象语义变化后必须增加 revision，并对派生结果做失效判断。

派生结果必须记录 Dependency Snapshot。

例如 Generation 至少可追溯：

```text
shot_revision
shot_spec_revision
character_bible_revision
scene_bible_revision
target_dialogue_revision
reference asset ids/hashes
provider/model/version
prompt compiler version
```

上游变化后：

```text
旧结果保留
→ stale
→ 不再作为默认正式输入
```

详细规则见 `docs/DEPENDENCY_AND_INVALIDATION_RULES.md`。

---

## 8. Shot 是核心生产单元

单 Shot 应可独立：

- 修正；
- 重新分析；
- 修改 Dialogue/Scene/Spec；
- 更换 Reference/Model/Provider；
- 重新生成；
- QC；
- TTS；
- Lip Sync；
- 人工替换；
- 选择 Final。

一个 Shot 失败不能要求整集重跑。

---

## 9. 生成型结果必须版本化

必须版本化：

- Video Generation；
- TTS；
- Lip Sync。

对应 Feature 实现时，Character Bible / Scene Bible / Shot Spec 也应保存可恢复的 Revision Snapshot，而不只是覆盖当前值。

禁止“重新生成 → 覆盖 old file”。

---

## 10. Final/Approved/Locked 是下游正式输入

示例：

- Character 分析读取 Final Shot；
- Casting 读取 Final Character；
- Character Bible 读取人工确认 Actor Mapping；
- Localization 读取 Final Source Dialogue；
- Shot Spec 读取 Locked Bible + Approved Target Dialogue；
- Video Generation 读取 Approved Shot Spec；
- Render 读取 Selected/Final Shot Media；
- Subtitle 读取 Approved Target Dialogue + Final Production Timeline。

Stale 数据不得静默进入正式生产。

---

## 11. Project Format Version

Feature 01 必须从第一版保存：

```text
project_format_version
```

它用于描述 Workspace、项目元数据、持久化 JSON/Bible/Asset 结构等项目级格式。

它不等同于 Alembic `schema_revision`。

项目元信息建议至少可追溯：

```text
project_format_version
app_version
schema_revision
created_at
```

---

## 12. 核心对象建议

```text
Project
└── Episode
    ├── Character
    │   ├── Actor Mapping
    │   └── Character Bible Revisions
    ├── Scene
    │   └── Scene Bible Revisions
    ├── Source Dialogue
    │   └── Target Dialogue Revisions
    ├── Shot
    │   ├── Character Relations
    │   ├── Shot Specification Revisions
    │   ├── Generation[]
    │   │   └── QC Result
    │   ├── Voice[]
    │   └── LipSync[]
    ├── Final Audio Mix
    ├── Subtitle Track
    └── Render / Export
```

---

## 13. ID 稳定

推荐稳定业务 ID：

```text
PROJECT_*
EPISODE_*
SCENE_*
SHOT_*
CHARACTER_*
ACTOR_*
DIALOGUE_*
GENERATION_*
QC_*
VOICE_*
LIPSYNC_*
RENDER_*
```

业务对象 ID 不因改名、换模型、换文件名或重新生成而改变。

版本/Revision 用独立字段/对象表达。

---

## 14. 媒体文件与 SQLite 分离

SQLite 保存：

- IDs；
- metadata；
- relative paths；
- state；
- relationships；
- structured JSON；
- revision/dependency info。

视频/图片/音频保存在 Workspace。

媒体写入必须遵守：`docs/DATA_RECOVERY_AND_MIGRATION_RULES.md`。

---

## 15. Source Video 原则上只读

原片进入项目后默认：

- 不覆盖；
- 不原地转码；
- 不由缓存清理删除；
- 不因重跑 Feature 自动替换。

显式替换 Source 属于重要业务动作，必须触发 revision/invalidation。

---

## 16. Bible / Shot Spec 必须结构化

不能只存 Markdown 自然语言。

结构化 Schema 才能支持：

- 人工精确编辑；
- Prompt Compiler；
- QC；
- Provider 切换；
- Revision；
- Migration。

---

## 17. Shot Specification 必须模型无关

Shot Spec 只描述真实镜头需求：

- Characters；
- Scene；
- Framing；
- Camera；
- Action；
- Emotion；
- Approved Target Dialogue；
- Duration；
- Wardrobe；
- Continuity；
- References。

Provider 私有参数由 Prompt Compiler / Adapter 负责。

---

## 18. Provider Call 必须可追溯

建议记录：

```text
provider
model
api/model version
task_type
project_id
shot_id
request_id
provider_task_id
request_time
response_time
cost/error/metadata
```

计费异步任务遵守 `docs/PROVIDER_JOB_RULES.md`。

---

## 19. 人工决策必须可追溯

重要人工操作至少考虑：

```text
human_decision
human_reason
reviewed_at
```

本地单用户不需要复杂 RBAC，但决策历史仍然需要保留。

---

## 20. Freeze Gate

用户验收前 Agent 最多为 `READY_FOR_REVIEW`。

用户验收通过后 Freeze 前确认：

```text
[ ] Input/Output/API/DB Contract
[ ] IDs / Paths / Status / Errors
[ ] Revision/Invalidation
[ ] P0 Reviews
[ ] Code/DB comments
[ ] Current Feature tests
[ ] Affected Stable regression
[ ] Real sample test
[ ] Feature documentation
[ ] Session Handoff
[ ] PROJECT_STATE
[ ] User acceptance reference
```
