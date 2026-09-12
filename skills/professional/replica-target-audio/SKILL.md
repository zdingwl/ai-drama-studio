# Replica Target Audio

## 目标

把 CURRENT `TARGET_SCRIPT` 的 `final_target_dialogue` 与 CURRENT `TARGET_BIBLE` 的目标人物身份绑定到显式参考声线，并使用 **IndexTTS-2.5** 生成可听审、可追溯的真实对白媒体。

## 硬输入

- CURRENT `TARGET_SCRIPT`
- CURRENT `TARGET_BIBLE`
- 用户显式提交的 reference voice binding

`TARGET_ASSETS` 不是硬输入。视觉资产 revision 不应无依据地使目标配音 STALE。

## Voice binding

已确定 `target_character_id` 的对白允许 CHARACTER scope binding；`target_character_id = null` 的对白必须使用 UTTERANCE scope binding。不得静默使用默认 narrator，不得根据姓名、性别、年龄或剧情猜 voice。

P14 的 voice key 指向 IndexTTS-2.5 的 `ref_audio` 参考音频，不是 OpenAI / Provider preset voice id。默认上游 demo 声线仅用于工程联调；正式生产听审必须替换为有明确授权的参考声线，禁止从 Source Episode 静默克隆原剧演员。

## Provider 与媒体

唯一正式 Provider 为 `IndexTeam/IndexTTS-2.5`，通过本地 vLLM-Omni `/v1/audio/speech` 服务调用。每条外部/模型 TTS 调用必须先持久化 `ProviderJob`。

默认启用模型原生文本情绪推断：`use_emo_text=true`、`emo_alpha=0.6`；首次生成 `speed=1.0`。Provider 不得改写 Final Target Dialogue，也不得为了时间槽静默加速。

音频先写入 Production storage，再由服务端 `ffprobe` 探测。`actual_speech_duration_us` 只认服务端对已持久化媒体的探测结果；Provider 返回 duration 不能替代该事实。

每条 clip 至少保存：utterance lineage、Final Target Dialogue hash、reference voice key、provider/model、ProviderJob id、媒体 SHA256、mime、采样率/声道（如可得）和实际语音时长。

## 发布

技术 Task succeeded 只产生 `NEEDS_REVIEW` candidate。人工听审并显式 ACCEPT 后，才发布 CURRENT `TARGET_AUDIO`。REJECT、Provider failure、媒体丢失或 SHA 不一致都不得覆盖旧 CURRENT。

## 边界

本 Skill 不改写 Final Target Dialogue，不做 Timing，不拉伸镜头，不做 Storyboard / Video Generation / Lip Sync / Post。
