# MiniMax H3 Video Generation / QC / Selection

## 目标

把 CURRENT `TARGET_STORYBOARD + GENERATION_SEGMENTS + TARGET_ASSETS` 送入 MiniMax H3，保留可审计的 GenerationAttempt，并把技术质检与真人视觉选片分离。

## MiniMax H3 V2

当前正式接口：

- 创建：`POST /v2/video_generation`
- 查询：`GET /v2/query/video_generation/{task_id}`
- `MiniMax-H3` 输出 4–15 秒，支持 768P / 2K；T2V 必须给具体 ratio。

ProviderJob 必须在 create 前落库。API Key 只从服务端环境读取，不进入 DB、Artifact、日志或前端。

P15 的 GenerationSegment 可以短于 H3 最小 4 秒。此时请求 4 秒视频，P17 再按照 authoritative segment timing trim。禁止为了满足 Provider 最小时长反向拉长 Source Shot。

## GenerationAttempt

每次 paid generation 都是 Attempt，不是正式 Artifact。远程成功后必须立即下载到本地 artifact storage，并记录 SHA256、ffprobe duration、width、height、codec 和 technical QC。

有限重试只用于技术失败，不能无限烧费。

## Technical QC

可自动确认：文件存在、SHA、decode、video stream、尺寸、codec、输出时长与本次 H3 requested duration 一致。

不能自动确认：人物像不像、场景对不对、动作是否自然、构图审美、连续性、原演员身份是否泄漏。这些属于真人 Semantic QC。

## Selection

每个 GenerationSegment 至少有一个 Technical QC PASS attempt 后形成 `NEEDS_REVIEW` Selection candidate。用户逐段预览并显式接受后，才同时发布 `GENERATED_VIDEO` 和 `GENERATION_SELECTION`。

只有 CURRENT `GENERATION_SELECTION` 可以进入 Post。P16 工程完成不等于 P16 PASS；统一真实验收前 `VIDEO_GENERATION / QC_SELECTION` 保持 PLANNED。
