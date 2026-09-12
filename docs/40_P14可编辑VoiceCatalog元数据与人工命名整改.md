# P14 可编辑 Voice Catalog 元数据与人工命名整改

> 日期：2026-09-12  
> 状态：P14 产品交互 / 本地声线库整改；本文补充并优先于 `docs/39_P14参考声线试听与可读选角整改.md` 中“未来可人工维护元数据”的待办描述。  
> 本整改不改变阶段验收状态：`TTS = PLANNED / TIMING = PLANNED / P14 PASS = NO`。

## 1. 问题

IndexTTS-2.5 官方 demo Reference Audio 只有 `voice_01.wav`、`voice_02.wav` 等技术编号。即使 P14 已提供真实试听，如果每次进入项目仍只看到编号，用户仍需重复试听和记忆，无法形成可复用的角色选角工作流。

系统不得把主观推断冒充官方事实，因此也不能自动把编号改成“青年女声 / 沉稳男声”等名字。

## 2. 新增本地人工元数据层

正式结构调整为：

```text
IndexTTS Voice Catalog
├─ voice_key                 技术稳定 ID
├─ Reference Audio           真实音色来源
├─ default_display_name      上游 / 默认目录名
└─ Human Voice Metadata      本机人工标注
   ├─ display_name
   ├─ gender
   ├─ age_range
   ├─ style_tags
   └─ notes
```

`Human Voice Metadata` 是人工试听后的本地事实，不是 IndexTTS 官方元数据，也不是模型推断。

数据库表：

```text
indextts_voice_metadata
```

以 `voice_key` 为主键，并保存当前 Reference Audio source fingerprint。若同一 `voice_key` 将来指向不同 Reference Audio，旧人工元数据不得静默套用；公共目录回退到默认名称并提示重新试听标注。

## 3. 元数据范围

当前人工可维护：

```text
display_name
gender = UNKNOWN / FEMALE / MALE / NEUTRAL
age_range = UNKNOWN / CHILD / TEEN / YOUNG_ADULT / ADULT / MATURE / SENIOR
style_tags <= 8
notes
```

约束：

- `display_name` 是用户自己的可读名称；
- `gender / age_range / style_tags` 只有人工明确选择后才成为事实；
- 未标注时继续显示 UNKNOWN / 未标注；
- 不根据音高、文件名、角色性别或模型输出自动填写；
- 可随时恢复“未标注”状态。

## 4. 作用域

人工声线元数据属于本机 Voice Catalog，不属于单一 Project：

```text
项目 A 试听并把 voice_01 标为“清亮青年女声”
→ 保存本机 Voice Catalog
→ 项目 B / C 再打开同一 voice_key
→ 直接复用该人工名称和标签
```

这是有意设计：Reference Voice 是可复用制作资源，不应该每个项目重复命名。

目标配音的正式 binding 仍保存：

```text
voice_key + 当次可读 voice_label
```

底层 TTS 仍只依赖 `voice_key -> Reference Audio`，人工标签不会改变 Provider 音频来源。

## 5. API

公共目录：

```text
GET /api/v3/projects/{project_id}/target-audio/voices
```

每个 voice option 额外返回：

```text
default_display_name
display_name
gender
age_range
style_tags
notes
metadata_source = CATALOG | USER
metadata_stale
metadata_updated_at
```

不返回原始 `reference_audio_url`。

人工保存：

```text
PUT /api/v3/projects/{project_id}/target-audio/voices/{voice_key}/metadata
```

恢复未标注：

```text
DELETE /api/v3/projects/{project_id}/target-audio/voices/{voice_key}/metadata
```

试听 API 保持：

```text
GET /api/v3/projects/{project_id}/target-audio/voices/{voice_key}/preview
```

以上元数据读写不创建 Task、ProviderJob、Candidate 或 Artifact，也不代表 TTS 阶段通过。

## 6. UI

P14 声线区新增“声线库”管理视图。每张卡片固定展示：

```text
可读名称
人工标注状态
技术 voice_key / 原始目录名
人工性别 / 年龄感 / 风格
备注
真实 Reference Audio 播放器
编辑名称 / 标签
```

角色选择卡优先显示人工可读名称和人工标签。

推荐工作流：

```text
先试听全部 Reference Voice
→ 人工命名 / 标注
→ 再给角色分配
→ 生成 IndexTTS-2.5 配音候选
```

## 7. 当前状态

本整改解决“声线有声音但没有可记忆名称”的产品问题，不等于配音质量通过。

继续保持：

```text
P13 = PASS
TARGET_ASSETS = AVAILABLE
TTS = PLANNED
TIMING = PLANNED
P14 PASS = NO
```

P14 仍需真实目标配音生成、逐句人工听审、正式 TARGET_AUDIO、TIMING_PLAN 与 overflow 处理，并由用户明确确认后才能 PASS。
