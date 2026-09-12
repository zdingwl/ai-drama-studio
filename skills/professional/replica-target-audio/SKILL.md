# Replica Target Audio

## 目标

把 CURRENT `TARGET_SCRIPT` 的 `final_target_dialogue` 与 CURRENT `TARGET_BIBLE` 的目标人物身份绑定到显式参考声线，并使用 **IndexTTS-2.5** 生成可听审、可追溯的真实对白媒体；人工听审或 Timing overflow 后允许对指定对白做可审计 Retake。

## 硬输入

- CURRENT `TARGET_SCRIPT`
- CURRENT `TARGET_BIBLE`
- 用户显式提交的 reference voice binding

`TARGET_ASSETS` 不是硬输入。视觉资产 revision 不应无依据地使目标配音 STALE。

## Voice binding

已确定 `target_character_id` 的对白允许 CHARACTER scope binding；`target_character_id = null` 的对白必须使用 UTTERANCE scope binding。不得静默使用默认 narrator，不得根据姓名、性别、年龄或剧情猜 voice。

P14 的 voice key 指向 IndexTTS-2.5 的 `ref_audio` 参考音频，不是 Provider preset voice id。正式生产听审必须使用有明确授权的参考声线，禁止从 Source Episode 静默克隆原剧演员。

## Frozen Dialogue 与 Acting Direction

`final_target_dialogue` 是冻结台词。TTS 与 Retake 都不得改写、删词、补词或把表演提示拼进对白。

逐句可选 `TargetDialogueDeliveryControl`：

```text
utterance_id
acting_direction     // 表演/语气提示，不会被念出来
emo_alpha            // 0.0 ~ 1.0，默认 0.6
duration_factor      // 产品允许 0.8 ~ 1.25，默认 1.0
```

IndexTTS 语义固定：`duration_factor < 1` 更快/更短，`> 1` 更慢/更长。不得因为 Timing overflow 静默修改该值；必须由用户显式调整、重新生成并重新听审。

## Provider 与媒体

唯一正式 Provider 为 `IndexTeam/IndexTTS-2.5`。每条**真实重新合成**都必须先持久化 `ProviderJob`。

首次生成无逐句覆盖时使用 `emo_alpha=0.6 / duration_factor=1.0`。有 Acting Direction 时通过 IndexTTS emotion text 传入，不能作为 spoken input。

音频先写入 Production storage，再由服务端 `ffprobe` 探测。`actual_speech_duration_us` 只认服务端对已持久化媒体的探测结果；Provider 返回 duration 不能替代该事实。

每条 clip 至少保存：utterance lineage、Final Target Dialogue hash、reference voice key、acting direction、emo_alpha、duration_factor、provider/model、ProviderJob id、媒体 SHA256、mime、采样率/声道（如可得）和实际语音时长。

## Retake

Retake 必须显式选择一条或多条 `utterance_id`，并以某个仍属于 CURRENT TARGET_SCRIPT / TARGET_BIBLE 的待审核或已确认 audio candidate 为基线。

```text
Base Candidate
├─ Selected utterances   → 新 ProviderJob → 新 IndexTTS WAV → ffprobe
└─ Unselected utterances → 直接复制基线真实 WAV → 不创建 ProviderJob
```

重录任务生成新的 `NEEDS_REVIEW` candidate，并记录 `base_candidate_id + retaken_utterance_ids`。旧候选和旧 CURRENT 在新候选正式 ACCEPT 前保持不变，因此重录失败不能破坏上一版正式配音。

如果重录基于已经 ACCEPT 的 CURRENT TARGET_AUDIO，新的 audio candidate 被 ACCEPT 后，Artifact Graph 的既有失效规则会使旧 TARGET_AUDIO / TIMING_PLAN 过期；随后必须重新计算 Timing。

## 发布

技术 Task succeeded 只产生 `NEEDS_REVIEW` candidate。人工听审并显式 ACCEPT 后，才发布 CURRENT `TARGET_AUDIO`。REJECT、Provider failure、媒体丢失或 SHA 不一致都不得覆盖旧 CURRENT。

## 边界

本 Skill 不改写 Final Target Dialogue，不在 TTS 内计算正式 Timing，不拉伸镜头，不做 Storyboard / Video Generation / Lip Sync / Post。
