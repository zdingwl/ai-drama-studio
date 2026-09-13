# Replica Post Production

## 目标

把已经人工确认的 `GENERATION_SELECTION` 与正式 `TARGET_AUDIO / TARGET_SCRIPT / TIMING_PLAN` 组合成可播放、可导出、可追溯的最终 Episode 成片。

## 硬输入

必须同时是 CURRENT：

- `GENERATION_SELECTION`
- `TARGET_AUDIO`
- `TARGET_SCRIPT`
- `TIMING_PLAN`

`GENERATION_SELECTION` 必须指向正式 `GENERATED_VIDEO`；Target Audio 必须属于当前 Target Script；Timing 必须属于当前 Script + Audio 且没有 overflow。

## Lip Sync

只有正式 GenerationSegment 标记 `requires_lip_sync=true` 才调用 Lip Sync Runtime。每次调用前先持久化 `ProviderJob`。Runtime 输出先本地落盘并重新 ffprobe，再按该 segment authoritative planned duration 归一。

无对白、VOICEOVER、OFFSCREEN 等不要求可见口型的段不调用 Lip Sync，直接使用正式 selected video。

## 确定性后期

后期只做本地确定性媒体操作：

1. 以 TIMING_PLAN 把 CURRENT TARGET_AUDIO 混入 Episode timeline；
2. selected segment 按 planned duration trim/pad；
3. 按 `episode_order → segment_number` 拼接；
4. 丢弃生成视频原始/未知音轨，只混入正式 Target Audio；
5. 字幕正文只读 CURRENT TARGET_SCRIPT，时间只读 CURRENT TIMING_PLAN，导出 SRT；
6. 最终视频重新 ffprobe 并校验 duration / dimensions / codec。

FFmpeg 是本地确定性 Tool，不得伪造 ProviderJob。

## Publication

Task 成功只生成 `NEEDS_REVIEW` candidate。用户播放最终 Episode、检查字幕后显式 ACCEPT，才发布 CURRENT `FINAL_OUTPUT`。拒绝或失败不覆盖旧 CURRENT。

## 当前验收状态

工程实现不等于真实阶段 PASS。`LIP_SYNC / POST_PRODUCTION` 在统一真实项目验收和用户明确确认前继续 `PLANNED`。
