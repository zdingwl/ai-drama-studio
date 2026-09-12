# P14 声线目录与 Provider Voice ID 隔离整改

> 日期：2026-09-12  
> 状态：P14 工程合同补充整改；优先级高于 `docs/32` 中任何可能被理解为“由普通用户直接填写 Provider voice id”的实现方式。`TTS / TIMING` 仍为 `PLANNED`，真实 Provider 与人工验收尚未完成。

## 1. 问题

P14 初版工程 UI 暴露了 `Provider voice id` 文本输入框，但 OpenAI-compatible `/audio/speech` 适配器没有统一的跨 Provider voice discovery API。让普通用户猜或手填底层 Provider voice id 不属于可验收产品合同。

## 2. 正式整改

声线选择链固定为：

```text
server/runtime Voice Catalog
→ public voice_key + display_name + locale/tags
→ user explicit selection
→ Target Voice Binding
→ server-side voice_key -> provider_voice_id mapping
→ Provider /audio/speech
```

普通产品 UI 不显示或要求填写 `provider_voice_id`。`provider_voice_id` 只属于服务端运行时配置与 Provider adapter，不能作为用户输入事实。

当前 wire schema 中已有字段名 `voice_id` 为兼容 P14 未验收的工程实现暂不迁移数据库；从本整改起它承载的是稳定的 **application voice key**，不是底层 Provider voice id。正式 P14 PASS 前如需 schema v2，可再完成字段名清理。

## 3. 默认 Voice Catalog

2026-09-12 按 OpenAI 官方 Audio API `POST /v1/audio/speech` 文档核对，当前支持的 built-in voice 名称包括：

```text
alloy
ash
ballad
coral
echo
fable
onyx
nova
sage
shimmer
verse
marin
cedar
```

官方 API Reference：`https://platform.openai.com/docs/api-reference/audio/voice-consent-list?lang=curl`。

这些公开名称现在直接作为仓库默认 Voice Catalog：`voice_key == provider_voice_id`，display name 使用对应首字母大写名称。它们不携带虚构的性别、年龄、情绪或 locale 标签；普通 UI 仅展示公开声线名称和 `openai / built-in` 标签。

默认目录的存在只代表**已知公开声线 ID 可供选择**，不代表当前运行时已经成功连接真实 Provider。真实 TTS 调用仍必须由配置的 `AI_DRAMA_P14_TTS_BASE_URL / MODEL / API_KEY` 完成，Provider 返回错误时继续 fail closed。

若实际使用的 OpenAI-compatible Provider 不接受上述 voice 名称，必须用：

```text
AI_DRAMA_P14_TTS_VOICE_CATALOG_JSON
```

整体覆盖成该 Provider 的真实 voice id 映射。

## 4. 只读 Voice Catalog API

普通产品 UI 通过：

```text
GET /api/v3/projects/{project_id}/target-audio/voices
```

读取 public catalog。响应只包含：

```text
voice_key
display_name
locale
tags
```

不得返回 `provider_voice_id`、API key 或其他 Provider secret。该 GET 只读，不创建 Task / ProviderJob / Artifact。

## 5. 绑定规则不变

- 已知 `target_character_id`：显式 CHARACTER binding；
- 未知人物对白：显式 UTTERANCE binding；
- 不得按人物姓名、性别、年龄、剧情或 narrator 默认值自动猜声线；
- 只展示实际出现在 CURRENT TARGET_SCRIPT 中的说话人物，不要求给未说话的 Target Bible 人物绑定声音。

## 6. Provider 边界

Provider adapter 在真正调用 `/audio/speech` 前才把 application voice key 解析为 provider-specific voice id。ProviderJob 业务 payload 只记录 application voice key；浏览器不知道底层 Provider id。

真实音频、服务端 `ffprobe` duration、候选人工听审、Timing overflow 规则继续沿用 `docs/32`，本整改不改变 P14 的 Artifact Graph 或验收门。
