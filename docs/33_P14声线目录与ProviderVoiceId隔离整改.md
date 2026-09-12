# P14 声线目录与 Provider Voice ID 隔离整改

> 日期：2026-09-12  
> 状态：P14 工程合同补充整改；优先级高于 `docs/32` 中任何可能被理解为“由普通用户直接填写 Provider voice id”的实现方式。`TTS / TIMING` 仍为 `PLANNED`，真实 Provider 与人工验收尚未完成。

## 1. 问题

P14 初版工程 UI 暴露了 `Provider voice id` 文本输入框，但当前 OpenAI-compatible `/audio/speech` 适配器没有通用的 voice discovery API，也没有为普通用户提供任何可信的 ID 来源。让用户猜或手填底层 Provider voice id 不属于可验收产品合同。

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

普通产品 UI 不再显示或要求填写 `provider_voice_id`。`provider_voice_id` 只属于服务端运行时配置与 Provider adapter，不能作为用户输入事实。

当前 wire schema 中已有字段名 `voice_id` 为兼容 P14 未验收的工程实现暂不迁移数据库；从本整改起它承载的是稳定的 **application voice key**，不是底层 Provider voice id。正式 P14 PASS 前如需 schema v2，可再完成字段名清理。

## 3. Voice Catalog 来源

当前通用 OpenAI-compatible TTS adapter 不假设 Provider 一定提供列出 voices 的标准接口，因此 Voice Catalog 由服务端运行时显式配置：

```text
AI_DRAMA_P14_TTS_VOICE_CATALOG_JSON
```

每个条目至少包含：

```json
{
  "voice_key": "warm_female_01",
  "display_name": "Warm Female 01",
  "provider_voice_id": "provider-specific-id",
  "locale": "en-US",
  "tags": ["female", "warm"]
}
```

其中只有 `voice_key / display_name / locale / tags` 可以下发前端。`provider_voice_id` 不进入普通用户 UI。

Voice Catalog 默认必须为空，禁止为了让界面可点而伪造默认 voice。目录为空时页面明确显示“尚未配置可用声线”，并阻断生成。

## 4. 绑定规则不变

- 已知 `target_character_id`：显式 CHARACTER binding；
- 未知人物对白：显式 UTTERANCE binding；
- 不得按人物姓名、性别、年龄、剧情或 narrator 默认值自动猜声线；
- 只展示实际出现在 CURRENT TARGET_SCRIPT 中的说话人物，不要求给未说话的 Target Bible 人物绑定声音。

## 5. Provider 边界

Provider adapter 在真正调用 `/audio/speech` 前才把 application voice key 解析为 provider-specific voice id。ProviderJob 业务 payload 只需要记录 application voice key；不得要求浏览器知道底层 Provider id。

真实音频、服务端 `ffprobe` duration、候选人工听审、Timing overflow 规则继续沿用 `docs/32`，本整改不改变 P14 的 Artifact Graph 或验收门。
