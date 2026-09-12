# P14 逐句表演指令与可控 Retake 数据契约

> 日期：2026-09-12  
> 状态：P14 v1.1 工程合同；补充 `docs/32`、`docs/34`，解决真实听审中的语气调整与 Timing overflow 重录闭环。  
> 本文不改变阶段验收状态：`TTS = PLANNED / TIMING = PLANNED / P14 PASS = NO`。

## 1. 为什么需要 Retake

第一轮真实 TTS 的作用是得到可试听媒体与真实时长，不保证每句一次就达到成片表演质量。短剧配音至少需要处理：

```text
语气不对
情绪强弱不对
停顿/压迫感/克制感不对
真实语音超过 source slot
```

因此 P14 必须支持逐句重录，而不能每次改一条台词的语气就整集重新调用 Provider。

## 2. 冻结对白

任何 TTS / Retake 的 spoken input 仍只能是 CURRENT TARGET_SCRIPT 的：

```text
final_target_dialogue
```

新增表演控制不携带新的台词正文，也不得把提示词拼接到 `final_target_dialogue`。

## 3. TargetDialogueDeliveryControl

```text
utterance_id: string
acting_direction: string | null, max 600
emo_alpha: 0.0 ~ 1.0, default 0.6
duration_factor: 0.8 ~ 1.25, default 1.0
```

映射到 IndexTTS-2.5：

```text
acting_direction → extra_params.emo_text
emo_alpha        → extra_params.emo_alpha
duration_factor  → /audio/speech speed → native IndexTTS duration_factor
```

IndexTTS 官方语义：

```text
duration_factor < 1.0 → 更快 / 更短
duration_factor = 1.0 → 默认
duration_factor > 1.0 → 更慢 / 更长
```

Provider 本身支持更大范围，但产品合同只开放 0.8~1.25，避免把“时序适配”变成极端倍速。仍然 overflow 时，应继续 Retake 或返回 P12 修改本土化对白，而不是无限加速。

## 4. ProviderJob 规则

每个真实合成 utterance 仍是一条 ProviderJob。

Retake 的关键规则：

```text
选中的 utterance   → 新建 ProviderJob → 真正重新合成
未选中的 utterance → 复用基线 WAV → 0 个新 ProviderJob
```

复用不是只复用 URL；服务端必须把基线真实媒体复制到新 candidate 的 task storage，并验证 SHA256，使新 candidate 自身仍可独立通过人工 ACCEPT 的媒体完整性检查。

## 5. Retake 基线

允许基于：

```text
NEEDS_REVIEW audio candidate
ACCEPTED audio candidate（例如正式 Timing 发现 overflow 后）
```

禁止基于 REJECTED / SUPERSEDED 或已经不属于 CURRENT TARGET_SCRIPT + TARGET_BIBLE 的候选。

请求必须提交：

```text
candidate_id
expected_target_script_artifact_id
expected_target_bible_artifact_id
expected_generation_sequence
retakes[]
```

任何 optimistic-concurrency 条件不匹配都 fail closed。

## 6. API

新增：

```text
POST /api/v3/projects/{project_id}/target-audio/candidates/{candidate_id}/commands/retake
Idempotency-Key: ...
```

请求中的 `retakes` 只包含需要重新合成的 utterance。后端从 base candidate 冻结原 voice binding，普通 Retake 不允许顺便换声音；如果要换角色声线，应走显式重新生成，而不是把两个决策混成一次操作。

## 7. Candidate / Provenance

TARGET_AUDIO schema 从 `1.0` 演进为 `1.1`，clip 新增：

```text
acting_direction
emo_alpha
duration_factor
```

candidate provenance 新增：

```text
base_candidate_id
retaken_utterance_ids
```

旧 1.0 candidate 仍可读取，缺失控制字段按 `acting_direction=null / emo_alpha=0.6 / duration_factor=1.0` 解释。

Professional Skill：

```text
replica-target-audio@1.1.0
replica-target-audio-v1.1
indextts-2.5-reference-audio-emotion-duration-v2
```

## 8. UI

P14 新增“逐句语气控制与 Retake”子面板：

- 播放当前真实 clip；
- 每句可填写 Acting Direction；
- 情绪强度 slider；
- duration factor slider；
- 单句立即 Retake；
- 多选批量 Retake；
- Timing overflow 可以显式加入重录列表；
- 不自动应用任何速度建议。

## 9. Artifact 与 Timing

Retake Task succeeded 仍只形成 `NEEDS_REVIEW` candidate。只有新 candidate 被人工 ACCEPT 才发布新 CURRENT TARGET_AUDIO。

如果旧正式 TARGET_AUDIO 已经有 TIMING_PLAN：

```text
ACCEPT 新 TARGET_AUDIO
→ 旧 TARGET_AUDIO SUPERSEDED / STALE
→ 旧 TIMING_PLAN STALE
→ 用新 ffprobe 时长重新计算 Timing
```

Timing 本身仍是确定性计算，不调用 Provider。

## 10. 当前状态

本合同只完成 P14 真实验收所需的工程闭环，不等于 P14 PASS。

继续保持：

```text
P13 = PASS
TARGET_ASSETS = AVAILABLE
TTS = PLANNED
TIMING = PLANNED
P14 PASS = NO
```

不得因此进入 Target Storyboard / Generation / QC / Lip Sync / Post。
