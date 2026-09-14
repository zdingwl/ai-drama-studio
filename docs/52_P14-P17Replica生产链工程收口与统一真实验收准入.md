# P14–P17 Replica 生产链工程收口与统一真实验收准入

> 日期：2026-09-13  
> 状态：P14–P17 工程链已完成到统一真实验收入口；本文优先级高于 `docs/31~51` 中较早的阶段状态描述。  
> 重要：工程完成不等于阶段 PASS。真实 Provider / Runtime、真实项目端到端和用户看 / 听质量尚未统一最终确认，因此 P14、P15、P16、P17 当前都不得记录 PASS，对应 capability 继续保持 `PLANNED`。

## 1. 当前唯一事实

截至本文，Replica 纵向链的正式阶段状态是：

```text
P0~P13 = PASS
TARGET_ASSETS = AVAILABLE

P14 engineering = COMPLETE
P15 engineering = COMPLETE
P16 engineering = COMPLETE
P17 engineering = COMPLETE

P14 PASS = NO
P15 PASS = NO
P16 PASS = NO
P17 PASS = NO
```

因此当前仍必须保持：

```text
TTS = PLANNED
TIMING = PLANNED
STORYBOARD = PLANNED
VIDEO_GENERATION = PLANNED
QC_SELECTION = PLANNED
LIP_SYNC = PLANNED
POST_PRODUCTION = PLANNED
```

不得因为 Task succeeded、candidate 可预览、mock/自动测试成功、Artifact publication 路径存在或 migration 已完成而提前升级这些状态。

## 2. 当前 Replica Root Production Chain

Root Skill 工程合同版本已推进到：

```text
project.replica@1.5.0
```

正式生产链为：

```text
P14 TARGET_SCRIPT + TARGET_BIBLE
  -> TARGET_AUDIO candidate
  -> explicit ACCEPT
  -> CURRENT TARGET_AUDIO
  -> deterministic TIMING candidate
  -> overflow triage / retake / targeted P12 rewrite when required
  -> explicit ACCEPT only when no unresolved overflow
  -> CURRENT TIMING_PLAN

P15 CURRENT SOURCE_VIDEO_SNAPSHOT
  + TARGET_BIBLE
  + TARGET_SCRIPT
  + TARGET_ASSETS
  + TARGET_AUDIO
  + TIMING_PLAN
  -> deterministic Replica storyboard compile
  -> NEEDS_REVIEW bundle candidate
  -> explicit ACCEPT
  -> CURRENT TARGET_STORYBOARD + GENERATION_SEGMENTS

P16 CURRENT TARGET_STORYBOARD
  + GENERATION_SEGMENTS
  + TARGET_ASSETS
  -> MiniMax H3 GenerationAttempt(s)
  -> local persistence + SHA256 + ffprobe Technical QC
  -> NEEDS_REVIEW Selection candidate
  -> explicit human ACCEPT
  -> CURRENT GENERATED_VIDEO + GENERATION_SELECTION

P17 CURRENT GENERATION_SELECTION
  + TARGET_AUDIO
  + TARGET_SCRIPT
  + TIMING_PLAN
  -> conditional Lip Sync
  -> deterministic trim/pad + concatenate
  -> formal Target Audio mix
  -> SRT export
  -> NEEDS_REVIEW Post candidate
  -> explicit human ACCEPT
  -> CURRENT FINAL_OUTPUT
```

## 3. P14 收口规则

P14 继续遵守 `docs/32~48`：

- Target Audio 只读取 CURRENT `TARGET_SCRIPT + TARGET_BIBLE` 与显式 voice binding；
- 一条 canonical target utterance 对应真实音频 clip 与 ProviderJob provenance；
- `actual_speech_duration_us` 只认服务端对已持久化音频的 ffprobe；
- Timing 只做确定性 source-slot conformance，不静默拉 Shot、不偷用未来 Storyboard slack；
- `OVERFLOW` 必须进入显式分诊；`required_duration_factor < 0.80` 的 selected utterance 可以走 P12 Timing Rewrite；
- Timing Rewrite 只能改 selected utterance 的 localization/final target dialogue 层，Source Truth、translation、utterance identity 与未选对白必须保持不变；
- 新 TARGET_SCRIPT revision 必须递归 stale 旧 TARGET_AUDIO / TIMING 及未来下游 Production Artifact；
- 只有无 unresolved overflow 的 Timing candidate 才允许人工 ACCEPT。

P14 当前仅完成工程链，不因本轮开发自动得到 `P14 PASS`。

## 4. P15 工程收口

合同：`docs/49_P15ReplicaStoryboard与GenerationSegments数据契约.md`。

已落地：

- `storyboard-directing@1.0.0`；
- typed `TARGET_STORYBOARD / GENERATION_SEGMENTS`；
- deterministic Replica compiler；
- CURRENT 六硬输入与 lineage / overflow fail-closed；
- Source Shot、TargetStoryboardShot、GenerationSegment 三层分离；
- Provider 最大时长分段，不反向修改 Source timing；
- candidate -> explicit ACCEPT -> 双 Artifact 原子 publication；
- Artifact Graph / STALE propagation；
- API 与普通用户产品工作区。

P15 candidate 未人工接受前不得产生正式 CURRENT Storyboard/Segments；工程完成不等于 `P15 PASS`。

## 5. P16 工程收口

合同：`docs/50_P16VideoGenerationQCSelection数据契约.md`。

已落地：

- `video-generation-qc@1.1.0`；
- H3 Generation Runtime boundary：Windows 默认本地 ComfyUI MiniMax-H3；SGLang 保留为 Linux / 私有 GPU 显式本地模式；MiniMax Cloud V2 仅显式 fallback；
- 本地失败禁止自动切付费云端；Cloud Secret 仍只在显式 Cloud 模式读取；
- ProviderJob-before-invocation（本地 / 云端一致）；
- GenerationAttempt storage；
- Runtime 媒体落 Studio 受管 storage、SHA256、ffprobe；
- H3 requested duration 与 planned segment duration 分层；
- 有限 retry 与 Technical QC；
- Technical QC PASS attempt 才可进入 Selection candidate；
- explicit human ACCEPT 后原子发布 `GENERATED_VIDEO + GENERATION_SELECTION`；
- 普通用户可逐段播放候选并确认正式选片。

GenerationAttempt 永远不是正式 Production selection。真实 H3 视觉质量仍必须统一人工验收。

## 6. P17 工程收口

合同：`docs/51_P17PostProductionFinalOutput数据契约.md`。

已落地：

- `post-production@1.0.0`；
- 只消费 CURRENT `GENERATION_SELECTION + TARGET_AUDIO + TARGET_SCRIPT + TIMING_PLAN`；
- Selection -> selected GenerationAttempt 的严格 lineage / hash / ffprobe 校验；
- `requires_lip_sync=true` 才调用本地 Lip Sync HTTP Runtime，调用前持久化 ProviderJob；
- Lip Sync Runtime 未配置或返回媒体不合法时 fail closed；
- selected segment 按 authoritative planned duration trim / pad；
- Episode 按 `episode_order -> segment_number` 确定性拼接；
- 丢弃生成视频未知音轨，只混入正式 Target Audio；
- 字幕只由 Target Script + Timing 确定性生成 SRT，不重新 ASR；
- 最终 MP4 再做 SHA256 + ffprobe；
- Post Task 只产生 `NEEDS_REVIEW` candidate；explicit ACCEPT 后才发布 CURRENT `FINAL_OUTPUT`。

P17 是当前 Replica 纵向链最后一个工程阶段，但 `FINAL_OUTPUT` 真正可接受仍必须由真实项目人工播放验收决定。

## 7. 数据库与 Root Skill

新增 migration：

```text
0027_p15_p16_p17_replica_production
```

该 migration：

- 建立 P15/P16/P17 typed candidate / revision / attempt 存储；
- 把持久化 Replica Root Skill 目标版本推进到 `1.5.0`；
- 使旧执行计划失效重编；
- 不改写历史 Artifact 内容；
- downgrade 恢复 Root Skill `1.4.0` 并移除本阶段新增表。

空库完整 Alembic upgrade 已实际跑到：

```text
0027_p15_p16_p17_replica_production (head)
```

## 8. 自动验证证据

本轮工程收口已经实际执行并通过：

```text
Python compile / narrow imports = PASS
app.main import = PASS
Alembic empty-db upgrade -> 0027 head = PASS
P15–P17 focused backend regression = PASS
backend full pytest = PASS (exit code 0)
frontend vue-tsc = PASS
frontend Vitest = 100 / 100 PASS
frontend production build = PASS
```

期间发现并修复：

1. P12 Timing Rewrite route decorator 位置导致 GET `/target-script` 被错误绑定到 rewrite command；已修复并由 focused/full regression 覆盖；
2. Replica Root Skill 新版本遗漏旧 `SOURCE_BIBLE -> STALE -> canonical Source Evidence` policy 文字；已恢复；
3. 统一启动器测试仍断言旧 `start.cmd -> start_studio.py` 入口；已按 `docs/46` 当前事实更新为 `start_studio_guard.py -> start_studio.py`，没有回退 Windows Job 生命周期整改。

这些自动验证只能证明工程行为，不替代真实 Provider/Runtime 与用户人工验收。

## 9. 统一真实验收准入

用户要求“先开发所有阶段，最后一起验收”，因此下一步不是继续新增 P18，而是按同一个真实 Replica 项目从 P14 一次跑到 P17：

```text
1. P14
   real IndexTTS voice binding / TTS
   -> real WAV persistence + ffprobe
   -> human listen review
   -> Timing
   -> overflow triage / retake / P12 targeted rewrite as needed
   -> all FIT
   -> explicit ACCEPT TARGET_AUDIO / TIMING_PLAN

2. P15
   compile real Target Storyboard / Generation Segments
   -> human shot / target identity / dialogue / timing review
   -> explicit ACCEPT

3. P16
   real MiniMax H3 generation through selected Runtime (LOCAL_COMFYUI default / explicit LOCAL_SGLANG or Cloud alternative)
   -> Studio-managed media + Technical QC
   -> human visual semantic QC / selection
   -> explicit ACCEPT

4. P17
   real Lip Sync where required
   -> deterministic edit / formal audio / subtitle
   -> play every final Episode
   -> verify SRT / audio / timing / continuity / lip sync
   -> explicit ACCEPT FINAL_OUTPUT
```

任何一步真实失败，都在对应阶段整改并重新验证，不跨阶段宣告 PASS。

## 10. 最终状态门禁

在用户完成统一真实验收并明确给出结论前，仓库必须继续记录：

```text
P14 PASS = NO
P15 PASS = NO
P16 PASS = NO
P17 PASS = NO

TTS = PLANNED
TIMING = PLANNED
STORYBOARD = PLANNED
VIDEO_GENERATION = PLANNED
QC_SELECTION = PLANNED
LIP_SYNC = PLANNED
POST_PRODUCTION = PLANNED
```

只有真实 Provider / Runtime、真实项目端到端和用户最终看 / 听质量全部完成，才允许另行更新 capability availability、阶段 PASS 与最终 Replica 产品验收状态。
