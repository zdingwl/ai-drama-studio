# Replica Target Audio

## 目标

把 CURRENT `TARGET_SCRIPT` 的 `final_target_dialogue` 与 CURRENT `TARGET_BIBLE` 的目标人物身份绑定到显式目标声线，并生成可听审、可追溯的真实对白媒体。

## 硬输入

- CURRENT `TARGET_SCRIPT`
- CURRENT `TARGET_BIBLE`
- 用户显式提交的 voice binding

`TARGET_ASSETS` 不是硬输入。视觉资产 revision 不应无依据地使目标配音 STALE。

## Voice binding

已确定 `target_character_id` 的对白允许 CHARACTER scope binding；`target_character_id = null` 的对白必须使用 UTTERANCE scope binding。不得静默使用默认 narrator，不得根据姓名、性别、年龄或剧情猜 voice。

## Provider 与媒体

每条付费/外部 TTS 调用必须先持久化 `ProviderJob`。Provider 只返回真实音频媒体，不拥有 Artifact id、revision、lineage 或正式时长裁决权。

音频先写入 Production storage，再由服务端 `ffprobe` 探测。`actual_speech_duration_us` 只认服务端对已持久化媒体的探测结果；Provider 返回 duration 不能替代该事实。

每条 clip 至少保存：utterance lineage、Final Target Dialogue hash、voice id、provider/model、ProviderJob id、媒体 SHA256、mime、采样率/声道（如可得）和实际语音时长。

## 发布

技术 Task succeeded 只产生 `NEEDS_REVIEW` candidate。人工听审并显式 ACCEPT 后，才发布 CURRENT `TARGET_AUDIO`。REJECT、Provider failure、媒体丢失或 SHA 不一致都不得覆盖旧 CURRENT。

## 边界

本 Skill 不改写 Final Target Dialogue，不做 Timing，不拉伸镜头，不做 Storyboard / Video Generation / Lip Sync / Post。
