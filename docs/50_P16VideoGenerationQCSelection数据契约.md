# P16 Video Generation / QC / Selection 数据契约

> 日期：2026-09-13  
> 状态：正式工程合同。目标视频 Provider 为 MiniMax H3；当前官方 V2 创建接口为 `POST /v2/video_generation`，查询接口为 `GET /v2/query/video_generation/{task_id}`。模型名/分辨率仍通过服务端配置控制。  
> 最终人工验收前 `VIDEO_GENERATION / QC_SELECTION = PLANNED`。

## 1. 唯一职责

P16 只负责：

```text
CURRENT GENERATION_SEGMENTS
+ CURRENT TARGET_STORYBOARD
+ CURRENT TARGET_ASSETS
        ↓
GenerationAttempt(s)
        ↓
Technical QC
        ↓
Human Semantic QC / Selection candidate
        ↓ explicit ACCEPT
GENERATED_VIDEO + GENERATION_SELECTION
```

GenerationAttempt 永远不是正式成片；只有 `GENERATION_SELECTION` 可进入 Post。

## 2. 正式硬输入

必须同时 CURRENT：

```text
TARGET_STORYBOARD
GENERATION_SEGMENTS
TARGET_ASSETS
```

并验证 Generation Segments 属于当前 Storyboard，Storyboard 属于当前 Assets lineage。

## 3. MiniMax H3 Provider Boundary

外部 Provider 规则：

1. API Key 仅来自服务端 Secret settings；禁止 DB/Artifact/日志/Git；
2. Provider endpoint/model 可配置，不在业务 Artifact 中写 secret；
3. 每个远程 GenerationAttempt 请求前先持久化 ProviderJob；
4. ProviderJob payload 只保存 prompt/hash/segment id/公开模型配置等安全信息；
5. H3 返回的远程 task id / file id / URL 只作为 provenance；
6. 远程媒体必须在 URL 失效前下载到本地 artifact storage；
7. 本地保存 SHA256 并 ffprobe；
8. Provider 未配置、远程失败、媒体不可下载、decode 失败均 fail closed；
9. retry 有上限，不允许无限付费重试。
10. H3 官方 V2 要求 `content[]` 至少含一条非空 `text`，T2V 必须提供具体 ratio；P15 必须把 Source Episode 比例映射到 H3 支持的 `21:9 / 16:9 / 4:3 / 1:1 / 3:4 / 9:16`。
11. MiniMax H3 输出 duration 官方范围为整数 `4~15s`。因此 planned GenerationSegment 可短于 4 秒，但 Provider 请求至少 4 秒；P17 再按 authoritative segment timing trim/pad。不得因为 Provider 最小时长反向改 Source timing。

## 4. GenerationAttempt

每次 attempt 至少记录：

```text
attempt_id
project_id
generation_segments_artifact_id
generation_segment_id
attempt_number
provider_job_id
provider / model
prompt_fingerprint
remote_job_id?
media_url (local API URL)
media_sha256
mime_type
actual_duration_us
width / height / codec
technical_qc_status
technical_qc_issues[]
correction_from_previous_attempt[]
created_at
```

Attempt 为生产记录，不是 Artifact current pointer。

## 5. Technical QC

每个下载视频必须重新执行：

- 文件存在且 SHA256 一致；
- ffprobe 可 decode；
- duration > 0；
- duration 与本次 **H3 requested duration**（`clamp(ceil(planned_seconds), 4, 15)`）在配置容差内；planned segment 若短于 4 秒由 P17 确定性 trim，不作为 P16 QC 失败；
- width / height > 0；
- video stream 存在；
- codec 可由 ffmpeg 读取。

技术 QC FAIL 时可在有限 attempt 内重试；correction 必须明确上一轮技术失败原因。

## 6. Semantic QC 与 Selection

P16 v1 不允许技术脚本自动声称“人物/动作/场景语义通过”。当每个 GenerationSegment 至少有一个 Technical QC PASS attempt 后，形成 `NEEDS_REVIEW` Selection candidate：

```text
segment_id -> selected_attempt_id
```

普通用户逐段预览视频，并人工检查：

- Target Character / Scene / Prop 与目标设定一致；
- 无明显 Source actor identity 泄漏；
- 动作完成；
- 构图/运镜符合 Target Storyboard；
- 连续性可接受；
- 无明显生成崩坏。

用户显式 ACCEPT 即同时完成 v1 的 human semantic QC 与 selection 决策。

## 7. Publication

ACCEPT 后同一事务发布：

```text
GENERATED_VIDEO
GENERATION_SELECTION
```

`GENERATED_VIDEO` 是当前 selection 所选本地媒体集合的 typed Artifact；`GENERATION_SELECTION` 记录每个 segment 的 selected attempt 和 review 结论。

Graph 至少：

- `GENERATION_SEGMENTS -> GENERATED_VIDEO : DERIVED_FROM`
- `TARGET_STORYBOARD -> GENERATED_VIDEO : USES`
- `TARGET_ASSETS -> GENERATED_VIDEO : USES`
- `GENERATED_VIDEO -> GENERATION_SELECTION : DERIVED_FROM`
- `TARGET_STORYBOARD -> GENERATION_SELECTION : USES`

只有 CURRENT `GENERATION_SELECTION` 可被 P17 消费。

## 8. Professional Skill

新增：

```text
video-generation-qc@1.0.0
required capabilities = VIDEO_GENERATION + QC_SELECTION
```

Provider execution 与 Artifact publication 必须分离；Provider 不能生成正式 Artifact ids/revision/fingerprint。

## 9. UI

普通用户“视频生成”工作区至少提供：

- 显式启动生成；
- 运行状态；
- 每个 GenerationSegment 的 attempt 视频与技术 QC；
- 只允许选择 Technical QC PASS attempt；
- 显式确认 Selection 或拒绝重新生成；
- GET 无副作用。

## 10. 完成定义

工程完成至少包括 H3 adapter、ProviderJob-before-remote、下载持久化、ffprobe QC、Attempt storage、Selection candidate/review/publication、Artifact Graph、UI、tests。真实 H3 Provider 与真人视觉质量在统一验收时完成，不能由 mock 单测代替。
