# P17 Lip Sync / Post Production / Final Output 数据契约

> 日期：2026-09-13  
> 状态：正式工程合同。最终人工验收前 `LIP_SYNC / POST_PRODUCTION = PLANNED`。  
> P17 是当前 Replica 纵向链的最终工程阶段。

## 1. 唯一职责

P17 消费已经人工选择的正式视频和正式目标音频，生成最终可播放 Episode 输出：

```text
CURRENT GENERATION_SELECTION
+ CURRENT TARGET_AUDIO
+ CURRENT TARGET_SCRIPT
+ CURRENT TIMING_PLAN
        ↓
segment lip sync (where required)
        ↓
edit / concatenate
        ↓
formal target dialogue audio mix
        ↓
subtitle render/export
        ↓
post candidate
        ↓ explicit ACCEPT
FINAL_OUTPUT
```

不得绕过 GenerationSelection 直接拿任意 GenerationAttempt 进入后期。

## 2. 正式硬输入

必须同时 CURRENT：

```text
GENERATION_SELECTION
TARGET_AUDIO
TARGET_SCRIPT
TIMING_PLAN
```

并验证：

- Selection 的 Generation Segments / Storyboard lineage 与当前 production chain 一致；
- Target Audio 属于当前 Target Script；
- Timing Plan 属于当前 Target Script + Target Audio；
- Timing Plan `has_overflow = false`。

## 3. Lip Sync Boundary

只有 GenerationSegment 中 `requires_lip_sync = true` 才调用 Lip Sync Runtime。

第一版采用可配置的本地 HTTP Lip Sync adapter：

- API Key 不需要进入 Artifact；若未来 Runtime 需要 credential，仍只允许服务端 Secret；
- 调用前必须先持久化 ProviderJob；
- 输入是 selected segment video + 该 segment 时间窗内确定性混合出的 formal Target Audio；
- Provider 不能改 Target Script；
- 返回视频必须落本地并做 SHA256 + ffprobe；
- Runtime 未配置/不可用时 fail closed，不允许假装口型已完成；
- OFFSCREEN / VOICEOVER / 无对白段可跳过 lip sync，直接使用 selected video。

## 4. Audio 与 Subtitle

最终对白音轨必须来自 CURRENT TARGET_AUDIO，不重新 TTS。

服务端按 CURRENT TIMING_PLAN 的 `planned_speech_start_us/end_us` 对每个正式 clip 做 timeline mix。

字幕至少导出 SRT：

```text
utterance_number
planned_speech_start_us
planned_speech_end_us
final_target_dialogue
```

字幕正文只读取 CURRENT TARGET_SCRIPT，不允许从音频重新 ASR。

## 5. Edit / Episode Output

GenerationSegment 必须按：

```text
episode_order → segment_number
```

确定性拼接。每段按计划时长 trim / pad 到 production timeline，避免 Provider 视频时长轻微漂移破坏后续 timing。

每个 Episode 输出至少：

```text
episode_id / episode_order
video_url
video_sha256
mime_type
duration_us
width / height / codec
subtitle_url
subtitle_sha256
lip_synced_segment_count
```

最终视频必须再次 ffprobe，并验证总 duration 与 Episode production timeline 在容差内。

## 6. Candidate / Review / FINAL_OUTPUT

P17 Task 成功先形成 `NEEDS_REVIEW` Post candidate；页面可播放最终 Episode 视频并下载/查看字幕。用户显式 ACCEPT 后才发布 CURRENT `FINAL_OUTPUT`。

Graph 至少：

- `GENERATION_SELECTION -> FINAL_OUTPUT : DERIVED_FROM`
- `TARGET_AUDIO -> FINAL_OUTPUT : USES`
- `TARGET_SCRIPT -> FINAL_OUTPUT : USES`
- `TIMING_PLAN -> FINAL_OUTPUT : USES`

上游任何新 revision 都必须使旧 FINAL_OUTPUT STALE。

## 7. Professional Skill

新增：

```text
post-production@1.0.0
required capabilities = LIP_SYNC + POST_PRODUCTION
```

Lip Sync Provider 与 deterministic FFmpeg post 必须分层；无 ProviderJob 的 ffmpeg 操作不能伪装外部模型调用。

## 8. UI

普通用户“成片”工作区至少提供：

- 当前输入 readiness；
- 显式启动后期；
- lip sync / ffmpeg Task 进度；
- 最终 Episode 视频播放器；
- SRT 字幕入口；
- 显式接受或拒绝；
- GET 无副作用。

## 9. 统一最终验收

用户已要求“先开发所有阶段，最后一起验收”。因此 P14–P17 工程完成后统一真实验收应按以下顺序一次跑完整链：

```text
P14 TARGET_AUDIO / TIMING
→ P15 TARGET_STORYBOARD / GENERATION_SEGMENTS
→ P16 H3 GenerationAttempt / QC / Selection
→ P17 Lip Sync / Post / FINAL_OUTPUT
```

工程期间即使 Task、candidate、正式 Artifact publication 路径测试成功，也不得提前记录：

```text
P14 PASS
P15 PASS
P16 PASS
P17 PASS
```

也不得提前把：

```text
TTS
TIMING
STORYBOARD
VIDEO_GENERATION
QC_SELECTION
LIP_SYNC
POST_PRODUCTION
```

升级为 AVAILABLE。只有真实 Provider/Runtime、真实项目端到端和用户最终看/听质量全部完成后，才按用户明确结论收口状态。
