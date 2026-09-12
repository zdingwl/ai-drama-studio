# P14 IndexTTS-2.5 单 Provider 与情绪/语速控制整改

> 日期：2026-09-12  
> 状态：P14 工程合同补充整改；优先级高于 `docs/32`、`docs/33` 中所有通用 / OpenAI TTS Provider 描述。  
> `TTS / TIMING` 仍为 `PLANNED`；真实本地 IndexTTS-2.5、真实音频和人工听审尚未完成。

## 1. Provider 决策

P14 TTS 正式工程实现只保留一个 Provider：

```text
IndexTeam/IndexTTS-2.5
served by local vLLM-Omni
```

不再保留 OpenAI 官方 TTS、`tts-1`、`gpt-4o-mini-tts` 或其他云 / 多 Provider 选择。

官方推荐的生产 serving 入口：

```bash
vllm serve IndexTeam/IndexTTS-2.5 \
  --omni \
  --trust-remote-code \
  --port 8092
```

应用默认连接：

```text
http://127.0.0.1:8092/v1
```

## 2. 声线语义

IndexTTS-2.5 是 zero-shot voice cloning，不存在 OpenAI 风格的内置 text-only preset speakers。

P14 的 `voice_id` 字段在 P14 PASS 前继续保留 wire compatibility，但其业务语义固定为：

```text
application reference-voice key
```

它不是 Provider voice id。

真实合成通过 `ref_audio` 传入参考音频。普通 UI 只能选择 reference voice，不再出现 `Provider voice id`。

默认工程目录使用 IndexTTS 上游 demo reference recordings，目的仅为本地工程联调与验收预览。正式 P14 人工 PASS 前必须替换为具有明确使用授权的目标声线。禁止从原剧 Source Audio 静默克隆演员音色。

## 3. 语言

IndexTTS-2.5 当前正式目标语言映射：

```text
zh-* -> zh
en-* -> en
ja-* -> ja
es-* -> es
ar-* -> ar
```

其他目标语言 fail closed，不允许静默切到别的 TTS。

## 4. 情绪 / 语气

P14 默认启用 IndexTTS-2.5 原生文本情绪推断：

```text
use_emo_text = true
emo_alpha = 0.6
```

该默认值用于让短剧对白保留自然语气，而不是机械朗读。后续如建立独立 Acting Direction typed contract，可再把显式 `emo_text / emo_vector / emotion reference audio` 纳入逐句控制；在该合同出现前不得让 Provider 改写 Final Target Dialogue。

## 5. 语速 / Timing

首次正式候选默认：

```text
speed = 1.0
```

不得为了硬塞 Source slot 在首次生成时自动加速。服务端仍以真实落盘音频的 `ffprobe` 结果作为 `actual_speech_duration_us` 唯一权威。

若 Timing 出现 `OVERFLOW`，后续显式 retake 可以在新的受控合同下使用 IndexTTS-2.5 原生 speed / duration_factor 做轻量调整；不能静默拉伸镜头或改写对白。

## 6. ProviderJob / Artifact

每句真实 IndexTTS 调用仍必须：

```text
persist ProviderJob
-> call local IndexTTS-2.5
-> persist WAV
-> ffprobe
-> NEEDS_REVIEW candidate
-> human ACCEPT
-> CURRENT TARGET_AUDIO
```

ProviderJob payload 记录 reference voice key、语言、speed、emotion control、文本 hash；不记录整段参考音频 bytes。

Artifact Graph、CURRENT/STALE、Timing overflow 和人工审核门继续沿用 `docs/32`。

## 7. 当前验收状态

```text
P13 = PASS
TARGET_ASSETS = AVAILABLE
P14 engineering = IndexTTS-2.5 only
TTS = PLANNED
TIMING = PLANNED
P14 PASS = NO
```

只有真实本地 IndexTTS-2.5 服务、真实参考音频、真实生成媒体、逐句听审、Timing 审核完成且用户明确 `P14 PASS` 后，才允许升级能力状态。
