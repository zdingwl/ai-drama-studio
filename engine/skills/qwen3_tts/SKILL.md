# Qwen3 TTS Skill

- **Skill ID:** `qwen3_tts`
- **Version:** `1.0.0`
- **Status:** `CONTRACT_ONLY`
- **Runtime Model / Provider:** local Qwen3-TTS provider

## Purpose

为已经锁定的目标对白生成目标角色语音。核心原则是：**角色 Voice Identity 固定，单句只调整表演；真实生成音频时长才是后续时间重排的正式依据。**

## Inputs

- 当前 TargetDialogue revision
- 当前 TargetCharacter / TargetVoiceProfile revision
- 锁定目标对白文本与 text fingerprint
- 目标语言 / 地区
- 对应 story beat / emotion / performance 指令
- 需要时的上下句语境，用于语气连续性

## Rules

1. 一个 TargetCharacter 使用唯一当前 TargetVoiceProfile，除非用户明确创建新的 voice revision。
2. Voice Identity（说话人音色/身份）与 Performance（情绪、语速、力度、停顿、语气）分离。
3. 每句可以根据剧情调整 emotion、pace、energy、pause、intonation，但不得偷偷更换 Voice Identity。
4. 输入台词必须逐字对应当前锁定 TargetDialogue；TTS Skill 不负责翻译或改写。
5. 生成后必须测量并保存真实 `measured_duration_ms`，不能用字符数估算替代正式时长。
6. 后续 RemakeTimeline / GenerationSegment 应以真实音频时长与戏剧功能共同重排。
7. 多人对话必须保持每条 TargetDialogue 的 speaker → TargetCharacter → TargetVoiceProfile 链完整。
8. 重新生成语音必须创建新的音频 revision/attempt，不静默覆盖已经被下游消费的音频。
9. Provider/模型离线、显存不足、模型文件缺失等属于 runtime failure。

## Forbidden Behaviors

- 在 TTS 阶段翻译、润色、删减或增加正式台词。
- 为贴原片时长而强行异常加速/减速到破坏自然语音。
- 同一人物在无 revision 的情况下随机换音色。
- 用 source actor 原始音频直接作为目标角色最终对白。
- 把 TTS runtime failure 变成人工内容审核任务。
- 未生成音频却伪造 `measured_duration_ms`。

## Output Contract

```json
{
  "target_dialogue_revision": "...",
  "skill": {"id": "qwen3_tts", "version": "1.0.0"},
  "voice_profile_revision": "...",
  "text_fingerprint": "...",
  "performance": {
    "emotion": "...",
    "pace": "...",
    "energy": "...",
    "intonation": "..."
  },
  "audio_asset": {
    "revision": "...",
    "path": "...",
    "measured_duration_ms": 0
  },
  "runtime": {
    "model": "Qwen3-TTS",
    "model_version": "..."
  }
}
```

## Validator

- text fingerprint 必须等于当前锁定 TargetDialogue。
- speaker / TargetCharacter / TargetVoiceProfile revision 必须一致。
- 音频资产必须真实存在且可读取。
- `measured_duration_ms` 必须由生成音频测得且 > 0。
- 输入 revision 改变后旧音频必须 stale，不得继续驱动新时间轴。
- runtime failure 与 content review 必须使用不同状态/错误类型。

## Completion Criteria

- 目标对白文本未被修改；
- 音色身份与角色绑定稳定；
- 表演符合当前剧情节拍和情绪；
- 真实音频资产与真实时长已保存；
- 输出可以安全驱动 RemakeTimeline / GenerationSegment 重排。

## References

- `docs/00_短剧重做系统开发总纲.md`
- `docs/01_十个模块详细设计.md`
- `docs/02_工作流V2技术实现规范.md`
