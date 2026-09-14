# H3 Generation Runtime / QC / Selection

`video-generation-qc@1.1.0`

## 目标

把 CURRENT `TARGET_STORYBOARD + GENERATION_SEGMENTS + TARGET_ASSETS` 送入统一 H3 Generation Runtime，保留可审计的 GenerationAttempt，并把技术质检与真人音画选片分离。

## Runtime Boundary

默认：

```text
AI_DRAMA_P16_H3_RUNTIME=LOCAL_COMFYUI
MiniMaxAI/MiniMax-H3
ComfyUI native MiniMax-H3 / FL2VA / task=t2va
POST /prompt
GET  /history/{prompt_id}
GET  /view
```

Windows 本地 adapter 使用 ComfyUI 原生 `MiniMaxH3ImageToVideo` 音画 pipeline，读取本机已安装 FL2VA UNET、Qwen3VL text encoder、video/audio VAE，通过 `SaveVideo` 输出 MP4。第一版使用官方 non-Turbo 20-step baseline；请求保持 4–15 秒、768 short edge，24fps frame length 按 H3 `17k+5` 网格对齐。P15 GenerationSegment 即使短于 4 秒，也只把 Runtime 请求提升到 4 秒，P17 再按 authoritative segment timing trim；禁止反向拉长 Source Shot。

Linux / 私有 GPU 服务器仍可显式选择：

```text
AI_DRAMA_P16_H3_RUNTIME=LOCAL_SGLANG
```

该模式继续使用 SGLang Diffusion `/v1/videos` 异步合同。两种本地 Runtime 都必须强制直连，不得继承系统 HTTP 代理去访问 loopback/private sidecar。

云端仅是显式 fallback：

```text
AI_DRAMA_P16_H3_RUNTIME=MINIMAX_CLOUD
```

只有这个模式才读取 MiniMax API Key 并调用 `/v2/video_generation`。本地 Runtime 不可用时禁止自动切云端，避免意外付费。

当前正式 P13 `reference_media` 尚未形成真实媒体，因此默认 ComfyUI adapter 先使用 FL2VA `t2va`。虽然本机已经具备 `MiniMaxH3ReferenceToVideo` / Ref2VA 权重，只有真实 image/video/audio reference 可以被 Runtime 访问后才能接入；不得把 Target Asset id 或文字描述伪装成 Ref2VA condition。

## ProviderJob / GenerationAttempt

每次 H3 Runtime invocation 前都必须先持久化 ProviderJob，无论 Runtime 是本地还是云端。GenerationAttempt 不是正式 Artifact。Runtime 成功后必须把 MP4 持久化到 Studio artifact storage，并记录 SHA256、ffprobe duration、width、height、codec 和 technical QC。

有限重试只用于技术失败。云端模式同样不允许无限付费重试。

## Technical QC

可自动确认：文件存在、SHA、decode、video stream、尺寸、codec、输出时长与本次 H3 requested duration 一致。

不能自动确认：人物像不像、场景对不对、对白是否准确完整、声线是否稳定、嘴型是否自然、环境音是否合理、构图审美、连续性、原演员身份是否泄漏。这些属于真人 Semantic / Audiovisual QC。

## Selection

每个 GenerationSegment 至少有一个 Technical QC PASS attempt 后形成 `NEEDS_REVIEW` Selection candidate。用户逐段播放并显式接受后，才同时发布 `GENERATED_VIDEO` 和 `GENERATION_SELECTION`。

只有 CURRENT `GENERATION_SELECTION` 可以进入 Post。P16 工程实现不等于 P16 PASS；真实本地 H3 Runtime、真实生成媒体和用户人工验收完成前，`VIDEO_GENERATION / QC_SELECTION` 继续保持 `PLANNED`。
