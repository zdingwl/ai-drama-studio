# AI Drama Studio — Data & Freeze Rules

本文件定义项目中最重要的数据边界、版本策略、冻结策略和兼容规则。

---

## 1. 总原则

项目采用“逐 Feature 开发 + Contract 冻结”模式。

每一个 Feature 都必须明确：

- 输入对象
- 输出对象
- 读取哪些数据
- 允许修改哪些数据
- 禁止修改哪些数据
- API Contract
- DB Contract
- 文件输出 Contract

下游 Feature 只能依赖已冻结的上游 Contract，不应该依赖上游内部实现。

---

## 2. AI 原始结果与人工最终结果必须分离

任何 AI 结果只要允许人工修正，就不能直接被人工覆盖。

推荐模式：

```text
AI Result
Final Result
```

例如 Shot：

```text
detected_start
detected_end
final_start
final_end
```

例如 Character：

```text
ai_cluster_id
final_character_id
```

例如 Dialogue：

```text
asr_text
final_text
speaker_candidate
final_character_id
```

例如 QC：

```text
ai_qc_status
ai_qc_scores
human_decision
human_reason
```

目的：

- 可追溯
- 可比较 AI 与人工
- 可重新跑算法
- 可形成后续优化数据
- 防止后续逻辑失去原始证据

---

## 3. Stable Feature 冻结规则

一个 Feature 只有通过真实素材和人工验收后才能进入 Stable。

Stable 后默认冻结：

```text
Input Contract
Output Contract
API Contract
核心 DB fields
核心文件路径规范
ID 规则
状态枚举
```

下游禁止：

- 为了方便直接修改上游 Stable 表字段含义
- 绕过 Final 数据直接读取 AI 原始数据
- 重写上游流程
- 在下游代码里复制上游算法
- 破坏已有 API 的请求/响应结构

---

## 4. 必须改 Stable Contract 时怎么办

优先级：

### 4.1 Additive Change

优先新增字段，不破坏旧字段。

### 4.2 Adapter

通过 Adapter 兼容新旧数据。

### 4.3 V2 Contract

破坏兼容性时明确：

```text
ShotContractV1
ShotContractV2
```

并提供 migration。

禁止偷偷改变同名字段语义。

---

## 5. Shot 是核心生产单元

任何 Shot 级问题必须支持只处理当前 Shot。

单 Shot 必须能独立：

- 重新分析
- 修改 Shot Spec
- 生成
- 切换 Provider
- 切换 Model
- 替换 Reference
- QC
- 重新 TTS
- 重新 Lip Sync
- 上传手工替换视频

一个 Shot 失败不能触发整集重跑。

---

## 6. Generation 必须版本化

禁止：

```text
生成失败
→ 覆盖 old.mp4
```

必须：

```text
SHOT_023
├── v001.mp4
├── v002.mp4
├── v003.mp4
└── v004.mp4
```

Shot 保存：

```text
selected_generation_id
```

Generation 至少记录：

```text
id
shot_id
version
provider
model
provider_task_id
prompt
references
duration
resolution
seed
output_path
status
cost
created_at
metadata
```

---

## 7. TTS 与 Lip Sync 同样版本化

TTS：

```text
DIALOGUE_001
├ VOICE_V001
├ VOICE_V002
└ VOICE_V003
```

Lip Sync：

```text
SHOT_023
├ LIP_V001
├ LIP_V002
└ LIP_V003
```

禁止覆盖用户已经选中的历史版本。

---

## 8. 核心对象

推荐核心关系：

```text
Project
└── Episode
    ├── Character
    │   ├── Actor Mapping
    │   └── Character Bible
    │
    ├── Scene
    │   ├── Scene Bible
    │   └── Shot
    │       ├── Character Relations
    │       ├── Dialogue
    │       ├── Shot Specification
    │       ├── Generation[]
    │       │   └── QC Result
    │       └── Selected Generation
    │
    └── Render / Export
```

---

## 9. ID 必须稳定

推荐：

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

业务对象的 ID 不因文件重命名、模型切换、重新生成而变化。

---

## 10. 状态与历史分离

对象可以有当前状态，但历史版本必须独立保存。

例如 Shot：

```text
analyzed
needs_review
approved
ready_generate
generating
generated
qc_pass
qc_review
failed
final
```

Generation 自己有：

```text
pending
running
completed
failed
cancelled
```

不要混用 Shot 状态和 Generation 状态。

---

## 11. 媒体文件与数据库分离

SQLite 不保存视频、图片、音频 Blob。

数据库保存：

- ID
- metadata
- relative path
- structured JSON
- state
- timestamps
- relationships

媒体保存在 Workspace。

示例：

```text
workspace/
└── project_001/
    ├── source/
    ├── proxy/
    ├── audio/
    ├── frames/
    ├── shots/
    ├── characters/
    ├── actors/
    ├── scenes/
    ├── generations/
    ├── voice/
    ├── lipsync/
    ├── cache/
    └── exports/
```

数据库优先存相对路径，避免整个项目移动位置后失效。

---

## 12. Source Video 原则上只读

原片进入项目后：

- 不覆盖
- 不重新编码覆盖源文件
- 不因后续操作删除

后续使用 Proxy、WAV、Frame、Shot Cache。

---

## 13. Final 数据是下游唯一业务输入

例如：

自动拉片输出 AI Shot 后，Feature 05 产生 Final Shot。

后面的 Character、Dialogue、Scene：

```text
只能读取 Final Shot
```

不能为了方便再自己从原片重新切一份 Shot。

同理：

- Final Character 是下游 Character 输入
- Final Dialogue 是后续 TTS / Shot Spec 输入
- Final Scene 是 Scene Bible 输入
- Locked Bible 是视频生成输入
- Approved Shot Spec 是 Generation 输入
- Selected Generation 是 Render 输入

---

## 14. Bible 必须结构化

Character Bible / Scene Bible 不能只保存自然语言 Markdown。

必须有稳定 JSON Schema。

自然语言描述只能作为辅助字段。

原因：

- Provider 可替换
- Prompt Compiler 可读取
- QC 可读取
- 人工可以精确修改某个字段
- 后续可做迁移和版本管理

---

## 15. Shot Specification 必须模型无关

Shot Spec 只描述真实镜头需求：

- Characters
- Scene
- Framing
- Camera
- Action
- Emotion
- Dialogue
- Duration
- Wardrobe
- Continuity
- References

禁止在 Shot Spec 中写死某一个视频模型专属参数。

模型专属参数由 Prompt Compiler / Provider Adapter 负责。

---

## 16. Provider Call 必须可追溯

建议记录：

```text
provider
model
task_type
project_id
shot_id
request_time
response_time
provider_task_id
cost
success
error_code
error_message
metadata
```

目的：

- 查失败原因
- 统计成本
- 比较模型
- 未来优化 Router

---

## 17. 人工决策必须记录

重要人工操作不要只改状态。

应记录：

```text
human_decision
human_reason
reviewed_at
```

本地单用户可以不做复杂用户体系，但决策历史仍然有价值。

---

## 18. 每个 Feature 的 Freeze 清单

Feature 验收时至少确认：

```text
[ ] Input 已冻结
[ ] Output 已冻结
[ ] API 已冻结
[ ] 核心 DB fields 已冻结
[ ] ID 规则已冻结
[ ] 文件路径已冻结
[ ] 状态枚举已冻结
[ ] 错误码已冻结
[ ] 真实素材验收记录已保存
```

只有全部完成才标记 Stable。
